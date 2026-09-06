"""
Production NASA FIRMS ingestion pipeline — Milestone 2.

Flow: download FIRMS CSV -> normalize rows -> retrieve historical + facility
context from MongoDB -> build_features_for_observation() -> model_inference
.run_inference() -> dedup/persist the full observation (raw fields + feature
snapshot + classification), never overwriting raw data with just a prediction.

FIRMS product is fixed to VIIRS_NOAA21_NRT to match the training notebook
(ThermoIntel_ML_ETL_Colab_IndiaWide.ipynb) — do not silently substitute
VIIRS_SNPP_NRT or any other product here.

The FIRMS API key is read from the FIRMS_API_KEY environment variable by the
caller and passed in; this module never logs it and always redacts it from
any error message before it can propagate to logs or API responses.
"""
import csv
import io
import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Optional

from pymongo import UpdateOne

from . import feature_engineering as fe
from . import model_inference

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger("thermointel.firms_pipeline")

FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
FIRMS_SOURCE = "VIIRS_NOAA21_NRT"  # must match the training notebook exactly

HISTORY_RADIUS_KM = 1.0
HISTORY_WINDOW_DAYS = 90
FACILITY_SEARCH_RADII_KM = (10, 50, 200)  # progressive widening for India-wide sparse-facility areas


def _redact(text: str, secret: Optional[str]) -> str:
    if not secret:
        return text
    return text.replace(secret, "***")


def firms_area_url(api_key: str, bbox, day_range: int = 1) -> str:
    west, south, east, north = bbox
    return f"{FIRMS_BASE}/{api_key}/{FIRMS_SOURCE}/{west},{south},{east},{north}/{day_range}"


def fetch_firms_csv(api_key: str, bbox, day_range: int = 1) -> str:
    if requests is None:
        raise RuntimeError("requests dependency unavailable")
    url = firms_area_url(api_key, bbox, day_range)
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except Exception as exc:
        raise RuntimeError(f"FIRMS request failed: {_redact(str(exc), api_key)}") from None
    return response.text


def parse_firms_csv(csv_text: str) -> list:
    """Parses raw FIRMS CSV text into normalized observation dicts (see
    feature_engineering.normalize_firms_row). Invalid rows are skipped, not raised."""
    rows = []
    for raw_row in csv.DictReader(io.StringIO(csv_text)):
        normalized = fe.normalize_firms_row(raw_row)
        if normalized is not None:
            rows.append(normalized)
    return rows


def _degree_padding(lat: float, radius_km: float, safety_factor: float = 1.5):
    lat_pad = (radius_km / 111.0) * safety_factor
    lon_pad = (radius_km / (111.0 * max(0.1, math.cos(math.radians(lat))))) * safety_factor
    return lat_pad, lon_pad


async def ensure_indexes(db):
    """Idempotent — Mongo no-ops if an identical index already exists."""
    await db.anomalies.create_index("observation_id", unique=True, sparse=True)
    await db.anomalies.create_index("acquisition_datetime")
    await db.anomalies.create_index([("geometry", "2dsphere")])
    await db.facilities.create_index("osm_id", unique=True, sparse=True)
    await db.facilities.create_index([("geometry", "2dsphere")])


async def get_historical_candidates(db, lat, lon, before_dt, exclude_observation_id=None, radius_km=HISTORY_RADIUS_KM, window_days=HISTORY_WINDOW_DAYS) -> list:
    """Coarse bbox + time pre-filter via MongoDB; the exact 1km radius is
    enforced afterwards in Python via feature_engineering.haversine_km so the
    final feature values stay numerically faithful to the notebook regardless
    of any bbox/degree approximation used only for candidate retrieval."""
    lat_pad, lon_pad = _degree_padding(lat, radius_km)
    since = before_dt - timedelta(days=window_days)
    query = {
        "latitude": {"$gte": lat - lat_pad, "$lte": lat + lat_pad},
        "longitude": {"$gte": lon - lon_pad, "$lte": lon + lon_pad},
        "acquisition_datetime": {"$gte": since, "$lte": before_dt},
    }
    docs = await db.anomalies.find(query, {"_id": 0}).to_list(2000)
    return [d for d in docs if d.get("observation_id") != exclude_observation_id]


async def get_facility_candidates(db, lat, lon, radii_km=FACILITY_SEARCH_RADII_KM) -> list:
    """Progressively widens the search box until candidates are found. This
    approximates the notebook's unrestricted global nearest-neighbor search
    (BallTree k=1, no radius cap) without scanning the full India-wide
    facilities collection on every request."""
    for max_km in radii_km:
        lat_pad, lon_pad = _degree_padding(lat, max_km, safety_factor=1.2)
        query = {
            "latitude": {"$gte": lat - lat_pad, "$lte": lat + lat_pad},
            "longitude": {"$gte": lon - lon_pad, "$lte": lon + lon_pad},
        }
        docs = await db.facilities.find(query, {"_id": 0}).to_list(1000)
        if docs:
            return docs
    return []


