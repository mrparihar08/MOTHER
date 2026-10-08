from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import requests

from backend.presentation.schemas import ImageResult, ImageSuggestResponse, VisualType
from backend.presentation.services.image_search.openverse import search_openverse
from backend.presentation.services.image_search.wikimedia import search_wikimedia
from backend.presentation.services.image_search.image_selector import (
    determine_visual_type,
    build_slide_image_query,
    rank_and_select_images,
)

logger = logging.getLogger(__name__)

ASSET_DIR = Path(os.getenv("PPT_ASSET_DIR", "./assets")).resolve()
ASSET_DIR.mkdir(parents=True, exist_ok=True)

# In-memory search query response cache
_SEARCH_CACHE: Dict[str, List[ImageResult]] = {}
_LOCAL_FILE_CACHE: Dict[str, str] = {}


def is_safe_external_url(url_text: str) -> bool:
    """SSRF & Security check: validates URL scheme and prevents private/localhost access."""
    if not url_text or not isinstance(url_text, str):
        return False
    u = url_text.strip().lower()

    if not (u.startswith("http://") or u.startswith("https://")):
        return False

    # Block localhost & private network ranges (SSRF protection)
    blocked_hosts = [
        "localhost", "127.0.0.1", "0.0.0.0", "169.254.169.254", "::1",
        "10.", "172.16.", "172.17.", "172.18.", "172.19.", "172.20.",
        "172.21.", "172.22.", "172.23.", "172.24.", "172.25.", "172.26.",
        "172.27.", "172.28.", "172.29.", "172.30.", "172.31.", "192.168."
    ]

    host_part = u.split("://")[-1].split("/")[0].split(":")[0]
    for b in blocked_hosts:
        if host_part == b or host_part.startswith(b):
            logger.warning("SSRF blocked attempt to access private/internal host: %s", url_text)
            return False

    return True


def search_images(
    query: str,
    provider: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    visual_type: Optional[str] = None,
    used_urls: Optional[Set[str]] = None,
) -> List[ImageResult]:
    """
    Executes smart fallback image discovery:
    Openverse API -> Wikimedia Commons API -> Unsplash Fallback.
    Returns ranked, license-validated ImageResult models.
    """
    clean_q = (query or "").strip()
    if not clean_q:
        return []

    cache_key = f"{clean_q.lower()}:{provider}:{page}:{page_size}:{visual_type}"
    if cache_key in _SEARCH_CACHE:
        return _SEARCH_CACHE[cache_key]

    results: List[ImageResult] = []
    used_urls = used_urls or set()

    req_provider = (provider or "").lower().strip()

    # 1. Openverse Search (Primary Provider)
    if not req_provider or req_provider == "openverse":
        try:
            ov_results = search_openverse(clean_q, page=page, page_size=page_size)
            if ov_results:
                results.extend(ov_results)
                logger.info("Openverse search for '%s' returned %d images", clean_q, len(ov_results))
        except Exception as exc:
            logger.warning("Openverse search failed for query '%s': %s", clean_q, exc)

    # 2. Wikimedia Commons Search (Fallback / Secondary Provider)
    if (not results and not req_provider) or req_provider == "wikimedia":
        try:
            wm_results = search_wikimedia(clean_q, limit=page_size)
            if wm_results:
                results.extend(wm_results)
                logger.info("Wikimedia Commons search for '%s' returned %d images", clean_q, len(wm_results))
        except Exception as exc:
            logger.warning("Wikimedia Commons search failed for query '%s': %s", clean_q, exc)

    # 3. Unsplash Fallback Provider
    if not results and not req_provider:
        try:
            from backend.chats.services.unsplash_service import fetch_unsplash_photos_list
            un_photos = fetch_unsplash_photos_list(clean_q, per_page=page_size)
            for item in un_photos:
                results.append(
                    ImageResult(
                        id=f"un_{item.get('id', '')}",
                        image_url=item.get("url", ""),
                        thumbnail_url=item.get("url", ""),
                        title=item.get("title", clean_q.title()),
                        creator="Unsplash Contributor",
                        license="Unsplash License",
                        license_url="https://unsplash.com/license",
                        source_url=item.get("url", ""),
                        provider="unsplash",
                        attribution=f"Image: {item.get('title', clean_q.title())} — Unsplash",
                        width=1200,
                        height=675,
                        aspect_ratio=1.78,
                        visual_type="photo",
                        license_status="commercial_safe",
                        commercial_use=True,
                        modification_allowed=True,
                    )
                )
        except Exception as exc:
            logger.warning("Unsplash fallback search failed for query '%s': %s", clean_q, exc)

    # 4. Direct AI Provider Request (if requested explicitly)
    if req_provider in {"ai", "gemini", "pollinations"}:
        try:
            from backend.presentation.services.ai_image_service import ai_image_service
            ai_res = ai_image_service.generate(
                prompt=clean_q,
                provider=req_provider if req_provider != "ai" else "auto",
                visual_type=visual_type or "photo",
            )
            if ai_res and ai_res.get("image_url"):
                results.append(
                    ImageResult(
                        id=f"ai_{hashlib.md5(clean_q.encode('utf-8')).hexdigest()[:8]}",
                        image_url=ai_res.get("image_url", ""),
                        thumbnail_url=ai_res.get("image_url", ""),
                        title=f"AI Generated: {clean_q}",
                        creator=ai_res.get("source", "AI Generator"),
                        license=ai_res.get("license", "AI Generated"),
                        license_url="",
                        source_url=ai_res.get("image_url", ""),
                        provider="ai",
                        attribution=ai_res.get("attribution", f"Image generated via AI ({clean_q})"),
                        width=ai_res.get("width", 1920),
                        height=ai_res.get("height", 1080),
                        aspect_ratio=1.78,
                        visual_type=visual_type or "photo",
                        license_status="commercial_safe",
                        commercial_use=True,
                        modification_allowed=True,
                    )
                )
        except Exception as exc:
            logger.warning("AI provider search failed for query '%s': %s", clean_q, exc)

    # 5. Score & Rank Results
    ranked = rank_and_select_images(
        results,
        query=clean_q,
        slide_title=clean_q,
        visual_type=visual_type or VisualType.PHOTO,
        limit=page_size,
        used_urls=used_urls,
    )

    if ranked:
        _SEARCH_CACHE[cache_key] = ranked

    return ranked


