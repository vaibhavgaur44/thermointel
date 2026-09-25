"""India industrial / facility intelligence.

Facility type is NOT event type (Phase 1, section 5). This collection exists to
provide ML context features, not classification rules.
"""
from datetime import datetime
from typing import Optional

from pydantic import Field

from models.common import BaseDocument, GeoPoint, utc_now
from models.enums import DataOrigin, SourceType


class Facility(BaseDocument):
    facility_id: str
    name: Optional[str] = None

    location: GeoPoint
    state: Optional[str] = None

    source_type: SourceType = SourceType.UNKNOWN_PERSISTENT_SOURCE

    # Provenance is mandatory for a research-grade dataset.
    dataset_source: Optional[str] = None
    dataset_version: Optional[str] = None
    verified: bool = False

    attributes: dict = Field(default_factory=dict)

    data_origin: DataOrigin = DataOrigin.PRODUCTION
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
