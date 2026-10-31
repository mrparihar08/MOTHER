# backend/presentation/services/presentation_store.py
"""
Persistent Presentation Store:
Database-backed persistence with resilient local file caching.
Eliminates ephemeral data loss on cloud container restarts (Render/Heroku).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from backend.api.database import SessionLocal
from backend.api.models.vitya import SavedPresentation

logger = logging.getLogger(__name__)

# Anchor root directory strictly to the project repository root
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
STORE_DIR = Path(os.getenv("PPT_STORE_DIR", str(ROOT_DIR / "outputs" / "store"))).resolve()
STORE_DIR.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()


class PresentationStore:
    """Thread-safe hybrid Database & JSON file store for presentation states."""

    def __init__(self, store_dir: Optional[Path] = None) -> None:
        self.store_dir = store_dir or STORE_DIR
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, presentation_id: str) -> Path:
        clean_id = "".join(c for c in presentation_id if c.isalnum() or c in ("-", "_")).strip()
        if not clean_id:
            raise ValueError("Invalid presentation_id")
        return self.store_dir / f"{clean_id}.json"

    def save(self, presentation_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save or update presentation state in Database and sync to local file cache atomically."""
        with _lock:
            now_iso = datetime.now(timezone.utc).isoformat()
            file_path = self._get_path(presentation_id)

            existing = {}
            version = 1

            # 1. Try reading existing record from DB first, then local file
            db: Optional[Session] = None
            try:
                db = SessionLocal()
                db_record = db.query(SavedPresentation).filter(SavedPresentation.id == presentation_id).first()
                if db_record and db_record.state_data:
                    existing = json.loads(db_record.state_data)
                    version = existing.get("version", 0) + 1
            except Exception as exc:
                logger.debug("DB read for existing presentation %s: %s", presentation_id, exc)
            finally:
                if db:
                    db.close()

            if not existing and file_path.exists():
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                    version = existing.get("version", 0) + 1
                except Exception as exc:
                    logger.warning("Error reading existing presentation file %s: %s", presentation_id, exc)

            merged_data = {
                **existing,
                **data,
                "presentation_id": presentation_id,
                "version": version,
                "updated_at": now_iso,
                "created_at": existing.get("created_at", now_iso),
            }

            # 2. Persist to SQL Database (Persistent across Render restarts)
            try:
                db = SessionLocal()
                rec = db.query(SavedPresentation).filter(SavedPresentation.id == presentation_id).first()
                title = str(merged_data.get("title") or "Untitled Presentation")[:250]
                user_id = merged_data.get("user_id")
                slides_count = int(merged_data.get("slides_count") or len(merged_data.get("slides", [])))
                state_json = json.dumps(merged_data, ensure_ascii=False)

                if rec:
                    rec.title = title
                    rec.slides_count = slides_count
                    rec.template_name = merged_data.get("template_name")
                    rec.content_theme = merged_data.get("content_theme")
                    rec.background_theme = merged_data.get("background_theme")
                    rec.visual_style = merged_data.get("visual_style")
                    rec.file_name = merged_data.get("file_name")
                    rec.state_data = state_json
                else:
                    rec = SavedPresentation(
                        id=presentation_id,
                        user_id=user_id if isinstance(user_id, int) else None,
                        title=title,
                        slides_count=slides_count,
                        template_name=merged_data.get("template_name"),
                        content_theme=merged_data.get("content_theme"),
                        background_theme=merged_data.get("background_theme"),
                        visual_style=merged_data.get("visual_style"),
                        file_name=merged_data.get("file_name"),
                        state_data=state_json,
                    )
                    db.add(rec)
                db.commit()
            except Exception as exc:
                if db:
                    db.rollback()
                logger.warning("Database persistence for presentation %s failed: %s", presentation_id, exc)
            finally:
                if db:
                    db.close()

            # 3. Save local file cache
            try:
                temp_path = file_path.with_suffix(f".tmp_{int(time.time() * 1000)}")
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(merged_data, f, indent=2, ensure_ascii=False)
                temp_path.replace(file_path)
            except Exception as exc:
                logger.warning("Local file write for presentation %s failed: %s", presentation_id, exc)

            return merged_data

    def get(self, presentation_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve presentation data by ID from DB or local cache."""
        with _lock:
            # 1. Try DB first (persists across restarts)
            db: Optional[Session] = None
            try:
                db = SessionLocal()
                rec = db.query(SavedPresentation).filter(SavedPresentation.id == presentation_id).first()
                if rec and rec.state_data:
                    data = json.loads(rec.state_data)
                    # Restore local file if missing
                    file_path = self._get_path(presentation_id)
                    if not file_path.exists():
                        try:
                            with open(file_path, "w", encoding="utf-8") as f:
                                json.dump(data, f, indent=2, ensure_ascii=False)
                        except Exception:
                            pass
                    return data
            except Exception as exc:
                logger.debug("DB fetch failed for %s: %s", presentation_id, exc)
            finally:
                if db:
                    db.close()

            # 2. Fall back to local file
            file_path = self._get_path(presentation_id)
            if file_path.exists():
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    return data
                except Exception as exc:
                    logger.error("Failed to load presentation file %s: %s", presentation_id, exc)

            return None

    def exists(self, presentation_id: str) -> bool:
        """Check if presentation exists in database or store."""
        db: Optional[Session] = None
        try:
            db = SessionLocal()
            exists_in_db = db.query(SavedPresentation.id).filter(SavedPresentation.id == presentation_id).first() is not None
            if exists_in_db:
                return True
        except Exception:
            pass
        finally:
            if db:
                db.close()

        try:
            return self._get_path(presentation_id).exists()
        except ValueError:
            return False

    def list_all(self, user_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """List presentations from database, falling back to local files."""
        results: List[Dict[str, Any]] = []
        db: Optional[Session] = None
        seen_ids = set()

        # 1. Fetch from Database
        try:
            db = SessionLocal()
            query = db.query(SavedPresentation)
            if user_id is not None:
                query = query.filter(SavedPresentation.user_id == user_id)
            query = query.order_by(SavedPresentation.updated_at.desc()).limit(limit)
            db_records = query.all()

            for r in db_records:
                seen_ids.add(r.id)
                results.append({
                    "presentation_id": r.id,
                    "title": r.title,
                    "slides_count": r.slides_count or 0,
                    "content_theme": r.content_theme,
                    "template_name": r.template_name,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "file_name": r.file_name,
                })
        except Exception as exc:
            logger.debug("DB list_all error: %s", exc)
        finally:
            if db:
                db.close()

        # 2. Merge any local files not in DB
        with _lock:
            try:
                for file_path in self.store_dir.glob("*.json"):
                    pres_id = file_path.stem
                    if pres_id.startswith(".") or pres_id in seen_ids:
                        continue
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            d = json.load(f)
                        if user_id is not None:
                            rec_uid = d.get("user_id")
                            if rec_uid is not None and rec_uid != user_id:
                                continue
                        seen_ids.add(pres_id)
                        results.append({
                            "presentation_id": d.get("presentation_id", pres_id),
                            "title": d.get("title", "Untitled Presentation"),
                            "slides_count": d.get("slides_count", 0),
                            "content_theme": d.get("content_theme"),
                            "template_name": d.get("template_name"),
                            "updated_at": d.get("updated_at"),
                            "created_at": d.get("created_at"),
                            "file_name": d.get("file_name"),
                        })
                    except Exception:
                        continue
            except Exception as exc:
                logger.error("Failed to read local store directory: %s", exc)

        results.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
        return results[:limit]

    def delete(self, presentation_id: str) -> bool:
        """Delete presentation from DB and local cache."""
        deleted = False
        db: Optional[Session] = None
        try:
            db = SessionLocal()
            rec = db.query(SavedPresentation).filter(SavedPresentation.id == presentation_id).first()
            if rec:
                db.delete(rec)
                db.commit()
                deleted = True
        except Exception as exc:
            if db:
                db.rollback()
            logger.error("DB delete failed for %s: %s", presentation_id, exc)
        finally:
            if db:
                db.close()

        with _lock:
            try:
                file_path = self._get_path(presentation_id)
                if file_path.exists():
                    file_path.unlink()
                    deleted = True
            except Exception as exc:
                logger.error("Failed to delete local presentation file %s: %s", presentation_id, exc)

        return deleted


presentation_store = PresentationStore()
