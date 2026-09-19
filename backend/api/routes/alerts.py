from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from models.alert import AlertSummary
from models.enums import AlertStatus, SourceType, TimeRange
from services import registry_service

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=dict)
async def get_alerts(
    status: Optional[AlertStatus] = AlertStatus.OPEN,
    state: Optional[str] = Query(None),
    classification: Optional[list[str]] = Query(None),
    source_type: Optional[list[str]] = Query(None),
    time_range: Optional[str] = Query(None),
    include_demo: bool = False,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    items, total = await registry_service.list_alerts(
        status=status,
        state=state,
        classifications=classification,
        source_types=[SourceType(value) for value in source_type] if source_type else None,
        time_range=TimeRange(time_range) if time_range else None,
        include_demo=include_demo,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{alert_id}", response_model=AlertSummary)
async def get_alert(alert_id: str):
    alert = await registry_service.get_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert
