from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from models.enums import EventStatus, EventType, SourceType, TimeRange
from models.event import EventDetail, EventSummary, RegionalOverview
from services import event_service
from services.filters import EventFilters

router = APIRouter(prefix="/events", tags=["events"])


def _filters(
    status: Optional[EventStatus],
    classification: list[EventType],
    source_type: list[SourceType],
    state: Optional[str],
    time_range: Optional[TimeRange],
    include_demo: bool,
) -> EventFilters:
    return EventFilters(
        status=status,
        event_types=classification,
        source_types=source_type,
        state=state,
        time_range=time_range,
        include_demo=include_demo,
    )


@router.get("/summary", response_model=RegionalOverview)
async def get_regional_overview(
    state: Optional[str] = Query(None, description="State / Union Territory name"),
    status: Optional[EventStatus] = EventStatus.ACTIVE,
    classification: list[EventType] = Query(default=[]),
    source_type: list[SourceType] = Query(default=[]),
    time_range: Optional[TimeRange] = None,
    include_demo: bool = False,
):
    """Counts for the Regional Overview panel. Default scope is India."""
    return await event_service.regional_overview(
        _filters(status, classification, source_type, state, time_range, include_demo)
    )


@router.get("/priority", response_model=list[EventSummary])
async def get_priority_events(
    state: Optional[str] = Query(None),
    limit: int = Query(5, ge=1, le=50),
    classification: list[EventType] = Query(default=[]),
    source_type: list[SourceType] = Query(default=[]),
    time_range: Optional[TimeRange] = None,
    include_demo: bool = False,
):
    """Highest-threat ACTIVE events ranked by threat score (not recency)."""
    filters = _filters(
        EventStatus.ACTIVE, classification, source_type, state, time_range, include_demo
    )
    return await event_service.priority_events(filters, limit=limit)


@router.get("", response_model=dict)
async def get_events(
    # Default is ALL statuses: the events list is the exploratory table, so
    # omitting `status` must not silently hide EXPIRED/INACTIVE history
    # (unlike /summary, which scopes to ACTIVE by default, and /priority,
    # which is ACTIVE-only by design).
    status: Optional[EventStatus] = None,
    classification: list[EventType] = Query(default=[]),
    source_type: list[SourceType] = Query(default=[]),
    state: Optional[str] = Query(None),
    time_range: Optional[TimeRange] = None,
    include_demo: bool = False,
    sort_by: str = Query("threat_score", pattern="^(threat_score|last_detected|first_detected|detection_count)$"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    filters = _filters(
        status, classification, source_type, state, time_range, include_demo
    )
    items, total = await event_service.list_events(
        filters, limit=limit, offset=offset, sort_by=sort_by
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{event_id}", response_model=EventDetail)
async def get_event(event_id: str):
    event = await event_service.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event
