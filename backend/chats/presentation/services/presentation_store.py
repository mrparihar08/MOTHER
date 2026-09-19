from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

STORE_DIR = Path(os.getenv("PPT_STORE_DIR", "./outputs/store")).resolve()
STORE_DIR.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()


class PresentationStore:
    """Thread-safe JSON file store for presentation states and metadata."""

    def __init__(self, store_dir: Optional[Path] = None) -> None:
        self.store_dir = store_dir or STORE_DIR
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, presentation_id: str) -> Path:
        # Sanitize presentation_id to prevent path traversal
        clean_id = "".join(c for c in presentation_id if c.isalnum() or c in ("-", "_")).strip()
        if not clean_id:
            raise ValueError("Invalid presentation_id")
        return self.store_dir / f"{clean_id}.json"

    def save(self, presentation_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save or update presentation state JSON atomically."""
        with _lock:
            file_path = self._get_path(presentation_id)
            existing = {}
            version = 1
            if file_path.exists():
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                    version = existing.get("version", 0) + 1
                except Exception as exc:
                    logger.warning("Error reading existing presentation %s: %s", presentation_id, exc)

            now_iso = datetime.now(timezone.utc).isoformat()
            
            merged_data = {
                **existing,
                **data,
                "presentation_id": presentation_id,
                "version": version,
                "updated_at": now_iso,
                "created_at": existing.get("created_at", now_iso),
            }

            temp_path = file_path.with_suffix(f".tmp_{int(time.time() * 1000)}")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(merged_data, f, indent=2, ensure_ascii=False)

            temp_path.replace(file_path)
            return merged_data

    def get(self, presentation_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve saved presentation data by ID."""
        with _lock:
            file_path = self._get_path(presentation_id)
            if not file_path.exists():
                return None
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as exc:
                logger.error("Failed to load presentation %s: %s", presentation_id, exc)
                return None

    def exists(self, presentation_id: str) -> bool:
        """Check if presentation exists in store."""
        try:
            return self._get_path(presentation_id).exists()
        except ValueError:
            return False

    def delete(self, presentation_id: str) -> bool:
        """Delete presentation state JSON."""
        with _lock:
            try:
                file_path = self._get_path(presentation_id)
                if file_path.exists():
                    file_path.unlink()
                    return True
            except Exception as exc:
                logger.error("Failed to delete presentation %s: %s", presentation_id, exc)
            return False


presentation_store = PresentationStore()
