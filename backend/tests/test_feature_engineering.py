"""
Focused unit tests for backend/services/feature_engineering.py — Milestone 2.

Every assertion here is checked against the exact formulas in
ThermoIntel_ML_ETL_Colab_IndiaWide.ipynb (cells 5, 7A, 8B), not an
approximation. These are deterministic, synthetic-fixture tests; they do not
require network, MongoDB, or a FIRMS API key, and they do not claim to prove
real-world model accuracy.
"""
import math
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services import feature_engineering as fe


# --- confidence_num (notebook cell 9) ---

def test_confidence_numeric_value_passthrough():
    assert fe.confidence_to_numeric("42") == 42.0
    assert fe.confidence_to_numeric(87) == 87.0


def test_confidence_categorical_mapping_matches_notebook():
    assert fe.confidence_to_numeric("l") == 0.33
    assert fe.confidence_to_numeric("n") == 0.66
    assert fe.confidence_to_numeric("h") == 1.0
    assert fe.confidence_to_numeric("H") == 1.0  # case-insensitive, per notebook's .str.lower()


def test_confidence_missing_or_unknown_defaults_to_zero():
    assert fe.confidence_to_numeric(None) == 0.0
    assert fe.confidence_to_numeric("") == 0.0
    assert fe.confidence_to_numeric("unexpected") == 0.0


# --- acq_time parsing (notebook cell 9) ---

def test_acq_datetime_parses_hhmm_clock():
    dt = fe.parse_acq_datetime("2026-06-15", "1345")
    assert dt == datetime(2026, 6, 15, 13, 45)


def test_acq_datetime_zero_pads_short_time():
    dt = fe.parse_acq_datetime("2026-06-15", "45")  # notebook zfills to "0045" -> 00:45
    assert dt == datetime(2026, 6, 15, 0, 45)


def test_acq_datetime_invalid_returns_none():
    assert fe.parse_acq_datetime("not-a-date", "1200") is None


# --- normalize_firms_row ---

def _base_row(**overrides):
    row = {
        "latitude": "22.35", "longitude": "69.89", "frp": "120.5",
        "acq_date": "2026-06-15", "acq_time": "1345", "confidence": "n",
        "bright_ti4": "330.2", "bright_ti5": "295.1", "satellite": "NOAA-21",
        "instrument": "VIIRS", "scan": "0.4", "track": "0.4", "daynight": "D",
    }
    row.update(overrides)
    return row


def test_normalize_firms_row_happy_path():
    row = fe.normalize_firms_row(_base_row())
    assert row is not None
    assert row["latitude"] == 22.35 and row["longitude"] == 69.89
    assert row["frp"] == 120.5
    assert row["confidence_num"] == 0.66  # "n" -> 0.66
    assert row["bright_ti4"] == 330.2 and row["bright_ti5"] == 295.1
    assert row["observation_id"]


def test_normalize_firms_row_missing_required_field_returns_none():
    row = _base_row()
    del row["frp"]
    assert fe.normalize_firms_row(row) is None


def test_normalize_firms_row_invalid_coordinates_returns_none():
    assert fe.normalize_firms_row(_base_row(latitude="999")) is None


def test_normalize_firms_row_negative_frp_returns_none():
    assert fe.normalize_firms_row(_base_row(frp="-5")) is None


def test_observation_id_is_deterministic():
    row1 = fe.normalize_firms_row(_base_row())
    row2 = fe.normalize_firms_row(_base_row())
    assert row1["observation_id"] == row2["observation_id"]


def test_observation_id_differs_for_different_location():
    row1 = fe.normalize_firms_row(_base_row())
    row2 = fe.normalize_firms_row(_base_row(latitude="22.99"))
    assert row1["observation_id"] != row2["observation_id"]


# --- historical temporal features (notebook cell 13) ---

def _candidate(obs_id, lat, lon, dt, frp):
    return {"observation_id": obs_id, "latitude": lat, "longitude": lon, "acquisition_datetime": dt, "frp": frp}


def test_detections_counts_use_correct_time_windows():
    current_time = datetime(2026, 7, 1, 0, 0)
    candidates = [
        _candidate("c1", 22.35, 69.89, datetime(2026, 6, 30, 12, 0), 50),   # 0.5 day ago
        _candidate("c2", 22.35, 69.89, datetime(2026, 6, 26, 0, 0), 60),    # 5 days ago
        _candidate("c3", 22.35, 69.89, datetime(2026, 6, 10, 0, 0), 70),    # 21 days ago
        _candidate("c4", 22.35, 69.89, datetime(2026, 5, 15, 0, 0), 80),    # 47 days ago
        _candidate("c5", 22.35, 69.89, datetime(2026, 1, 1, 0, 0), 999),   # >90 days ago, excluded
    ]
    result = fe.compute_historical_features(22.35, 69.89, current_time, "current", candidates)
    assert result["detections_1d"] == 1
    assert result["detections_7d"] == 2
    assert result["detections_30d"] == 3
    assert result["detections_90d"] == 4


def test_self_exclusion_by_observation_id():
    current_time = datetime(2026, 7, 1, 0, 0)
    candidates = [_candidate("current", 22.35, 69.89, current_time, 999)]
    result = fe.compute_historical_features(22.35, 69.89, current_time, "current", candidates)
    assert result["detections_1d"] == 0


def test_future_observations_are_excluded():
    current_time = datetime(2026, 7, 1, 0, 0)
    candidates = [_candidate("future", 22.35, 69.89, datetime(2026, 7, 2, 0, 0), 999)]
    result = fe.compute_historical_features(22.35, 69.89, current_time, "current", candidates)
    assert result["detections_1d"] == 0


