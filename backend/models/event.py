"""ThermoIntel event objects - the primary operational dataset.

An event is the result of grouping raw FIRMS detections (space + time +
spatial-cluster continuity) and then interpreting them. All interpretation
fields are Optional and default to None: in Phase 2 no model exists, and the
UI must render an explicit "unavailable" state rather than a fabricated value.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from models.common import BaseDocument, GeoPoint, utc_now
from models.enums import (
    DataOrigin,
    EventCategory,
    EventStatus,
    EventType,
    EvidenceCode,
    SourceType,
    ThreatLevel,
)


class SupportingEvidence(BaseModel):
    """One 'why flagged' item. Produced by the Phase 4 threat engine."""

    model_config = ConfigDict(use_enum_values=True)

    code: EvidenceCode
    label: str
    detail: Optional[str] = None


class ClassificationResult(BaseModel):
    """Output of the hierarchical ML stack. Empty until Phase 4/5."""

    model_config = ConfigDict(protected_namespaces=(), use_enum_values=True)

    event_category: Optional[EventCategory] = None
    event_type: Optional[EventType] = None
    source_type: Optional[SourceType] = None
    # Calibrated predictive probability in [0, 1]. None => not available.
    confidence: Optional[float] = None
    model_version_id: Optional[str] = None
    inferred_at: Optional[datetime] = None


class ThreatAssessment(BaseModel):
    """Output of the threat/anomaly engine. Separate from classification
    confidence by design (Phase 1, section 10)."""

    model_config = ConfigDict(use_enum_values=True)

    threat_level: Optional[ThreatLevel] = None
    # Unbounded-by-contract score used for ranking. None => unranked.
    threat_score: Optional[float] = None
    supporting_evidence: list[SupportingEvidence] = Field(default_factory=list)
    assessed_at: Optional[datetime] = None
    engine_version: Optional[str] = None


class ThermalMetrics(BaseModel):
    """Aggregated thermal behaviour of the event. Derived from detections
    only - no interpretation."""

    peak_frp: Optional[float] = None
    latest_frp: Optional[float] = None
    mean_frp: Optional[float] = None
    spatial_extent_km2: Optional[float] = None


class Event(BaseDocument):
    event_id: str

    status: EventStatus = EventStatus.ACTIVE
    data_origin: DataOrigin = DataOrigin.PRODUCTION

    # Geography
    centroid: GeoPoint
    state: Optional[str] = None

    # Lifecycle
    first_detected: datetime
    last_detected: datetime
    detection_count: int = 0
    detection_ids: list[str] = Field(default_factory=list)

    # Interpretation (all optional, all model-produced)
    classification: ClassificationResult = Field(default_factory=ClassificationResult)
    threat: ThreatAssessment = Field(default_factory=ThreatAssessment)
    metrics: ThermalMetrics = Field(default_factory=ThermalMetrics)

    # Facility intelligence is a FEATURE, never a classification rule.
    facility_reference: Optional[str] = None

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class EventSummary(BaseModel):
    """Flattened event shape consumed by the frontend list views."""

    model_config = ConfigDict(protected_namespaces=())

    event_id: str
    status: EventStatus
    data_origin: DataOrigin
    event_type: Optional[EventType] = None
    event_category: Optional[EventCategory] = None
    source_type: Optional[SourceType] = None
    state: Optional[str] = None
    latitude: float
    longitude: float
    first_detected: datetime
    last_detected: datetime
    detection_count: int
    threat_level: Optional[ThreatLevel] = None
    threat_score: Optional[float] = None
    model_confidence: Optional[float] = None

    @classmethod
    def from_event(cls, event: Event) -> "EventSummary":
        return cls(
            event_id=event.event_id,
            status=event.status,
            data_origin=event.data_origin,
            event_type=event.classification.event_type,
            event_category=event.classification.event_category,
            source_type=event.classification.source_type,
            state=event.state,
            latitude=event.centroid.latitude,
            longitude=event.centroid.longitude,
            first_detected=event.first_detected,
            last_detected=event.last_detected,
            detection_count=event.detection_count,
            threat_level=event.threat.threat_level,
            threat_score=event.threat.threat_score,
            model_confidence=event.classification.confidence,
        )


class EventDetail(EventSummary):
    """Everything the Selected Event Intelligence panel needs."""

    supporting_evidence: list[SupportingEvidence] = Field(default_factory=list)
    model_version_id: Optional[str] = None
    peak_frp: Optional[float] = None
    latest_frp: Optional[float] = None
    mean_frp: Optional[float] = None
    spatial_extent_km2: Optional[float] = None
    facility_reference: Optional[str] = None
    # Detection-level enrichment joined for the detail view (None when the
    # detection lacks it). Additive display fields; Event model unchanged.
    lulc_2021_code: Optional[str] = None
    lulc_2021_class: Optional[str] = None
    state_lgd: Optional[str] = None
    nearest_facility_km: Optional[float] = None
    updated_at: datetime

    @classmethod
    def from_event(cls, event: Event, detection: Optional[dict] = None, facility_distance_km: Optional[float] = None) -> "EventDetail":
        base = EventSummary.from_event(event).model_dump()
        detection = detection or {}
        return cls(
            **base,
            supporting_evidence=event.threat.supporting_evidence,
            model_version_id=event.classification.model_version_id,
            peak_frp=event.metrics.peak_frp,
            latest_frp = event.metrics.latest_frp,
            mean_frp=event.metrics.mean_frp,
            spatial_extent_km2=event.metrics.spatial_extent_km2,
            facility_reference=event.facility_reference,
            lulc_2021_code=detection.get("lulc_2021_code"),
            lulc_2021_class=detection.get("lulc_2021_class"),
            state_lgd=detection.get("state_lgd"),
            nearest_facility_km=facility_distance_km,
            updated_at=event.updated_at,
        )


class RegionalOverview(BaseModel):
    """Left panel payload."""

    region: str
    region_kind: str
    status_scope: EventStatus
    total_events: int
    by_event_type: dict[str, int]
    unclassified_events: int
    data_origin_scope: list[DataOrigin]
