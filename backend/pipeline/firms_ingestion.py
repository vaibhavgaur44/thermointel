"""NASA FIRMS production ingestion."""

import logging
import os
import csv
import io
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

import asyncio

from core.config import settings
from core.database import Collections, get_db
from models.detection import ThermalDetection
from models.enums import DayNight, PipelineStage, Satellite
from pipeline import live_enrichment

STAGE = PipelineStage.FIRMS_INGESTION

logger = logging.getLogger(__name__)

# India bounding box: west, south, east, north
INDIA_BBOX = "68.0,6.0,97.5,37.5"

FIRMS_SOURCES = {
    "VIIRS_NOAA20_NRT": Satellite.VIIRS_NOAA20,
    "VIIRS_NOAA21_NRT": Satellite.VIIRS_NOAA21,
    "VIIRS_SNPP_NRT": Satellite.VIIRS_SNPP,
    "MODIS_NRT": Satellite.MODIS_TERRA,
}

# Production ingestion sources (P0 task): both NRT VIIRS satellites are
# ingested through this SAME pipeline. Overlapping/repeated detections
# between the two are acceptable; observation_id is satellite-scoped, so no
# cross-satellite deduplication is performed.
INGESTION_SOURCES = ("VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT")
STANDARDIZED_DIR = r"D:\SIH2026\SIH_DATASETS\data\standardized"

STATES_CSV = os.path.join(
        STANDARDIZED_DIR,
        "firms_india_with_states.csv",
)

LULC_CSV = os.path.join(
        STANDARDIZED_DIR,
        "firms_india_lulc.csv",
)


def is_configured() -> bool:
    return settings.firms_configured


