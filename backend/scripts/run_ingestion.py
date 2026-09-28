"""Render Cron Job entrypoint for the Phase 5 production pipeline.

Runs the SAME pipeline as POST /api/ingestion/run by calling the existing
API implementation (``api.routes.ingestion.run_ingestion``) directly — no
pipeline logic is duplicated and no behavior can drift between the manual
endpoint and the scheduled trigger.

Why a script and not an in-process scheduler: the web service runs on the
Render free plan, where instances restart, redeploy and sleep on idle. A
loop inside the web process is therefore not a reliable production
scheduler. Render Cron Jobs run as separate scheduled processes and are the
platform-appropriate mechanism (see render.yaml at the repo root).

Setup performed here (mirrors server.py startup, nothing more):
  - load backend/.env (local convenience; Render injects real env vars)
  - create MongoDB indexes exactly as the web service does
  - call the existing run_ingestion() with triggered_by="render-cron" and
    the configured default window
  - close the Mongo client cleanly

Exit codes (visible in the Render cron Runs log):
  0 - pipeline returned a run record with overall status SUCCEEDED/PARTIAL
      (PARTIAL is a completed run with degraded sources — reported, not hidden)
  1 - the run FAILED, the entrypoint itself crashed, or FIRMS/models are
      not configured. Never exits 0 for a hidden failure.
"""

import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

from api.routes.ingestion import run_ingestion  # noqa: E402
from core.config import settings  # noqa: E402
from core.database import close_db, ensure_indexes  # noqa: E402
from models.enums import IngestionStatus  # noqa: E402

DEFAULT_WINDOW_HOURS = 24


def _configured() -> tuple[bool, str | None]:
    """Same requirement as the pipeline's own firms_configured gate.

    ACTIVE_MODEL_VERSION is deliberately NOT required: the frozen Phase 4
    artifacts load independently and pin their own model_version_id; the
    setting only feeds GET /api/ingestion/status. Its presence is reported
    truthfully in the run log instead of blocking ingestion.
    """
    missing = []
    if not settings.FIRMS_API_KEY:
        missing.append("FIRMS_API_KEY")
    if not settings.FIRMS_BASE_URL:
        missing.append("FIRMS_BASE_URL")
    return (not missing), (", ".join(missing) if missing else None)


async def main() -> int:
    ok, missing = _configured()
    if not ok:
        print(
            "FIRMS cron run ABORTED - not configured (missing: "
            f"{missing}). No pipeline run was started.",
            flush=True,
        )
        return 1

    print(
        "Scheduled FIRMS pipeline starting "
        f"(triggered_by=render-cron, window={DEFAULT_WINDOW_HOURS}h, "
        f"active_model_version={settings.ACTIVE_MODEL_VERSION or 'unset'}).",
        flush=True,
    )

    await ensure_indexes()

    try:
        run = await run_ingestion(
            window_hours=DEFAULT_WINDOW_HOURS,
            triggered_by="render-cron",
        )
    finally:
        await close_db()

    status = str(run.get("status"))
    print(
        f"Run {run.get('run_id')} finished with status {status}.",
        flush=True,
    )
    for stage in run.get("stages", []):
        print(f"  [{stage.get('status')}] {stage.get('stage')}: {stage.get('message')}", flush=True)
    if run.get("error"):
        print(f"  error: {run['error']}", flush=True)

    if status in (
        IngestionStatus.SUCCEEDED.value,
        IngestionStatus.PARTIAL.value,
    ):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
