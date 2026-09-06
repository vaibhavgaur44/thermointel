"""
Production feature engineering for ThermoIntel — Milestone 2.

Source of truth: ThermoIntel_ML_ETL_Colab_IndiaWide.ipynb (cells 5, 7A, 8B).
Every formula below is a direct, deliberate reproduction of that notebook's
training-time logic so the production feature vector matches what the
trained XGBoost artifacts (model1/model2) were fit on. Do not "improve" these
formulas without updating the notebook and retraining — that is out of scope
for this milestone.

All acquisition datetimes are treated as naive UTC (FIRMS timestamps are UTC,
and Motor/PyMongo stores/reads datetimes as naive UTC by default). Mixing
naive and timezone-aware datetimes here would raise on comparison, so this
module deliberately never attaches tzinfo to acquisition_datetime.
"""
import math
from datetime import datetime
from typing import Optional

import numpy as np

EARTH_RADIUS_KM = 6371.0088  # matches the notebook's haversine_km() constant exactly

# Notebook cell 5 (normalize_firms): VIIRS confidence is categorical (l/n/h) for
# NRT products. Numeric confidence (when present) is used as-is, unscaled.
CONFIDENCE_CATEGORY_MAP = {"l": 0.33, "n": 0.66, "h": 1.0}

REQUIRED_FIRMS_FIELDS = ["latitude", "longitude", "frp", "acq_date", "acq_time"]


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Exact port of the notebook's haversine_km() (cell 13)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def confidence_to_numeric(confidence_raw) -> float:
    """Exact port of normalize_firms()'s confidence_num logic (cell 9):
    numeric value used as-is if parseable, else categorical l/n/h map, else 0.0."""
    if confidence_raw is None:
        return 0.0
    try:
        return float(confidence_raw)
    except (TypeError, ValueError):
        pass
    key = str(confidence_raw).strip().lower()
    return CONFIDENCE_CATEGORY_MAP.get(key, 0.0)


def _parse_acq_clock(acq_time_raw) -> str:
    """Exact port of normalize_firms()'s parse_acq_time() (cell 9)."""
    try:
        s = str(int(float(acq_time_raw))).zfill(4)
        return s[:2] + ":" + s[2:]
    except Exception:
        return "00:00"


def parse_acq_datetime(acq_date: str, acq_time_raw) -> Optional[datetime]:
    """Combines acq_date + acq_time into a naive UTC datetime, or None if unparseable."""
    clock = _parse_acq_clock(acq_time_raw)
    try:
        return datetime.strptime(f"{acq_date} {clock}", "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return None


def compute_observation_id(lat: float, lon: float, acq_datetime: datetime, satellite: str = "unknown") -> str:
    """Deterministic per-detection identity for deduplication.

    Uses the same identity fields as the notebook's observation_id (cell 9):
    lat rounded to 5dp, lon rounded to 5dp, acquisition datetime, satellite.
    The hash algorithm itself (sha256) intentionally differs from the
    notebook's pandas.util.hash_pandas_object — bit-identical hashing isn't
    required, only a stable, collision-resistant identity per unique row.
    """
    import hashlib
    key = f"{round(lat, 5)}_{round(lon, 5)}_{acq_datetime.isoformat()}_{satellite or 'unknown'}"
    return hashlib.sha256(key.encode()).hexdigest()


def normalize_firms_row(row: dict) -> Optional[dict]:
    """Exact port of normalize_firms() applied to a single CSV row (cell 9).
    Returns None for rows that fail the notebook's required-field/validity checks."""
    if any(row.get(f) in (None, "") for f in REQUIRED_FIRMS_FIELDS):
        return None
    try:
        lat, lon, frp = float(row["latitude"]), float(row["longitude"]), float(row["frp"])
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180) or frp < 0:
        return None

    acq_dt = parse_acq_datetime(row["acq_date"], row["acq_time"])
    if acq_dt is None:
        return None

    def _optional_num(key):
        try:
            return float(row[key])
        except (TypeError, ValueError, KeyError):
            return None

    satellite = row.get("satellite") or "unknown"
    confidence_raw = row.get("confidence")

    return {
        "observation_id": compute_observation_id(lat, lon, acq_dt, satellite),
        "latitude": lat,
        "longitude": lon,
        "frp": frp,
        "acq_date": row["acq_date"],
        "acq_time": row["acq_time"],
        "acquisition_datetime": acq_dt,
        "confidence_raw": confidence_raw,
        "confidence_num": confidence_to_numeric(confidence_raw),
        "bright_ti4": _optional_num("bright_ti4"),
        "bright_ti5": _optional_num("bright_ti5"),
        "scan": _optional_num("scan"),
        "track": _optional_num("track"),
        "satellite": satellite,
        "instrument": row.get("instrument"),
        "daynight": row.get("daynight"),
    }