def _observation_id(row: dict[str, Any]) -> str:
    raw = "|".join(
        str(row.get(key, ""))
        for key in (
            "satellite",
            "instrument",
            "acq_date",
            "acq_time",
            "latitude",
            "longitude",
        )
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _parse_confidence(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value).strip()


def _parse_datetime(row: dict[str, Any]) -> datetime:
    date = str(row["acq_date"])
    time = str(row.get("acq_time", "0")).zfill(4)

    return datetime.strptime(
        f"{date} {time[:2]}:{time[2:4]}",
        "%Y-%m-%d %H:%M",
    ).replace(tzinfo=timezone.utc)


def _satellite(value: str | None) -> Satellite:
    if not value:
        return Satellite.OTHER

    value = value.strip().upper()

    # FIRMS NRT CSV short codes (the actual values in production rows:
    # "N20", "N21", ...). Phase 3 firms_clean_a4.py documents the same map.
    short = {
        "N20": Satellite.VIIRS_NOAA20,
        "N21": Satellite.VIIRS_NOAA21,
        "N": Satellite.VIIRS_SNPP,
        "1": Satellite.MODIS_TERRA,
        "A": Satellite.MODIS_AQUA,
    }
    if value in short:
        return short[value]

    if "NOAA-20" in value or "NOAA20" in value:
        return Satellite.VIIRS_NOAA20
    if "NOAA-21" in value or "NOAA21" in value:
        return Satellite.VIIRS_NOAA21
    if "SUOMI" in value or "SNPP" in value:
        return Satellite.VIIRS_SNPP
    if "TERRA" in value:
        return Satellite.MODIS_TERRA
    if "AQUA" in value:
        return Satellite.MODIS_AQUA

    return Satellite.OTHER


def _daynight(value: str | None) -> DayNight | None:
    if not value:
        return None

    value = value.upper()

    if value.startswith("D"):
        return DayNight.DAY
    if value.startswith("N"):
        return DayNight.NIGHT

    return None


def _float(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _load_enrichment() -> tuple[dict[str, dict], dict[str, dict]]:
    states = {}
    lulc = {}

    with open(STATES_CSV, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            detection_id = row.get("detection_id")
            if detection_id:
                states[detection_id] = row

    with open(LULC_CSV, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            detection_id = row.get("detection_id")
            if detection_id:
                lulc[detection_id] = row

    return states, lulc

def _build_detection(
    row: dict[str, Any],
    run_id: str,
) -> ThermalDetection:
    satellite_raw = row.get("satellite")

    return ThermalDetection(
        observation_id=_observation_id(row),
        location={
        "type": "Point",
        "coordinates": [
            float(row["longitude"]),
            float(row["latitude"]),
            ],
        },  
        acquired_at=_parse_datetime(row),
        satellite=_satellite(satellite_raw),
        satellite_std=satellite_raw,
        instrument=row.get("instrument"),
        version=row.get("version"),
        day_night=_daynight(row.get("daynight")),
        frp=_float(row.get("frp")),
        brightness_ti4=_float(
            row.get("bright_ti4") or row.get("brightness_ti4")
        ),
        brightness_ti5=_float(
            row.get("bright_ti5") or row.get("brightness_ti5")
        ),
        firms_confidence=_parse_confidence(
            row.get("confidence")
        ),
        scan=_float(row.get("scan")),
        track=_float(row.get("track")),
        state=row.get("state") or row.get("state_ut"),
        state_lgd=None,
        lulc_2021_code=None,
        lulc_2021_class=None,
        ingestion_run_id=run_id,
        data_origin="production",
    )


async def fetch_detections(window_hours: int) -> list[ThermalDetection]:
    if not is_configured():
        raise RuntimeError("NASA FIRMS is not configured.")

    api_key = getattr(settings, "FIRMS_API_KEY", None)

    if not api_key:
        raise RuntimeError("NASA FIRMS API key is not configured.")

    # window_hours remains ingestion bookkeeping (run identity); the FIRMS
    # area API is day-granular and NRT coverage is requested at its full 2-day
    # granularity. Reported truthfully in the ingestion status.
    days = 2

    run_id = hashlib.sha256(
        f"{datetime.now(timezone.utc).isoformat()}|{window_hours}".encode()
    ).hexdigest()[:16]

    detections: list[ThermalDetection] = []
    fetch_report: dict[str, Any] = {
        "sources": {},
        "errors": [],
        "enrichment": {},
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Both production sources through the SAME pipeline.
        for source in INGESTION_SOURCES:
            url = (
                "https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
                f"{api_key}/{source}/{INDIA_BBOX}/{days}"
            )
            try:
                response = await client.get(url)
                response.raise_for_status()
            except Exception as exc:
                # A single-source failure must be visible in the ingestion
                # status, never silently swallowed.
                fetch_report["sources"][source] = None
                fetch_report["errors"].append(f"{source}: {exc}")
                continue

            rows = list(csv.DictReader(io.StringIO(response.text)))
            fetch_report["sources"][source] = len(rows)

            for row in rows:
                if not row.get("latitude") or not row.get("longitude"):
                    continue
                detections.append(_build_detection(row, run_id))

    if not detections and fetch_report["errors"]:
        raise RuntimeError(
            "FIRMS ingestion failed for all sources: "
            + "; ".join(fetch_report["errors"])
        )

    await _enrich_detections(detections)

    # Truthful enrichment accounting: how many detections actually received
    # state/LULC values (explicit None when enrichment was unavailable).
    fetch_report["enrichment"] = {
        "total": len(detections),
        "state": sum(1 for d in detections if d.state),
        "lulc": sum(1 for d in detections if d.lulc_2021_code),
    }

    return detections, fetch_report


async def _enrich_detections(detections: list[ThermalDetection]) -> None:
    """Attach state/LGD + LULC 2021 enrichment to detections, in place.

    Live NRT detections (later than the historical archive coverage) are
    enriched with the established Phase 3 methodology (SOI states
    point-in-polygon join + ESA WorldCover 2021 sampling) computed from the
    detection coordinates. Historical/replay detections whose Phase 3 sha1
    detection_id exists in the archive CSVs are enriched from the archive.

    Enrichment is batched per ingestion run and reference data (state
    polygons, WorldCover tile overviews) is loaded at most once per process.
    The ThermoIntel ``observation_id`` is never altered. Unenrichable
    detections keep explicit None values.
    """
    if not detections:
        return

    cutoff = datetime.fromisoformat(live_enrichment.HISTORICAL_COVERAGE_END)

    live_indices = [
        i
        for i, d in enumerate(detections)
        if d.acquired_at.date() > cutoff.date()
    ]
    historical_indices = [
        i for i in range(len(detections)) if i not in set(live_indices)
    ]

    # --- historical archive path (Phase 3 sha1 detection_id lookup) ---
    if historical_indices:
        import hashlib

        ids = [
            _phase3_detection_id(detections[i])
            for i in historical_indices
        ]
        try:
            records = live_enrichment.historical_enrich_batch(ids)
        except Exception:
            # Enrichment unavailability must never fail ingestion; affected
            # detections keep explicit None (no fabrication).
            logger.warning(
                "Historical Phase 3 archive enrichment unavailable; "
                "leaving state/LULC explicitly None.",
                exc_info=True,
            )
            records = [None] * len(historical_indices)
        for i, record in zip(historical_indices, records):
            if record is None:
                continue
            detection = detections[i]
            if record.get("state"):
                detection.state = record["state"]
                detection.state_lgd = record.get("state_lgd")
            if record.get("lulc_2021_code"):
                detection.lulc_2021_code = record["lulc_2021_code"]
                detection.lulc_2021_class = record.get("lulc_2021_class")

    # --- live NRT path (Phase 3 methodology, computed from coordinates) ---
    if live_indices:
        try:
            enricher = live_enrichment.get_live_enricher()
            lats = [detections[i].location.latitude for i in live_indices]
            lons = [detections[i].location.longitude for i in live_indices]

            results = await asyncio.to_thread(
                enricher.enrich_batch, lats, lons
            )
        except Exception:
            # Missing reference data / rasterio failure must never fail
            # ingestion; affected detections keep explicit None values.
            logger.warning(
                "Live Phase 3 enrichment unavailable; leaving state/LULC "
                "explicitly None.",
                exc_info=True,
            )
            results = [None] * len(live_indices)

        for i, record in zip(live_indices, results):
            if record is None:
                continue
            detection = detections[i]
            if record.get("state"):
                detection.state = record["state"]
                detection.state_lgd = record.get("state_lgd")
            if record.get("lulc_2021_code"):
                detection.lulc_2021_code = record["lulc_2021_code"]
                detection.lulc_2021_class = record.get("lulc_2021_class")


def _phase3_detection_id(detection: ThermalDetection) -> str:
    """Recompute the Phase 3 sha1 detection_id for archive lookups ONLY.

    This is a lookup key for the historical CSVs, never a replacement for the
    ThermoIntel ``observation_id`` stored on the document.
    """
    import hashlib

    satellite_std = detection.satellite_std or getattr(
        detection.satellite, "value", detection.satellite
    )
    dt = detection.acquired_at.strftime("%Y-%m-%d %H:%M:%S")
    frp = detection.frp if detection.frp is not None else ""
    key = (
        f"{satellite_std}|{detection.location.latitude:.6f}|"
        f"{detection.location.longitude:.6f}|{dt}|{frp}"
    )
    return hashlib.sha1(key.encode()).hexdigest()[:16]


async def persist_detections(
    detections: list[ThermalDetection],
    run_id: str,
) -> list[ThermalDetection]:
    if not detections:
        return []

    db = get_db()
    collection = db[Collections.THERMAL_DETECTIONS]
    new_detections = []

    for detection in detections:
        document = detection.to_mongo()
        document["ingestion_run_id"] = run_id
        document["data_origin"] = "production"

        result = await collection.update_one(
            {"observation_id": detection.observation_id},
            {"$setOnInsert": document},
            upsert=True,
        )

        if result.upserted_id is not None:
            new_detections.append(detection)

    return new_detections


async def run(
    window_hours: int,
    triggered_by: str = "manual",
) -> datetime:
    started_at = datetime.now(timezone.utc)

    detections, _report = await fetch_detections(window_hours)

    run_id = (
        f"firms-{started_at.strftime('%Y%m%d%H%M%S')}"
    )

    await persist_detections(detections, run_id)

    return started_at