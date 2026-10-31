# backend/api/tasks/celery_app.py
"""
Celery Worker Configuration & Task Definitions for MOTHER.
Compatible with standard Celery / ARQ / Redis deployments.

Run worker with:
    celery -A backend.api.tasks.celery_app worker --loglevel=info -c 2
"""
from __future__ import annotations

import os
import logging
from typing import Any, Dict

logger = logging.getLogger("CeleryWorker")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Optional Celery integration
celery_app = None
try:
    from celery import Celery

    celery_app = Celery(
        "mother_tasks",
        broker=REDIS_URL,
        backend=REDIS_URL,
    )

    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_time_limit=600,  # 10 minutes max for large presentations
        worker_prefetch_multiplier=1,
    )

    @celery_app.task(name="tasks.generate_presentation", bind=True)
    def celery_generate_presentation(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        from backend.api.tasks.handlers import handle_generate_presentation
        return handle_generate_presentation(payload)

    @celery_app.task(name="tasks.convert_pdf", bind=True)
    def celery_convert_pdf(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        from backend.api.tasks.handlers import handle_convert_pdf
        return handle_convert_pdf(payload)

    @celery_app.task(name="tasks.generate_ai_image", bind=True)
    def celery_generate_ai_image(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        from backend.api.tasks.handlers import handle_generate_ai_image
        return handle_generate_ai_image(payload)

    @celery_app.task(name="tasks.process_push_deliveries", bind=True)
    def celery_process_push_deliveries(self, payload: Dict[str, Any]) -> int:
        from backend.api.tasks.handlers import handle_process_push_deliveries
        return handle_process_push_deliveries(payload)

    logger.info("Celery application configured successfully for broker %s", REDIS_URL.split("@")[-1])
except ImportError:
    logger.debug("Celery not installed; native Redis/Bounded worker queue active.")
