from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional
import requests

from backend.chats.presentation.schemas import ImageResult
from backend.chats.presentation.services.image_search.license_checker import (
    evaluate_license,
    build_attribution_string,
)

logger = logging.getLogger(__name__)

OPENVERSE_API_URL = "https://api.openverse.org/v1/images/"
OPENVERSE_TOKEN_URL = "https://api.openverse.org/v1/auth_tokens/token/"

_ACCESS_TOKEN: Optional[str] = None
_TOKEN_EXPIRES_AT: float = 0.0


def _get_openverse_token() -> Optional[str]:
    """Retrieves or refreshes OAuth2 token if OPENVERSE_CLIENT_ID and OPENVERSE_CLIENT_SECRET environment variables are set."""
    global _ACCESS_TOKEN, _TOKEN_EXPIRES_AT

    client_id = os.getenv("OPENVERSE_CLIENT_ID")
    client_secret = os.getenv("OPENVERSE_CLIENT_SECRET")

    if not client_id or not client_secret:
        return None

    if _ACCESS_TOKEN and time.time() < _TOKEN_EXPIRES_AT - 60:
        return _ACCESS_TOKEN

    try:
        resp = requests.post(
            OPENVERSE_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=8,
        )
        if resp.status_code == 200:
            data = resp.json()
            _ACCESS_TOKEN = data.get("access_token")
            expires_in = int(data.get("expires_in", 3600))
            _TOKEN_EXPIRES_AT = time.time() + expires_in
            return _ACCESS_TOKEN
        else:
            logger.warning("Openverse auth token endpoint returned status %d: %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.warning("Openverse authentication token request failed: %s", exc)

    return None


def search_openverse(
    query: str,
    page: int = 1,
    page_size: int = 20,
    filter_license: Optional[str] = None,
) -> List[ImageResult]:
    """
    Integrates the official Openverse Image API.
    Performs public or authenticated image search with safe error handling.
    """
    clean_q = (query or "").strip()
    if not clean_q:
        return []

    token = _get_openverse_token()
    headers = {"User-Agent": "VityaPresentationGenerator/2.0 (Openverse Integration)"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    params: Dict[str, Any] = {
        "q": clean_q,
        "page": max(1, page),
        "page_size": min(50, max(1, page_size)),
    }
    if filter_license:
        params["license_type"] = filter_license

    results: List[ImageResult] = []

    try:
        response = requests.get(OPENVERSE_API_URL, params=params, headers=headers, timeout=10)
        if response.status_code == 429:
            logger.warning("Openverse API rate limit encountered for query '%s'", clean_q)
            return []
        elif response.status_code != 200:
            logger.warning("Openverse API returned HTTP %d for query '%s'", response.status_code, clean_q)
            return []

        data = response.json()
        items = data.get("results") or []

        for item in items:
            if not isinstance(item, dict):
                continue

            img_id = str(item.get("id") or "")
            img_url = str(item.get("url") or "").strip()
            thumb_url = str(item.get("thumbnail") or "").strip() or img_url

            if not img_url or not (img_url.startswith("http://") or img_url.startswith("https://")):
                continue

            title = str(item.get("title") or "").strip() or "Untitled Image"
            creator = str(item.get("creator") or "").strip() or "Unknown Creator"
            creator_url = str(item.get("creator_url") or "").strip()
            raw_lic = str(item.get("license") or "").strip()
            lic_url = str(item.get("license_url") or "").strip()
            source_url = str(item.get("foreign_landing_url") or "").strip() or img_url
            provider = str(item.get("provider") or "openverse").lower()

            w = int(item.get("width") or 0)
            h = int(item.get("height") or 0)
            aspect = round(w / h, 2) if h > 0 else 1.0

            lic_eval = evaluate_license(raw_lic, lic_url)
            attribution = build_attribution_string(title, creator, lic_eval["license"], provider="Openverse")

            results.append(
                ImageResult(
                    id=f"ov_{img_id}",
                    image_url=img_url,
                    thumbnail_url=thumb_url,
                    title=title,
                    creator=creator,
                    creator_url=creator_url,
                    license=lic_eval["license"],
                    license_url=lic_eval["license_url"],
                    source_url=source_url,
                    provider="openverse",
                    attribution=attribution,
                    width=w,
                    height=h,
                    aspect_ratio=aspect,
                    visual_type="photo",
                    relevance_score=0.0,
                    license_status=lic_eval["license_status"],
                    commercial_use=lic_eval["commercial_use"],
                    modification_allowed=lic_eval["modification_allowed"],
                )
            )

    except requests.exceptions.Timeout:
        logger.warning("Openverse API search timed out for query '%s'", clean_q)
    except Exception as exc:
        logger.warning("Openverse API search error for query '%s': %s", clean_q, exc)

    return results
