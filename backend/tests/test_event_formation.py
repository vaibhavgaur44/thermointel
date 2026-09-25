"""Focused Phase 5 event-formation tests.

Runs against an ISOLATED test database (thermointel_event_test) which is
dropped afterwards, so neither the operational database nor the demo dataset
is touched. Covers the behavior defined by the existing architecture:

- each detection forms exactly one event (documented interim rule until
  grouping parameters are calibrated - ARCHITECTURE.md "Deliberately
  unfrozen configuration")
- persistence is idempotent (unique event_id upsert, created_at preserved)
- detection identity (observation_id) is never modified
- production/demo separation follows the detection's data_origin
- event <-> detection relationship is queryable both ways
- empty input produces nothing
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import settings  # noqa: E402
from core.database import Collections, close_db, ensure_indexes, get_db  # noqa: E402
from models.common import GeoPoint  # noqa: E402
from models.enums import EventStatus  # noqa: E402
from models.event import Event  # noqa: E402
from pipeline import event_formation  # noqa: E402

TEST_DB_NAME = "thermointel_event_test"

_LOOP = None


def run(coro):
    """Run a coroutine on one module-lifetime event loop (Motor binds to the
    loop it first runs on)."""
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


@pytest.fixture(scope="module", autouse=True)
def event_test_db():
    """Point the database layer at an isolated test DB for this module."""
    original_db_name = settings.DB_NAME
    settings.DB_NAME = TEST_DB_NAME
    run(ensure_indexes())
    run(get_db()[Collections.EVENTS].delete_many({}))
    run(get_db()[Collections.THERMAL_DETECTIONS].delete_many({}))
    yield
    run(get_db().client.drop_database(TEST_DB_NAME))
    run(close_db())
    if _LOOP is not None and not _LOOP.is_closed():
        _LOOP.close()
    settings.DB_NAME = original_db_name


def _detection(observation_id: str, lat: float, lon: float, origin: str = "production"):
    from models.detection import ThermalDetection
    from models.enums import DayNight, Satellite

    return ThermalDetection(
        observation_id=observation_id,
        location=GeoPoint.from_lat_lon(lat, lon),
        acquired_at="2026-09-22T06:49:00+00:00",
        satellite=Satellite.VIIRS_NOAA20,
        satellite_std="N20",
        instrument="VIIRS",
        version="2.0NRT",
        day_night=DayNight.NIGHT,
        frp=5.71,
        brightness_ti4=332.58,
        brightness_ti5=296.22,
        firms_confidence="n",
        scan=0.44,
        track=0.38,
        ingestion_run_id="run-event-test",
        data_origin=origin,
        state="Odisha",
        state_lgd="21",
        lulc_2021_code="40",
        lulc_2021_class="Cropland",
    )


async def _seed_detection(db, detection) -> None:
    await db[Collections.THERMAL_DETECTIONS].insert_one(detection.to_mongo())


# ------------------------------------------------------------- formation ---


def test_detection_forms_exactly_one_event():
    det = _detection("obs-form-1", 20.29, 85.82)
    events = run(event_formation.group_detections([det]))

    assert len(events) == 1
    event = events[0]
    assert event.event_id == "evt-obs-form-1"
    assert event.detection_ids == ["obs-form-1"]
    assert event.detection_count == 1
    assert event.centroid.latitude == 20.29
    assert event.centroid.longitude == 85.82
    assert event.state == "Odisha"
    assert event.status == EventStatus.ACTIVE


def test_grouping_config_unchanged_and_uncalibrated():
    """The documented unfrozen fields stay None until the owner calibrates."""
    cfg = event_formation.CONFIG
    assert cfg.grouping_radius_km is None
    assert cfg.time_window_hours is None
    assert cfg.min_detections is None
    assert cfg.grace_period_hours is None
    assert cfg.is_calibrated is False


def test_empty_input_produces_no_events():
    events = run(event_formation.group_detections([]))
    assert events == []
    assert run(event_formation.persist_events([])) == 0


# ------------------------------------------------------------ persistence ---


def test_persist_and_relationships_are_queryable():
    run(_seed_detection(get_db(), _detection("obs-persist-1", 21.5, 84.03)))
    det = _detection("obs-persist-1", 21.5, 84.03)
    events = run(event_formation.group_detections([det]))
    inserted = run(event_formation.persist_events(events))
    assert inserted == 1

    db = get_db()

    async def _check():
        event_doc = await db[Collections.EVENTS].find_one(
            {"event_id": "evt-obs-persist-1"}
        )
        detection_doc = await db[Collections.THERMAL_DETECTIONS].find_one(
            {"observation_id": "obs-persist-1"}
        )
        return event_doc, detection_doc

    event_doc, detection_doc = run(_check())

    # event -> detection relationship
    assert event_doc["detection_ids"] == ["obs-persist-1"]
    assert event_doc["detection_count"] == 1
    # detection -> event relationship (event_id written back)
    assert detection_doc["event_id"] == "evt-obs-persist-1"
    # detection identity untouched
    assert detection_doc["observation_id"] == "obs-persist-1"


def test_reprocessing_is_idempotent():
    det = _detection("obs-idem-1", 22.0, 84.5)
    run(_seed_detection(get_db(), det))

    events_first = run(event_formation.group_detections([det]))
    assert run(event_formation.persist_events(events_first)) == 1

    db = get_db()

    async def _first_created():
        doc = await db[Collections.EVENTS].find_one({"event_id": "evt-obs-idem-1"})
        return doc["created_at"]

    first_created = run(_first_created())

    # Re-run the SAME detection through formation + persistence.
    events_second = run(event_formation.group_detections([det]))
    assert run(event_formation.persist_events(events_second)) == 0  # no new event

    async def _second_state():
        total = await db[Collections.EVENTS].count_documents(
            {"event_id": "evt-obs-idem-1"}
        )
        doc = await db[Collections.EVENTS].find_one({"event_id": "evt-obs-idem-1"})
        return total, doc["created_at"]

    total, second_created = run(_second_state())
    assert total == 1  # exactly one event document
    assert second_created == first_created  # created_at preserved ($setOnInsert)


def test_persistence_uses_existing_event_collection_indexes():
    """event_id unique + centroid 2dsphere exist (documented event indexes)."""
    info = run(get_db()[Collections.EVENTS].index_information())

    unique_event_id = any(
        spec["key"] == [("event_id", 1)] and spec.get("unique")
        for spec in info.values()
    )
    geosphere = any(
        spec["key"] == [("centroid", "2dsphere")] for spec in info.values()
    )
    assert unique_event_id
    assert geosphere


# ---------------------------------------------------- production vs demo ---


def test_production_detection_makes_production_event():
    det = _detection("obs-prod-1", 20.0, 85.0, origin="production")
    events = run(event_formation.group_detections([det]))
    assert events[0].data_origin == "production"


def test_demo_detection_never_makes_production_event():
    det = _detection("obs-demo-1", 20.0, 85.0, origin="demo")
    events = run(event_formation.group_detections([det]))
    assert events[0].data_origin == "demo"


def test_mixed_origins_stay_separate():
    prod = _detection("obs-mix-prod", 20.1, 85.1, origin="production")
    demo = _detection("obs-mix-demo", 20.1, 85.1, origin="demo")
    events = run(event_formation.group_detections([prod, demo]))

    by_origin = {e.data_origin: e for e in events}
    assert by_origin["production"].event_id == "evt-obs-mix-prod"
    assert by_origin["demo"].event_id == "evt-obs-mix-demo"
    # No cross-contamination of detection lists.
    assert by_origin["production"].detection_ids == ["obs-mix-prod"]
    assert by_origin["demo"].detection_ids == ["obs-mix-demo"]


# -------------------------------------------------------- lifecycle (24B) ---


from datetime import datetime, timedelta, timezone  # noqa: E402


def _roundtrip_dt(value):
    """Normalize a Mongo round-tripped datetime for comparison: reattach
    tzinfo (BSON stores naive UTC) and truncate to millisecond precision
    (BSON's datetime resolution)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.replace(microsecond=(value.microsecond // 1000) * 1000)


def _insert_aged_event(event_id: str, age_hours: float, origin: str = "production") -> dict:
    """Insert an event whose last detection is age_hours in the past."""
    now = datetime.now(timezone.utc)
    last = now - timedelta(hours=age_hours)
    event = Event(
        event_id=event_id,
        centroid=GeoPoint.from_lat_lon(20.0, 85.0),
        first_detected=last,
        last_detected=last,
        detection_count=1,
        detection_ids=[f"obs-{event_id}"],
        data_origin=origin,
    )
    run(get_db()[Collections.EVENTS].insert_one(event.to_mongo()))
    return event.to_mongo()


def _event_status(event_id: str) -> str:
    async def _get():
        doc = await get_db()[Collections.EVENTS].find_one(
            {"event_id": event_id}, {"status": 1}
        )
        return doc["status"]

    return run(_get())


@pytest.fixture(autouse=True)
def clean_lifecycle_events():
    """Isolate lifecycle tests from each other and from earlier modules."""
    run(get_db()[Collections.EVENTS].delete_many(
        {"event_id": {"$regex": "^evt-lc-"}}
    ))
    yield
    run(get_db()[Collections.EVENTS].delete_many(
        {"event_id": {"$regex": "^evt-lc-"}}
    ))


def test_active_event_stays_active_within_window():
    doc = _insert_aged_event("evt-lc-active", age_hours=1)
    run(event_formation.expire_stale_events())  # default 24h window
    assert _event_status(doc["event_id"]) == "ACTIVE"


def test_event_expires_beyond_configured_window():
    doc = _insert_aged_event("evt-lc-expired", age_hours=25)  # > 24h window
    expired = run(event_formation.expire_stale_events())
    assert expired >= 1  # our stale event transitioned (others may too)
    assert _event_status(doc["event_id"]) == "EXPIRED"


def test_event_exactly_at_window_boundary_is_not_expired():
    # last_detected == cutoff is NOT expired ($lt cutoff).
    cfg = event_formation.EventFormationConfig(expiry_window_hours=24.0)
    now = datetime.now(timezone.utc)
    event = Event(
        event_id="evt-lc-boundary",
        centroid=GeoPoint.from_lat_lon(20.0, 85.0),
        first_detected=now - timedelta(hours=24),
        last_detected=now - timedelta(hours=24),
        detection_count=1,
        detection_ids=["obs-lc-boundary"],
    )
    run(get_db()[Collections.EVENTS].insert_one(event.to_mongo()))
    run(event_formation.expire_stale_events(now=now, config=cfg))
    assert _event_status("evt-lc-boundary") == "ACTIVE"


@pytest.mark.parametrize("window", [1.0, 6.0, 24.0, 168.0])
def test_each_supported_window(window):
    cfg = event_formation.EventFormationConfig(expiry_window_hours=window)
    now = datetime.now(timezone.utc)

    fresh = Event(
        event_id=f"evt-lc-fresh-{window}",
        centroid=GeoPoint.from_lat_lon(20.0, 85.0),
        first_detected=now - timedelta(hours=window - 0.5),
        last_detected=now - timedelta(hours=window - 0.5),
        detection_count=1,
        detection_ids=[f"obs-{window}"],
    )
    stale = Event(
        event_id=f"evt-lc-stale-{window}",
        centroid=GeoPoint.from_lat_lon(20.0, 85.0),
        first_detected=now - timedelta(hours=window + 0.5),
        last_detected=now - timedelta(hours=window + 0.5),
        detection_count=1,
        detection_ids=[f"obs-{window}"],
    )
    col = get_db()[Collections.EVENTS]
    run(col.insert_one(fresh.to_mongo()))
    run(col.insert_one(stale.to_mongo()))

    run(event_formation.expire_stale_events(now=now, config=cfg))
    assert _event_status(f"evt-lc-fresh-{window}") == "ACTIVE"
    assert _event_status(f"evt-lc-stale-{window}") == "EXPIRED"


def test_expiry_is_idempotent():
    doc = _insert_aged_event("evt-lc-idem", age_hours=30)
    first = run(event_formation.expire_stale_events())
    second = run(event_formation.expire_stale_events())
    assert first >= 1
    assert second == 0  # every transition happened in the first call
    assert _event_status(doc["event_id"]) == "EXPIRED"


def test_expiry_preserves_lifecycle_fields():
    doc = _insert_aged_event("evt-lc-fields", age_hours=40)
    run(event_formation.expire_stale_events())

    async def _reload():
        return await get_db()[Collections.EVENTS].find_one(
            {"event_id": doc["event_id"]}
        )

    after = run(_reload())
    assert _roundtrip_dt(after["first_detected"]) == _roundtrip_dt(doc["first_detected"])
    assert _roundtrip_dt(after["last_detected"]) == _roundtrip_dt(doc["last_detected"])
    assert after["detection_count"] == doc["detection_count"]
    assert after["detection_ids"] == doc["detection_ids"]
    assert after["status"] == "EXPIRED"  # only status transitioned


def test_expiry_applies_to_production_and_demo_alike_without_mixing():
    prod = _insert_aged_event("evt-lc-prod", age_hours=40, origin="production")
    demo = _insert_aged_event("evt-lc-demo", age_hours=40, origin="demo")
    run(event_formation.expire_stale_events())

    assert _event_status(prod["event_id"]) == "EXPIRED"
    assert _event_status(demo["event_id"]) == "EXPIRED"

    async def _origins():
        col = get_db()[Collections.EVENTS]
        p = await col.find_one({"event_id": prod["event_id"]}, {"data_origin": 1})
        d = await col.find_one({"event_id": demo["event_id"]}, {"data_origin": 1})
        return p["data_origin"], d["data_origin"]

    assert run(_origins()) == ("production", "demo")  # origins unchanged


def test_expiry_disabled_when_window_is_none():
    cfg = event_formation.EventFormationConfig(expiry_window_hours=None)
    doc = _insert_aged_event("evt-lc-disabled", age_hours=1000)
    assert run(event_formation.expire_stale_events(config=cfg)) == 0
    assert _event_status(doc["event_id"]) == "ACTIVE"


def test_unsupported_window_is_rejected():
    cfg = event_formation.EventFormationConfig(expiry_window_hours=12.0)
    with pytest.raises(ValueError):
        run(event_formation.expire_stale_events(config=cfg))
