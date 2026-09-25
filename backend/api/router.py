"""Aggregates every /api route group."""
from fastapi import APIRouter

from api.routes import alerts, data, dev, events, ingestion, models, reference

api_router = APIRouter(prefix="/api")

api_router.include_router(events.router)
api_router.include_router(alerts.router)
api_router.include_router(data.router)
api_router.include_router(ingestion.router)
api_router.include_router(models.router)
api_router.include_router(reference.router)
api_router.include_router(dev.router)
