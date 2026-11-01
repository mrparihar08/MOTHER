# backend/tests/test_background_tasks.py
import time
import pytest
from unittest.mock import patch, MagicMock

from backend.api.tasks.queue import TaskQueue
from backend.api.tasks.handlers import (
    handle_cleanup_expired_storage,
    handle_process_push_deliveries,
    TASK_PROCESS_PUSH_DELIVERIES,
    TASK_CLEANUP_EXPIRED_STORAGE,
)


def test_task_queue_initialization_local():
    """Verify local fallback queue is created when no Redis URL provided."""
    q = TaskQueue(redis_url="")
    assert not q.is_redis_available
    assert q.get_queue_size() == 0


def test_task_queue_register_and_execute():
    """Verify handler registration and task execution."""
    q = TaskQueue(redis_url="")
    executed = []

    def mock_handler(payload):
        executed.append(payload.get("msg"))
        return "ok"

    q.register_handler("test_task", mock_handler)
    res = q._execute_task({"task_name": "test_task", "payload": {"msg": "hello"}})
    assert res == "ok"
    assert executed == ["hello"]


def test_task_queue_debouncing():
    """Verify rapid debounce prevents duplicate tasks from enqueueing."""
    q = TaskQueue(redis_url="")
    q.register_handler("debounced_task", lambda p: None)

    # First enqueue succeeds
    id1 = q.enqueue("debounced_task", {"foo": "bar"}, debounce_seconds=10)
    assert id1 is not None

    # Immediate second enqueue is debounced
    id2 = q.enqueue("debounced_task", {"foo": "bar"}, debounce_seconds=10)
    assert id2 is None


def test_task_queue_local_worker_execution():
    """Verify in-process bounded worker pool picks up and processes tasks."""
    q = TaskQueue(redis_url="")
    results = []

    def test_handler(payload):
        results.append(payload.get("value"))

    q.register_handler("async_test", test_handler)
    q.enqueue("async_test", {"value": 42})

    # Give local worker thread a short moment to process
    time.sleep(0.3)
    assert 42 in results
    q.shutdown()


def test_push_delivery_handler():
    """Verify push delivery task handler invokes process_pending_deliveries."""
    with patch("backend.api.services.push_worker.process_pending_deliveries", return_value=5) as mock_push:
        res = handle_process_push_deliveries({"max_batch": 25})
        assert res == 5
        mock_push.assert_called_once_with(max_batch=25)


def test_cleanup_expired_storage_handler():
    """Verify storage cleanup handler invokes cleanup_expired_files."""
    with patch("backend.presentation.services.cleanup_service.cleanup_expired_files", return_value={"deleted_files": 2, "reclaimed_bytes": 1024}) as mock_cleanup:
        res = handle_cleanup_expired_storage({"max_age_hours": 12})
        assert res["deleted_files"] == 2
        mock_cleanup.assert_called_once_with(max_age_hours=12)


def test_redis_queue_mocked():
    """Verify Redis enqueue and pop when redis client is active."""
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.llen.return_value = 1

    with patch("redis.Redis.from_url", return_value=mock_redis):
        q = TaskQueue(redis_url="redis://localhost:6379/0")
        assert q.is_redis_available

        task_id = q.enqueue("sample_task", {"test": True})
        assert task_id is not None
        mock_redis.rpush.assert_called_once()
