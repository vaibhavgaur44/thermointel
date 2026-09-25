import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from core.config import settings
from models.enums import IngestionStatus, PipelineStage
from models.ingestion_run import IngestionRun, StageResult
from pipeline import event_formation, firms_ingestion, ml_inference, threat_engine
from services import registry_service

from pipeline import feature_engineering

router = APIRouter(prefix="/ingestion", tags=["ingestion"])
logger = logging.getLogger(__name__)


@router.get("/status")
async def get_ingestion_status():
    """Pipeline readiness plus the most recent runs."""
    latest = await registry_service.latest_ingestion_run()
    recent = await registry_service.list_ingestion_runs(limit=10)
    facility_status = await registry_service.facility_context_status()
    return {
        "firms_source_configured": firms_ingestion.is_configured(),
        "event_formation_calibrated": event_formation.CONFIG.is_calibrated,
        "ml_models_available": ml_inference.is_available(),
        "threat_engine_calibrated": threat_engine.CONFIG.is_calibrated,
        "active_model_version": settings.ACTIVE_MODEL_VERSION,
        "facility_context": facility_status,
        "latest_run": latest.model_dump(exclude={"id"}) if latest else None,
        "recent_runs": [run.model_dump(exclude={"id"}) for run in recent],
    }


@router.post("/run")
async def run_ingestion(
    window_hours: int = Query(24, ge=1, le=168),
    triggered_by: str = Query("manual"),
):
    """Run the Phase 5 production pipeline (NOAA-20 + NOAA-21 -> alerts)."""

    run_id = f"firms-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    stages = []
    inserted = 0

    try:
        # 1. FIRMS ingestion (both production sources, same pipeline).
        detections, fetch_report = await firms_ingestion.fetch_detections(window_hours)
        fetched_count = len(detections)  # truthfully reported before narrowing to NEW rows
        new_detections = await firms_ingestion.persist_detections(
            detections,
            run_id,
        )
        inserted = len(new_detections)
        detections = new_detections

        # --- Truthful FIRMS stage accounting -------------------------------
        # fetch_report: {"sources": {source: rows|None}, "errors": [str],
        #                "enrichment": {"total", "state", "lulc"}}
        source_reports = fetch_report.get("sources", {})
        fetch_errors = list(fetch_report.get("errors", []))
        ok_sources = [s for s, n in source_reports.items() if n]
        zero_sources = [s for s, n in source_reports.items() if n == 0]
        failed_sources = [e.split(":", 1)[0] for e in fetch_errors]
        enrichment = fetch_report.get("enrichment", {})

        if not ok_sources and fetch_errors:
            # Every source failed -> the run failed.
            fetch_status = IngestionStatus.FAILED
        elif (
            fetch_errors
            or zero_sources
            or not ok_sources
            # Detections arrived but enrichment produced nothing at all.
            or (
                enrichment.get("total", 0) > 0
                and enrichment.get("state", 0) == 0
                and enrichment.get("lulc", 0) == 0
            )
        ):
            fetch_status = IngestionStatus.PARTIAL
        else:
            fetch_status = IngestionStatus.SUCCEEDED

        fetch_parts = [
            f"{source}: {count if count is not None else 'FAILED'} rows"
            for source, count in source_reports.items()
        ]
        if fetch_errors:
            fetch_parts.append("errors: " + "; ".join(fetch_errors))
        if enrichment:
            fetch_parts.append(
                "enrichment: {state}/{total} state, {lulc}/{total} LULC".format(
                    **enrichment
                )
            )
        stages.append(
            StageResult(
                stage=PipelineStage.FIRMS_INGESTION,
                status=fetch_status,
                message=(
                    f"Fetched {fetched_count} FIRMS detections "
                    f"({', '.join(fetch_parts) if fetch_parts else 'no sources reported'}); "
                    f"inserted {inserted} new production detections"
                    + (
                        f" ({fetched_count - inserted} already persisted, idempotent upsert)"
                        if fetched_count > inserted
                        else ""
                    )
                    + "."
                ),
            )
        )

        # 2. Event formation
        events = await event_formation.group_detections(detections)
        event_inserted = await event_formation.persist_events(events)
        expired = await event_formation.expire_stale_events()

        stages.append(
            StageResult(
                stage=PipelineStage.EVENT_FORMATION,
                status=IngestionStatus.SUCCEEDED,
                message=(
                    f"Formed {len(events)} production events; "
                    f"persisted {event_inserted}; "
                    f"{expired} expired (window: "
                    f"{event_formation.CONFIG.expiry_window_hours}h)."
                ),
            )
        )

        # 3. Feature engineering + ML inference + threat/alert stages
        detection_by_id = {
            detection.observation_id: detection for detection in detections
        }

        classified = 0
        assessed = 0
        missing_context = 0
        ml_failures = 0
        normalized_by_event: dict[str, dict] = {}

        for event in events:
            if not event.detection_ids:
                continue

            detection = detection_by_id.get(event.detection_ids[0])
            if detection is None:
                continue

            detection_data = detection.model_dump()

            # Facility context from MongoDB (Phase 3 standardized dataset is
            # the canonical production source). Missing context stays
            # explicit: nearest_facility_* remain None and the frozen Phase 4
            # preprocessing imputes them. No value is fabricated.
            facility = await registry_service.nearest_facility(
                event.centroid.latitude,
                event.centroid.longitude,
            )

            if facility is None:
                missing_context += 1
            else:
                event.facility_reference = facility["facility_id"]

            context = facility or {}

            features = feature_engineering.build_features(
                event,
                detection_data,
                context,
            )

            try:
                classification = ml_inference.classify_sync(event, features)
            except Exception:
                # One unclassifiable event must not fail the whole run;
                # the failure is counted and reported truthfully.
                ml_failures += 1
                logger.exception(
                    "ML inference failed for event %s", event.event_id
                )
                continue

            event.classification = classification
            classified += 1

            # Threat evaluation with the owner-proposed provisional contract
            # (Task 21). Signals whose normalization is UNDEFINED yield None
            # and contribute 0; events with no computable signal stay
            # explicitly UNASSESSED - nothing is fabricated.
            normalized_by_event[event.event_id] = threat_engine.normalize_signals(
                event, features
            )
            assessment = await threat_engine.assess(event, features)
            if assessment is not None:
                event.threat = assessment
                assessed += 1

        await event_formation.persist_events(events)

        # 5. Alert generation (owner eligibility contract + duplicate
        # suppression; see pipeline/threat_engine.py).
        alerts_raised = await threat_engine.generate_alerts(
            events, normalized_by_event
        )

        ml_status = (
            IngestionStatus.FAILED
            if classified == 0 and ml_failures
            else (
                IngestionStatus.PARTIAL
                if ml_failures
                else IngestionStatus.SUCCEEDED
            )
        )

        stages.append(
            StageResult(
                stage=PipelineStage.FEATURE_ENGINEERING,
                status=IngestionStatus.SUCCEEDED,
                message=(
                    f"Built Phase 4-compatible features for "
                    f"{classified + ml_failures} events "
                    f"({missing_context} without facility context)."
                ),
            )
        )

        stages.append(
            StageResult(
                stage=PipelineStage.ML_INFERENCE,
                status=ml_status,
                message=(
                    f"Classified {classified} production events"
                    + (
                        f"; {ml_failures} inference failure(s)"
                        if ml_failures
                        else ""
                    )
                    + "."
                ),
            )
        )

        stages.append(
            StageResult(
                stage=PipelineStage.THREAT_ANALYSIS,
                status=IngestionStatus.SUCCEEDED,
                message=(
                    f"Threat engine scored {assessed}/{classified} events "
                    f"with the {threat_engine.CONFIG.threshold_profile} "
                    f"profile ({threat_engine.CONFIG.calibration_status} - "
                    f"not yet calibrated/validated)."
                ),
            )
        )

        stages.append(
            StageResult(
                stage=PipelineStage.ALERT_GENERATION,
                status=IngestionStatus.SUCCEEDED,
                message=(
                    f"{alerts_raised} alert(s) raised per the owner "
                    f"eligibility contract (profile "
                    f"{threat_engine.CONFIG.threshold_profile})."
                ),
            )
        )

        # --- Truthful overall status ---------------------------------------
        stage_statuses = [stage.status for stage in stages]
        if IngestionStatus.FAILED in stage_statuses:
            overall = IngestionStatus.FAILED
        elif IngestionStatus.PARTIAL in stage_statuses:
            overall = IngestionStatus.PARTIAL
        else:
            overall = IngestionStatus.SUCCEEDED

        if overall is IngestionStatus.SUCCEEDED:
            message = (
                "Phase 5 pipeline completed: ingestion, enrichment, events, "
                "ML classification, threat evaluation and alerts."
            )
        elif overall is IngestionStatus.PARTIAL:
            message = (
                "Phase 5 pipeline completed PARTIALLY - one or more FIRMS "
                "sources failed/returned no data or some inferences failed; "
                "see per-stage messages."
            )
        else:
            message = "Phase 5 pipeline FAILED - see per-stage messages."

        run = IngestionRun(
            run_id=run_id,
            detections_ingested=inserted,
            status=overall,
            triggered_by=triggered_by,
            source="NASA_FIRMS",
            requested_window_hours=window_hours,
            stages=stages,
            message=message,
            finished_at=datetime.now(timezone.utc),
        )

        return (
            await registry_service.record_ingestion_run(run)
        ).model_dump(exclude={"id"})

    except Exception as exc:
        logger.exception("Phase 5 ingestion pipeline failed")

        run = IngestionRun(
            run_id=run_id,
            detections_ingested=inserted,
            status=IngestionStatus.FAILED,
            triggered_by=triggered_by,
            source="NASA_FIRMS",
            requested_window_hours=window_hours,
            stages=stages,
            message=f"Pipeline failed: {exc}",
            error=str(exc),
            finished_at=datetime.now(timezone.utc),
        )

        return (
            await registry_service.record_ingestion_run(run)
        ).model_dump(exclude={"id"})
