# backend/api/tasks/worker.py
"""
Dedicated Background Worker Daemon for MOTHER.
Processes background tasks (push notifications, storage cleanup, ML jobs)
out-of-process, preventing API server thread starvation and latency spikes.

Usage:
    python -m backend.api.tasks.worker          # Continuous daemon
    python -m backend.api.tasks.worker --once   # Run pending tasks once and exit (for Cron)
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time

# Ensure task handlers are registered
import backend.api.tasks.handlers  # noqa: F401
from backend.api.tasks.queue import task_queue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Worker] %(message)s",
)
logger = logging.getLogger("WorkerDaemon")

running = True


def _signal_handler(signum, frame):
    global running
    logger.info("Received termination signal (%d). Initiating graceful shutdown...", signum)
    running = False
    task_queue.shutdown()


def run_worker(once: bool = False, poll_timeout: int = 2) -> None:
    signal.signal(signal.SIGINT, _signal_handler)
    try:
        signal.signal(signal.SIGTERM, _signal_handler)
    except AttributeError:
        pass  # Windows may not have SIGTERM

    backend_type = "Redis" if task_queue.is_redis_available else "Local In-Memory Queue"
    logger.info("Starting MOTHER Dedicated Task Worker (Backend: %s, mode: %s)", backend_type, "single-pass" if once else "daemon")

    processed_tasks = 0

    while running:
        try:
            task_data = task_queue.pop_task(timeout=poll_timeout)
            if task_data:
                try:
                    task_queue._execute_task(task_data)
                    processed_tasks += 1
                except Exception as task_err:
                    logger.error("Failed to execute task: %s", task_err, exc_info=True)
            elif once:
                logger.info("No more tasks pending. Worker exiting (--once mode). Total processed: %d", processed_tasks)
                break
        except Exception as loop_err:
            logger.error("Error in worker polling loop: %s", loop_err, exc_info=True)
            time.sleep(1)

    logger.info("Task Worker terminated gracefully. Total tasks processed: %d", processed_tasks)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MOTHER Dedicated Task Worker")
    parser.add_argument("--once", action="store_true", help="Process pending tasks once and exit")
    parser.add_argument("--timeout", type=int, default=2, help="Poll timeout in seconds")
    args = parser.parse_args()

    run_worker(once=args.once, poll_timeout=args.timeout)