def suggest_images_for_slide(
    presentation_topic: str,
    slide_title: str = "",
    slide_content: str = "",
    visual_type: Optional[str] = None,
    slide_index: int = 0,
    used_urls: Optional[Set[str]] = None,
) -> ImageSuggestResponse:
    """
    Generates slide-specific queries, selects optimal visual types, and retrieves ranked image suggestions.
    """
    v_type = visual_type or determine_visual_type(slide_title, slide_content)
    query = build_slide_image_query(presentation_topic, slide_title, slide_content, visual_type=v_type)

    images = search_images(query, provider=None, page=1, page_size=15, visual_type=v_type, used_urls=used_urls)

    return ImageSuggestResponse(
        query=query,
        visual_type=v_type,
        suggested_images=images,
    )


def fetch_and_cache_image(image_url: str, timeout: int = 10) -> Optional[str]:
    """
    Safely downloads and caches an external image locally.
    Validates URL, HTTP status, content-type (JPEG/PNG/WEBP/GIF), and max size limit (15MB).
    """
    if not is_safe_external_url(image_url):
        if Path(image_url).is_file():
            return str(Path(image_url).resolve())
        return None

    if image_url in _LOCAL_FILE_CACHE:
        cached_file = Path(_LOCAL_FILE_CACHE[image_url])
        if cached_file.exists() and cached_file.stat().st_size > 1000:
            return str(cached_file)

    url_hash = hashlib.md5(image_url.encode("utf-8")).hexdigest()
    target_file = ASSET_DIR / f"img_cache_{url_hash[:16]}.jpg"

    if target_file.exists() and target_file.stat().st_size > 1000:
        _LOCAL_FILE_CACHE[image_url] = str(target_file)
        return str(target_file)

    try:
        resp = requests.get(image_url, timeout=timeout, stream=True, headers={"User-Agent": "VityaPresentationGenerator/2.0"})
        if resp.status_code == 200:
            content_length = int(resp.headers.get("Content-Length", 0))
            if content_length > 15 * 1024 * 1024:
                logger.warning("Image download exceeded size limit (15MB): %s", image_url)
                return None

            c_type = str(resp.headers.get("Content-Type", "")).lower()
            if c_type and not any(fmt in c_type for fmt in ["image/jpeg", "image/png", "image/webp", "image/gif", "image/jpg", "octet-stream"]):
                logger.warning("Disallowed Content-Type '%s' for image %s", c_type, image_url)
                return None

            data = resp.content
            if len(data) > 1000:
                target_file.write_bytes(data)
                _LOCAL_FILE_CACHE[image_url] = str(target_file)
                return str(target_file)

    except Exception as exc:
        logger.warning("Failed to download image %s: %s", image_url, exc)

    return None
