# backend/api/tasks/__init__.py
"""
Task queue and background worker subsystem.
Supports both Redis-backed distributed queues and bounded in-process queues.
"""
from backend.api.tasks.queue import task_queue, TaskQueue

__all__ = ["task_queue", "TaskQueue"]
