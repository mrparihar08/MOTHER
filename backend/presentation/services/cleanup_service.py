from __future__ import annotations

import logging
import os
import time
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(os.getenv("PPT_OUTPUT_DIR", "./outputs")).resolve()
ASSET_DIR = Path(os.getenv("PPT_ASSET_DIR", "./assets")).resolve()
DEFAULT_MAX_AGE_HOURS = int(os.getenv("PPT_CLEANUP_MAX_AGE_HOURS", "24"))

_cleanup_thread_started = False
_cleanup_lock = threading.Lock()


def cleanup_expired_files(max_age_hours: int = DEFAULT_MAX_AGE_HOURS) -> dict[str, int]:
    """
    Scans output and asset directories for files older than `max_age_hours` and deletes them.
    Returns stats on deleted files and space reclaimed.
    """
    now = time.time()
    cutoff_time = now - (max_age_hours * 3600)
    deleted_count = 0
    reclaimed_bytes = 0

    target_dirs = [OUTPUT_DIR, ASSET_DIR]

    for target_dir in target_dirs:
        if not target_dir.exists():
            continue
        try:
            for item in target_dir.iterdir():
                if item.is_file():
                    try:
                        mtime = item.stat().st_mtime
                        if mtime < cutoff_time:
                            size = item.stat().st_size
                            item.unlink()
                            deleted_count += 1
                            reclaimed_bytes += size
                    except Exception as err:
                        logger.warning("Failed to delete expired file %s: %s", item, err)
        except Exception as exc:
            logger.warning("Error scanning directory %s for cleanup: %s", target_dir, exc)

    if deleted_count > 0:
        reclaimed_mb = round(reclaimed_bytes / (1024 * 1024), 2)
        logger.info("Storage Cleanup: Deleted %d expired files, reclaimed %s MB", deleted_count, reclaimed_mb)

    return {"deleted_files": deleted_count, "reclaimed_bytes": reclaimed_bytes}


def _periodic_cleanup_loop(interval_hours: int = 6, max_age_hours: int = DEFAULT_MAX_AGE_HOURS):
    while True:
        try:
            cleanup_expired_files(max_age_hours=max_age_hours)
        except Exception as exc:
            logger.warning("Periodic storage cleanup loop encountered an error: %s", exc)
        time.sleep(interval_hours * 3600)


def start_periodic_cleanup(interval_hours: int = 6, max_age_hours: int = DEFAULT_MAX_AGE_HOURS):
    """Start background daemon thread for periodic file storage cleanup."""
    global _cleanup_thread_started
    with _cleanup_lock:
        if not _cleanup_thread_started:
            thread = threading.Thread(
                target=_periodic_cleanup_loop,
                args=(interval_hours, max_age_hours),
                daemon=True,
                name="PresentationStorageCleanupThread"
            )
            thread.start()
            _cleanup_thread_started = True
            logger.info("Storage Cleanup daemon thread started (runs every %dh, max_age=%dh)", interval_hours, max_age_hours)
