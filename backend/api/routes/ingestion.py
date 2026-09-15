import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from core.config import settings
from models.enums import IngestionStatus, PipelineStage
from models.ingestion_run import IngestionRun, StageResult
from pipeline import event_formation, firms_ingestion, ml_inference, threat_engine
from services import registry_service

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.get("/status")
async def get_ingestion_status():
    """Pipeline readiness plus the most recent run."""
    latest = await registry_service.latest_ingestion_run()
    recent = await registry_service.list_ingestion_runs(limit=10)
    return {
        "firms_source_configured": firms_ingestion.is_configured(),
        "event_formation_calibrated": event_formation.CONFIG.is_calibrated,
        "ml_models_available": ml_inference.is_available(),
        "threat_engine_calibrated": threat_engine.CONFIG.is_calibrated,
        "active_model_version": settings.ACTIVE_MODEL_VERSION,
        "latest_run": latest.model_dump(exclude={"id"}) if latest else None,
        "recent_runs": [run.model_dump(exclude={"id"}) for run in recent],
    }


@router.post("/run")
async def run_ingestion(
    window_hours: int = Query(24, ge=1, le=168),
    triggered_by: str = Query("manual"),
):
    """Trigger the ingestion pipeline.

    Phase 2 has no FIRMS credentials, no event-formation thresholds and no
    models, so the run is recorded as NOT_IMPLEMENTED per stage. This keeps
    ``ingestion_runs`` honest and auditable instead of producing fake data.
    """
    run = IngestionRun(
        run_id=str(uuid.uuid4()),
        status=IngestionStatus.NOT_IMPLEMENTED,
        triggered_by=triggered_by,
        source="NASA_FIRMS" if firms_ingestion.is_configured() else None,
        requested_window_hours=window_hours,
        stages=[
            StageResult(
                stage=PipelineStage.FIRMS_INGESTION,
                status=IngestionStatus.NOT_IMPLEMENTED,
                message="FIRMS credentials not configured (Phase 3/5).",
            ),
            StageResult(
                stage=PipelineStage.EVENT_FORMATION,
                status=IngestionStatus.NOT_IMPLEMENTED,
                message="Grouping radius and time window are unfrozen (Phase 5).",
            ),
            StageResult(
                stage=PipelineStage.FEATURE_ENGINEERING,
                status=IngestionStatus.NOT_IMPLEMENTED,
                message="Feature subset finalised in Phase 4.",
            ),
            StageResult(
                stage=PipelineStage.ML_INFERENCE,
                status=IngestionStatus.NOT_IMPLEMENTED,
                message="No model artifacts registered (Phase 4).",
            ),
            StageResult(
                stage=PipelineStage.THREAT_ANALYSIS,
                status=IngestionStatus.NOT_IMPLEMENTED,
                message="Threat weights and levels are unfrozen (Phase 4).",
            ),
            StageResult(
                stage=PipelineStage.ALERT_GENERATION,
                status=IngestionStatus.NOT_IMPLEMENTED,
                message="Alert threshold is unfrozen (Phase 4).",
            ),
        ],
        message="Pipeline interfaces exist; no stage is implemented in Phase 2.",
        finished_at=datetime.now(timezone.utc),
    )
    return (await registry_service.record_ingestion_run(run)).model_dump(
        exclude={"id"}
    )
