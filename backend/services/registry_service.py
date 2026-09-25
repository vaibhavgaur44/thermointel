"""Read services for alerts, facilities, detections, ingestion runs, models."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.database import Collections, get_db
from models.alert import Alert, AlertSummary
from models.detection import ThermalDetection
from models.enums import TIME_RANGE_SECONDS, AlertStatus, DataOrigin, SourceType, TimeRange
from models.facility import Facility
from models.ingestion_run import IngestionRun
from models.model_version import ModelVersion


def _origin_query(include_demo: bool) -> dict:
    origins = [DataOrigin.PRODUCTION.value]
    if include_demo:
        origins.append(DataOrigin.DEMO.value)
    return {"data_origin": {"$in": origins}}


async def list_alerts(
    status: Optional[AlertStatus] = AlertStatus.OPEN,
    state: Optional[str] = None,
    classifications: Optional[list[str]] = None,
    source_types: Optional[list[SourceType]] = None,
    time_range: Optional[TimeRange] = None,
    include_demo: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AlertSummary], int]:
    db = get_db()
    query = _origin_query(include_demo)

    if status is not None:
        query["status"] = status.value

    if state:
        query["state"] = state

    if classifications:
        query["event_type"] = {"$in": classifications}

    if source_types:
        query["source_type"] = {"$in": [s.value for s in source_types]}

    if time_range is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(
            seconds=TIME_RANGE_SECONDS[time_range]
        )
        query["raised_at"] = {"$gte": cutoff}

    total = await db[Collections.ALERTS].count_documents(query)

    docs = (
        await db[Collections.ALERTS]
        .find(query)
        .sort([("threat_score", -1), ("raised_at", -1)])
        .skip(offset)
        .limit(limit)
        .to_list(length=limit)
    )

    return [AlertSummary.from_alert(Alert.from_mongo(d)) for d in docs], total


async def get_alert(alert_id: str) -> Optional[AlertSummary]:
    doc = await get_db()[Collections.ALERTS].find_one({"alert_id": alert_id})
    if doc is None:
        return None
    return AlertSummary.from_alert(Alert.from_mongo(doc))


async def list_facilities(
    state: Optional[str] = None,
    source_types: Optional[list[SourceType]] = None,
    include_demo: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[Facility], int]:
    db = get_db()
    query = _origin_query(include_demo)
    if state:
        query["state"] = state
    if source_types:
        query["source_type"] = {"$in": [s.value for s in source_types]}

    total = await db[Collections.FACILITIES].count_documents(query)
    docs = (
        await db[Collections.FACILITIES]
        .find(query)
        .skip(offset)
        .limit(limit)
        .to_list(length=limit)
    )
    return [Facility.from_mongo(d) for d in docs], total


async def list_detections(
    state: Optional[str] = None,
    event_id: Optional[str] = None,
    time_range: Optional[TimeRange] = None,
    include_demo: bool = False,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[ThermalDetection], int]:
    db = get_db()
    query = _origin_query(include_demo)
    if state:
        query["state"] = state
    if event_id:
        query["event_id"] = event_id
    if time_range is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(
            seconds=TIME_RANGE_SECONDS[time_range]
        )
        query["acquired_at"] = {"$gte": cutoff}

    total = await db[Collections.THERMAL_DETECTIONS].count_documents(query)
    docs = (
        await db[Collections.THERMAL_DETECTIONS]
        .find(query)
        .sort([("acquired_at", -1)])
        .skip(offset)
        .limit(limit)
        .to_list(length=limit)
    )
    return [ThermalDetection.from_mongo(d) for d in docs], total


async def latest_ingestion_run() -> Optional[IngestionRun]:
    db = get_db()
    docs = (
        await db[Collections.INGESTION_RUNS]
        .find({})
        .sort([("started_at", -1)])
        .limit(1)
        .to_list(length=1)
    )
    return IngestionRun.from_mongo(docs[0]) if docs else None


async def list_ingestion_runs(limit: int = 20) -> list[IngestionRun]:
    db = get_db()
    docs = (
        await get_db()[Collections.INGESTION_RUNS]
        .find({})
        .sort([("started_at", -1)])
        .limit(limit)
        .to_list(length=limit)
    )
    return [IngestionRun.from_mongo(d) for d in docs]


async def record_ingestion_run(run: IngestionRun) -> IngestionRun:
    await get_db()[Collections.INGESTION_RUNS].insert_one(run.to_mongo())
    return run


async def list_model_versions(limit: int = 50) -> list[ModelVersion]:
    db = get_db()
    docs = (
        await db[Collections.MODEL_VERSIONS]
        .find({})
        .sort([("created_at", -1)])
        .limit(limit)
        .to_list(length=limit)
    )
    return [ModelVersion.from_mongo(d) for d in docs]


async def facility_context_status() -> dict:
    """Composition of the facilities collection for readiness reporting.

    ``imported`` counts canonical Phase 3 production facilities available to
    nearest_facility(); 0 means the import has not been run.
    """
    db = get_db()
    collection = db[Collections.FACILITIES]
    demo_origin = DataOrigin.DEMO.value
    return {
        "imported": await collection.count_documents(
            {"data_origin": DataOrigin.PRODUCTION.value}
        ),
        "legacy": await collection.count_documents(
            {
                "data_origin": {"$exists": False},
                "is_demo": {"$ne": True},
            }
        ),
        "demo": await collection.count_documents(
            {"data_origin": {"$eq": demo_origin}}
        ),
    }


async def nearest_facility(
    latitude: float,
    longitude: float,
) -> dict | None:
    """Return the nearest production facility and its distance.

    Queries the ``facilities`` collection via its ``location`` 2dsphere
    index. Demo facilities are excluded; legacy OSM documents (no
    ``data_origin`` field, never written by the demo seed) are included
    because they are production provenance, not demo data.

    Returns explicit missing context (None) when no facility exists in the
    collection. No facility, distance, or type is ever fabricated.
    """

    db = get_db()

    pipeline = [
        {
            "$geoNear": {
                "near": {
                    "type": "Point",
                    "coordinates": [longitude, latitude],
                },
                "key": "location",
                "distanceField": "distance_m",
                "spherical": True,
                "query": {
                    "data_origin": {"$ne": DataOrigin.DEMO.value},
                },
            }
        },
        {
            "$limit": 1,
        },
        {
            "$project": {
                "_id": 0,
                "facility_id": 1,
                "name": 1,
                "source_type": 1,
                "attributes": 1,
                "distance_m": 1,
            }
        },
    ]

    docs = await db[Collections.FACILITIES].aggregate(
        pipeline
    ).to_list(length=1)

    if not docs:
        return None

    doc = docs[0]

    return {
        "facility_id": doc.get("facility_id"),
        "name": doc.get("name"),
        "nearest_facility_km": doc["distance_m"] / 1000.0,
        "nearest_facility_type": doc.get("attributes", {}).get("facility_type"),
        # Verbatim Phase 3 facility attributes. This is the raw context the
        # (future, unfrozen) threat engine's industrial_context signal will
        # consume. No scoring, weighting, or thresholding happens here.
        "industrial_context": doc.get("attributes") or None,
    }