def test_equal_timestamp_different_observation_still_counts():
    """Reproduces the notebook's `t <= current_time` (inclusive) behavior:
    a distinct observation at the exact same timestamp counts as historical."""
    current_time = datetime(2026, 7, 1, 0, 0)
    candidates = [_candidate("other-same-time", 22.35, 69.89, current_time, 55)]
    result = fe.compute_historical_features(22.35, 69.89, current_time, "current", candidates)
    assert result["detections_1d"] == 1


def test_spatial_radius_excludes_far_detections():
    current_time = datetime(2026, 7, 1, 0, 0)
    candidates = [_candidate("far", 22.45, 69.89, datetime(2026, 6, 30, 0, 0), 999)]  # ~11km away
    result = fe.compute_historical_features(22.35, 69.89, current_time, "current", candidates)
    assert result["detections_1d"] == 0


def test_days_active_counts_distinct_calendar_dates():
    current_time = datetime(2026, 7, 1, 0, 0)
    candidates = [
        _candidate("c1", 22.35, 69.89, datetime(2026, 6, 30, 1, 0), 10),
        _candidate("c2", 22.35, 69.89, datetime(2026, 6, 30, 20, 0), 20),  # same date as c1
        _candidate("c3", 22.35, 69.89, datetime(2026, 6, 20, 0, 0), 30),
    ]
    result = fe.compute_historical_features(22.35, 69.89, current_time, "current", candidates)
    assert result["days_active_30d"] == 2
    assert result["days_active_90d"] == 2


def test_historical_mean_max_std_over_30d_window():
    current_time = datetime(2026, 7, 1, 0, 0)
    candidates = [
        _candidate("c1", 22.35, 69.89, datetime(2026, 6, 20, 0, 0), 100),
        _candidate("c2", 22.35, 69.89, datetime(2026, 6, 25, 0, 0), 200),
    ]
    result = fe.compute_historical_features(22.35, 69.89, current_time, "current", candidates)
    assert result["historical_mean_frp_30d"] == 150.0
    assert result["historical_max_frp_30d"] == 200.0
    assert round(result["historical_std_frp_30d"], 4) == 50.0


def test_no_history_returns_zeros():
    current_time = datetime(2026, 7, 1, 0, 0)
    result = fe.compute_historical_features(22.35, 69.89, current_time, "current", [])
    assert result["detections_30d"] == 0
    assert result["historical_mean_frp_30d"] == 0.0
    assert result["historical_std_frp_30d"] == 0.0


# --- baseline_z_score (notebook cell 13) ---

def test_baseline_z_score_normal_case():
    z = fe.compute_baseline_z_score(frp=250.0, historical_mean_frp_30d=150.0, historical_std_frp_30d=50.0)
    assert z == 2.0


def test_baseline_z_score_zero_std_falls_back_to_one():
    z = fe.compute_baseline_z_score(frp=10.0, historical_mean_frp_30d=5.0, historical_std_frp_30d=0.0)
    assert z == 5.0  # (10 - 5) / 1


def test_baseline_z_score_cold_start_equals_frp():
    """No history -> mean=0.0, std=0.0->1 -> z == frp exactly."""
    z = fe.compute_baseline_z_score(frp=42.0, historical_mean_frp_30d=0.0, historical_std_frp_30d=0.0)
    assert z == 42.0


# --- facility proximity (notebook cell 18) ---

def test_facility_features_nearest_and_thresholds():
    facilities = [{"latitude": 22.355, "longitude": 69.89}, {"latitude": 25.0, "longitude": 80.0}]
    result = fe.compute_facility_features(22.35, 69.89, facilities)
    assert result["nearest_facility_km"] < 1.0
    assert result["facility_within_1km"] == 1
    assert result["facility_within_3km"] == 1
    assert result["facility_within_10km"] == 1


def test_facility_features_empty_dataset_returns_all_zero():
    result = fe.compute_facility_features(22.35, 69.89, [])
    assert result == {"nearest_facility_km": 0.0, "facility_within_1km": 0, "facility_within_3km": 0, "facility_within_10km": 0}


def test_facility_within_thresholds_are_inclusive_boundaries():
    # place a facility so nearest distance is > 3km and <= 10km
    facilities = [{"latitude": 22.35 + (5 / 111.0), "longitude": 69.89}]
    result = fe.compute_facility_features(22.35, 69.89, facilities)
    assert result["facility_within_1km"] == 0
    assert result["facility_within_3km"] == 0
    assert result["facility_within_10km"] == 1


# --- build_features_for_observation (full assembly) ---

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


def _observation():
    return {
        "observation_id": "obs-1", "latitude": 22.35, "longitude": 69.89,
        "acquisition_datetime": datetime(2026, 7, 1, 0, 0), "frp": 150.0,
        "confidence_num": 0.66, "bright_ti4": 330.0, "bright_ti5": 295.0,
    }


def test_build_features_covers_both_model_feature_sets():
    facility_features = fe.compute_facility_features(22.35, 69.89, [{"latitude": 22.36, "longitude": 69.89}])
    features = fe.build_features_for_observation(_observation(), [], facility_features)
    assert set(MODEL1_FEATURES).issubset(features.keys())
    assert set(MODEL2_FEATURES).issubset(features.keys())


def test_build_features_missing_bright_ti_does_not_crash():
    obs = _observation()
    obs["bright_ti4"] = None
    obs["bright_ti5"] = None
    facility_features = fe.compute_facility_features(22.35, 69.89, [])
    features = fe.build_features_for_observation(obs, [], facility_features)
    assert features["bright_ti4"] is None and features["bright_ti5"] is None
    # downstream model_inference already fills None/NaN with 0.0 before predict_proba
