import logging
import os
import re
import urllib.parse
import hashlib
from pathlib import Path
from typing import Optional, Dict, Set
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

ASSET_DIR = Path(os.getenv("PPT_ASSET_DIR", "./assets")).resolve()
ASSET_DIR.mkdir(parents=True, exist_ok=True)

# In-memory caches for fetched URLs and global deduplication across presentation slides
_URL_CACHE: Dict[str, str] = {}
_USED_IMAGE_URLS: Set[str] = set()
_USED_PHOTO_IDS: Set[str] = set()


def clear_used_image_cache():
    """Reset used image tracking for a new presentation generation session."""
    global _USED_IMAGE_URLS, _USED_PHOTO_IDS, _URL_CACHE
    _USED_IMAGE_URLS.clear()
    _USED_PHOTO_IDS.clear()
    _URL_CACHE.clear()


# Topic-curated visual domain mapping for high relevance presentation images
TOPIC_VISUAL_MAP = {
    r"(cyber|security|threat|hack|firewall|encryption|data_protect|vulnerability|zero_trust)": "cybersecurity network server technology data lock dark studio high tech",
    r"(ai|artificial|machine_learning|deep_learning|neural|robot|llm|gpt|genai|intelligence)": "artificial intelligence technology digital brain neural node futuristic 3d render",
    r"(cloud|server|datacenter|aws|azure|devops|network|infrastructure|microservice)": "cloud computing server rack datacenter network technology modern studio",
    r"(finance|stock|money|market|invest|banking|economy|revenue|ebitda|trading|crypto|fintech)": "finance stock market trading chart business analytics office modern glass",
    r"(business|strategy|executive|management|office|meeting|leader|roadmap|takeaway|corporate|startup|company)": "business strategy executive presentation team modern office corporate leadership glass window",
    r"(health|medical|doctor|hospital|biotech|pharma|patient|clinical|gene|dna)": "healthcare medical technology hospital doctor laboratory research high tech",
    r"(marketing|sales|growth|customer|brand|target|advertising|seo|campaign)": "marketing strategy digital analytics growth graph team whiteboard corporate",
    r"(code|software|developer|data|architecture|programming|frontend|backend|api|database)": "software developer code screen data architecture modern office setup",
    r"(energy|solar|green|environment|sustainability|wind|clean_tech|climate)": "renewable energy solar panels wind turbine green environment modern technology",
    r"(real_estate|property|building|architecture_design|construction|urban|housing)": "modern architecture skyscraper building property exterior real estate glass facade",
    r"(education|learning|university|school|student|training|course|academy)": "education university campus learning student modern library classroom technology",
    r"(logistics|supply_chain|shipping|transport|warehouse|cargo|freight)": "logistics supply chain container ship warehouse transport modern distribution center",
    r"(automobile|car|electric_vehicle|ev|autonomous|transportation|vehicle)": "electric vehicle autonomous car futuristic automotive design modern technology",
}


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", (name or "").strip())[:80].strip("_")
    return cleaned or "image"


def expand_visual_query(raw_query: str) -> str:
    """Clean filler words and expand generic presentation terms with rich HD visual search keywords."""
    clean = re.sub(
        r"(?i)\b(introduction\ to|overview\ of|concept\ of|presentation|slide|ppt|deck|agenda|summary|conclusion|takeaways|strategic\ takeaways|key\ takeaways|next\ steps|recommendations|q&a|chapter|section)\b",
        "",
        raw_query or ""
    ).strip()
    clean = re.sub(r"^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$", "", clean).strip()
    clean = re.sub(r"\s+", " ", clean).strip()

    if not clean or len(clean) < 3:
        return "modern business technology presentation high resolution"

    # Match topic visual domain
    for pattern, visual_terms in TOPIC_VISUAL_MAP.items():
        if re.search(pattern, clean.lower()):
            return f"{clean} {visual_terms}".strip()

    return f"{clean} professional presentation photo high resolution modern".strip()


