# backend/api/tasks/handlers.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from backend.api.tasks.queue import task_queue

logger = logging.getLogger("TaskHandlers")

# Task Names Constants
TASK_PROCESS_PUSH_DELIVERIES = "process_push_deliveries"
TASK_CLEANUP_EXPIRED_STORAGE = "cleanup_expired_storage"
TASK_GENERATE_PRESENTATION = "generate_presentation"
TASK_CONVERT_PDF = "convert_pdf"
TASK_GENERATE_AI_IMAGE = "generate_ai_image"


def handle_process_push_deliveries(payload: Dict[str, Any]) -> int:
    """Handler to drain and process pending web push notifications."""
    from backend.api.services.push_worker import process_pending_deliveries

    max_batch = payload.get("max_batch", 50)
    count = process_pending_deliveries(max_batch=max_batch)
    logger.info("Executed push delivery task: processed %d records", count)
    return count


def handle_cleanup_expired_storage(payload: Dict[str, Any]) -> Dict[str, int]:
    """Handler to scan and clean expired files from output/asset directories."""
    from backend.presentation.services.cleanup_service import cleanup_expired_files

    max_age_hours = payload.get("max_age_hours", 24)
    stats = cleanup_expired_files(max_age_hours=max_age_hours)
    logger.info("Executed storage cleanup task: %s", stats)
    return stats


def handle_generate_presentation(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Runs heavy presentation generation in background worker process to prevent HTTP timeouts."""
    from backend.presentation.generator import PresentationService
    from backend.presentation.schemas import GenerateRequest
    from backend.presentation.services.presentation_store import presentation_store
    from backend.api.services.storage_service import storage_service

    req_data = payload.get("request_data", {})
    req = GenerateRequest(**req_data)
    service = PresentationService()

    file_path, plan, title, telemetry = service.generate(req)
    path_obj = Path(file_path)

    # Sync to Cloud Object Storage & get presigned download URL
    cloud_res = storage_service.upload_file(
        file_input=path_obj.read_bytes(),
        filename=path_obj.name,
        folder="outputs",
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )

    download_url = cloud_res.get("presigned_url") or cloud_res.get("url")

    # Persist state to store
    presentation_store.save(req.presentation_id, {
        "presentation_id": req.presentation_id,
        "title": title,
        "topic": req.topic,
        "plan": plan.model_dump() if hasattr(plan, "model_dump") else plan,
        "filename": path_obj.name,
        "file_path": str(path_obj),
        "download_url": download_url,
        "telemetry": telemetry,
    })

    logger.info("Completed async presentation generation for %s", req.presentation_id)
    return {
        "presentation_id": req.presentation_id,
        "title": title,
        "filename": path_obj.name,
        "download_url": download_url,
        "telemetry": telemetry,
    }


def handle_convert_pdf(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Runs PDF conversion in background worker process to prevent HTTP timeouts."""
    from backend.presentation.exporter import save_presentation_as_pdf
    from backend.presentation.schemas import PresentationPlan
    from backend.api.services.storage_service import storage_service

    plan_data = payload.get("plan")
    title = payload.get("title", "Presentation")
    presentation_id = payload.get("presentation_id")

    # Reconstruct plan if dict
    plan = PresentationPlan(**plan_data) if isinstance(plan_data, dict) else plan_data

    pdf_path = save_presentation_as_pdf(plan, title=title, presentation_id=presentation_id)
    path_obj = Path(pdf_path)

    cloud_res = storage_service.upload_file(
        file_input=path_obj.read_bytes(),
        filename=path_obj.name,
        folder="outputs",
        content_type="application/pdf",
    )

    pdf_url = cloud_res.get("presigned_url") or cloud_res.get("url")
    logger.info("Completed async PDF conversion for %s", presentation_id)
    return {
        "presentation_id": presentation_id,
        "pdf_filename": path_obj.name,
        "pdf_url": pdf_url,
    }


def handle_generate_ai_image(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Runs AI image generation in background worker process."""
    from backend.presentation.services.ai_image_service import generate_ai_image

    prompt = payload.get("prompt", "Professional presentation visual")
    width = payload.get("width", 1280)
    height = payload.get("height", 720)
    seed = payload.get("seed")

    img_url = generate_ai_image(prompt, width=width, height=height, seed=seed)
    return {
        "prompt": prompt,
        "image_url": img_url,
    }


def register_default_handlers() -> None:
    """Register all core background task handlers into the global queue."""
    task_queue.register_handler(TASK_PROCESS_PUSH_DELIVERIES, handle_process_push_deliveries)
    task_queue.register_handler(TASK_CLEANUP_EXPIRED_STORAGE, handle_cleanup_expired_storage)
    task_queue.register_handler(TASK_GENERATE_PRESENTATION, handle_generate_presentation)
    task_queue.register_handler(TASK_CONVERT_PDF, handle_convert_pdf)
    task_queue.register_handler(TASK_GENERATE_AI_IMAGE, handle_generate_ai_image)
    logger.info("Default task handlers registered successfully (Push, Storage, PPT, PDF, AI Image)")


# Auto-register on import
register_default_handlers()
