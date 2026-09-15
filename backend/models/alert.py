"""Alerts - events that crossed the (future) alert threshold.

An alert carries the same basic event information as its marker but emphasises
WHY it was flagged. Thresholds are a Phase 4 decision; nothing here decides
what qualifies.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from models.common import BaseDocument, utc_now
from models.enums import (
    AlertStatus,
    DataOrigin,
    EventType,
    SourceType,
    ThreatLevel,
)
from models.event import SupportingEvidence


class Alert(BaseDocument):
    alert_id: str
    event_id: str

    status: AlertStatus = AlertStatus.OPEN
    data_origin: DataOrigin = DataOrigin.PRODUCTION

    # Snapshot of the event at flag time so the queue stays auditable.
    event_type: Optional[EventType] = None
    source_type: Optional[SourceType] = None
    state: Optional[str] = None
    threat_level: Optional[ThreatLevel] = None
    threat_score: Optional[float] = None

    # The reason the alert exists. This is the headline of the queue item.
    primary_reason: Optional[str] = None
    supporting_evidence: list[SupportingEvidence] = Field(default_factory=list)

    # Which threshold configuration raised it (traceability).
    threshold_profile: Optional[str] = None
    engine_version: Optional[str] = None

    raised_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AlertSummary(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    alert_id: str
    event_id: str
    status: AlertStatus
    data_origin: DataOrigin
    event_type: Optional[EventType] = None
    source_type: Optional[SourceType] = None
    state: Optional[str] = None
    threat_level: Optional[ThreatLevel] = None
    threat_score: Optional[float] = None
    primary_reason: Optional[str] = None
    supporting_evidence: list[SupportingEvidence] = Field(default_factory=list)
    raised_at: datetime

    @classmethod
    def from_alert(cls, alert: Alert) -> "AlertSummary":
        return cls(**alert.model_dump(exclude={"id", "updated_at",
                                               "threshold_profile",
                                               "engine_version"}))
