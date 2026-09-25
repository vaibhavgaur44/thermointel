"""MongoDB (Atlas compatible) connection and index management."""
import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, GEOSPHERE

from core.config import settings

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None


class Collections:
    THERMAL_DETECTIONS = "thermal_detections"
    EVENTS = "events"
    FACILITIES = "facilities"
    GROUND_TRUTH = "ground_truth"
    ALERTS = "alerts"
    INGESTION_RUNS = "ingestion_runs"
    MODEL_VERSIONS = "model_versions"


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.MONGO_URL)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    return get_client()[settings.DB_NAME]


async def close_db() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


async def ensure_indexes() -> None:
    """Create the indexes described in the Phase 1 database design."""
    db = get_db()

    await db[Collections.THERMAL_DETECTIONS].create_index(
        [("observation_id", ASCENDING)], unique=True
    )
    await db[Collections.THERMAL_DETECTIONS].create_index([("location", GEOSPHERE)])
    await db[Collections.THERMAL_DETECTIONS].create_index([("acquired_at", DESCENDING)])
    await db[Collections.THERMAL_DETECTIONS].create_index(
        [("state", ASCENDING), ("acquired_at", DESCENDING)]
    )
    await db[Collections.THERMAL_DETECTIONS].create_index([("event_id", ASCENDING)])

    await db[Collections.EVENTS].create_index([("event_id", ASCENDING)], unique=True)
    await db[Collections.EVENTS].create_index([("centroid", GEOSPHERE)])
    await db[Collections.EVENTS].create_index(
        [("status", ASCENDING), ("threat_score", DESCENDING)]
    )
    await db[Collections.EVENTS].create_index(
        [("state", ASCENDING), ("status", ASCENDING), ("threat_score", DESCENDING)]
    )
    await db[Collections.EVENTS].create_index([("event_type", ASCENDING)])
    await db[Collections.EVENTS].create_index([("source_type", ASCENDING)])
    await db[Collections.EVENTS].create_index([("last_detected", DESCENDING)])
    await db[Collections.EVENTS].create_index([("data_origin", ASCENDING)])

    # Unique per facility_id. Partial on the presence of facility_id: the
    # collection also contains legacy OSM-ingest documents identified only by
    # osm_id (no facility_id). Without the partial filter those documents all
    # carry an implicit null key and MongoDB refuses to build the unique
    # index, which previously aborted ensure_indexes() and silently left the
    # facilities 2dsphere index (and every later index) uncreated.
    await db[Collections.FACILITIES].create_index(
        [("facility_id", ASCENDING)],
        unique=True,
        partialFilterExpression={"facility_id": {"$exists": True}},
    )
    # Geospatial index backing nearest_facility() lookups.
    await db[Collections.FACILITIES].create_index([("location", GEOSPHERE)])
    await db[Collections.FACILITIES].create_index([("state", ASCENDING)])
    await db[Collections.FACILITIES].create_index([("source_type", ASCENDING)])

    await db[Collections.ALERTS].create_index([("alert_id", ASCENDING)], unique=True)
    await db[Collections.ALERTS].create_index([("event_id", ASCENDING)])
    await db[Collections.ALERTS].create_index([("raised_at", DESCENDING)])
    await db[Collections.ALERTS].create_index(
        [("status", ASCENDING), ("threat_score", DESCENDING)]
    )

    await db[Collections.GROUND_TRUTH].create_index([("label_id", ASCENDING)], unique=True)
    await db[Collections.GROUND_TRUTH].create_index([("split", ASCENDING)])
    await db[Collections.GROUND_TRUTH].create_index([("location", GEOSPHERE)])

    await db[Collections.INGESTION_RUNS].create_index([("run_id", ASCENDING)], unique=True)
    await db[Collections.INGESTION_RUNS].create_index([("started_at", DESCENDING)])

    await db[Collections.MODEL_VERSIONS].create_index(
        [("model_version_id", ASCENDING)], unique=True
    )
    await db[Collections.MODEL_VERSIONS].create_index([("created_at", DESCENDING)])

    logger.info("MongoDB indexes ensured for database '%s'", settings.DB_NAME)
