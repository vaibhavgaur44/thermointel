"""Development-only routes for the clearly labelled DEMO dataset.

Disabled entirely when ALLOW_DEMO_DATA is false.
"""
from fastapi import APIRouter, HTTPException

from core.config import settings
from dev import demo_dataset

router = APIRouter(prefix="/dev/demo-data", tags=["development"])

_WARNING = (
    "DEVELOPMENT DATA ONLY. Not FIRMS observations, not model output, "
    "not a threat assessment."
)


def _guard():
    if not settings.ALLOW_DEMO_DATA:
        raise HTTPException(status_code=403, detail="Demo data is disabled on this deployment.")


@router.get("/status")
async def demo_status():
    return {
        "allowed": settings.ALLOW_DEMO_DATA,
        "warning": _WARNING,
        "counts": await demo_dataset.status() if settings.ALLOW_DEMO_DATA else {},
    }


@router.post("/seed")
async def demo_seed():
    _guard()
    result = await demo_dataset.seed()
    return {**result, "warning": _WARNING}


@router.delete("/clear")
async def demo_clear():
    _guard()
    return await demo_dataset.clear()
