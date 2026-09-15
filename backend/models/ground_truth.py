"""Verified training / evaluation labels (Phase 3 deliverable).

Phase 2 only defines the schema. No labels are generated here, and heuristic
pseudo-labels are explicitly forbidden by the specification.
"""
from datetime import datetime
from typing import Optional

from pydantic import Field

from models.common import BaseDocument, GeoPoint, utc_now
from models.enums import EventCategory, EventType, SourceType


class GroundTruthLabel(BaseDocument):
    label_id: str

    location: GeoPoint
    state: Optional[str] = None
    observed_from: Optional[datetime] = None
    observed_to: Optional[datetime] = None

    event_category: Optional[EventCategory] = None
    event_type: Optional[EventType] = None
    source_type: Optional[SourceType] = None

    # Evidence trail - a label without evidence is not usable.
    evidence_source: Optional[str] = None
    evidence_url: Optional[str] = None
    labelled_by: Optional[str] = None
    label_notes: Optional[str] = None

    # train / validation / test. Kept free-form so leakage-aware splitting
    # strategies can be decided in Phase 4.
    split: Optional[str] = None
    split_strategy: Optional[str] = None

    linked_event_id: Optional[str] = None
    linked_detection_ids: list[str] = Field(default_factory=list)

    dataset_version: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
