"""Stage 1 - NASA FIRMS ingestion (Phase 3 / 5).

Responsibility: pull FIRMS active-fire/thermal-anomaly records for the India
bounding box, de-duplicate them by observation_id, assign the state/UT from
India administrative boundaries, and insert them into ``thermal_detections``
verbatim. No interpretation whatsoever.
"""
from datetime import datetime

from core.config import settings
from models.detection import ThermalDetection
from models.enums import PipelineStage
from pipeline.base import PipelineStageNotImplemented

STAGE = PipelineStage.FIRMS_INGESTION


def is_configured() -> bool:
    return settings.firms_configured


async def fetch_detections(window_hours: int) -> list[ThermalDetection]:
    """Fetch raw FIRMS detections for the India bbox over the given window."""
    raise PipelineStageNotImplemented(STAGE, "Phase 3 (data) / Phase 5 (integration)")


async def persist_detections(
    detections: list[ThermalDetection], run_id: str
) -> int:
    """Upsert detections keyed on observation_id. Never overwrite measurements."""
    raise PipelineStageNotImplemented(STAGE, "Phase 5 (integration)")


async def run(window_hours: int, triggered_by: str = "manual") -> datetime:
    raise PipelineStageNotImplemented(STAGE, "Phase 5 (integration)")
