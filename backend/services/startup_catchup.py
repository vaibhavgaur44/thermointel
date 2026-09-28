"""Startup freshness/catch-up trigger for the Phase 5 production pipeline.

Render free-tier instances restart, redeploy and sleep. The Render Cron Job
remains the guaranteed scheduler; this module adds one extra safety net: when
the backend process starts, check whether the latest SUCCESSFUL/PARTIAL
ingestion is older than FRESHNESS_THRESHOLD_HOURS and, if so, run the
EXISTING pipeline once in the background.

Strictly non-blocking and non-recurring:
  - the freshness check is a single fast MongoDB read awaited during startup
  - the ingestion itself is dispatched with asyncio.create_task, so FastAPI
    becomes ready normally and never waits for FIRMS/ML processing
  - no loop, no sleep, no polling: at most one catch-up per process start

Duplicate protection: a module-level task reference (idempotent start, same
pattern as the v1 scheduler's start()) plus an asyncio.Lock serializing the
check-and-spawn section, so concurrent/hot-reload startup calls can never
launch two simultaneous catch-up runs.

No pipeline logic lives here: the run is performed by the SAME
api.routes.ingestion.run_ingestion() implementation the manual
POST /api/ingestion/run endpoint uses, with triggered_by="startup-catchup".
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from api.routes.ingestion import run_ingestion
from core.database import Collections, get_db
from models.enums import IngestionStatus
from pipeline import firms_ingestion

logger = logging.getLogger("thermointel.startup_catchup")

FRESHNESS_THRESHOLD_HOURS = 6.0
CATCHUP_WINDOW_HOURS = 24
CATCHUP_TRIGGERED_BY = "startup-catchup"

# Statuses that count as "the data was actually produced recently".
_FRESH_STATUSES = [IngestionStatus.SUCCEEDED, IngestionStatus.PARTIAL]

_catchup_task: Optional[asyncio.Task] = None
_spawn_lock = asyncio.Lock()


def _as_utc(dt: datetime) -> datetime:
    """Motor returns naive UTC datetimes (client has no tz_aware=True);
    treat naive values as UTC and keep aware ones as they are."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def _latest_successful_started_at() -> Optional[datetime]:
    """started_at of the newest SUCCEEDED/PARTIAL ingestion run, else None."""
    doc = (
        await get_db()[Collections.INGESTION_RUNS]
        .find(
            {"status": {"$in": [status.value for status in _FRESH_STATUSES]}},
            {"started_at": 1, "run_id": 1, "triggered_by": 1, "_id": 0},
        )
        .sort([("started_at", -1)])
        .limit(1)
        .to_list(length=1)
    )
    if not doc:
        return None
    started_at = doc[0].get("started_at")
    if not isinstance(started_at, datetime):
        return None
    return _as_utc(started_at)


async def _catchup() -> None:
    """One background catch-up ingestion via the EXISTING pipeline entry."""
    try:
        logger.info(
            "Startup catch-up: triggering Phase 5 pipeline "
            "(triggered_by=%s, window_hours=%s).",
            CATCHUP_TRIGGERED_BY,
            CATCHUP_WINDOW_HOURS,
        )
        run = await run_ingestion(
            window_hours=CATCHUP_WINDOW_HOURS,
            triggered_by=CATCHUP_TRIGGERED_BY,
        )
        logger.info(
            "Startup catch-up finished: run_id=%s status=%s detections=%s.",
            run.get("run_id"),
            run.get("status"),
            run.get("detections_ingested"),
        )
    except Exception:
        # A failed catch-up must never crash the application or the loop.
        logger.exception("Startup catch-up ingestion FAILED.")


async def _maybe_spawn_catchup() -> bool:
    """Freshness check + guarded spawn. Returns True if a run was spawned."""
    global _catchup_task

    # Idempotent guard: an in-flight catch-up is never duplicated.
    if _catchup_task is not None and not _catchup_task.done():
        logger.info(
            "Startup catch-up already in flight; skipping freshness trigger."
        )
        return False

    if not firms_ingestion.is_configured():
        logger.info(
            "Startup freshness check skipped: NASA FIRMS is not configured."
        )
        return False

    latest = await _latest_successful_started_at()
    now = datetime.now(timezone.utc)

    if latest is None:
        logger.info(
            "Startup freshness check: no previous SUCCEEDED/PARTIAL "
            "ingestion run found."
        )
    else:
        age_hours = (now - latest).total_seconds() / 3600.0
        logger.info(
            "Startup freshness check: latest successful run started_at=%s "
            "(age %.2fh, threshold %.1fh).",
            latest.isoformat(),
            age_hours,
            FRESHNESS_THRESHOLD_HOURS,
        )
        if age_hours < FRESHNESS_THRESHOLD_HOURS:
            logger.info(
                "Startup freshness check: data is FRESH; no catch-up needed."
            )
            return False

    logger.info(
        "Startup freshness check: data is STALE (or absent); catch-up "
        "required."
    )
    _catchup_task = asyncio.create_task(_catchup())
    return True


async def maybe_trigger_startup_catchup() -> bool:
    """Public entry for the FastAPI lifespan. Awaitable and fast: performs
    only the freshness read here; the ingestion runs in a background task.
    Concurrent startup calls are serialized and deduplicated."""
    logger.info("Startup freshness check begins.")
    try:
        async with _spawn_lock:
            return await _maybe_spawn_catchup()
    except Exception:
        # A failed freshness check must never prevent the app from starting.
        logger.exception(
            "Startup freshness check failed; no catch-up was triggered."
        )
        return False


async def cancel_catchup() -> None:
    """Best-effort cancel on shutdown so a mid-run catch-up does not leave
    dangling tasks when the process is stopped/redeployed."""
    global _catchup_task
    if _catchup_task is not None and not _catchup_task.done():
        logger.info("Cancelling in-flight startup catch-up (shutdown).")
        _catchup_task.cancel()
        try:
            await _catchup_task
        except asyncio.CancelledError:
            pass
    _catchup_task = None
