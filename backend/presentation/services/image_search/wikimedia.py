from __future__ import annotations

import logging
import re
from typing import Any, Dict, List
import requests

from backend.presentation.schemas import ImageResult
from backend.presentation.services.image_search.license_checker import (
    evaluate_license,
    build_attribution_string,
)

logger = logging.getLogger(__name__)

WIKIMEDIA_API_URL = "https://commons.wikimedia.org/w/api.php"


def _clean_html(raw_html: str) -> str:
    """Strips HTML tags and normalizes whitespace from MediaWiki metadata fields."""
    if not raw_html:
        return ""
    clean = re.sub(r"<[^>]+>", "", raw_html)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def search_wikimedia(query: str, limit: int = 20) -> List[ImageResult]:
    """
    Integrates the official Wikimedia Commons MediaWiki API.
    Retrieves public media files with license, author, and source metadata.
    """
    clean_q = (query or "").strip()
    if not clean_q:
        return []

    # Strip File: prefix if user entered it
    search_term = re.sub(r"^File:\s*", "", clean_q, flags=re.IGNORECASE)

    params: Dict[str, Any] = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"File:{search_term}",
        "gsrnamespace": 6,  # File namespace
        "gsrlimit": min(50, max(1, limit)),
        "prop": "imageinfo",
        "iiprop": "url|size|extmetadata|mime",
        "iiurlwidth": 800,
        "format": "json",
        "origin": "*",
    }

    headers = {"User-Agent": "VityaPresentationGenerator/2.0 (Wikimedia Commons Integration)"}
    results: List[ImageResult] = []

    try:
        response = requests.get(WIKIMEDIA_API_URL, params=params, headers=headers, timeout=10)
        if response.status_code != 200:
            logger.warning("Wikimedia Commons API returned HTTP %d for query '%s'", response.status_code, clean_q)
            return []

        data = response.json()
        pages = data.get("query", {}).get("pages", {})

        for page_id, page in pages.items():
            if not isinstance(page, dict):
                continue

            imageinfo_list = page.get("imageinfo") or []
            if not imageinfo_list or not isinstance(imageinfo_list[0], dict):
                continue

            info = imageinfo_list[0]
            mime = str(info.get("mime") or "").lower()

            # Restrict to valid presentation image formats
            if not mime.startswith("image/") or "svg" in mime:
                continue

            img_url = str(info.get("url") or "").strip()
            thumb_url = str(info.get("thumburl") or info.get("url") or "").strip()

            if not img_url or not (img_url.startswith("http://") or img_url.startswith("https://")):
                continue

            raw_title = str(page.get("title") or "").replace("File:", "").strip()
            title = _clean_html(raw_title) or "Wikimedia Visual"

            extdata = info.get("extmetadata") or {}

            # Author / Creator
            raw_artist = extdata.get("Artist", {}).get("value", "")
            creator = _clean_html(raw_artist) or "Wikimedia Creator"

            # License
            raw_lic = extdata.get("LicenseShortName", {}).get("value", "") or extdata.get("License", {}).get("value", "")
            lic_url = extdata.get("LicenseUrl", {}).get("value", "")

            # Source URL
            source_url = str(info.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/File:{raw_title}")

            w = int(info.get("width") or 0)
            h = int(info.get("height") or 0)
            aspect = round(w / h, 2) if h > 0 else 1.0

            lic_eval = evaluate_license(raw_lic, lic_url)
            attribution = build_attribution_string(title, creator, lic_eval["license"], provider="Wikimedia Commons")

            results.append(
                ImageResult(
                    id=f"wm_{page_id}",
                    image_url=img_url,
                    thumbnail_url=thumb_url,
                    title=title,
                    creator=creator,
                    creator_url="",
                    license=lic_eval["license"],
                    license_url=lic_eval["license_url"],
                    source_url=source_url,
                    provider="wikimedia",
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
        logger.warning("Wikimedia Commons API search timed out for query '%s'", clean_q)
    except Exception as exc:
        logger.warning("Wikimedia Commons API search error for query '%s': %s", clean_q, exc)

    return results
