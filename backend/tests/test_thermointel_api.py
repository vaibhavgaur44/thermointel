import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    from dotenv import dotenv_values
    BASE_URL = dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL")
BASE_URL = BASE_URL.rstrip("/")


def test_core_read_endpoints_and_demo_contract():
    session = requests.Session()
    root = session.get(f"{BASE_URL}/api/", timeout=20)
    assert root.status_code == 200 and root.json()["status"] == "online"
    summary = session.get(f"{BASE_URL}/api/dashboard/summary?region=gujarat", timeout=20)
    assert summary.status_code == 200 and summary.json()["scope"] == "Gujarat"
    assert summary.json()["data_mode"] == "DEMO DATA"
    anomalies = session.get(f"{BASE_URL}/api/anomalies?region=all-india", timeout=20)
    assert anomalies.status_code == 200
    payload = anomalies.json()
    assert payload["items"] and all("_id" not in item for item in payload["items"])
    assert all(item["type"] == "Feature" for item in payload["items"])
    detail = session.get(f"{BASE_URL}/api/anomalies/{payload['items'][0]['id']}", timeout=20)
    assert detail.status_code == 200 and detail.json()["history"] and detail.json()["classification_probabilities"]
    facilities = session.get(f"{BASE_URL}/api/facilities?region=gujarat", timeout=20)
    hotspots = session.get(f"{BASE_URL}/api/hotspots?region=gujarat", timeout=20)
    alerts = session.get(f"{BASE_URL}/api/alerts?region=gujarat", timeout=20)
    assert facilities.status_code == hotspots.status_code == alerts.status_code == 200


def test_status_and_safe_unconfigured_integrations():
    session = requests.Session()
    model = session.get(f"{BASE_URL}/api/model/status", timeout=20)
    ingestion = session.get(f"{BASE_URL}/api/ingestion/status", timeout=20)
    firms = session.post(f"{BASE_URL}/api/ingestion/firms?region=all-india", timeout=20)
    assert model.status_code == 200 and model.json()["metrics_available"] is False
    assert ingestion.status_code == 200 and ingestion.json()["firms"]["status"] == "configuration_required"
    assert ingestion.json()["satellite"]["status"] == "unavailable"
    assert ingestion.json()["land_cover"]["status"] == "unavailable"
    assert firms.status_code == 503 and "not configured" in firms.json()["detail"]