def compute_historical_features(current_lat, current_lon, current_time, current_observation_id, candidates: list, radius_km: float = 1.0) -> dict:
    """Exact port of add_temporal_features()'s per-observation loop (cell 13).

    `candidates` is a plain list of dicts each with latitude/longitude/frp/
    acquisition_datetime/observation_id. Self-exclusion uses observation_id
    (equivalent to the notebook's `if j == i: continue` by row identity).
    Future observations (acquisition_datetime > current_time) are excluded —
    the notebook keeps `t <= current_time`, i.e. equal timestamps from a
    DIFFERENT observation still count as historical, which we reproduce here.
    """
    prior = []
    for c in candidates:
        if c.get("observation_id") == current_observation_id:
            continue
        t = c["acquisition_datetime"]
        if t > current_time:
            continue
        distance = haversine_km(current_lat, current_lon, c["latitude"], c["longitude"])
        if distance > radius_km:
            continue
        days = (current_time - t).total_seconds() / 86400
        if days > 90:
            continue
        prior.append({"days": days, "frp": c["frp"], "date": t.date()})

    def frp_within(max_days):
        return [p["frp"] for p in prior if p["days"] <= max_days]

    v1, v7, v30, v90 = frp_within(1), frp_within(7), frp_within(30), frp_within(90)

    return {
        "detections_1d": len(v1),
        "detections_7d": len(v7),
        "detections_30d": len(v30),
        "detections_90d": len(v90),
        "historical_mean_frp_30d": float(np.mean(v30)) if v30 else 0.0,
        "historical_max_frp_30d": float(np.max(v30)) if v30 else 0.0,
        "historical_std_frp_30d": float(np.std(v30)) if v30 else 0.0,
        "days_active_30d": len({p["date"] for p in prior if p["days"] <= 30}),
        "days_active_90d": len({p["date"] for p in prior if p["days"] <= 90}),
    }


def compute_baseline_z_score(frp: float, historical_mean_frp_30d: float, historical_std_frp_30d: float) -> float:
    """Exact port of add_temporal_features()'s baseline_z_score (cell 13):
    (frp - mean_30d) / std_30d, with std==0 replaced by 1 to avoid division by
    zero. On cold start (no history), mean=0.0 and std=0.0->1, so z == frp."""
    denominator = historical_std_frp_30d if historical_std_frp_30d != 0 else 1.0
    return (frp - historical_mean_frp_30d) / denominator


def compute_facility_features(lat, lon, facilities: list) -> dict:
    """Exact port of add_facility_features() (cell 18) for the case where the
    caller has already resolved the relevant facility candidates. If the
    dataset is genuinely empty, the notebook returns all-zero features."""
    if not facilities:
        return {"nearest_facility_km": 0.0, "facility_within_1km": 0, "facility_within_3km": 0, "facility_within_10km": 0}
    nearest_km = min(haversine_km(lat, lon, f["latitude"], f["longitude"]) for f in facilities)
    return {
        "nearest_facility_km": float(nearest_km),
        "facility_within_1km": int(nearest_km <= 1),
        "facility_within_3km": int(nearest_km <= 3),
        "facility_within_10km": int(nearest_km <= 10),
    }


def build_features_for_observation(observation: dict, historical_candidates: list, facility_features: dict) -> dict:
    """Assembles the exact feature dict consumed by model_inference.run_inference().
    `facility_features` must already contain the 4 facility-proximity keys
    (see compute_facility_features) — resolving those against MongoDB (with
    India-wide search-radius widening) is the ingestion pipeline's job, kept
    separate from this pure/testable feature-assembly function."""
    historical = compute_historical_features(
        observation["latitude"], observation["longitude"],
        observation["acquisition_datetime"], observation.get("observation_id"),
        historical_candidates,
    )
    baseline_z_score = compute_baseline_z_score(
        observation["frp"], historical["historical_mean_frp_30d"], historical["historical_std_frp_30d"],
    )
    return {
        "frp": observation["frp"],
        "confidence_num": observation.get("confidence_num", 0.0),
        "bright_ti4": observation.get("bright_ti4"),
        "bright_ti5": observation.get("bright_ti5"),
        **facility_features,
        **historical,
        "baseline_z_score": baseline_z_score,
    }
