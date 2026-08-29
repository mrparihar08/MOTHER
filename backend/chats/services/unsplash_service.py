import logging
import os
import re
import urllib.parse
from pathlib import Path
from typing import Optional, Dict
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

ASSET_DIR = Path(os.getenv("PPT_ASSET_DIR", "./assets")).resolve()
ASSET_DIR.mkdir(parents=True, exist_ok=True)

# In-memory cache for fetched URLs to prevent redundant network calls
_URL_CACHE: Dict[str, str] = {}

# Topic-curated fallback keywords for presentation domains
TOPIC_VISUAL_MAP = {
    r"(cyber|security|threat|hack|firewall|encryption|data_protect)": "cybersecurity network server technology data lock",
    r"(ai|artificial|machine_learning|deep_learning|neural|robot)": "artificial intelligence technology digital code robot",
    r"(cloud|server|datacenter|aws|azure|devops|network)": "cloud computing server room network technology",
    r"(finance|stock|money|market|invest|banking|economy)": "finance stock market business chart analytics",
    r"(business|strategy|executive|management|office|meeting)": "business strategy executive presentation team office",
    r"(health|medical|doctor|hospital|biotech|pharma)": "healthcare medical technology hospital doctor",
    r"(marketing|sales|growth|customer|brand|target)": "marketing strategy analytics growth graph team",
}


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", (name or "").strip())[:80].strip("_")
    return cleaned or "image"


def expand_visual_query(raw_query: str) -> str:
    """Clean filler words and expand generic presentation terms with rich HD visual search keywords."""
    clean = re.sub(r"(?i)\b(introduction\ to|overview\ of|concept\ of|presentation|slide|ppt|deck|agenda|summary|conclusion|q&a)\b", "", raw_query or "").strip()
    clean = re.sub(r"\s+", " ", clean).strip()

    if not clean:
        return "business technology presentation"

    # Match topic visual domain
    for pattern, visual_terms in TOPIC_VISUAL_MAP.items():
        if re.search(pattern, clean.lower()):
            return f"{clean} {visual_terms}".strip()

    return f"{clean} HD professional landscape".strip()


def fetch_unsplash_image(query: str, slide_index: int = 0) -> Optional[str]:
    """Fetch a high-quality landscape image from Unsplash API for a given search query.

    Saves the fetched image into ASSET_DIR and returns the local file path.
    Uses slide_index to ensure unique, non-duplicate images across slides.
    """
    load_dotenv()
    query = (query or "").strip()
    if not query:
        return None

    expanded_query = expand_visual_query(query)
    safe_name = safe_filename(query)
    target_file = ASSET_DIR / f"unsplash_{safe_name}_{slide_index + 1}.jpg"
    if target_file.exists() and target_file.stat().st_size > 1000:
        return str(target_file)

    unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY")
    image_url = None

    if unsplash_key:
        try:
            url = f"https://api.unsplash.com/search/photos?query={urllib.parse.quote(expanded_query)}&per_page=10&orientation=landscape&content_filter=high"
            headers = {"Authorization": f"Client-ID {unsplash_key}"}
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    pick_idx = slide_index % len(results)
                    selected = results[pick_idx].get("urls", {})
                    base_url = selected.get("regular") or selected.get("small")
                    if base_url:
                        image_url = f"{base_url}&auto=format&fit=crop&w=1200&h=675&q=80"
        except Exception as exc:
            logger.warning("Unsplash API request failed: %s", exc)

    if not image_url:
        image_url = f"https://picsum.photos/seed/{urllib.parse.quote(safe_name)}_{slide_index + 1}/1200/675"

    try:
        img_resp = requests.get(image_url, timeout=8)
        if img_resp.status_code == 200 and len(img_resp.content) > 1000:
            target_file.write_bytes(img_resp.content)
            return str(target_file)
    except Exception as exc:
        logger.warning("Failed to download image from %s: %s", image_url, exc)

    return None


def fetch_unsplash_url(query: str, slide_index: int = 0) -> Optional[str]:
    """Fetch a direct live Unsplash image URL for a given search query using UNSPLASH_ACCESS_KEY.
    Uses slide_index to ensure unique, non-duplicate images across slides, 16:9 widescreen dimensions, and keyword expansion.
    """
    load_dotenv()
    query = (query or "").strip()
    if not query:
        return None

    cache_key = f"{query}_{slide_index}"
    if cache_key in _URL_CACHE:
        return _URL_CACHE[cache_key]

    expanded_query = expand_visual_query(query)
    unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY")
    if unsplash_key:
        try:
            url = f"https://api.unsplash.com/search/photos?query={urllib.parse.quote(expanded_query)}&per_page=10&orientation=landscape&content_filter=high"
            headers = {"Authorization": f"Client-ID {unsplash_key}"}
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    pick_idx = slide_index % len(results)
                    selected = results[pick_idx].get("urls", {})
                    base_url = selected.get("regular") or selected.get("small")
                    if base_url:
                        final_url = f"{base_url}&auto=format&fit=crop&w=1200&h=675&q=80"
                        _URL_CACHE[cache_key] = final_url
                        return final_url
        except Exception as exc:
            logger.warning("Unsplash API URL request failed: %s", exc)

    safe_name = safe_filename(query)
    fallback_url = f"https://picsum.photos/seed/{urllib.parse.quote(safe_name)}_{slide_index + 1}/1200/675"
    _URL_CACHE[cache_key] = fallback_url
    return fallback_url
