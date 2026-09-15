"""Static reference data: operational geography and frozen taxonomy."""
from fastapi import APIRouter

from data.india_regions import INDIA_BBOX, list_regions
from models.enums import (
    EVENT_TYPE_CATEGORY,
    EventCategory,
    EventStatus,
    EventType,
    EvidenceCode,
    SourceType,
    ThreatLevel,
    TimeRange,
)

router = APIRouter(tags=["reference"])


@router.get("/regions")
async def get_regions():
    """India states and Union Territories. Districts are out of scope."""
    return {
        "country": "India",
        "bbox": INDIA_BBOX,
        "regions": list_regions(),
    }


@router.get("/taxonomy")
async def get_taxonomy():
    """The frozen Phase 1 vocabulary, served so the UI never hard-codes it."""
    return {
        "event_categories": [c.value for c in EventCategory],
        "event_types": [
            {
                "value": t.value,
                "category": EVENT_TYPE_CATEGORY[t].value,
            }
            for t in EventType
        ],
        "source_types": [s.value for s in SourceType],
        "threat_levels": [t.value for t in ThreatLevel],
        "event_statuses": [s.value for s in EventStatus],
        "time_ranges": [t.value for t in TimeRange],
        "evidence_codes": [e.value for e in EvidenceCode],
    }
