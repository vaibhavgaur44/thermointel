"""Tests for POST /api/reprocess/existing-data (isolated DB, no FIRMS)."""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.routes.reprocess import reprocess_existing_data  # noqa: E402
from core.config import settings  # noqa: E402
from core.database import Collections, close_db, ensure_indexes, get_db  # noqa: E402
from models.common import GeoPoint  # noqa: E402
from models.detection import ThermalDetection  # noqa: E402
from models.enums import DayNight, EventStatus, Satellite  # noqa: E402
from models.event import ClassificationResult, Event  # noqa: E402
from pipeline import firms_ingestion  # noqa: E402

TEST_DB_NAME = "thermointel_reprocess_test"
WHITELIST = {"classification", "threat", "facility_reference", "updated_at"}

_LOOP = None


def run(coro):
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


@pytest.fixture(scope="module", autouse=True)
def reprocess_test_db():
    original = settings.DB_NAME
    settings.DB_NAME = TEST_DB_NAME
    run(ensure_indexes())
    for name in (Collections.EVENTS, Collections.THERMAL_DETECTIONS,
                 Collections.ALERTS, Collections.INGESTION_RUNS):
        run(get_db()[name].delete_many({}))
    yield
    run(get_db().client.drop_database(TEST_DB_NAME))
    run(close_db())
    if _LOOP is not None and not _LOOP.is_closed():
        _LOOP.close()
    settings.DB_NAME = original


def _seed(observation_id: str, frp: float, confidence, last_detected: datetime,
          status: EventStatus = EventStatus.ACTIVE) -> str:
    return run(_seed_async(observation_id, frp, confidence, last_detected, status))


async def _seed_async(observation_id: str, frp: float, confidence,
                      last_detected: datetime,
                      status: EventStatus = EventStatus.ACTIVE) -> str:
    det = ThermalDetection(
        observation_id=observation_id,
        location=GeoPoint.from_lat_lon(20.29, 85.82),
        acquired_at=last_detected,
        satellite=Satellite.VIIRS_NOAA20,
        satellite_std="N20",
        instrument="VIIRS",
        version="2.0NRT",
        day_night=DayNight.NIGHT,
        frp=frp,
        brightness_ti4=332.58,
        brightness_ti5=296.22,
        firms_confidence=confidence,
        scan=0.44,
        track=0.38,
        ingestion_run_id="run-reprocess-test",
        data_origin="production",
        state="Odisha",
        state_lgd="21",
        lulc_2021_code="40",
        lulc_2021_class="Cropland",
    )
    event = Event(
        event_id=f"evt-{observation_id}",
        centroid=det.location,
        state=det.state,
        first_detected=det.acquired_at,
        last_detected=det.acquired_at,
        detection_count=1,
        detection_ids=[det.observation_id],
        status=status,
    )
    event.classification = ClassificationResult(
        event_category="INDUSTRIAL",
        event_type="PERSISTENT_HEAT_SOURCE",
        source_type="GAS_FLARE",
        confidence=0.357,
        model_version_id="thermointel-phase4-final",
        inferred_at=datetime(2026, 9, 26, tzinfo=timezone.utc),
    )
    db = get_db()
    await db[Collections.THERMAL_DETECTIONS].insert_one(det.to_mongo())
    await db[Collections.EVENTS].insert_one(event.to_mongo())
    return event.event_id


def _get(event_id: str) -> dict:
    return run(get_db()[Collections.EVENTS].find_one({"event_id": event_id}))


class TestReprocessExistingData:
    def test_bounded_run_updates_only_selected(self):
        e1 = _seed("rep-test-1", 0.0, None,
                   datetime.now(timezone.utc) - timedelta(days=3),
                   status=EventStatus.EXPIRED)
        e2 = _seed("rep-test-2", 12.5, "n", datetime.now(timezone.utc))
        det_count = run(get_db()[Collections.THERMAL_DETECTIONS].count_documents({}))

        result = run(reprocess_existing_data(limit=1, triggered_by="pytest-bounded"))

        assert result["status"] in ("SUCCEEDED", "PARTIAL")
        assert result["source"] == "EXISTING_DATABASE"
        assert result["updated"] == 1
        assert result["selected"] == 1
        assert result["failed"] == 0

        # The NEW model processed the selected event (inferred_at advanced).
        after2 = _get(e2)
        assert after2["classification"]["inferred_at"] > datetime(2026, 9, 27)
        # The unselected event kept its seeded OLD-model classification.
        after1 = _get(e1)
        assert after1["classification"]["confidence"] == 0.357
        assert after1["status"] == "EXPIRED"  # never resurrected
        # No duplicates, no deletions.
        assert run(get_db()[Collections.THERMAL_DETECTIONS].count_documents({})) == det_count

    def test_targeted_update_whitelist(self):
        e = _seed("rep-test-3", 5.71, "n", datetime.now(timezone.utc))
        before = _get(e)
        run(reprocess_existing_data(limit=None, triggered_by="pytest-whitelist"))
        after = _get(e)

        changed = {k for k in before
                   if before[k] != after[k]}
        assert changed <= WHITELIST
        assert after["classification"]["inferred_at"] > before["classification"]["inferred_at"]

    def test_no_firms_fetch_and_truthful_run_record(self):
        _seed("rep-test-4", 5.71, "n", datetime.now(timezone.utc))

        def _tripwire(*a, **k):
            raise AssertionError("FIRMS fetch attempted during reprocess")

        original = firms_ingestion.fetch_detections
        firms_ingestion.fetch_detections = _tripwire
        try:
            result = run(reprocess_existing_data(limit=None, triggered_by="pytest-nofirms"))
        finally:
            firms_ingestion.fetch_detections = original

        assert result["status"] in ("SUCCEEDED", "PARTIAL")
        run_doc = run(get_db()[Collections.INGESTION_RUNS].find_one(
            {"run_id": result["run_id"]}))
        assert run_doc["source"] == "EXISTING_DATABASE"
        assert run_doc["detections_ingested"] == 0
        assert run_doc["requested_window_hours"] is None

    def test_idempotent_second_run(self):
        e = _seed("rep-test-5", 5.71, "n", datetime.now(timezone.utc))
        run(reprocess_existing_data(limit=None, triggered_by="pytest-idem-1"))
        after1 = _get(e)
        run(reprocess_existing_data(limit=None, triggered_by="pytest-idem-2"))
        after2 = _get(e)

        # Deterministic model: the second run reproduces the same decision;
        # only the inference timestamp advances.
        c1, c2 = after1["classification"], after2["classification"]
        assert {k: v for k, v in c1.items() if k != "inferred_at"} == \
            {k: v for k, v in c2.items() if k != "inferred_at"}
        assert c2["inferred_at"] >= c1["inferred_at"]
        # No detection growth across repeated runs.
        assert run(get_db()[Collections.THERMAL_DETECTIONS].count_documents(
            {"observation_id": "rep-test-5"})) == 1
