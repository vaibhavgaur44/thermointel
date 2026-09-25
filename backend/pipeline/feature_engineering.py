"""Phase 4-compatible feature engineering for Phase 5 inference."""

import math
from datetime import datetime, timezone
from typing import Any

from models.enums import PipelineStage
from models.event import Event
from pipeline.base import PipelineStageNotImplemented

STAGE = PipelineStage.FEATURE_ENGINEERING

# Phase 3 cleaned-CSV representation of the satellite columns
# (firms_clean_a4.py): ``satellite`` holds the FIRMS short code (N20, N21,
# ...) and ``satellite_std`` the normalized long name (NOAA20, NOAA21, ...).
# The frozen Phase 4 preprocessing one-hot encodes exactly those vocabularies
# (satellite: ['N20'], satellite_std: ['NOAA20']). Production stores the
# Phase 1 enum + the raw FIRMS code; these adapters reproduce the trained
# representation without touching the schema.
_SAT_LONG_MAP = {
    "N20": "NOAA20",
    "N21": "NOAA21",
    "N": "SNPP",
    "1": "Terra",
    "A": "Aqua",
}
_ENUM_TO_FIRMS_SHORT = {
    "VIIRS_NOAA20": "N20",
    "VIIRS_NOAA21": "N21",
    "VIIRS_SNPP": "N",
    "MODIS_TERRA": "1",
    "MODIS_AQUA": "A",
}

RAW_FEATURES = [
    "latitude",
    "longitude",
    "satellite",
    "satellite_std",
    "instrument",
    "confidence",
    "conf_level",
    "version",
    "bright_ti4",
    "bright_ti5",
    "frp",
    "scan",
    "track",
    "daynight",
    "state_ut",
    "State_LGD",
    "lulc_2021_code",
    "lulc_2021_class",
    "year",
    "month",
    "dayofyear",
    "hour_utc",
    "weekday",
    "daynight_bin",
    "month_sin",
    "month_cos",
    "doy_sin",
    "doy_cos",
    "hour_sin",
    "hour_cos",
    "frp_log1p",
    "brightness_diff",
    "confidence_num",
    "nearest_facility_km",
    "nearest_facility_type",
]


def _value(data: dict[str, Any], key: str, default=None):
    value = data.get(key)
    return default if value is None else value


def _confidence_num(value) -> float | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().lower()

    mapping = {
    "l": 0.0,
    "low": 0.0,
    "n": 1.0,
    "nominal": 1.0,
    "nominal confidence": 1.0,
    "h": 2.0,
    "high": 2.0,
}

    if text in mapping:
        return mapping[text]

    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _conf_level(value) -> int | None:
    """Phase 4 training representation of conf_level.

    The frozen preprocessing artifact one-hot encodes conf_level over the
    categories [1, 2, 3] - the numeric codes produced by the established
    Phase 3 cleaning (firms_clean_a4.py CONFIDENCE_MAP:
    l/low->1, n/nominal->2, h/high->3). Out-of-vocabulary input maps to 0,
    exactly as Phase 3 does. Nothing is fabricated.
    """
    if value is None:
        return None

    text = str(value).strip().lower()

    mapping = {"l": 1, "low": 1, "n": 2, "nominal": 2, "h": 3, "high": 3}
    return mapping.get(text, 0)


def _cyclic(value: float, period: float) -> tuple[float, float]:
    angle = 2.0 * math.pi * value / period
    return math.sin(angle), math.cos(angle)


def build_features(
    event: Event,
    detection: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build exactly the 35 raw features used by Phase 4.

    No classification logic is performed here.
    Missing contextual values remain None rather than being fabricated.
    """

    context = context or {}

    latitude = event.centroid.latitude
    longitude = event.centroid.longitude

    acquired_at = detection.get("acquired_at")

    if isinstance(acquired_at, str):
        acquired_at = datetime.fromisoformat(
            acquired_at.replace("Z", "+00:00")
        )

    if acquired_at is None:
        acquired_at = event.last_detected

    if acquired_at.tzinfo is None:
        acquired_at = acquired_at.replace(tzinfo=timezone.utc)

    year = acquired_at.year
    month = acquired_at.month
    dayofyear = acquired_at.timetuple().tm_yday
    hour_utc = acquired_at.hour
    weekday = acquired_at.weekday()

    month_sin, month_cos = _cyclic(month, 12.0)
    doy_sin, doy_cos = _cyclic(dayofyear, 365.25)
    hour_sin, hour_cos = _cyclic(hour_utc, 24.0)

    frp = detection.get("frp")
    ti4 = detection.get("brightness_ti4")
    ti5 = detection.get("brightness_ti5")

    daynight = detection.get("day_night")
    if hasattr(daynight, "value"):
        daynight = daynight.value

    satellite = detection.get("satellite")
    if hasattr(satellite, "value"):
        satellite = satellite.value

    # Phase 3 trained representation (see adapter maps above).
    satellite_raw = detection.get("satellite_std")
    satellite_short = (
        satellite_raw
        or _ENUM_TO_FIRMS_SHORT.get(satellite, satellite)
    )
    satellite_long = _SAT_LONG_MAP.get(
        str(satellite_short).strip().upper(), satellite_short
    )

    confidence = detection.get("firms_confidence")

    confidence_numeric = None
    if confidence is not None:
        try:
            confidence_numeric = float(confidence)
        except (TypeError, ValueError):
            confidence_numeric = None

    conf_level = _conf_level(confidence)

    features = {
        "latitude": latitude,
        "longitude": longitude,
        "satellite": satellite_short,
        "satellite_std": satellite_long,
        "instrument": detection.get("instrument"),
        "confidence": confidence_numeric,
        "conf_level": conf_level,
        "version": detection.get("version"),
        "bright_ti4": ti4,
        "bright_ti5": ti5,
        "frp": frp,
        "scan": detection.get("scan"),
        "track": detection.get("track"),
        "daynight": daynight,
        "state_ut": detection.get("state") or event.state,
        "State_LGD": detection.get("state_lgd"),
        "lulc_2021_code": detection.get("lulc_2021_code"),
        "lulc_2021_class": detection.get("lulc_2021_class"),
        "year": year,
        "month": month,
        "dayofyear": dayofyear,
        "hour_utc": hour_utc,
        "weekday": weekday,
        "daynight_bin": daynight,
        "month_sin": month_sin,
        "month_cos": month_cos,
        "doy_sin": doy_sin,
        "doy_cos": doy_cos,
        "hour_sin": hour_sin,
        "hour_cos": hour_cos,
        "frp_log1p": math.log1p(max(float(frp), 0.0)) if frp is not None else None,
        "brightness_diff": (
            float(ti4) - float(ti5)
            if ti4 is not None and ti5 is not None
            else None
        ),
        "confidence_num": _confidence_num(confidence),
        "nearest_facility_km": context.get("nearest_facility_km"),
        "nearest_facility_type": context.get("nearest_facility_type"),
    }

    return {name: features.get(name) for name in RAW_FEATURES}


async def build_feature_vector(
    event: Event,
    features: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compatibility wrapper for the pipeline interface."""

    if features is None:
        raise ValueError(
            "Phase 4 feature construction requires an enriched detection "
            "feature dictionary; no values are fabricated."
        )

    return build_features(event, features, features)