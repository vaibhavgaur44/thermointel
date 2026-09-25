"""Real-data facility verification against the OPERATIONAL database.

Unlike tests/test_facility_context.py (isolated test DB), this module runs
`nearest_facility()` against the imported Phase 3 facility corpus and the
operational geospatial indexes. Skips cleanly if the corpus or indexes are
absent, so it never blocks environments without the imported data.
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hashlib  # noqa: E402

from core.database import (  # noqa: E402
    Collections,
    close_db,
    get_db,
)
from models.common import GeoPoint  # noqa: E402
from models.detection import ThermalDetection  # noqa: E402
from models.enums import DayNight, Satellite  # noqa: E402
from models.event import Event  # noqa: E402
from pipeline.feature_engineering import RAW_FEATURES, build_features  # noqa: E402
from pipeline.ml_inference import classify_sync  # noqa: E402
from services import registry_service  # noqa: E402

_LOOP = None


def run(coro):
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        # Motor binds futures to the policy's current loop; make this module's
        # loop the current one so every Motor call rebinds here.
        asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


@pytest.fixture(scope="module", autouse=True)
def fresh_motor_client():
    """Motor clients bind to the loop they first run on; when pytest-xdist
    reuses a worker that already ran the isolated-DB module, dispose the
    shared client and rebuild it INSIDE this module's running loop."""
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()

    import core.database as _dbmod

    async def _reset():
        if _dbmod._client is not None:
            _dbmod._client.close()
            _dbmod._client = None
        # Constructed while the loop is running so Motor binds to it.
        get_db()

    _LOOP.run_until_complete(_reset())
    yield


def teardown_module():
    if _LOOP is not None and not _LOOP.is_closed():
        run(close_db())
        _LOOP.close()


@pytest.fixture(scope="module")
def corpus_present():
    async def _check():
        collection = get_db()[Collections.FACILITIES]
        doc = await collection.find_one(
            {"facility_id": "CT-ct-1897099",
             "dataset_version": "phase3-standardized"}
        )
        info = await collection.index_information()
        return doc, info

    doc, info = run(_check())
    if doc is None:
        pytest.skip("Phase 3 facility corpus not imported in this DB")
    if not any(spec["key"] == [("location", "2dsphere")] for spec in info.values()):
        pytest.skip("operational location_2dsphere index not built")


def test_known_phase3_facility_is_nearest(corpus_present):
    # 1 meter east of CT-ct-1897099 / Andhra Cements Dachepalli Cement Plant.
    context = run(registry_service.nearest_facility(16.64789, 79.70232))

    assert context is not None
    assert context["facility_id"] == "CT-ct-1897099"
    assert context["name"] == "Andhra Cements Dachepalli Cement Plant"
    assert context["nearest_facility_km"] < 0.1
    assert context["nearest_facility_type"] == "Cement / Kiln"
    assert context["industrial_context"]["facility_type"] == "Cement / Kiln"


def test_facility_context_fields_contract(corpus_present):
    context = run(registry_service.nearest_facility(16.64789, 79.70232))
    assert set(context.keys()) == {
        "facility_id",
        "name",
        "nearest_facility_km",
        "nearest_facility_type",
        "industrial_context",
    }


def test_full_35_feature_production_path_with_facility_context(corpus_present):
    """Task 5 regression: detection -> facility context -> build_features ->
    frozen ML inference, against the operational facility corpus.

    Guards the complete Phase 5 flow: the facility context from
    nearest_facility() must reach feature engineering without altering the
    frozen 35-feature schema, and inference must still execute.
    """
    lat, lon = 16.64789, 79.70231  # at CT-ct-1897099 (Dachepalli Cement Plant)
    detection = ThermalDetection(
        observation_id=hashlib.sha256(b"operational-path-test").hexdigest(),
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
        ingestion_run_id="run-operational-test",
        data_origin="production",
        state="Andhra Pradesh",
        state_lgd="1",
        lulc_2021_code="50",
        lulc_2021_class="Built-up",
    )

    facility = run(registry_service.nearest_facility(lat, lon))
    assert facility is not None  # corpus guarantees a facility here

    event = Event(
        event_id=f"evt-{detection.observation_id}",
        centroid=detection.location,
        state=detection.state,
        first_detected=detection.acquired_at,
        last_detected=detection.acquired_at,
        detection_count=1,
    )
    features = build_features(event, detection.model_dump(), facility)

    # Frozen schema: exact names, exact order, exact count.
    assert list(features.keys()) == RAW_FEATURES
    assert len(features) == 35

    # Enrichment fields reach feature engineering.
    assert features["state_ut"] == "Andhra Pradesh"
    assert features["State_LGD"] == "1"
    assert features["lulc_2021_code"] == "50"
    assert features["lulc_2021_class"] == "Built-up"

    # Facility context reaches feature engineering from the real 2dsphere lookup.
    assert features["nearest_facility_km"] == facility["nearest_facility_km"]
    assert features["nearest_facility_type"] == "Cement / Kiln"

    # Frozen preprocessing + ML inference still execute on the vector.
    result = classify_sync(event, features)
    assert result.event_type is not None
    assert result.source_type is not None
    assert 0.0 <= result.confidence <= 1.0
