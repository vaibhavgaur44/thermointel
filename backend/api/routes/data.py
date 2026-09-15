from typing import Optional

from fastapi import APIRouter, Query

from models.enums import SourceType, TimeRange
from services import registry_service

router = APIRouter(tags=["data"])


@router.get("/facilities", response_model=dict)
async def get_facilities(
    state: Optional[str] = Query(None),
    source_type: list[SourceType] = Query(default=[]),
    include_demo: bool = False,
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
):
    items, total = await registry_service.list_facilities(
        state=state,
        source_types=source_type,
        include_demo=include_demo,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/thermal-detections", response_model=dict)
async def get_thermal_detections(
    state: Optional[str] = Query(None),
    event_id: Optional[str] = Query(None),
    time_range: Optional[TimeRange] = None,
    include_demo: bool = False,
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    """Raw FIRMS observations, exactly as ingested."""
    items, total = await registry_service.list_detections(
        state=state,
        event_id=event_id,
        time_range=time_range,
        include_demo=include_demo,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}
