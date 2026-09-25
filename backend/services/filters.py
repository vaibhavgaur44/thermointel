"""Query-filter construction shared by the read endpoints.

All filtering happens here (backend), never in React.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from models.enums import (
    TIME_RANGE_SECONDS,
    DataOrigin,
    EventStatus,
    EventType,
    SourceType,
    TimeRange,
)


@dataclass
class EventFilters:
    status: Optional[EventStatus] = EventStatus.ACTIVE
    event_types: list[EventType] = field(default_factory=list)
    source_types: list[SourceType] = field(default_factory=list)
    state: Optional[str] = None
    time_range: Optional[TimeRange] = None
    include_demo: bool = False
    only_demo: bool = False

    def data_origins(self) -> list[DataOrigin]:
        if self.only_demo:
            return [DataOrigin.DEMO]
        if self.include_demo:
            return [DataOrigin.PRODUCTION, DataOrigin.DEMO]
        return [DataOrigin.PRODUCTION]

    def to_query(self, time_field: str = "last_detected") -> dict:
        query: dict = {
            "data_origin": {"$in": [o.value for o in self.data_origins()]}
        }
        if self.status is not None:
            query["status"] = self.status.value
        if self.event_types:
            query["classification.event_type"] = {
                "$in": [t.value for t in self.event_types]
            }
        if self.source_types:
            query["classification.source_type"] = {
                "$in": [t.value for t in self.source_types]
            }
        if self.state:
            # Case-insensitive match: production state values come from the
            # SOI shapefile join (Phase 3), while the frontend sends names
            # from the regions list. Compare case-insensitively so 'rajasthan'
            # and 'Rajasthan' resolve to the same filtered set without
            # rewriting stored production data.
            query["state"] = {
                "$regex": "^" + re.escape(self.state) + "$",
                "$options": "i",
            }
        if self.time_range is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(
                seconds=TIME_RANGE_SECONDS[self.time_range]
            )
            query[time_field] = {"$gte": cutoff}
        return query
