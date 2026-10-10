from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional
from backend.chats.services.unified_connector.models import ResultCategory, StandardizedResult

logger = logging.getLogger(__name__)

DEFAULT_TTLS: Dict[ResultCategory, float] = {
    ResultCategory.NEWS: 600.0,          # 10 minutes
    ResultCategory.SHOPPING: 1800.0,     # 30 minutes
    ResultCategory.EDUCATION: 7200.0,    # 2 hours
    ResultCategory.RESEARCH: 14400.0,    # 4 hours
    ResultCategory.GOVERNMENT: 43200.0,  # 12 hours
    ResultCategory.WEB_SEARCH: 900.0,    # 15 minutes
}


class ConnectorCache:
    """Thread-safe in-memory cache for external connectors to preserve rate limits."""

    def __init__(self) -> None:
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _make_key(self, category: ResultCategory, query: str, **kwargs: Any) -> str:
        serialized = json.dumps({"cat": category.value, "q": query.strip().lower(), "extra": kwargs}, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get(self, category: ResultCategory, query: str, **kwargs: Any) -> Optional[List[StandardizedResult]]:
        key = self._make_key(category, query, **kwargs)
        now = time.time()
        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            if now > entry["expires_at"]:
                del self._cache[key]
                return None
            return entry["results"]

    def set(
        self,
        category: ResultCategory,
        query: str,
        results: List[StandardizedResult],
        ttl_seconds: Optional[float] = None,
        **kwargs: Any,
    ) -> None:
        key = self._make_key(category, query, **kwargs)
        ttl = ttl_seconds if ttl_seconds is not None else DEFAULT_TTLS.get(category, 900.0)
        with self._lock:
            self._cache[key] = {
                "results": results,
                "expires_at": time.time() + ttl,
            }

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


connector_cache = ConnectorCache()
