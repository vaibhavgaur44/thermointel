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
from services.startup_catchup import cancel_catchup, maybe_trigger_startup_catchup

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
    # Startup freshness/catch-up: non-blocking (fast Mongo read here; the
    # ingestion itself runs in a background task - see
    # services/startup_catchup.py). Must never prevent app startup.
    try:
        await maybe_trigger_startup_catchup()
    except Exception as exc:  # pragma: no cover - startup must never hard-fail
        logger.error("Startup catch-up check failed: %s", exc)
    yield
    await cancel_catchup()
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
    # Explicit origin allow-list (never "*"). The deployed frontend and
    # localhost dev origins are guaranteed so a bad/missing CORS_ORIGINS env
    # value cannot lock the dashboard out again.
    allow_origins=settings.required_cors_origins(),
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