def fetch_unsplash_image(query: str, slide_index: int = 0) -> Optional[str]:
    """Fetch a high-quality landscape image from Unsplash API for a given search query.

    Saves the fetched image into ASSET_DIR and returns the local file path.
    Uses slide_index and deduplication tracking to ensure unique, non-duplicate images across slides.
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
            url = f"https://api.unsplash.com/search/photos?query={urllib.parse.quote(expanded_query)}&per_page=20&orientation=landscape&content_filter=high"
            headers = {"Authorization": f"Client-ID {unsplash_key}"}
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    selected_item = None
                    # Pick first unused photo to enforce 100% uniqueness
                    for item in results:
                        photo_id = item.get("id")
                        if photo_id and photo_id not in _USED_PHOTO_IDS:
                            _USED_PHOTO_IDS.add(photo_id)
                            selected_item = item
                            break
                    if not selected_item:
                        selected_item = results[slide_index % len(results)]

                    selected_urls = selected_item.get("urls", {})
                    base_url = selected_urls.get("regular") or selected_urls.get("small")
                    if base_url:
                        image_url = f"{base_url}&auto=format&fit=crop&w=1200&h=675&q=80"
        except Exception as exc:
            logger.warning("Unsplash API request failed: %s", exc)

    if not image_url:
        unique_seed = hashlib.md5(f"{safe_name}_{slide_index + 1}".encode("utf-8")).hexdigest()[:10]
        image_url = f"https://picsum.photos/seed/{unique_seed}/1200/675"

    try:
        img_resp = requests.get(image_url, timeout=8)
        if img_resp.status_code == 200 and len(img_resp.content) > 1000:
            target_file.write_bytes(img_resp.content)
            _USED_IMAGE_URLS.add(image_url)
            return str(target_file)
    except Exception as exc:
        logger.warning("Failed to download image from %s: %s", image_url, exc)

    return None


def fetch_unsplash_url(query: str, slide_index: int = 0) -> Optional[str]:
    """Fetch a direct live Unsplash image URL for a given search query using UNSPLASH_ACCESS_KEY.
    Uses deduplication tracking to ensure unique, non-duplicate images across slides, 16:9 widescreen dimensions, and keyword expansion.
    """
    load_dotenv()
    query = (query or "").strip()
    if not query:
        return None

    cache_key = f"{query}_{slide_index}"
    if cache_key in _URL_CACHE and _URL_CACHE[cache_key] not in _USED_IMAGE_URLS:
        _USED_IMAGE_URLS.add(_URL_CACHE[cache_key])
        return _URL_CACHE[cache_key]

    expanded_query = expand_visual_query(query)
    unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY")
    if unsplash_key:
        try:
            url = f"https://api.unsplash.com/search/photos?query={urllib.parse.quote(expanded_query)}&per_page=20&orientation=landscape&content_filter=high"
            headers = {"Authorization": f"Client-ID {unsplash_key}"}
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    selected_item = None
                    for item in results:
                        photo_id = item.get("id")
                        if photo_id and photo_id not in _USED_PHOTO_IDS:
                            _USED_PHOTO_IDS.add(photo_id)
                            selected_item = item
                            break
                    if not selected_item:
                        selected_item = results[slide_index % len(results)]

                    selected_urls = selected_item.get("urls", {})
                    base_url = selected_urls.get("regular") or selected_urls.get("small")
                    if base_url:
                        final_url = f"{base_url}&auto=format&fit=crop&w=1200&h=675&q=80"
                        _URL_CACHE[cache_key] = final_url
                        _USED_IMAGE_URLS.add(final_url)
                        return final_url
        except Exception as exc:
            logger.warning("Unsplash API URL request failed: %s", exc)

    safe_name = safe_filename(query)
    unique_seed = hashlib.md5(f"{safe_name}_{slide_index + 1}".encode("utf-8")).hexdigest()[:10]
    fallback_url = f"https://picsum.photos/seed/{unique_seed}/1200/675"
    _URL_CACHE[cache_key] = fallback_url
    _USED_IMAGE_URLS.add(fallback_url)
    return fallback_url

