"""
Focused unit tests for backend/services/firms_scheduler.py — Task 3.

Verifies the hourly scheduling mechanism (asyncio background task, no
APScheduler/Celery/Redis) without any live NASA FIRMS request or live
MongoDB — network/DB calls are mocked out via patching
services.firms_pipeline.run_firms_ingestion directly.
"""
import asyncio
import os
import sys
from unittest.mock import patch, AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services import firms_scheduler

BBOX = (68.0, 6.0, 98.0, 38.0)
REGION_LABEL = "All India"


def setup_function(_):
    # Reset in-memory state + scheduler task between tests.
    firms_scheduler.INGESTION_STATE.update(last_attempt=None, last_success=None, last_result=None, last_error=None)
    firms_scheduler._scheduler_task = None


def test_scheduled_ingestion_skips_when_firms_api_key_missing(monkeypatch):
    monkeypatch.delenv("FIRMS_API_KEY", raising=False)
    with patch("services.firms_scheduler.firms_pipeline.run_firms_ingestion", new=AsyncMock()) as mock_run:
        asyncio.run(firms_scheduler.run_scheduled_firms_ingestion(db=object(), bbox=BBOX, region_label=REGION_LABEL))
    mock_run.assert_not_called()
    assert firms_scheduler.INGESTION_STATE["last_success"] is None


def test_scheduled_ingestion_calls_pipeline_with_all_india_and_days_1(monkeypatch):
    monkeypatch.setenv("FIRMS_API_KEY", "test-secret-key")
    fake_db = object()
    with patch("services.firms_scheduler.firms_pipeline.run_firms_ingestion", new=AsyncMock(return_value={"status": "complete", "processed": 3, "inserted": 3, "errors": 0})) as mock_run:
        asyncio.run(firms_scheduler.run_scheduled_firms_ingestion(db=fake_db, bbox=BBOX, region_label=REGION_LABEL))
    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    call_args = args + tuple(kwargs.values())
    assert "test-secret-key" in call_args
    assert BBOX in call_args
    assert REGION_LABEL in call_args
    assert 1 in call_args  # days=1


def test_successful_scheduled_run_updates_last_run(monkeypatch):
    monkeypatch.setenv("FIRMS_API_KEY", "test-secret-key")
    with patch("services.firms_scheduler.firms_pipeline.run_firms_ingestion", new=AsyncMock(return_value={"status": "complete", "processed": 1, "inserted": 1, "errors": 0})):
        assert firms_scheduler.INGESTION_STATE["last_success"] is None
        asyncio.run(firms_scheduler.run_scheduled_firms_ingestion(db=object(), bbox=BBOX, region_label=REGION_LABEL))
    assert firms_scheduler.INGESTION_STATE["last_success"] is not None
    assert firms_scheduler.INGESTION_STATE["last_attempt"] is not None
    assert firms_scheduler.INGESTION_STATE["last_result"]["inserted"] == 1


def test_failed_scheduled_run_does_not_raise_and_records_error(monkeypatch):
    monkeypatch.setenv("FIRMS_API_KEY", "test-secret-key")
    with patch("services.firms_scheduler.firms_pipeline.run_firms_ingestion", new=AsyncMock(side_effect=RuntimeError("FIRMS request failed: connection reset"))):
        # Must not raise — the hourly loop has to survive this.
        asyncio.run(firms_scheduler.run_scheduled_firms_ingestion(db=object(), bbox=BBOX, region_label=REGION_LABEL))
    assert firms_scheduler.INGESTION_STATE["last_success"] is None
    assert firms_scheduler.INGESTION_STATE["last_error"] is not None
    assert firms_scheduler.INGESTION_STATE["last_attempt"] is not None


def test_scheduled_error_message_never_contains_the_api_key(monkeypatch):
    secret = "TOP-SECRET-FIRMS-KEY"
    monkeypatch.setenv("FIRMS_API_KEY", secret)
    with patch("services.firms_scheduler.firms_pipeline.run_firms_ingestion", new=AsyncMock(side_effect=RuntimeError(f"request to .../{secret}/... failed"))):
        asyncio.run(firms_scheduler.run_scheduled_firms_ingestion(db=object(), bbox=BBOX, region_label=REGION_LABEL))
    assert secret not in firms_scheduler.INGESTION_STATE["last_error"]
    assert "***" in firms_scheduler.INGESTION_STATE["last_error"]


def test_start_is_idempotent_and_does_not_create_duplicate_tasks():
    async def _run():
        task1 = firms_scheduler.start(db=object(), bbox=BBOX, region_label=REGION_LABEL)
        task2 = firms_scheduler.start(db=object(), bbox=BBOX, region_label=REGION_LABEL)
        assert task1 is task2
        await firms_scheduler.stop()

    asyncio.run(_run())


def test_stop_cancels_the_running_task_cleanly():
    async def _run():
        firms_scheduler.start(db=object(), bbox=BBOX, region_label=REGION_LABEL)
        await firms_scheduler.stop()
        assert firms_scheduler._scheduler_task is None

    asyncio.run(_run())


def test_perform_firms_ingestion_raises_when_key_missing(monkeypatch):
    monkeypatch.delenv("FIRMS_API_KEY", raising=False)
    try:
        asyncio.run(firms_scheduler.perform_firms_ingestion(db=object(), bbox=BBOX, region_label=REGION_LABEL))
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "not configured" in str(exc)
    # attempt timestamp is still recorded even when the key is missing
    assert firms_scheduler.INGESTION_STATE["last_attempt"] is not None
