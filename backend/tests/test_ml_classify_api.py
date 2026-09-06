"""
Milestone 1 API tests for ML inference endpoints (/api/ml/classify, /api/ml/schema)
and /api/model/status trained_models block. Also covers regression on unrelated endpoints.
"""
import os
import math
import requests
from dotenv import dotenv_values

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL")
BASE_URL = BASE_URL.rstrip("/")

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

INDUSTRIAL_LIKE = {
    "frp": 250, "confidence_num": 95, "bright_ti4": 340, "bright_ti5": 300,
    "nearest_facility_km": 0.5, "facility_within_1km": 1, "facility_within_3km": 1,
    "facility_within_10km": 1, "detections_1d": 20, "detections_7d": 60,
    "detections_30d": 90, "detections_90d": 200, "historical_mean_frp_30d": 180,
    "historical_max_frp_30d": 260, "historical_std_frp_30d": 30, "days_active_30d": 25,
    "days_active_90d": 60, "baseline_z_score": 3.5,
}

AGRICULTURAL_LIKE = {
    "frp": 15, "confidence_num": 60, "bright_ti4": 300, "bright_ti5": 290,
    "nearest_facility_km": 45.0, "facility_within_1km": 0, "facility_within_3km": 0,
    "facility_within_10km": 0, "detections_1d": 1, "detections_7d": 1,
    "detections_30d": 1, "detections_90d": 1, "historical_mean_frp_30d": 10,
    "historical_max_frp_30d": 15, "historical_std_frp_30d": 3, "days_active_30d": 1,
    "days_active_90d": 1, "baseline_z_score": 0.2,
}


def _post_classify(payload):
    return requests.post(f"{BASE_URL}/api/ml/classify", json=payload, timeout=30)


def test_schema_endpoint_returns_exact_feature_order():
    r = requests.get(f"{BASE_URL}/api/ml/schema", timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert data["model1_features"] == MODEL1_FEATURES
    assert data["model2_features"] == MODEL2_FEATURES
    assert len(data["model1_features"]) == 18
    assert len(data["model2_features"]) == 15


def test_classify_industrial_like_runs_both_models():
    r = _post_classify({"features": INDUSTRIAL_LIKE})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["model1_class"] == "industrial"
    assert isinstance(d["model1_probability"], float) and 0.0 <= d["model1_probability"] <= 1.0
    assert d["model2_class"] in ("persistent_source", "industrial_fire")
    assert isinstance(d["model2_probability"], float) and 0.0 <= d["model2_probability"] <= 1.0
    assert d["final_class"] == d["model2_class"]
    assert isinstance(d.get("disclaimer"), str) and d["disclaimer"]


def test_classify_agricultural_like_skips_model2():
    r = _post_classify({"features": AGRICULTURAL_LIKE})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["model1_class"] == "agricultural"
    assert d["model2_class"] == "not_applicable"
    assert d["model2_probability"] is None
    assert d["final_class"] == "agricultural"


def test_classify_missing_null_and_nonnumeric_values_do_not_crash():
    payload = {"features": {
        "frp": 200, "confidence_num": None, "nearest_facility_km": "inf",
        "detections_30d": "not-a-number", "baseline_z_score": None,
    }}
    r = _post_classify(payload)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["model1_class"] in ("agricultural", "industrial")
    assert isinstance(d["model1_probability"], float)
    assert not math.isnan(d["model1_probability"])


def test_classify_empty_features_dict_does_not_crash():
    r = _post_classify({"features": {}})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["model1_class"] in ("agricultural", "industrial")
    assert isinstance(d["model1_probability"], float)
    assert not math.isnan(d["model1_probability"])


def test_model_status_includes_trained_models_block():
    r = requests.get(f"{BASE_URL}/api/model/status", timeout=20)
    assert r.status_code == 200
    d = r.json()
    assert d["metrics_available"] is False
    tm = d.get("trained_models")
    assert tm is not None
    assert tm.get("model1_agricultural_vs_industrial") is True
    assert tm.get("model2_persistent_vs_industrial_fire") is True


# --- Regression on unrelated endpoints ---

def test_regression_core_endpoints_still_work():
    s = requests.Session()
    assert s.get(f"{BASE_URL}/api/", timeout=20).status_code == 200
    assert s.get(f"{BASE_URL}/api/dashboard/summary?region=gujarat", timeout=20).status_code == 200
    anomalies = s.get(f"{BASE_URL}/api/anomalies", timeout=20)
    assert anomalies.status_code == 200
    items = anomalies.json().get("items", [])
    if items:
        assert s.get(f"{BASE_URL}/api/anomalies/{items[0]['id']}", timeout=20).status_code == 200
    assert s.get(f"{BASE_URL}/api/facilities", timeout=20).status_code == 200
    assert s.get(f"{BASE_URL}/api/hotspots", timeout=20).status_code == 200
    assert s.get(f"{BASE_URL}/api/alerts", timeout=20).status_code == 200
    assert s.get(f"{BASE_URL}/api/ingestion/status", timeout=20).status_code == 200
    firms = s.post(f"{BASE_URL}/api/ingestion/firms", timeout=20)
    assert firms.status_code == 503
