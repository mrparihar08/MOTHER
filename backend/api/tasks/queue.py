# backend/api/tasks/queue.py
from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
import uuid
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("TaskQueue")

REDIS_URL = os.getenv("REDIS_URL", "").strip()
REDIS_QUEUE_KEY = os.getenv("REDIS_QUEUE_KEY", "mother:task_queue")
REDIS_JOB_PREFIX = os.getenv("REDIS_JOB_PREFIX", "mother:job:")
MAX_INPROCESS_QUEUE_SIZE = int(os.getenv("MAX_TASK_QUEUE_SIZE", "1000"))
NUM_LOCAL_WORKERS = int(os.getenv("NUM_LOCAL_WORKERS", "2"))
JOB_TTL_SECONDS = int(os.getenv("JOB_TTL_SECONDS", "86400"))  # 24 hours


class TaskQueue:
    """
    Hybrid Task Queue supporting:
    1. Redis-backed reliable queue for distributed, dedicated workers (when REDIS_URL is present).
    2. Bounded, rate-limited threadpool queue for standalone/local mode (when REDIS_URL is absent).
    3. Job status tracking (queued, processing, completed, failed) with TTL.
    """

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url if redis_url is not None else REDIS_URL
        self._redis_client = None
        self._handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        self._last_executed: Dict[str, float] = {}
        self._debounce_lock = threading.Lock()

        # In-process bounded queue & job store for non-Redis mode
        self._local_queue: queue.Queue = queue.Queue(maxsize=MAX_INPROCESS_QUEUE_SIZE)
        self._local_jobs: Dict[str, Dict[str, Any]] = {}
        self._jobs_lock = threading.Lock()
        self._workers_started = False
        self._workers_lock = threading.Lock()
        self._shutdown_event = threading.Event()

        self._init_backend()

    def _init_backend(self):
        if self.redis_url:
            try:
                import redis
                self._redis_client = redis.Redis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=3,
                    socket_timeout=5,
                )
                self._redis_client.ping()
                logger.info("Connected to Redis Task Queue at %s", self.redis_url.split("@")[-1])
            except Exception as exc:
                logger.warning(
                    "Failed to connect to Redis (%s). Falling back to bounded in-memory worker queue.",
                    exc,
                )
                self._redis_client = None

    @property
    def is_redis_available(self) -> bool:
        if self._redis_client is None:
            return False
        try:
            self._redis_client.ping()
            return True
        except Exception:
            return False

    def register_handler(self, task_name: str, handler: Callable[[Dict[str, Any]], Any]) -> None:
        """Register a callable worker handler for a given task name."""
        self._handlers[task_name] = handler
        logger.debug("Registered task handler for '%s'", task_name)

    def _ensure_local_workers(self) -> None:
        with self._workers_lock:
            if not self._workers_started and self._redis_client is None:
                for i in range(NUM_LOCAL_WORKERS):
                    thread = threading.Thread(
                        target=self._local_worker_loop,
                        name=f"BoundedTaskWorker-{i+1}",
                        daemon=True,
                    )
                    thread.start()
                self._workers_started = True
                logger.info("Started %d bounded background task workers", NUM_LOCAL_WORKERS)

    def _local_worker_loop(self) -> None:
        while not self._shutdown_event.is_set():
            try:
                task_item = self._local_queue.get(timeout=1.0)
                if task_item is None:
                    break
                self._execute_task(task_item)
                self._local_queue.task_done()
            except queue.Empty:
                continue
            except Exception as exc:
                logger.error("Unexpected error in local task worker: %s", exc, exc_info=True)

    # ==========================================================
    # JOB STATUS TRACKING
    # ==========================================================
    def set_job_status(
        self,
        job_id: str,
        status: str,
        progress: int = 0,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        """Set job state in Redis or local store."""
        now = time.time()
        job_data: Dict[str, Any] = {
            "job_id": job_id,
            "status": status,
            "progress": progress,
            "updated_at": now,
        }
        if result is not None:
            job_data["result"] = result
        if error is not None:
            job_data["error"] = error

        if self._redis_client is not None:
            try:
                key = f"{REDIS_JOB_PREFIX}{job_id}"
                self._redis_client.set(key, json.dumps(job_data), ex=JOB_TTL_SECONDS)
                return
            except Exception as exc:
                logger.warning("Failed to set job status in Redis (%s): %s", job_id, exc)

        with self._jobs_lock:
            if job_id not in self._local_jobs:
                job_data["created_at"] = now
            else:
                job_data["created_at"] = self._local_jobs[job_id].get("created_at", now)
            self._local_jobs[job_id] = job_data

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Fetch current job state."""
        if self._redis_client is not None:
            try:
                key = f"{REDIS_JOB_PREFIX}{job_id}"
                raw = self._redis_client.get(key)
                if raw:
                    return json.loads(raw)
            except Exception as exc:
                logger.warning("Failed to fetch job status from Redis (%s): %s", job_id, exc)

        with self._jobs_lock:
            return self._local_jobs.get(job_id)

    def _execute_task(self, task_data: Dict[str, Any]) -> Any:
        task_name = task_data.get("task_name")
        payload = task_data.get("payload", {})
        task_id = task_data.get("task_id", "unknown")
        job_id = payload.get("job_id", task_id)

        handler = self._handlers.get(task_name)
        if not handler:
            logger.warning("No handler registered for task '%s' (task_id=%s)", task_name, task_id)
            self.set_job_status(job_id, status="failed", error=f"No handler for {task_name}")
            return None

        t0 = time.time()
        try:
            logger.info("Executing task '%s' (task_id=%s, job_id=%s)", task_name, task_id, job_id)
            self.set_job_status(job_id, status="processing", progress=25)

            result = handler(payload)
            elapsed = time.time() - t0

            # Package result dict if not already
            res_dict = result if isinstance(result, dict) else {"data": result}
            self.set_job_status(job_id, status="completed", progress=100, result=res_dict)

            logger.info("Completed task '%s' (task_id=%s) in %.3fs", task_name, task_id, elapsed)
            return result
        except Exception as exc:
            elapsed = time.time() - t0
            err_msg = str(exc)
            logger.error(
                "Task '%s' (task_id=%s) failed after %.3fs: %s",
                task_name,
                task_id,
                err_msg,
                exc_info=True,
            )
            self.set_job_status(job_id, status="failed", error=err_msg)
            raise

    def enqueue(
        self,
        task_name: str,
        payload: Optional[Dict[str, Any]] = None,
        debounce_seconds: Optional[int] = None,
    ) -> Optional[str]:
        """
        Enqueue a task for execution.
        Supports optional debouncing and custom job_id tracking.
        """
        now = time.time()
        if debounce_seconds:
            with self._debounce_lock:
                last_time = self._last_executed.get(task_name, 0.0)
                if (now - last_time) < debounce_seconds:
                    logger.debug(
                        "Task '%s' debounced (ran %.1fs ago, debounce=%ds)",
                        task_name,
                        now - last_time,
                        debounce_seconds,
                    )
                    return None
                self._last_executed[task_name] = now

        payload = payload or {}
        task_id = payload.get("job_id") or str(uuid.uuid4())
        payload["job_id"] = task_id

        task_item = {
            "task_id": task_id,
            "task_name": task_name,
            "payload": payload,
            "enqueued_at": now,
        }

        # Initialize queued status
        self.set_job_status(task_id, status="queued", progress=0)

        # 1. Try Redis Queue first if available
        if self._redis_client is not None:
            try:
                self._redis_client.rpush(REDIS_QUEUE_KEY, json.dumps(task_item))
                logger.info("Enqueued task '%s' (id=%s) to Redis queue", task_name, task_id)
                return task_id
            except Exception as exc:
                logger.warning("Redis enqueue failed (%s). Falling back to bounded local queue.", exc)

        # 2. Fallback to Bounded In-Memory Queue
        self._ensure_local_workers()
        try:
            self._local_queue.put_nowait(task_item)
            logger.info("Enqueued task '%s' (id=%s) to bounded local queue", task_name, task_id)
            return task_id
        except queue.Full:
            logger.error("Bounded task queue is full (%d items)! Dropping task '%s'", MAX_INPROCESS_QUEUE_SIZE, task_name)
            self.set_job_status(task_id, status="failed", error="Queue full")
            return None

    def pop_task(self, timeout: int = 2) -> Optional[Dict[str, Any]]:
        """Pop next task from Redis queue (blocking). Used by dedicated worker daemon."""
        if self._redis_client is None:
            try:
                return self._local_queue.get(timeout=timeout)
            except queue.Empty:
                return None

        try:
            item = self._redis_client.blpop(REDIS_QUEUE_KEY, timeout=timeout)
            if item:
                _, task_json = item
                return json.loads(task_json)
        except Exception as exc:
            logger.warning("Error popping from Redis task queue: %s", exc)
        return None

    def get_queue_size(self) -> int:
        if self._redis_client is not None:
            try:
                return int(self._redis_client.llen(REDIS_QUEUE_KEY))
            except Exception:
                pass
        return self._local_queue.qsize()

    def shutdown(self, timeout: float = 3.0) -> None:
        self._shutdown_event.set()


# Global Singleton Task Queue
task_queue = TaskQueue()