async def resolve_facility_features(db, lat, lon) -> dict:
    total_facilities = await db.facilities.count_documents({})
    if total_facilities == 0:
        # Matches the notebook's add_facility_features() empty-dataset branch exactly.
        return fe.compute_facility_features(lat, lon, [])
    candidates = await get_facility_candidates(db, lat, lon)
    if not candidates:
        # Facilities exist somewhere in India but none within the widened search —
        # report a safe "far away" sentinel rather than falsely claiming 0.0 km.
        return {"nearest_facility_km": 999.0, "facility_within_1km": 0, "facility_within_3km": 0, "facility_within_10km": 0}
    return fe.compute_facility_features(lat, lon, candidates)


async def process_observation(db, raw_observation: dict) -> dict:
    """Runs one normalized FIRMS row through feature engineering + model inference."""
    lat, lon = raw_observation["latitude"], raw_observation["longitude"]
    acq_dt = raw_observation["acquisition_datetime"]

    history = await get_historical_candidates(db, lat, lon, acq_dt, exclude_observation_id=raw_observation["observation_id"])
    facility_features = await resolve_facility_features(db, lat, lon)

    features = fe.build_features_for_observation(raw_observation, history, facility_features)

    try:
        result = model_inference.run_inference(features)
    except RuntimeError:
        logger.warning("Model inference unavailable; storing raw observation without classification")
        result = {"model1_class": None, "model1_probability": None, "model2_class": None,
                  "model2_probability": None, "final_class": None, "disclaimer": model_inference.DISCLAIMER}

    prediction_confidence = result.get("model2_probability")
    if prediction_confidence is None:
        prediction_confidence = result.get("model1_probability")
    if prediction_confidence is None:
        prediction_confidence = 0.5

    return {
        "id": raw_observation["observation_id"],
        "observation_id": raw_observation["observation_id"],
        "latitude": lat,
        "longitude": lon,
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "acquisition_datetime": acq_dt,
        "acq_date": raw_observation["acq_date"],
        "acq_time": raw_observation["acq_time"],
        "frp": raw_observation["frp"],
        "confidence": raw_observation.get("confidence_raw"),
        "confidence_num": raw_observation["confidence_num"],
        "bright_ti4": raw_observation.get("bright_ti4"),
        "bright_ti5": raw_observation.get("bright_ti5"),
        "satellite": raw_observation.get("satellite"),
        "instrument": raw_observation.get("instrument"),
        "daynight": raw_observation.get("daynight"),
        "source": f"NASA FIRMS ({FIRMS_SOURCE})",
        "is_demo": False,
        "features": features,
        "model1_class": result["model1_class"],
        "model1_probability": result["model1_probability"],
        "model2_class": result["model2_class"],
        "model2_probability": result["model2_probability"],
        "final_class": result["final_class"],
        "predicted_class": result["final_class"],
        "prediction_confidence": prediction_confidence,
        "evidence": [
            f"Model 1 (agricultural/industrial): {result['model1_class']} ({result['model1_probability']:.2f})" if result["model1_probability"] is not None else "Model 1 unavailable",
            f"Model 2 (persistent source/industrial fire): {result['model2_class']}" + (f" ({result['model2_probability']:.2f})" if result.get("model2_probability") is not None else ""),
            f"Nearest facility: {features.get('nearest_facility_km')} km",
        ],
        "processing_disclaimer": result["disclaimer"],
        "processed_at": datetime.now(timezone.utc),
    }


async def run_firms_ingestion(db, api_key: str, bbox, region_label: str, days: int = 1) -> dict:
    csv_text = fetch_firms_csv(api_key, bbox, day_range=days)
    normalized_rows = parse_firms_csv(csv_text)

    await ensure_indexes(db)

    operations = []
    processed = 0
    errors = 0
    for row in normalized_rows:
        try:
            doc = await process_observation(db, row)
            doc["region"] = region_label
        except Exception:
            logger.exception("Failed to process a FIRMS observation")
            errors += 1
            continue
        operations.append(UpdateOne({"observation_id": doc["observation_id"]}, {"$setOnInsert": doc}, upsert=True))
        processed += 1

    inserted = 0
    if operations:
        result = await db.anomalies.bulk_write(operations, ordered=False)
        inserted = result.upserted_count

    return {
        "status": "complete",
        "source": FIRMS_SOURCE,
        "region": region_label,
        "rows_downloaded": len(normalized_rows),
        "processed": processed,
        "inserted": inserted,
        "duplicates_skipped": max(0, processed - inserted),
        "errors": errors,
    }
