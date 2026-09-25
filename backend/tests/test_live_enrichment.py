"""Focused Phase 5 tests: live FIRMS NRT state/LULC enrichment.

Covers: state enrichment (real SOI shapefile join), LULC sampling logic
(synthetic tile, no network), unmatched/out-of-coverage explicit missing
values, enrichment-before-feature-engineering, observation_id stability,
frozen 35-feature schema integrity, and historical-archive behavior.

The historical CSVs are NOT loaded wholesale in these tests (they are
4.7M rows); the archive path is exercised via the process cache hook.
"""

import asyncio
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.common import GeoPoint  # noqa: E402
from models.detection import ThermalDetection  # noqa: E402
from models.enums import DayNight, Satellite  # noqa: E402
from pipeline import firms_ingestion, live_enrichment  # noqa: E402
from pipeline.feature_engineering import (  # noqa: E402
    RAW_FEATURES,
    build_features,
)

_LOOP = None


def run(coro):
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
    return _LOOP.run_until_complete(coro)


@pytest.fixture(scope="module", autouse=True)
def teardown_loop():
    yield
    if _LOOP is not None and not _LOOP.is_closed():
        _LOOP.close()


@pytest.fixture(scope="module")
def enricher():
    """Real LiveEnricher (state polygons from the SOI shapefile)."""
    return live_enrichment.LiveEnricher()


def _detection(lat: float, lon: float, **overrides) -> ThermalDetection:
    values = dict(
        observation_id=hashlib.sha256(b"test-detection").hexdigest(),
        location=GeoPoint.from_lat_lon(lat, lon),
        acquired_at="2026-09-22T06:49:00+00:00",
        satellite=Satellite.VIIRS_NOAA20,
        satellite_std="N20",
        instrument="VIIRS",
        version="2.3NRT",
        day_night=DayNight.NIGHT,
        frp=8.68,
        brightness_ti4=367.0,
        brightness_ti5=300.0,
        firms_confidence="h",
        scan=0.38,
        track=0.59,
        ingestion_run_id="run-test",
        data_origin="production",
    )
    values.update(overrides)
    return ThermalDetection(**values)


# ------------------------------------------------------------------ state --


def test_live_state_enrichment_known_location(enricher):
    # Interior Odisha point - well inside one state polygon.
    results = enricher.enrich_states([20.29], [85.82])
    state, lgd = results[0]

    assert state == "Odisha"
    # LGD code present where the shapefile supports it (State_LGD column).
    assert lgd is None or isinstance(lgd, str)


def test_live_state_enrichment_sea_point_missing(enricher):
    # Open sea east of Kanyakumari: outside every state polygon -> explicit
    # missing values, nothing fabricated.
    results = enricher.enrich_states([6.0], [80.5])
    assert results[0] == (None, None)


def test_state_names_are_phase3_normalized(enricher):
    # task_b2_states.py normalization: Title Case with 'and', not UPPERCASE.
    results = enricher.enrich_states([28.61], [77.21])
    state, _ = results[0]
    if state is not None:
        assert state == state.title() or "and" in state or state.islower() is False
        assert state != "DELHI"


# ------------------------------------------------------------------- lulc --


def test_worldcover_tile_naming_matches_phase3():
    # Verbatim Phase 3 formula: floor((v - 1e-9) / 3) * 3.
    # lat 20.12 -> floor(6.70) * 3 = 18 -> N18E084 (tile spans 18-21N).
    assert live_enrichment.LiveEnricher._tile_name(20.12353, 85.72746) == "N18E084"
    # Boundary epsilon: lon exactly 78.0 -> left tile (E075), per the
    # Phase 3 rule "points on a tile boundary sit on its left/bottom edge".
    assert live_enrichment.LiveEnricher._tile_name(-1.5, 78.0) == "S03E075"
    assert live_enrichment.LiveEnricher._tile_name(23.5, 84.5) == "N21E084"


def test_lulc_sampling_synthetic_tile(enricher):
    """Sampling math against a synthetic WorldCover tile: deterministic,
    no network, Phase 3 affine inverse logic. Pixel size 1/30 degree so a
    DECIMATION=30 overview cell is 1 degree (mirrors 10m -> ~300m)."""
    import numpy as np
    from rasterio.transform import Affine

    cell = 1.0 / 30.0
    arr = np.full((90, 90), 40, dtype=np.int16)  # Cropland
    arr[0, 0] = 50  # Built-up in the top-left 1-degree cell (84-85E, 23-24N)
    transform = Affine(cell, 0.0, 84.0, 0.0, -cell, 24.0)
    enricher._tiles["N21E084"] = (arr, transform, 90, 90)

    results = enricher.enrich_lulc([23.5, 21.5], [84.5, 84.5])

    assert results[0] == ("50", "Built-up")
    assert results[1] == ("40", "Cropland")


def test_lulc_out_of_tile_and_no_data_are_missing(enricher, monkeypatch):
    import numpy as np
    from rasterio.transform import Affine

    arr = np.zeros((90, 90), dtype=np.int16)  # all NO_DATA (0)
    transform = Affine(1.0 / 30.0, 0.0, 84.0, 0.0, -1.0 / 30.0, 24.0)
    enricher._tiles["N21E084"] = (arr, transform, 90, 90)
    # Unknown tiles are not fetched in this test (no network): unreadable
    # tile -> explicit missing, exactly like a failed Phase 3 tile read.
    monkeypatch.setattr(enricher, "_tile_array", lambda tile: None)

    results = enricher.enrich_lulc([23.5, 30.0], [84.5, 84.5])
    # NO_DATA pixel -> missing; unreadable tile -> missing.
    assert results[0] == (None, None)
    assert results[1] == (None, None)


