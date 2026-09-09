"""
Focused unit tests for the Milestone 1 ML inference layer (services/model_inference.py).

These tests validate wiring, schema compliance, and safe handling of missing
values using small synthetic inputs. They do NOT validate real-world model
accuracy — the underlying models were trained on heuristic pseudo-labels.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np

from services import model_inference as mi

MODEL1_FEATURES = [
    "frp", "confidence_num", "bright_ti4", "bright_ti5", "nearest_facility_km",
    "facility_within_1km", "facility_within_3km", "facility_within_10km",
    "detections_1d", "detections_7d", "detections_30d", "detections_90d",
    "historical_mean_frp_30d", "historical_max_frp_30d", "historical_std_frp_30d",
    "days_active_30d", "days_active_90d", "baseline_z_score",
]

MODEL2_FEATURES = [
    "frp", "confidence_num", "nearest_facility_km", "facility_within_1km",
    "facility_within_3km", "detections_1d", "detections_7d", "detections_30d",
    "detections_90d", "historical_mean_frp_30d", "historical_max_frp_30d",
    "historical_std_frp_30d", "days_active_30d", "days_active_90d", "baseline_z_score",
]

AGRICULTURAL_LIKE = {
    "frp": 15, "confidence_num": 60, "bright_ti4": 300, "bright_ti5": 290,
    "nearest_facility_km": 45.0, "facility_within_1km": 0, "facility_within_3km": 0,
    "facility_within_10km": 0, "detections_1d": 1, "detections_7d": 1,
    "detections_30d": 1, "detections_90d": 1, "historical_mean_frp_30d": 10,
    "historical_max_frp_30d": 15, "historical_std_frp_30d": 3, "days_active_30d": 1,
    "days_active_90d": 1, "baseline_z_score": 0.2,
}

INDUSTRIAL_LIKE = {
    "frp": 250, "confidence_num": 95, "bright_ti4": 340, "bright_ti5": 300,
    "nearest_facility_km": 0.5, "facility_within_1km": 1, "facility_within_3km": 1,
    "facility_within_10km": 1, "detections_1d": 20, "detections_7d": 60,
    "detections_30d": 90, "detections_90d": 200, "historical_mean_frp_30d": 180,
    "historical_max_frp_30d": 260, "historical_std_frp_30d": 30, "days_active_30d": 25,
    "days_active_90d": 60, "baseline_z_score": 3.5,
}


def test_both_model_artifacts_load():
    availability = mi.models_available()
    assert availability["model1_loaded"] is True
    assert availability["model2_loaded"] is True


def test_model1_schema_has_18_features_in_exact_order():
    schema = mi.get_feature_schema()
    assert schema["model1_features"] == MODEL1_FEATURES
    assert len(schema["model1_features"]) == 18


def test_model2_schema_has_15_features_in_exact_order():
    schema = mi.get_feature_schema()
    assert schema["model2_features"] == MODEL2_FEATURES
    assert len(schema["model2_features"]) == 15


def test_model1_inference_returns_valid_label_and_probability():
    label, probability = mi.predict_model1(INDUSTRIAL_LIKE)
    assert label in ("agricultural", "industrial")
    assert 0.0 <= probability <= 1.0


def test_model2_inference_returns_valid_label_and_probability():
    label, probability = mi.predict_model2(INDUSTRIAL_LIKE)
    assert label in ("persistent_source", "industrial_fire")
    assert 0.0 <= probability <= 1.0


def test_agricultural_observation_skips_model2():
    result = mi.run_inference(AGRICULTURAL_LIKE)
    assert result["model1_class"] == "agricultural"
    assert result["model2_class"] == "not_applicable"
    assert result["model2_probability"] is None
    assert result["final_class"] == "agricultural"


def test_industrial_observation_runs_model2():
    result = mi.run_inference(INDUSTRIAL_LIKE)
    assert result["model1_class"] == "industrial"
    assert result["model2_class"] in ("persistent_source", "industrial_fire")
    assert result["model2_probability"] is not None
    assert 0.0 <= result["model2_probability"] <= 1.0
    assert result["final_class"] == result["model2_class"]


def test_missing_and_non_finite_values_do_not_crash_inference():
    partial = {"frp": 200, "confidence_num": None, "nearest_facility_km": float("inf")}
    result = mi.run_inference(partial)
    assert result["model1_class"] in ("agricultural", "industrial")
    assert isinstance(result["model1_probability"], float)
    assert not math.isnan(result["model1_probability"])


def test_missing_and_non_finite_values_are_filled_with_zero_before_predict():
    partial = {
        "frp": 200, "confidence_num": None, "nearest_facility_km": float("inf"),
        "detections_30d": float("-inf"), "baseline_z_score": "not-a-number",
    }
    vector = mi._build_feature_vector(partial, MODEL1_FEATURES)
    assert not np.isnan(vector).any()
    assert not np.isinf(vector).any()
    idx = {name: i for i, name in enumerate(MODEL1_FEATURES)}
    assert vector[0, idx["confidence_num"]] == 0.0
    assert vector[0, idx["nearest_facility_km"]] == 0.0
    assert vector[0, idx["detections_30d"]] == 0.0
    assert vector[0, idx["baseline_z_score"]] == 0.0
    assert vector[0, idx["frp"]] == 200.0


def test_empty_observation_does_not_crash_inference():
    result = mi.run_inference({})
    assert result["model1_class"] in ("agricultural", "industrial")
    assert isinstance(result["model1_probability"], float)


def test_inference_result_has_expected_structure():
    result = mi.run_inference(INDUSTRIAL_LIKE)
    assert set(result.keys()) == {
        "model1_class", "model1_probability", "model2_class",
        "model2_probability", "final_class", "disclaimer",
    }
    assert isinstance(result["disclaimer"], str) and len(result["disclaimer"]) > 0
