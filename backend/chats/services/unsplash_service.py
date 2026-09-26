import logging
import os
import re
import urllib.parse
import hashlib
from pathlib import Path
from typing import Optional, Dict, Set, List
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
    r"(home|house|interior|living_room|kitchen|decor|residence|villa|apartment|furniture)": "modern home house interior design living room cozy architecture furniture real estate",
    r"(real_estate|property|building|architecture_design|construction|urban|housing|skyscraper)": "modern architecture skyscraper building property exterior real estate glass facade",
    r"(cyber|security|threat|hack|firewall|encryption|data_protect|vulnerability|zero_trust)": "cybersecurity network server technology data lock dark studio high tech",
    r"(ai|artificial|machine_learning|deep_learning|neural|robot|llm|gpt|genai|intelligence)": "artificial intelligence technology digital brain neural node futuristic 3d render",
    r"(cloud|server|datacenter|aws|azure|devops|network|infrastructure|microservice)": "cloud computing server rack datacenter network technology modern studio",
    r"(finance|stock|money|market|invest|banking|economy|revenue|ebitda|trading|crypto|fintech)": "finance stock market trading chart business analytics office modern glass",
    r"(business|strategy|executive|management|office|meeting|leader|roadmap|takeaway|corporate|startup|company)": "business strategy executive presentation team modern office corporate leadership glass window",
    r"(health|medical|doctor|hospital|biotech|pharma|patient|clinical|gene|dna)": "healthcare medical technology hospital doctor laboratory research high tech",
    r"(marketing|sales|growth|customer|brand|target|advertising|seo|campaign)": "marketing strategy digital analytics growth graph team whiteboard corporate",
    r"(code|software|developer|data|architecture|programming|frontend|backend|api|database)": "software developer code screen data architecture modern office setup",
    r"(energy|solar|green|environment|sustainability|wind|clean_tech|climate|nature|forest)": "renewable energy solar panels wind turbine green environment modern technology forest nature",
    r"(education|learning|university|school|student|training|course|academy)": "education university campus learning student modern library classroom technology",
    r"(logistics|supply_chain|shipping|transport|warehouse|cargo|freight)": "logistics supply chain container ship warehouse transport modern distribution center",
    r"(automobile|car|electric_vehicle|ev|autonomous|transportation|vehicle)": "electric vehicle autonomous car futuristic automotive design modern technology",
    r"(food|dining|restaurant|chef|cooking|meal)": "gourmet food presentation modern restaurant dining chef dish",
    r"(sports|fitness|gym|athlete|workout|training)": "sports athlete fitness gym workout high performance training",
    r"(travel|vacation|flight|hotel|resort|destination)": "travel destination resort hotel flight landscape aesthetic",
}

