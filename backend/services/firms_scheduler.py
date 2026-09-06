"""
Lightweight hourly NASA FIRMS ingestion scheduler — Task 3.

Uses a single asyncio background task (no APScheduler/Celery/Redis) that
re-runs the existing firms_pipeline.run_firms_ingestion() approximately once
per hour, reusing the same pipeline the manual /api/ingestion/firms endpoint
calls. All state is in-memory for this process only and intentionally resets
on backend restart (no new DB collection, per Task 3 scope).
"""
import asyncio
import logging
import os
from datetime import datetime, timezone

from . import firms_pipeline

logger = logging.getLogger("thermointel.firms_scheduler")

HOURLY_INTERVAL_SECONDS = 3600
SCHEDULED_DAYS = 1

# In-memory only — resets on backend restart, which is acceptable per scope.
INGESTION_STATE = {
    "last_attempt": None,
    "last_success": None,
    "last_result": None,
    "last_error": None,
}

_scheduler_task = None


async def perform_firms_ingestion(db, bbox, region_label: str, days: int = SCHEDULED_DAYS) -> dict:
    """Shared ingestion helper used by BOTH the manual /api/ingestion/firms
    endpoint and the hourly scheduler, so the ingestion logic itself is never
    duplicated. Always records the attempt; records success/result only if
    the pipeline actually completes."""
    key = os.environ.get("FIRMS_API_KEY")
    INGESTION_STATE["last_attempt"] = datetime.now(timezone.utc).isoformat()
    if not key:
        raise RuntimeError("FIRMS_API_KEY is not configured; demo data remains available.")
    result = await firms_pipeline.run_firms_ingestion(db, key, bbox, region_label, days=days)
    INGESTION_STATE["last_success"] = datetime.now(timezone.utc).isoformat()
    INGESTION_STATE["last_result"] = result
    INGESTION_STATE["last_error"] = None
    return result


async def run_scheduled_firms_ingestion(db, bbox, region_label: str = "All India") -> None:
    """One scheduled attempt. Never raises — a failure is logged and recorded
    so the hourly loop keeps running and the next attempt still happens."""
    if not os.environ.get("FIRMS_API_KEY"):
        logger.info("Scheduled FIRMS ingestion skipped: FIRMS_API_KEY is not configured.")
        return
    try:
        result = await perform_firms_ingestion(db, bbox, region_label, days=SCHEDULED_DAYS)
        logger.info("Scheduled FIRMS ingestion complete: %s", {k: result.get(k) for k in ("processed", "inserted", "errors")})
    except Exception as exc:
        key = os.environ.get("FIRMS_API_KEY")
        safe_msg = str(exc).replace(key, "***") if key else str(exc)
        INGESTION_STATE["last_error"] = safe_msg
        logger.error("Scheduled FIRMS ingestion failed: %s", safe_msg)


async def _scheduler_loop(db, bbox, region_label: str):
    while True:
        await run_scheduled_firms_ingestion(db, bbox, region_label)
        await asyncio.sleep(HOURLY_INTERVAL_SECONDS)


def start(db, bbox, region_label: str = "All India"):
    """Idempotent: a repeated FastAPI lifecycle trigger (e.g. hot reload)
    never creates a second concurrent scheduler task."""
    global _scheduler_task
    if _scheduler_task is not None and not _scheduler_task.done():
        return _scheduler_task
    _scheduler_task = asyncio.create_task(_scheduler_loop(db, bbox, region_label))
    return _scheduler_task


async def stop():
    global _scheduler_task
    if _scheduler_task is not None:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
        _scheduler_task = None
