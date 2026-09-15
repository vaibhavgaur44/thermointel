"""Read-side event services. Retrieval and filtering only - no intelligence."""
from typing import Optional

from core.database import Collections, get_db
from models.enums import EventStatus, EventType
from models.event import Event, EventDetail, EventSummary, RegionalOverview
from services.filters import EventFilters

SORT_FIELDS = {
    "threat_score": "threat.threat_score",
    "last_detected": "last_detected",
    "first_detected": "first_detected",
    "detection_count": "detection_count",
}


async def list_events(
    filters: EventFilters,
    limit: int = 200,
    offset: int = 0,
    sort_by: str = "threat_score",
) -> tuple[list[EventSummary], int]:
    db = get_db()
    query = filters.to_query()
    sort_field = SORT_FIELDS.get(sort_by, SORT_FIELDS["threat_score"])

    total = await db[Collections.EVENTS].count_documents(query)
    cursor = (
        db[Collections.EVENTS]
        .find(query)
        .sort([(sort_field, -1), ("last_detected", -1)])
        .skip(offset)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    return [EventSummary.from_event(Event.from_mongo(d)) for d in docs], total


async def get_event(event_id: str) -> Optional[EventDetail]:
    db = get_db()
    doc = await db[Collections.EVENTS].find_one({"event_id": event_id})
    if doc is None:
        return None
    return EventDetail.from_event(Event.from_mongo(doc))


async def priority_events(filters: EventFilters, limit: int = 5) -> list[EventSummary]:
    """Top-N highest-threat ACTIVE events, ranked by threat score.

    Deliberately NOT 'most recent'. Events with no threat score yet sort last
    (BSON orders null below numbers), so real assessments always win.
    """
    items, _ = await list_events(filters, limit=limit, offset=0, sort_by="threat_score")
    return items


async def regional_overview(filters: EventFilters) -> RegionalOverview:
    db = get_db()
    query = filters.to_query()

    pipeline = [
        {"$match": query},
        {"$group": {"_id": "$classification.event_type", "count": {"$sum": 1}}},
    ]
    rows = await db[Collections.EVENTS].aggregate(pipeline).to_list(length=50)

    by_type = {t.value: 0 for t in EventType}
    unclassified = 0
    total = 0
    for row in rows:
        total += row["count"]
        key = row["_id"]
        if key is None:
            unclassified += row["count"]
        else:
            by_type[key] = by_type.get(key, 0) + row["count"]

    return RegionalOverview(
        region=filters.state or "India",
        region_kind="REGION" if filters.state else "COUNTRY",
        status_scope=filters.status or EventStatus.ACTIVE,
        total_events=total,
        by_event_type=by_type,
        unclassified_events=unclassified,
        data_origin_scope=filters.data_origins(),
    )
