"""Reprocess EXISTING production records with the CURRENT installed M1 model.

This is an explicit manual operation triggered from the dashboard Refresh
button. It is NOT ingestion:

    existing database records
        -> stored features/enrichment
        -> CURRENT pipeline.ml_inference.classify_sync (newly installed M1)
        -> existing threat-engine assessment
        -> targeted update of the stored classification/threat fields
        -> dashboard refetches and displays updated classifications

It NEVER fetches FIRMS data, never inserts detections, never deletes
anything, and never changes the M1-M4 models or the downstream hierarchy.
Only the classification/threat fields on EXISTING events are updated, plus
the idempotent alert upsert reusing the EXISTING threat-engine contract.
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from core.database import Collections, get_db
from models.detection import ThermalDetection
from models.enums import DataOrigin, IngestionStatus, PipelineStage
from models.event import Event
from models.ingestion_run import IngestionRun, StageResult
from pipeline import feature_engineering, ml_inference, threat_engine
from services import registry_service

router = APIRouter(prefix="/reprocess", tags=["reprocess"])
logger = logging.getLogger(__name__)

# Targeted-update projection: ONLY these fields are ever written back. The
# lifecycle/status fields (status, first_detected, last_detected,
# detection_count, detection_ids, created_at) are deliberately absent so a
# reprocessing run can never resurrect an EXPIRED event or rewrite history.
_EVENT_SET_KEYS = [
    "classification",
    "threat",
    "facility_reference",
    "updated_at",
]


@router.post("/existing-data")
async def reprocess_existing_data(
    limit: int | None = Query(
        default=None, ge=1, description="Process at most N events (bounded test)."
    ),
    triggered_by: str = Query("manual-refresh"),
):
    """Re-run the current ML inference + threat assessment on events that are
    already stored, using their existing detection/enrichment data.

    No FIRMS request is made anywhere on this path.
    """
    # Normalize FastAPI Query defaults: over HTTP these arrive as parsed
    # values; direct coroutine calls (scripts/tests) receive the raw Query
    # marker object when left at their default.
    if not isinstance(limit, int) or limit < 1:
        limit = None
    if not isinstance(triggered_by, str) or not triggered_by:
        triggered_by = "manual-refresh"

    # Unique suffix: the ingestion_runs.run_id index is unique, and reprocess
    # runs can start within the same second (rapid successive triggers) — a
    # second-granularity id collides on the unique index.
    run_id = ("reprocess-"
              f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-"
              f"{uuid.uuid4().hex[:8]}")
    started_at = datetime.now(timezone.utc)
    stages: list[StageResult] = []

    # Guards: the same readiness gates the ingestion route surfaces.
    if not ml_inference.is_available():
        return _record_failure(run_id, triggered_by, started_at,
                               "ML models are not available; nothing was changed.")

    db = get_db()

    # 1. Select EXISTING production events. No upserts, no new records: the
    # selection reads what the normal pipeline already persisted.
    query = {"data_origin": DataOrigin.PRODUCTION.value}
    total_events = await db[Collections.EVENTS].count_documents(query)
    cursor = db[Collections.EVENTS].find(query).sort([("last_detected", -1)])
    if limit is not None:
        cursor = cursor.limit(limit)

    classified = 0
    failed = 0
    skipped = 0
    alerts_generated = 0
    failure_reasons: list[str] = []
    failures_by_reason: dict[str, int] = {}
    event_ids_updated: list[str] = []
    now = datetime.now(timezone.utc)

    # 2. Per-event reclassification.
    async for event_doc in cursor:
        event_id = event_doc.get("event_id")
        detection_ids = event_doc.get("detection_ids") or []
        if not event_id or not detection_ids:
            skipped += 1
            failures_by_reason["no detection_ids"] = (
                failures_by_reason.get("no detection_ids", 0) + 1)
            continue

        detection_doc = await db[Collections.THERMAL_DETECTIONS].find_one(
            {"observation_id": detection_ids[0]}
        )
        if detection_doc is None:
            skipped += 1
            failures_by_reason["primary detection not found"] = (
                failures_by_reason.get("primary detection not found", 0) + 1)
            continue

        try:
            detection = ThermalDetection.from_mongo(detection_doc)
            event = Event.from_mongo(event_doc)

            # Same facility context + feature path as the live pipeline.
            facility = await registry_service.nearest_facility(
                event.centroid.latitude,
                event.centroid.longitude,
            )
            context = facility or {}
            features = feature_engineering.build_features(
                event, detection.model_dump(), context
            )

            # THE EXISTING inference path with the CURRENTLY INSTALLED M1.
            classification = ml_inference.classify_sync(event, features)

            # EXISTING threat engine with the SAME features (contract:
            # alert-time eligibility uses assessment-time signals).
            normalized = threat_engine.normalize_signals(event, features)
            assessment = await threat_engine.assess(event, features)

            # 3. Targeted update of interpretation fields ONLY.
            event.classification = classification
            if assessment is not None:
                event.threat = assessment
            event.facility_reference = facility["facility_id"] if facility else None
            event.updated_at = now

            set_doc = {k: event.to_mongo()[k] for k in _EVENT_SET_KEYS}
            result = await db[Collections.EVENTS].update_one(
                {"event_id": event_id, "data_origin": DataOrigin.PRODUCTION.value},
                {"$set": set_doc},
            )
            if result.matched_count == 0:
                failed += 1
                failures_by_reason["event disappeared mid-run"] = (
                    failures_by_reason.get("event disappeared mid-run", 0) + 1)
                continue

            classified += 1
            event_ids_updated.append(event_id)
        except Exception as exc:  # one bad event never fails the run
            failed += 1
            reason = f"{type(exc).__name__}: {exc}"
            failure_reasons.append(f"{event_id}: {reason}")
            failures_by_reason[reason.split(":", 1)[0]] = (
                failures_by_reason.get(reason.split(":", 1)[0], 0) + 1)
            logger.exception("Reprocess inference failed for event %s", event_id)
            continue

    # 4. Alert refresh through the EXISTING engine. Eligibility is
    # recomputed from the CURRENT assessment-time signals; the deterministic
    # alert_id upsert keeps at most one alert per event (idempotent).
    if classified:
        try:
            refreshed = await _refresh_alerts(db, event_ids_updated)
            alerts_generated = refreshed
        except Exception as exc:
            logger.exception("Alert refresh failed during reprocess")
            stages.append(
                StageResult(
                    stage=PipelineStage.ALERT_GENERATION,
                    status=IngestionStatus.PARTIAL,
                    message=f"Alert refresh failed: {exc}",
                )
            )

    processed = classified + failed + skipped
    ml_status = (
        IngestionStatus.FAILED
        if classified == 0 and failed
        else (IngestionStatus.PARTIAL if failed or skipped else IngestionStatus.SUCCEEDED)
    )
    stages.append(
        StageResult(
            stage=PipelineStage.ML_INFERENCE,
            status=ml_status,
            message=(
                f"Reprocessed {classified}/{processed} existing production events "
                f"with the current M1 ({failed} failed, {skipped} skipped). "
                f"No new detections were created; no FIRMS request was made."
            ),
        )
    )

    stage_statuses = [stage.status for stage in stages]
    overall = (
        IngestionStatus.FAILED
        if IngestionStatus.FAILED in stage_statuses
        else (IngestionStatus.PARTIAL if IngestionStatus.PARTIAL in stage_statuses
              else IngestionStatus.SUCCEEDED)
    )
    message = (
        f"Reprocessing finished: {classified} reclassified, {failed} failed, "
        f"{skipped} skipped, {alerts_generated} alert(s) refreshed."
    )

    run = IngestionRun(
        run_id=run_id,
        detections_ingested=0,  # this operation never creates detections
        status=overall,
        triggered_by=triggered_by,
        source="EXISTING_DATABASE",  # NOT NASA_FIRMS: nothing was fetched
        requested_window_hours=None,
        stages=stages,
        message=message,
        finished_at=datetime.now(timezone.utc),
    )
    await registry_service.record_ingestion_run(run)

    return {
        "status": overall.value,
        "run_id": run_id,
        "source": "EXISTING_DATABASE",
        "total_existing_events": total_events,
        "selected": processed,
        "processed": classified,
        "updated": classified,
        "skipped": skipped,
        "failed": failed,
        "failure_reasons": failure_reasons[:20],
        "failures_by_reason": failures_by_reason,
        "alerts_refreshed": alerts_generated,
        "note": (
            "Existing records reclassified with the currently installed M1 "
            "via the existing pipeline.ml_inference path. No FIRMS data was "
            "fetched; no detections were created or deleted."
        ),
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc),
    }


async def _refresh_alerts(db, event_ids_updated: list[str]) -> int:
    """Recompute alert eligibility for reprocessed events.

    Loads the UPDATED event documents, rebuilds each event's assessment-time
    normalized signals by re-running the threat normalizers on the SAME
    stored feature inputs, and upserts through threat_engine.generate_alerts
    (deterministic alert_id, idempotent, never supersedes an existing alert).
    """
    from models.enums import PipelineStage

    created = 0
    events: list[Event] = []
    normalized_by_event: dict[str, dict] = {}

    # Chunked reload of just the updated events.
    for i in range(0, len(event_ids_updated), 500):
        chunk = event_ids_updated[i:i + 500]
        docs = await db[Collections.EVENTS].find(
            {"event_id": {"$in": chunk}}
        ).to_list(length=len(chunk))
        for doc in docs:
            try:
                event = Event.from_mongo(doc)
                detection_ids = doc.get("detection_ids") or []
                if not detection_ids:
                    continue
                detection_doc = await db[Collections.THERMAL_DETECTIONS].find_one(
                    {"observation_id": detection_ids[0]}
                )
                if detection_doc is None:
                    continue
                facility = await registry_service.nearest_facility(
                    event.centroid.latitude, event.centroid.longitude,
                )
                features = feature_engineering.build_features(
                    event, ThermalDetection.from_mongo(detection_doc).model_dump(),
                    facility or {},
                )
                events.append(event)
                normalized_by_event[event.event_id] = threat_engine.normalize_signals(
                    event, features
                )
            except Exception:
                logger.exception(
                    "Alert refresh feature rebuild failed for %s", doc.get("event_id")
                )

    # generate_alerts persists via deterministic alert_id upsert (idempotent,
    # at most one alert per event) and refreshes the stored alert content for
    # events whose classification changed; it REPORTS only newly created
    # alerts, which is exactly what we surface.
    created = await threat_engine.generate_alerts(events, normalized_by_event)
    return created


async def _record_failure(run_id, triggered_by, started_at, message):
    run = IngestionRun(
        run_id=run_id,
        detections_ingested=0,
        status=IngestionStatus.FAILED,
        triggered_by=triggered_by,
        source="EXISTING_DATABASE",
        requested_window_hours=None,
        stages=[],
        message=message,
        finished_at=datetime.now(timezone.utc),
    )
    await registry_service.record_ingestion_run(run)
    return {
        "status": "FAILED",
        "run_id": run_id,
        "source": "EXISTING_DATABASE",
        "selected": 0,
        "processed": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "failure_reasons": [message],
        "failures_by_reason": {},
        "alerts_refreshed": 0,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc),
    }