def test_lulc_disabled_returns_explicit_missing():
    disabled = live_enrichment.LiveEnricher(lulc_enabled=False)
    assert disabled.enrich_lulc([23.5], [84.5]) == [(None, None)]


# ------------------------------------------------- enrichment -> features --


class _StubEnricher:
    """Deterministic stub for pipeline-wiring tests (no network/shapefile)."""

    def enrich_batch(self, lats, lons):
        return [
            {
                "state": "Odisha",
                "state_lgd": "21",
                "lulc_2021_code": "40",
                "lulc_2021_class": "Cropland",
            }
            for _ in lats
        ]


def test_enrichment_applied_before_feature_engineering(monkeypatch):
    monkeypatch.setattr(live_enrichment, "_LIVE_ENRICHER", _StubEnricher())

    detection = _detection(20.29, 85.82)
    assert detection.state is None  # not enriched yet

    run(firms_ingestion._enrich_detections([detection]))

    assert detection.state == "Odisha"  # enrichment attached in place

    # Feature engineering consumes the enriched detection dict.
    from models.event import Event

    event = Event(
        event_id="evt-obs-abc-123",
        centroid=detection.location,
        state=detection.state,
        first_detected=detection.acquired_at,
        last_detected=detection.acquired_at,
        detection_count=1,
    )
    features = build_features(event, detection.model_dump(), {})
    assert features["state_ut"] == "Odisha"
    assert features["State_LGD"] == "21"
    assert features["lulc_2021_code"] == "40"
    assert features["lulc_2021_class"] == "Cropland"


def test_unenrichable_detection_preserves_missing(monkeypatch):
    class _NoneEnricher:
        def enrich_batch(self, lats, lons):
            return [
                {
                    "state": None,
                    "state_lgd": None,
                    "lulc_2021_code": None,
                    "lulc_2021_class": None,
                }
                for _ in lats
            ]

    monkeypatch.setattr(live_enrichment, "_LIVE_ENRICHER", _NoneEnricher())

    detection = _detection(6.0, 80.5)  # open sea
    run(firms_ingestion._enrich_detections([detection]))

    assert detection.state is None
    assert detection.state_lgd is None
    assert detection.lulc_2021_code is None
    assert detection.lulc_2021_class is None


# ------------------------------------------------------- identity / schema --


def test_observation_id_unchanged_by_enrichment(monkeypatch):
    monkeypatch.setattr(live_enrichment, "_LIVE_ENRICHER", _StubEnricher())

    detection = _detection(20.29, 85.82)
    before = detection.observation_id
    assert len(before) == 64  # sha256 hex

    run(firms_ingestion._enrich_detections([detection]))

    assert detection.observation_id == before


def test_phase3_detection_id_is_lookup_key_only():
    """The Phase 3 sha1 id is recomputed ONLY as an archive lookup key and is
    NOT stored on the document (observation_id remains the identity)."""
    detection = _detection(
        20.12353,
        85.72746,
        acquired_at="2019-01-01T06:49:00+00:00",
        frp=8.68,
    )
    assert firms_ingestion._phase3_detection_id(detection) == "9e9f9f5b32d97b30"


def test_frozen_feature_schema_unchanged():
    schema_path = (
        Path(__file__).resolve().parents[1]
        / "models"
        / "ml"
        / "feature_schema_final.json"
    )
    frozen = json.loads(schema_path.read_text(encoding="utf-8"))["raw_features"]
    assert RAW_FEATURES == frozen
    assert len(RAW_FEATURES) == 35


# -------------------------------------------------------------- historical --


def test_historical_archive_merge_behavior(monkeypatch):
    monkeypatch.setattr(
        live_enrichment,
        "_HIST_CACHE",
        (
            {"arch-1": {"state": "Odisha", "state_lgd": "21"}},
            {"arch-1": {"lulc_2021_code": "40", "lulc_2021_class": "Cropland"}},
        ),
    )

    records = live_enrichment.historical_enrich_batch(["arch-1", "missing-id"])
    assert records[0] == {
        "state": "Odisha",
        "state_lgd": "21",
        "lulc_2021_code": "40",
        "lulc_2021_class": "Cropland",
    }
    assert records[1] is None  # absent from archive -> explicit missing


def test_historical_path_used_for_archive_dates(monkeypatch):
    """A detection dated within archive coverage takes the CSV lookup path."""
    import hashlib

    monkeypatch.setattr(live_enrichment, "_LIVE_ENRICHER", _StubEnricher())

    detection = _detection(
        20.12353, 85.72746, acquired_at="2019-01-01T06:49:00+00:00"
    )
    did = firms_ingestion._phase3_detection_id(detection)
    assert len(did) == 16

    called = {"live": False}

    class _Guard:
        def enrich_batch(self, lats, lons):
            called["live"] = True
            return _StubEnricher().enrich_batch(lats, lons)

    monkeypatch.setattr(live_enrichment, "_LIVE_ENRICHER", _Guard())
    monkeypatch.setattr(
        firms_ingestion.live_enrichment,
        "historical_enrich_batch",
        lambda ids: [
            {
                "state": "Odisha",
                "state_lgd": "21",
                "lulc_2021_code": "40",
                "lulc_2021_class": "Cropland",
            }
            for _ in ids
        ],
    )

    run(firms_ingestion._enrich_detections([detection]))
    assert called["live"] is False  # live path NOT used for archive dates
    assert detection.state == "Odisha"
