"""
Focused unit tests for backend/services/firms_pipeline.py — Milestone 2.

Uses mocked requests + a minimal in-memory fake MongoDB collection so no
network, real MongoDB, or FIRMS_API_KEY is required. Confirms:
- VIIRS_NOAA21_NRT product selection (never VIIRS_SNPP_NRT)
- categorical confidence normalization end-to-end through CSV parsing
- duplicate observations are not re-inserted (upsert dedup)
- the FIRMS API key is never leaked into an error message
- the full pipeline connects feature engineering -> model_inference and only
  runs Model 2 for industrial Model-1 predictions
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services import firms_pipeline


# --- minimal in-memory fake Motor-like collection/db (no mongomock dependency) ---

class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, n):
        return list(self._docs[:n])


class FakeBulkResult:
    def __init__(self, upserted_count=0, modified_count=0):
        self.upserted_count = upserted_count
        self.modified_count = modified_count


def _matches(doc, query):
    for key, cond in (query or {}).items():
        val = doc.get(key)
        if isinstance(cond, dict):
            for op, target in cond.items():
                if op == "$gte" and not (val is not None and val >= target):
                    return False
                if op == "$lte" and not (val is not None and val <= target):
                    return False
        else:
            if val != cond:
                return False
    return True


class FakeCollection:
    def __init__(self):
        self._docs = []

    def find(self, query=None, projection=None):
        return FakeCursor([dict(d) for d in self._docs if _matches(d, query or {})])

    async def find_one(self, query):
        for d in self._docs:
            if _matches(d, query):
                return dict(d)
        return None

    async def count_documents(self, query=None):
        return sum(1 for d in self._docs if _matches(d, query or {}))

    async def create_index(self, *a, **k):
        return "index-ok"

    async def bulk_write(self, operations, ordered=False):
        upserted = 0
        for op in operations:
            filt, update, upsert = op._filter, op._doc, op._upsert
            existing = next((d for d in self._docs if _matches(d, filt)), None)
            if existing is None and upsert:
                new_doc = {}
                if "$setOnInsert" in update:
                    new_doc.update(update["$setOnInsert"])
                if "$set" in update:
                    new_doc.update(update["$set"])
                self._docs.append(new_doc)
                upserted += 1
        return FakeBulkResult(upserted_count=upserted)


class FakeDB:
    def __init__(self):
        self.anomalies = FakeCollection()
        self.facilities = FakeCollection()


FIRMS_CSV_SAMPLE = (
    "latitude,longitude,acq_date,acq_time,frp,confidence,bright_ti4,bright_ti5,satellite,instrument,scan,track,daynight\n"
    "22.35,69.89,2026-06-15,1345,150.2,n,330.1,295.4,NOAA-21,VIIRS,0.4,0.4,D\n"
    "22.40,69.95,2026-06-15,1345,20.0,l,300.0,290.0,NOAA-21,VIIRS,0.4,0.4,D\n"
    "not-a-lat,69.95,2026-06-15,1345,20.0,l,300.0,290.0,NOAA-21,VIIRS,0.4,0.4,D\n"
)


# --- product selection ---

def test_firms_source_is_noaa21_not_snpp():
    assert firms_pipeline.FIRMS_SOURCE == "VIIRS_NOAA21_NRT"
    assert firms_pipeline.FIRMS_SOURCE != "VIIRS_SNPP_NRT"


def test_firms_area_url_embeds_noaa21_product():
    url = firms_pipeline.firms_area_url("FAKEKEY123", (68.0, 6.0, 98.0, 38.0), day_range=1)
    assert "VIIRS_NOAA21_NRT" in url
    assert "VIIRS_SNPP_NRT" not in url
    assert "FAKEKEY123" in url  # key belongs in the URL we send to NASA, just never in errors/logs


# --- CSV parsing / confidence normalization / invalid row skipping ---

def test_parse_firms_csv_normalizes_confidence_and_skips_invalid_rows():
    rows = firms_pipeline.parse_firms_csv(FIRMS_CSV_SAMPLE)
    assert len(rows) == 2  # the "not-a-lat" row is dropped
    confidences = {round(r["confidence_num"], 2) for r in rows}
    assert confidences == {0.66, 0.33}  # "n" -> 0.66, "l" -> 0.33


# --- API key redaction ---

def test_fetch_firms_csv_never_leaks_key_on_error():
    secret_key = "SUPER-SECRET-MAP-KEY"

    class FakeResponse:
        def raise_for_status(self):
            raise Exception(f"HTTPError for url: https://firms.modaps.eosdis.nasa.gov/api/area/csv/{secret_key}/VIIRS_NOAA21_NRT/...")

    with patch("services.firms_pipeline.requests") as mock_requests:
        mock_requests.get.return_value = FakeResponse()
        try:
            firms_pipeline.fetch_firms_csv(secret_key, (68.0, 6.0, 98.0, 38.0))
            assert False, "expected RuntimeError"
        except RuntimeError as exc:
            assert secret_key not in str(exc)
            assert "***" in str(exc)


# --- deduplication ---

def test_run_firms_ingestion_dedups_across_repeated_calls():
    db = FakeDB()

    with patch("services.firms_pipeline.fetch_firms_csv", return_value=FIRMS_CSV_SAMPLE):
        first = asyncio.run(
            firms_pipeline.run_firms_ingestion(db, "fake-key", (68.0, 6.0, 98.0, 38.0), "All India")
        )
        second = asyncio.run(
            firms_pipeline.run_firms_ingestion(db, "fake-key", (68.0, 6.0, 98.0, 38.0), "All India")
        )

    assert first["inserted"] == 2
    assert second["inserted"] == 0  # both rows already exist -> upsert matches, no new inserts
    assert asyncio.run(db.anomalies.count_documents({})) == 2


# --- full pipeline: feature engineering -> model_inference wiring ---

def test_process_observation_runs_model2_only_for_industrial():
    db = FakeDB()
    # facilities collection has one entry very close to the observation -> industrial-leaning
    db.facilities._docs.append({"latitude": 22.351, "longitude": 69.891})

    industrial_row = {
        "observation_id": "obs-industrial", "latitude": 22.35, "longitude": 69.89,
        "acq_date": "2026-06-15", "acq_time": "1345", "acquisition_datetime": datetime(2026, 6, 15, 13, 45),
        "frp": 200.0, "confidence_raw": "h", "confidence_num": 1.0,
        "bright_ti4": 340.0, "bright_ti5": 300.0, "satellite": "NOAA-21", "instrument": "VIIRS", "daynight": "D",
    }
    doc = asyncio.run(firms_pipeline.process_observation(db, industrial_row))
    assert doc["model1_class"] in ("agricultural", "industrial")
    if doc["model1_class"] == "industrial":
        assert doc["model2_class"] in ("persistent_source", "industrial_fire")
        assert isinstance(doc["model2_probability"], float)
    else:
        assert doc["model2_class"] == "not_applicable"
        assert doc["model2_probability"] is None
    # raw observation fields must be preserved alongside the classification, not overwritten
    assert doc["frp"] == 200.0
    assert doc["latitude"] == 22.35 and doc["longitude"] == 69.89
    assert doc["observation_id"] == "obs-industrial"
    assert isinstance(doc["prediction_confidence"], float)


def test_process_observation_agricultural_skips_model2():
    db = FakeDB()  # no facilities at all -> facility_within_1km == 0 -> agricultural-leaning
    remote_row = {
        "observation_id": "obs-agri", "latitude": 10.0, "longitude": 78.0,
        "acq_date": "2026-06-15", "acq_time": "1200", "acquisition_datetime": datetime(2026, 6, 15, 12, 0),
        "frp": 12.0, "confidence_raw": "l", "confidence_num": 0.33,
        "bright_ti4": 300.0, "bright_ti5": 290.0, "satellite": "NOAA-21", "instrument": "VIIRS", "daynight": "D",
    }
    doc = asyncio.run(firms_pipeline.process_observation(db, remote_row))
    assert doc["model1_class"] == "agricultural"
    assert doc["model2_class"] == "not_applicable"
    assert doc["model2_probability"] is None
    assert doc["final_class"] == "agricultural"


def test_ensure_indexes_does_not_raise():
    db = FakeDB()
    asyncio.run(firms_pipeline.ensure_indexes(db))
