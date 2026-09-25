"""ThermoIntel v2 - FastAPI application entry point.

FastAPI is the orchestrator/middleman between MongoDB and the React/Cesium
frontend. No classification, threat or anomaly logic lives in the frontend.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from api.router import api_router
from core.config import settings
from core.database import close_db, ensure_indexes, get_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("thermointel")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        await ensure_indexes()
    except Exception as exc:  # pragma: no cover - startup must never hard-fail
        logger.error("Index creation failed: %s", exc)
    yield
    await close_db()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="India-only thermal-event intelligence platform (Phase 2 foundation).",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    database = "unavailable"
    try:
        await get_db().command("ping")
        database = "connected"
    except Exception as exc:
        logger.warning("Mongo ping failed: %s", exc)

    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "operational_scope": settings.OPERATIONAL_COUNTRY,
        "database": database,
        "phase": "Phase 2 - application foundation",
    }


app.include_router(api_router)
