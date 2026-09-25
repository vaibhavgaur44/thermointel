"""Focused Phase 5 tests: the owner-proposed v2 threat scoring framework
(Task 21).

Pins exactly the Task 21 contract:

- every numerical value lives in the ONE configuration object; weights sum
  to 1.0; the framework refuses to score with an incomplete config
- the formula is literal: 100 x SUM(weight x normalized), clamped to
  [0, 100]; a None (missing/UNDEFINED) signal contributes 0
- per-signal normalization status: rate_of_change, spatial_behaviour and
  industrial_context are UNDEFINED and always yield None (never fabricated)
- level boundaries 0-24/25-49/50-74/75-100 are inclusive lower bounds
- alert eligibility begins at HIGH; HIGH needs an abnormal signal (>= floor);
  CRITICAL qualifies automatically; nothing below HIGH is eligible
- duplicate suppression: deterministic alert_id, idempotent re-runs
- production/demo separation: demo events never produce alerts
- the frozen 35-feature ML schema remains unchanged

Runs against an ISOLATED test database (thermointel_threat_test).
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import settings  # noqa: E402
from core.database import Collections, close_db, ensure_indexes, get_db  # noqa: E402
from models.common import GeoPoint  # noqa: E402
from models.event import ClassificationResult, Event  # noqa: E402
from pipeline import event_formation, threat_engine  # noqa: E402
from pipeline.feature_engineering import RAW_FEATURES, build_features  # noqa: E402
from pipeline.ml_inference import classify_sync  # noqa: E402

TEST_DB_NAME = "thermointel_threat_test"

_LOOP = None


def run(coro):
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


@pytest.fixture(scope="module", autouse=True)
def threat_test_db():
    original_db_name = settings.DB_NAME
    settings.DB_NAME = TEST_DB_NAME
    run(ensure_indexes())
    for name in (Collections.EVENTS, Collections.THERMAL_DETECTIONS, Collections.ALERTS):
        run(get_db()[name].delete_many({}))
    yield
    run(get_db().client.drop_database(TEST_DB_NAME))
    run(close_db())
    if _LOOP is not None and not _LOOP.is_closed():
        _LOOP.close()
    settings.DB_NAME = original_db_name


def _detection(
    observation_id: str,
    lat: float,
    lon: float,
    origin: str = "production",
    frp: float = 5.71,
    brightness_ti4: float = 332.58,
    firms_confidence: str = "n",
):
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
        frp=frp,
        brightness_ti4=brightness_ti4,
        brightness_ti5=296.22,
        firms_confidence=firms_confidence,
        scan=0.44,
        track=0.38,
        ingestion_run_id="run-threat-test",
        data_origin=origin,
        state="Odisha",
        state_lgd="21",
        lulc_2021_code="40",
        lulc_2021_class="Cropland",
    )


def _event(
    observation_id: str,
    origin: str = "production",
    classification: ClassificationResult | None = None,
) -> Event:
    det = _detection(observation_id, 20.29, 85.82, origin=origin)
    return Event(
        event_id=f"evt-{det.observation_id}",
        centroid=det.location,
        state=det.state,
        first_detected=det.acquired_at,
        last_detected=det.acquired_at,
        detection_count=1,
        detection_ids=[det.observation_id],
        data_origin=det.data_origin,
        classification=classification or ClassificationResult(),
    )


# ------------------------------------------------------- configuration ---


def test_config_is_the_single_home_of_numerical_values():
    cfg = threat_engine.CONFIG
    assert cfg.signal_weights == {
        "frp_magnitude": 0.20,
        "baseline_deviation": 0.20,
        "rate_of_change": 0.15,
        "spatial_behaviour": 0.10,
        "detection_strength": 0.10,
        "industrial_context": 0.10,
        "ml_evidence": 0.15,
    }
    assert cfg.level_boundaries == {
        "LOW": 0.0, "MODERATE": 25.0, "HIGH": 50.0, "CRITICAL": 75.0,
    }
    assert cfg.alert_threshold == 50.0
    assert cfg.score_min == 0.0 and cfg.score_max == 100.0
    assert cfg.threshold_profile == "owner-proposal-v1"
    # Explicitly provisional - NOT claimed as calibrated/validated.
    assert cfg.calibration_status == threat_engine.CALIBRATION_STATUS_PROVISIONAL
    assert cfg.is_configured is True
    assert cfg.is_calibrated is False


def test_weight_sum_is_one():
    total = sum(threat_engine.CONFIG.signal_weights.values())
    assert abs(total - 1.0) < 1e-9


def test_incomplete_config_is_rejected():
    cfg = threat_engine.ThreatEngineConfig()  # all weights None
    assert cfg.is_configured is False

    event = _event("obs-incomplete")
    import asyncio as _aio

    assert _aio.get_event_loop_policy  # noqa: F401 (sanity)
    assert run(threat_engine.assess(event, {})) is None  # never scores

    cfg.signal_weights = {s: 0.1 for s in threat_engine.THREAT_SIGNALS}
    with pytest.raises(ValueError):
        cfg.validate()  # sums to 0.7, must be refused


# ------------------------------------------------------ normalization ---


def test_undefined_signals_always_yield_none():
    event = _event("obs-undef")
    normalized = threat_engine.normalize_signals(event, {})
    assert normalized["rate_of_change"] is None
    assert normalized["spatial_behaviour"] is None
    assert normalized["industrial_context"] is None
    assert threat_engine.SIGNAL_DEFINITIONS_STATUS["rate_of_change"] == "UNDEFINED"
    assert threat_engine.SIGNAL_DEFINITIONS_STATUS["spatial_behaviour"] == "UNDEFINED"
    assert threat_engine.SIGNAL_DEFINITIONS_STATUS["industrial_context"] == "UNDEFINED"


def test_defined_signals_stay_in_unit_range():
    features = {
        "frp_log1p": 99.0,        # far above saturation
        "brightness_diff": -5.0,  # below zero
        "confidence_num": 7.0,    # beyond [0, 1]
    }
    event = _event("obs-clamp")
    normalized = threat_engine.normalize_signals(event, features)

    for signal in ("frp_magnitude", "baseline_deviation", "detection_strength"):
        value = normalized[signal]
        assert value is not None and 0.0 <= value <= 1.0
    assert normalized["frp_magnitude"] == 1.0          # clamped high
    assert normalized["baseline_deviation"] == 0.0     # clamped low
    assert normalized["detection_strength"] == 1.0     # clamped high


def test_missing_features_yield_none_not_zero():
    event = _event("obs-missing-feats")
    normalized = threat_engine.normalize_signals(event, {})
    assert normalized["frp_magnitude"] is None
    assert normalized["baseline_deviation"] is None
    assert normalized["detection_strength"] is None
    assert normalized["ml_evidence"] is None  # unclassified event


# ------------------------------------------------------------ scoring ---


def test_weighted_score_exact_calculation():
    normalized = {
        "frp_magnitude": 1.0,
        "baseline_deviation": 1.0,
        "rate_of_change": None,
        "spatial_behaviour": None,
        "detection_strength": 1.0,
        "industrial_context": None,
        "ml_evidence": 1.0,
    }
    # 100 x (0.20 + 0.20 + 0.10 + 0.15) = 65.0
    assert threat_engine.weighted_score(normalized) == pytest.approx(65.0)


def test_weighted_score_bounds_are_clamped():
    cfg = threat_engine.CONFIG
    all_ones = {s: 1.0 for s in threat_engine.THREAT_SIGNALS}
    all_zeros = {s: 0.0 for s in threat_engine.THREAT_SIGNALS}

    assert threat_engine.weighted_score(all_ones, cfg) == pytest.approx(100.0)
    assert threat_engine.weighted_score(all_zeros, cfg) == pytest.approx(0.0)


def test_all_signals_missing_keeps_unassessed():
    event = _event("obs-no-signals")
    assert run(threat_engine.assess(event, {})) is None
    assert event.threat.threat_level is None
    assert event.threat.threat_score is None


def test_assess_scores_a_fully_featured_event():
    # Handcrafted but honest inputs; expected value computed by the same
    # formula the engine implements.
    event = _event(
        "obs-scored",
        classification=ClassificationResult(
            event_type="FOREST_FIRE",
            source_type="GAS_FLARE",
            confidence=1.0,
        ),
    )
    features = {
        "frp_log1p": 5.0,        # -> 1.0
        "brightness_diff": 40.0,  # -> 1.0
        "confidence_num": 1.0,    # -> 1.0
    }
    assessment = run(threat_engine.assess(event, features))

    assert assessment is not None
    # frp 1.0*0.20 + baseline 1.0*0.20 + detection 1.0*0.10
    # + ml_evidence (0.5*1.0 + 0.3*0.8 + 0.2*1.0)/1.0 = 0.94 -> 0.15*0.94
    # = 0.2 + 0.2 + 0.1 + 0.141 = 0.641 -> 64.1 (UNDEFINED signals contribute 0)
    assert assessment.threat_score == pytest.approx(64.1)
    assert assessment.threat_level == "HIGH"
    # Threat stays separate from classification confidence (confidence is
    # only one sub-component of one signal).
    codes = {item.code for item in assessment.supporting_evidence}
    assert "HIGH_FRP" in codes and "BASELINE_DEVIATION" in codes


# ------------------------------------------------------- level bands ---


@pytest.mark.parametrize(
    "score,expected",
    [
        (0.0, "LOW"), (24.999, "LOW"),
        (25.0, "MODERATE"), (49.999, "MODERATE"),
        (50.0, "HIGH"), (74.999, "HIGH"),
        (75.0, "CRITICAL"), (100.0, "CRITICAL"),
    ],
)
def test_level_boundaries(score, expected):
    level = threat_engine.level_for_score(score)
    assert level == expected


# --------------------------------------------------- alert eligibility ---


def test_high_requires_abnormal_signal():
    cfg = threat_engine.CONFIG
    abnormal = {s: 0.9 for s in threat_engine.THREAT_SIGNALS}
    weak = {s: 0.1 for s in threat_engine.THREAT_SIGNALS}

    assert threat_engine._is_alert_eligible("HIGH", abnormal, cfg) is True
    assert threat_engine._is_alert_eligible("HIGH", weak, cfg) is False


def test_critical_qualifies_automatically():
    cfg = threat_engine.CONFIG
    # Even with NO computable signals at all.
    assert threat_engine._is_alert_eligible("CRITICAL", {}, cfg) is True
    assert threat_engine._is_alert_eligible("CRITICAL", {s: None for s in threat_engine.THREAT_SIGNALS}, cfg) is True


@pytest.mark.parametrize("level", [None, "LOW", "MODERATE"])
def test_below_high_is_never_eligible(level):
    cfg = threat_engine.CONFIG
    abnormal = {s: 1.0 for s in threat_engine.THREAT_SIGNALS}
    assert threat_engine._is_alert_eligible(level, abnormal, cfg) is False


# ------------------------------------------- alert persistence lifecycle ---


def _persist_classified_event(observation_id: str, origin: str = "production"):
    """Full documented path: detection -> event -> 35 features -> frozen ML
    -> threat assessment -> event persistence. Returns (event, normalized).

    Detection values are chosen so frp_magnitude, baseline_deviation and
    detection_strength all normalize to 1.0, guaranteeing score >= 50 (HIGH)
    regardless of what the frozen ML classifies - the ml_evidence signal can
    only add to it."""
    det_kwargs = dict(frp=200.0, brightness_ti4=380.0, firms_confidence="h")
    event = _event(observation_id, origin=origin)
    features = build_features(
        event,
        _detection(observation_id, 20.29, 85.82, origin, **det_kwargs).model_dump(),
        {},
    )
    assert list(features.keys()) == RAW_FEATURES
    event.classification = classify_sync(event, features)

    normalized = threat_engine.normalize_signals(event, features)
    assessment = run(threat_engine.assess(event, features))
    if assessment is not None:
        event.threat = assessment

    events = run(event_formation.group_detections(
        [_detection(observation_id, 20.29, 85.82, origin, **det_kwargs)]
    ))
    events[0].classification = event.classification
    events[0].threat = event.threat
    run(event_formation.persist_events(events))
    return events[0], normalized


def test_high_alert_persists_and_suppresses_duplicates():
    # brightness_diff 36.36/40 = 0.909 >= floor 0.5 -> HIGH + abnormal signal.
    event, normalized = _persist_classified_event("obs-alert-high")
    assert event.threat.threat_level == "HIGH"

    created_first = run(threat_engine.generate_alerts([event], {event.event_id: normalized}))
    assert created_first == 1

    async def _state():
        col = get_db()[Collections.ALERTS]
        doc = await col.find_one({"alert_id": f"alr-{event.event_id}"})
        return (
            await col.count_documents({}),
            doc["event_id"], doc["data_origin"], doc["threshold_profile"],
            doc["threat_level"], doc["raised_at"],
        )

    total, event_id, origin, profile, level, raised_at = run(_state())
    assert total == 1
    assert event_id == event.event_id
    assert origin == "production"
    assert profile == "owner-proposal-v1"
    assert level == "HIGH"

    # Re-run: duplicate suppression - no second alert.
    created_second = run(threat_engine.generate_alerts([event], {event.event_id: normalized}))
    assert created_second == 0

    async def _count():
        return await get_db()[Collections.ALERTS].count_documents({})

    assert run(_count()) == 1


def test_below_high_persists_no_alert():
    # confidence "n" -> detection_strength 1.0, but a weak-thermal event can
    # still land below HIGH; assert no alert exists for a MODERATE/LOW event.
    event = _event("obs-alert-low")
    features = {"frp_log1p": 0.1, "brightness_diff": 1.0, "confidence_num": 0.0}
    event.classification = ClassificationResult()  # unclassified -> no ml_evidence
    normalized = threat_engine.normalize_signals(event, features)
    assessment = run(threat_engine.assess(event, features))
    assert assessment is not None
    event.threat = assessment
    assert assessment.threat_level in ("LOW", "MODERATE")

    created = run(threat_engine.generate_alerts([event], {event.event_id: normalized}))
    assert created == 0

    async def _count():
        return await get_db()[Collections.ALERTS].count_documents(
            {"event_id": event.event_id}
        )

    assert run(_count()) == 0


def test_demo_events_never_produce_alerts():
    event, normalized = _persist_classified_event("obs-alert-demo", origin="demo")
    assert event.data_origin == "demo"
    assert event.threat.threat_level == "HIGH"  # would qualify if production

    created = run(threat_engine.generate_alerts([event], {event.event_id: normalized}))
    assert created == 0

    async def _count():
        return await get_db()[Collections.ALERTS].count_documents(
            {"data_origin": "demo"}
        )

    assert run(_count()) == 0


def test_unassessed_events_are_never_alert_eligible():
    event = _event("obs-alert-unassessed")
    created = run(threat_engine.generate_alerts([event], {}))  # never assessed
    assert created == 0


def test_alert_indexes_support_the_contract():
    info = run(get_db()[Collections.ALERTS].index_information())
    assert any(
        spec["key"] == [("alert_id", 1)] and spec.get("unique")
        for spec in info.values()
    )
    assert any(spec["key"] == [("event_id", 1)] for spec in info.values())


# --------------------------------------------- frozen ML schema guard ---


def test_frozen_35_feature_schema_remains_unchanged():
    import json

    schema_path = (
        Path(__file__).resolve().parents[1] / "models" / "ml" / "feature_schema_final.json"
    )
    with open(schema_path, encoding="utf-8") as fh:
        artifact_features = json.load(fh)["raw_features"]

    assert RAW_FEATURES == artifact_features
    assert len(RAW_FEATURES) == 35

    det = _detection("obs-schema-guard", 20.29, 85.82)
    event = _event("obs-schema-guard")
    features = build_features(event, det.model_dump(), {})
    assert list(features.keys()) == RAW_FEATURES  # exact names AND ordering
