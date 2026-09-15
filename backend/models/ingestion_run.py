"""Pipeline execution history."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from models.common import BaseDocument, utc_now
from models.enums import IngestionStatus, PipelineStage


class StageResult(BaseModel):
    stage: PipelineStage
    status: IngestionStatus
    message: Optional[str] = None
    records_in: int = 0
    records_out: int = 0


class IngestionRun(BaseDocument):
    run_id: str
    status: IngestionStatus = IngestionStatus.PENDING

    triggered_by: str = "manual"
    source: Optional[str] = None  # e.g. "NASA_FIRMS_VIIRS_NRT"
    requested_window_hours: Optional[int] = None

    stages: list[StageResult] = Field(default_factory=list)

    detections_ingested: int = 0
    events_created: int = 0
    events_updated: int = 0
    events_expired: int = 0
    alerts_raised: int = 0

    message: Optional[str] = None
    error: Optional[str] = None

    started_at: datetime = Field(default_factory=utc_now)
    finished_at: Optional[datetime] = None