# Curated HD Unsplash photos catalog for instant, 100% semantically accurate fallback response
CURATED_UNSPLASH_CATALOG: Dict[str, List[Dict[str, str]]] = {
    "home": [
        {"id": "home-1", "url": "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Modern Luxury Home Exterior", "source": "Unsplash (Architecture)"},
        {"id": "home-2", "url": "https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Contemporary Living Room Interior", "source": "Unsplash (Interior)"},
        {"id": "home-3", "url": "https://images.unsplash.com/photo-1618221195710-dd6b41faaea6?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Minimalist Home Interior Design", "source": "Unsplash (Interior)"},
        {"id": "home-4", "url": "https://images.unsplash.com/photo-1513694203232-719a280e022f?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Cozy Home Workplace & Study", "source": "Unsplash (Workspace)"},
        {"id": "home-5", "url": "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Modern Open Plan Kitchen & Living", "source": "Unsplash (Interior)"},
        {"id": "home-6", "url": "https://images.unsplash.com/photo-1512917774080-9991f1c4c750?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Suburban Residence Architecture", "source": "Unsplash (Real Estate)"},
        {"id": "home-7", "url": "https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Warm Modern Living Space", "source": "Unsplash (Interior)"},
        {"id": "home-8", "url": "https://images.unsplash.com/photo-1600566753376-12c8ab7fb75b?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Luxury Residential Property", "source": "Unsplash (Real Estate)"},
    ],
    "real_estate": [
        {"id": "re-1", "url": "https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Modern Glass Skyscraper", "source": "Unsplash (Architecture)"},
        {"id": "re-2", "url": "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Urban Corporate Buildings", "source": "Unsplash (Real Estate)"},
        {"id": "re-3", "url": "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Luxury Residence Design", "source": "Unsplash (Architecture)"},
    ],
    "technology": [
        {"id": "tech-1", "url": "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Artificial Intelligence Circuit", "source": "Unsplash (Tech)"},
        {"id": "tech-2", "url": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Global Data Network Infrastructure", "source": "Unsplash (Tech)"},
        {"id": "tech-3", "url": "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Cyber Security Digital Matrix", "source": "Unsplash (Tech)"},
        {"id": "tech-4", "url": "https://images.unsplash.com/photo-1550751827-4bd374c3f58b?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Cloud Server Center Racks", "source": "Unsplash (Tech)"},
        {"id": "tech-5", "url": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Futuristic 3D Gradient Sphere", "source": "Unsplash (Tech)"},
        {"id": "tech-6", "url": "https://images.unsplash.com/photo-1485827404703-89b55fcc595e?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Robotics & Automation Technology", "source": "Unsplash (Tech)"},
    ],
    "business": [
        {"id": "biz-1", "url": "https://images.unsplash.com/photo-1460925895917-afdab827c52f?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Financial Chart Analytics Dashboard", "source": "Unsplash (Business)"},
        {"id": "biz-2", "url": "https://images.unsplash.com/photo-1507679799987-c73779587ccf?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Executive Strategic Planning", "source": "Unsplash (Business)"},
        {"id": "biz-3", "url": "https://images.unsplash.com/photo-1551836022-d5d88e9218df?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Modern Team Collaboration", "source": "Unsplash (Business)"},
        {"id": "biz-4", "url": "https://images.unsplash.com/photo-1559526324-4b87b5e36e44?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Market Growth Metrics Chart", "source": "Unsplash (Finance)"},
        {"id": "biz-5", "url": "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Corporate Strategy Roadmap", "source": "Unsplash (Business)"},
    ],
    "health": [
        {"id": "hlth-1", "url": "https://images.unsplash.com/photo-1507413245164-6160d8298b31?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Biotech Laboratory Research", "source": "Unsplash (Science)"},
        {"id": "hlth-2", "url": "https://images.unsplash.com/photo-1532094349884-543bc11b234d?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Molecular Chemistry & Science", "source": "Unsplash (Science)"},
        {"id": "hlth-3", "url": "https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Healthcare Medical Innovation", "source": "Unsplash (Medical)"},
    ],
    "education": [
        {"id": "edu-1", "url": "https://images.unsplash.com/photo-1523240795612-9a054b0db644?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Academic University Learning", "source": "Unsplash (Education)"},
        {"id": "edu-2", "url": "https://images.unsplash.com/photo-1497633762265-9d179a990aa6?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Library Research & Books", "source": "Unsplash (Education)"},
        {"id": "edu-3", "url": "https://images.unsplash.com/photo-1509062522246-3755977927d7?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Digital Classroom Workshop", "source": "Unsplash (Education)"},
    ],
    "nature": [
        {"id": "nat-1", "url": "https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Lush Forest & Mountain Nature", "source": "Unsplash (Nature)"},
        {"id": "nat-2", "url": "https://images.unsplash.com/photo-1509391365360-2e959784a276?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Renewable Solar Panels", "source": "Unsplash (Environment)"},
        {"id": "nat-3", "url": "https://images.unsplash.com/photo-1466611653911-95081537e5b7?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Wind Turbines Clean Energy", "source": "Unsplash (Environment)"},
    ],
    "car": [
        {"id": "car-1", "url": "https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Luxury Automobile Design", "source": "Unsplash (Automotive)"},
        {"id": "car-2", "url": "https://images.unsplash.com/photo-1552519507-da3b142c6e3d?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Modern Sports Vehicle", "source": "Unsplash (Automotive)"},
        {"id": "car-3", "url": "https://images.unsplash.com/photo-1563720223185-11003d516935?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Electric Vehicle Technology", "source": "Unsplash (Automotive)"},
    ],
    "food": [
        {"id": "food-1", "url": "https://images.unsplash.com/photo-1504674900247-0877df9cc836?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Gourmet Culinary Presentation", "source": "Unsplash (Food)"},
        {"id": "food-2", "url": "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=1200&h=675&q=80", "title": "Modern Restaurant Atmosphere", "source": "Unsplash (Dining)"},
    ]
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


def get_curated_fallback_category(query: str) -> str:
    q = query.lower()
    if re.search(r"(home|house|interior|living|kitchen|decor|villa|apartment|furniture)", q):
        return "home"
    if re.search(r"(real_estate|property|building|skyscraper|architecture)", q):
        return "real_estate"
    if re.search(r"(cyber|security|ai|tech|code|cloud|server|software|data|robot)", q):
        return "technology"
    if re.search(r"(finance|stock|money|market|business|strategy|office|executive|corporate)", q):
        return "business"
    if re.search(r"(health|medical|doctor|hospital|biotech|dna|pharma)", q):
        return "health"
    if re.search(r"(education|university|school|student|book|library)", q):
        return "education"
    if re.search(r"(nature|green|solar|wind|energy|environment|forest)", q):
        return "nature"
    if re.search(r"(car|automobile|vehicle|ev|transport)", q):
        return "car"
    if re.search(r"(food|dining|restaurant|chef)", q):
        return "food"
    return "technology"


def fetch_unsplash_photos_list(query: str, count: int = 9) -> List[Dict[str, str]]:
    """Fetch structured list of high quality HD photos for search modal presentation."""
    query = (query or "").strip()
    if not query:
        query = "technology"

    expanded_query = expand_visual_query(query)
    unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY")

    if unsplash_key:
        try:
            url = f"https://api.unsplash.com/search/photos?query={urllib.parse.quote(expanded_query)}&per_page={count}&orientation=landscape&content_filter=high"
            headers = {"Authorization": f"Client-ID {unsplash_key}"}
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    photos = []
                    for item in results[:count]:
                        selected_urls = item.get("urls", {})
                        base_url = selected_urls.get("regular") or selected_urls.get("small")
                        if base_url:
                            final_url = f"{base_url}&auto=format&fit=crop&w=1200&h=675&q=80"
                            alt = item.get("alt_description") or item.get("description") or f"{query} Visual"
                            user_name = item.get("user", {}).get("name") or "Unsplash Contributor"
                            photos.append({
                                "id": item.get("id") or f"unsplash-{len(photos)}",
                                "url": final_url,
                                "title": alt.capitalize(),
                                "source": f"Unsplash ({user_name})"
                            })
                    if photos:
                        return photos
        except Exception as exc:
            logger.warning("Unsplash API multi-photo fetch failed: %s", exc)

    cat = get_curated_fallback_category(query)
    fallback_photos = CURATED_UNSPLASH_CATALOG.get(cat, CURATED_UNSPLASH_CATALOG["technology"])
    return fallback_photos[:count]


def fetch_unsplash_image(query: str, slide_index: int = 0) -> Optional[str]:
    """Fetch a high-quality landscape image from Unsplash API for a given search query.
    Saves the fetched image into ASSET_DIR and returns the local file path.
    """
    query = (query or "").strip()
    if not query:
        return None

    expanded_query = expand_visual_query(query)
    safe_name = safe_filename(query)
    target_file = ASSET_DIR / f"unsplash_{safe_name}_{slide_index + 1}.jpg"
    if target_file.exists() and target_file.stat().st_size > 1000:
        return str(target_file)

    image_url = fetch_unsplash_url(query, slide_index)

    if image_url:
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
    """Fetch a direct live Unsplash image URL for a given search query.
    Uses deduplication tracking, curated fallbacks, and keyword expansion.
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

    # High-relevance curated fallback matching search query semantic domain
    cat = get_curated_fallback_category(query)
    photos = CURATED_UNSPLASH_CATALOG.get(cat, CURATED_UNSPLASH_CATALOG["technology"])
    selected_photo = photos[slide_index % len(photos)]
    fallback_url = selected_photo["url"]

    _URL_CACHE[cache_key] = fallback_url
    _USED_IMAGE_URLS.add(fallback_url)
    return fallback_url
