from __future__ import annotations

import os
import re
import time
import hashlib
import logging
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Provider Endpoints
# -----------------------------------------------------------------------------

NEWSAPI_TOP = "https://newsapi.org/v2/top-headlines"
NEWSAPI_SEARCH = "https://newsapi.org/v2/everything"

MEDIASTACK_NEWS = "https://api.mediastack.com/v1/news"

CURRENTS_LATEST = "https://api.currentsapi.services/v1/latest-news"
CURRENTS_SEARCH = "https://api.currentsapi.services/v1/search"

# -----------------------------------------------------------------------------
# Defaults & Configuration
# -----------------------------------------------------------------------------

DEFAULT_PROVIDER = os.getenv("NEWS_PROVIDER", "auto").strip().lower() or "auto"
DEFAULT_COUNTRY = os.getenv("NEWS_COUNTRY", "in").strip().lower() or "in"
DEFAULT_LANGUAGE = os.getenv("NEWS_LANGUAGE", "en").strip().lower() or "en"

REQUEST_TIMEOUT = float(os.getenv("NEWS_REQUEST_TIMEOUT", "10"))
MAX_LIMIT = int(os.getenv("NEWS_MAX_LIMIT", "50"))
DEFAULT_LIMIT = int(os.getenv("NEWS_DEFAULT_LIMIT", "5"))
CACHE_TTL = float(os.getenv("NEWS_CACHE_TTL", "600"))  # 10 minutes cache

SESSION = requests.Session()

# In-memory news cache: key -> (timestamp, articles)
_NEWS_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}

# -----------------------------------------------------------------------------
# Category Aliases & Standard Taxonomy
# -----------------------------------------------------------------------------

CATEGORY_ALIASES = {
    "general": "general",
    "world": "general",
    "news": "general",
    "top": "general",
    "breaking": "general",

    "business": "business",
    "finance": "business",
    "economy": "business",
    "stock": "business",
    "economy_business_finance": "business",

    "technology": "technology",
    "tech": "technology",
    "ai": "technology",
    "software": "technology",
    "hardware": "technology",
    "science_technology": "technology",

    "politics": "politics",
    "government": "politics",
    "election": "politics",
    "politics_government": "politics",

    "entertainment": "entertainment",
    "movie": "entertainment",
    "movies": "entertainment",
    "music": "entertainment",
    "tv": "entertainment",
    "bollywood": "entertainment",
    "arts_culture_entertainment": "entertainment",

    "sports": "sports",
    "sport": "sports",
    "cricket": "sports",
    "football": "sports",
    "soccer": "sports",
    "tennis": "sports",

    "health": "health",
    "medicine": "health",
    "medical": "health",
    "fitness": "health",

    "science": "science",
    "space": "science",
    "nasa": "science",
    "isro": "science",
}

# -----------------------------------------------------------------------------
# Helpers & Cache
# -----------------------------------------------------------------------------

def get_api_key(provider: str) -> Optional[str]:
    """Retrieve API key for specified provider from environment."""
    provider = (provider or "").strip().lower()
    if provider == "newsapi":
        return os.getenv("NEWS_API_KEY")
    if provider == "mediastack":
        return os.getenv("MEDIASTACK_API_KEY")
    if provider == "currents":
        return os.getenv("CURRENTS_API_KEY")
    return None


def get_available_providers() -> List[str]:
    """List all providers that currently have an active API key configured."""
    available = []
    if get_api_key("newsapi"):
        available.append("newsapi")
    if get_api_key("mediastack"):
        available.append("mediastack")
    if get_api_key("currents"):
        available.append("currents")
    return available


def _clean_limit(limit: int) -> int:
    try:
        return max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    except Exception:
        return DEFAULT_LIMIT


def _first_non_empty(*values: Any) -> Any:
    for v in values:
        if v not in (None, "", [], {}, ()):
            return v
    return None


def _safe_json(res: requests.Response) -> Dict[str, Any]:
    try:
        data = res.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _request(
    url: str,
    *,
    params: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Execute authenticated HTTP GET request with timeout and error handling."""
    try:
        res = SESSION.get(url, params=params, headers=headers or {}, timeout=REQUEST_TIMEOUT)
        if res.status_code != 200:
            data = _safe_json(res)
            detail = _first_non_empty(
                data.get("message"),
                data.get("msg"),
                data.get("error", {}).get("message") if isinstance(data.get("error"), dict) else None,
                data.get("error"),
                data.get("detail"),
                f"HTTP {res.status_code}",
            )
            raise HTTPException(status_code=res.status_code, detail=str(detail))
        return _safe_json(res)
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="News provider request timed out")
    except requests.exceptions.RequestException as exc:
        logger.warning("News network error: %s", exc)
        raise HTTPException(status_code=502, detail="News network error")


def _deduplicate_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate articles based on normalized title and original URL."""
    seen_titles = set()
    seen_urls = set()
    deduped = []

    for a in articles:
        raw_title = (a.get("title") or "").strip().lower()
        clean_title = re.sub(r"[^\w\s]", "", raw_title)
        url = (a.get("url") or "").strip()

        if not clean_title or clean_title in seen_titles:
            continue
        if url and url != "#" and url in seen_urls:
            continue

        seen_titles.add(clean_title)
        if url and url != "#":
            seen_urls.add(url)
        deduped.append(a)

    return deduped


CATEGORY_FALLBACK_IMAGES: Dict[str, str] = {
    "politics": "https://images.unsplash.com/photo-1541872703-74c5e44368f9?w=400&auto=format&fit=crop&q=80",
    "general": "https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=400&auto=format&fit=crop&q=80",
    "business": "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=400&auto=format&fit=crop&q=80",
    "technology": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=400&auto=format&fit=crop&q=80",
    "sports": "https://images.unsplash.com/photo-1531415074968-036ba1b575da?w=400&auto=format&fit=crop&q=80",
    "science": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=400&auto=format&fit=crop&q=80",
    "health": "https://images.unsplash.com/photo-1505751172876-fa1923c5c528?w=400&auto=format&fit=crop&q=80",
    "entertainment": "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=400&auto=format&fit=crop&q=80",
}


def _parse_publication_date(val: Any) -> Tuple[Optional[str], Optional[str]]:
    """Parse date string into (iso_str, formatted_readable_str)."""
    if not val or not isinstance(val, str):
        return None, None
    val = val.strip()
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(val)
        return dt.isoformat(), dt.strftime("%d %b %Y, %I:%M %p %Z").strip()
    except Exception:
        pass
    try:
        from datetime import datetime
        # Check ISO format
        clean_iso = val.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_iso)
        return dt.isoformat(), dt.strftime("%d %b %Y, %I:%M %p UTC").strip()
    except Exception:
        pass
    return val, val


def _normalize_common_article(a: Dict[str, Any], provider: str = "generic") -> Dict[str, Any]:
    """Transform diverse API schemas into Vitya.ai's standard article representation."""
    from datetime import datetime

    source = a.get("source")
    source_name = None

    if isinstance(source, dict):
        source_name = source.get("name") or source.get("id")
    elif isinstance(source, str):
        source_name = source
    else:
        source_name = a.get("source_name") or a.get("author") or "News"

    title = (a.get("title") or "Headline").strip()
    url = (a.get("url") or a.get("link") or "#").strip()
    art_id = hashlib.md5(f"{title}_{url}".encode("utf-8")).hexdigest()[:12]

    category_val = a.get("category") or "general"
    img_candidate = _first_non_empty(a.get("urlToImage"), a.get("image"), a.get("image_url"), a.get("thumbnail"), a.get("imageUrl"))
    if not img_candidate:
        img_candidate = CATEGORY_FALLBACK_IMAGES.get(category_val, CATEGORY_FALLBACK_IMAGES["general"])

    raw_date = _first_non_empty(a.get("published_at"), a.get("publishedAt"), a.get("published"), a.get("date"), a.get("pubDate"))
    iso_date, formatted_date = _parse_publication_date(raw_date)
    final_pub_date = formatted_date or iso_date or raw_date

    now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "id": art_id,
        "title": title,
        "description": (a.get("description") or a.get("summary") or a.get("snippet") or "").strip(),
        "url": url,
        "image": img_candidate,
        "image_url": img_candidate,
        "published_at": final_pub_date,
        "publishedAt": final_pub_date,
        "source": source_name or "Verified Source",
        "source_name": source_name or "Verified Source",
        "author": a.get("author"),
        "category": category_val,
        "country_or_region": a.get("country_or_region") or a.get("country") or "India",
        "retrieved_at": a.get("retrieved_at") or now_iso,
        "provider": provider,
    }

# -----------------------------------------------------------------------------
# Provider Fetchers
# -----------------------------------------------------------------------------

def fetch_from_newsapi(
    category: str = "general",
    q: str = "",
    country: str = "in",
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Fetch live articles from NewsAPI (newsapi.org)."""
    api_key = get_api_key("newsapi")
    if not api_key:
        raise HTTPException(status_code=400, detail="NEWS_API_KEY not configured")

    category = (category or "general").strip().lower()
    q = (q or "").strip()
    limit = _clean_limit(limit)

    if q:
        url = NEWSAPI_SEARCH
        params = {
            "q": q,
            "language": DEFAULT_LANGUAGE,
            "sortBy": "publishedAt",
            "pageSize": limit,
            "apiKey": api_key,
        }
    else:
        url = NEWSAPI_TOP
        params = {
            "country": country or DEFAULT_COUNTRY,
            "category": category if category != "general" else None,
            "pageSize": limit,
            "apiKey": api_key,
        }
        params = {k: v for k, v in params.items() if v is not None}

    payload = _request(url, params=params)
    articles = payload.get("articles", [])
    if not isinstance(articles, list) or not articles:
        raise HTTPException(status_code=404, detail="No articles found on NewsAPI")

    return [_normalize_common_article(a, provider="newsapi") for a in articles[:limit]]


def fetch_from_mediastack(
    category: str = "general",
    q: str = "",
    country: str = "in",
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Fetch live articles from Mediastack (mediastack.com)."""
    api_key = get_api_key("mediastack")
    if not api_key:
        raise HTTPException(status_code=400, detail="MEDIASTACK_API_KEY not configured")

    category = (category or "general").strip().lower()
    q = (q or "").strip()
    limit = _clean_limit(limit)

    params = {
        "access_key": api_key,
        "languages": DEFAULT_LANGUAGE,
        "limit": limit,
        "sort": "published_desc",
    }

    if q:
        params["keywords"] = q
    else:
        if country:
            params["countries"] = country
        if category and category != "general":
            params["categories"] = category

    payload = _request(MEDIASTACK_NEWS, params=params)
    articles = payload.get("data", [])
    if not isinstance(articles, list) or not articles:
        raise HTTPException(status_code=404, detail="No articles found on Mediastack")

    return [_normalize_common_article(a, provider="mediastack") for a in articles[:limit]]


def fetch_from_currents(
    category: str = "general",
    q: str = "",
    country: str = "in",
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Fetch live articles from Currents API (currentsapi.services)."""
    api_key = get_api_key("currents")
    if not api_key:
        raise HTTPException(status_code=400, detail="CURRENTS_API_KEY not configured")

    category = (category or "general").strip().lower()
    q = (q or "").strip()
    limit = _clean_limit(limit)

    headers = {"Authorization": f"Bearer {api_key}"}

    if q:
        url = CURRENTS_SEARCH
        params = {
            "keywords": q,
            "language": DEFAULT_LANGUAGE,
            "page_size": limit,
        }
        if category and category != "general":
            params["category"] = category
    else:
        url = CURRENTS_LATEST
        params = {
            "language": DEFAULT_LANGUAGE,
            "country": country or DEFAULT_COUNTRY,
            "category": category if category != "general" else None,
            "page_size": limit,
        }
        params = {k: v for k, v in params.items() if v is not None}

    payload = _request(url, params=params, headers=headers)
    raw = _first_non_empty(payload.get("news"), payload.get("articles"), payload.get("data"), [])
    if not isinstance(raw, list) or not raw:
        raise HTTPException(status_code=404, detail="No articles found on Currents")

    return [_normalize_common_article(a, provider="currents") for a in raw[:limit]]


def fetch_from_google_news_rss(
    category: str = "general",
    q: str = "",
    country: str = "in",
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """
    Fetches real-time verified articles via Google News RSS without requiring API keys.
    Provides up-to-the-minute coverage for India, states, cities, categories, and topics.
    """
    import xml.etree.ElementTree as ET
    from urllib.parse import quote_plus
    import html

    limit = _clean_limit(limit)
    country_code = (country or DEFAULT_COUNTRY).strip().lower()

    hl = "en-IN" if country_code == "in" else ("en-US" if country_code == "us" else "en-GB")
    gl = country_code.upper()
    ceid = f"{gl}:{hl.split('-')[0]}"

    query_str = (q or "").strip()
    if not query_str and category and category != "general":
        query_str = category

    if query_str:
        encoded_query = quote_plus(query_str)
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl={hl}&gl={gl}&ceid={ceid}"
    else:
        rss_url = f"https://news.google.com/rss?hl={hl}&gl={gl}&ceid={ceid}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

    try:
        res = SESSION.get(rss_url, headers=headers, timeout=REQUEST_TIMEOUT)
        if res.status_code != 200:
            logger.warning("Google News RSS returned HTTP %d", res.status_code)
            return []

        root = ET.fromstring(res.content)
        items = root.findall(".//item")
        if not items:
            return []

        articles = []
        for item in items:
            raw_title = item.findtext("title") or ""
            link = item.findtext("link") or ""
            pub_date_raw = item.findtext("pubDate") or ""
            source_elem = item.find("source")
            source_name = source_elem.text.strip() if source_elem is not None and source_elem.text else ""
            raw_desc = item.findtext("description") or ""

            clean_title = raw_title.strip()
            if " - " in clean_title:
                parts = clean_title.rsplit(" - ", 1)
                clean_title = parts[0].strip()
                if not source_name and len(parts) > 1:
                    source_name = parts[1].strip()

            if not source_name:
                source_name = "News Source"

            clean_desc = ""
            if raw_desc:
                text_no_tags = re.sub(r"<[^>]+>", " ", raw_desc)
                text_no_tags = html.unescape(text_no_tags)
                clean_desc = re.sub(r"\s+", " ", text_no_tags).strip()
                if clean_desc.startswith(clean_title):
                    clean_desc = clean_desc[len(clean_title):].strip()
                    if clean_desc.startswith(source_name):
                        clean_desc = clean_desc[len(source_name):].strip()

            if not clean_desc or len(clean_desc) < 10:
                clean_desc = f"Latest verified report from {source_name} regarding {clean_title}."

            iso_date, formatted_date = _parse_publication_date(pub_date_raw)

            normalized = _normalize_common_article({
                "title": clean_title,
                "description": clean_desc,
                "url": link,
                "source": source_name,
                "published_at": formatted_date or iso_date or pub_date_raw,
                "publishedAt": formatted_date or iso_date or pub_date_raw,
                "category": category,
                "country_or_region": query_str if query_str else country_code,
            }, provider="google_news_rss")

            articles.append(normalized)
            if len(articles) >= limit:
                break

        return articles
    except Exception as e:
        logger.warning("Error fetching from Google News RSS: %s", e)
        return []


def fetch_from_web_fallback(
    category: str = "general",
    q: str = "",
    country: str = "in",
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Resilient fallback that queries real-time web news if dedicated APIs are unconfigured or down."""
    try:
        from urllib.parse import urlparse
        from backend.chats.services.web_search_service import perform_web_search

        search_terms = [q or category]
        if country == "in" and "india" not in (q or "").lower() and "bharat" not in (q or "").lower():
            search_terms.append("India")
        search_terms.append("latest news")
        search_query = " ".join(search_terms)

        results = perform_web_search(search_query, max_results=limit)
        if not results:
            return []

        articles = []
        for item in results[:limit]:
            title = item.get("title") or "News Headline"
            url = item.get("link") or item.get("url") or "#"
            domain = urlparse(url).netloc.replace("www.", "") if url and url != "#" else "Web News"
            articles.append(_normalize_common_article({
                "title": title,
                "description": item.get("snippet") or "Recent news headline update.",
                "url": url,
                "image": None,
                "published_at": None,
                "publishedAt": None,
                "source": domain or "Web News",
                "category": category,
                "country_or_region": country,
            }, provider="web_fallback"))
        return articles
    except Exception as e:
        logger.warning("Web search news fallback failed: %s", e)
        return []

# -----------------------------------------------------------------------------
# Central News Coordinator
# -----------------------------------------------------------------------------

def fetch_news(
    category: str = "general",
    q: str = "",
    country: str = "in",
    limit: int = 5,
    provider: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Central news dispatcher supporting:
    - In-memory TTL caching to save quota limits
    - Provider-specific calls (newsapi, mediastack, currents, google_news_rss)
    - 'auto' multi-provider failover with automatic fallback to live Google News RSS
    - Cross-provider article deduplication
    """
    category = (category or "general").strip().lower()
    category = CATEGORY_ALIASES.get(category, category)
    q = (q or "").strip()
    country = (country or DEFAULT_COUNTRY).strip().lower()
    limit = _clean_limit(limit)
    chosen_provider = (provider or DEFAULT_PROVIDER).strip().lower()

    # 1. Check TTL Cache
    cache_key = f"{chosen_provider}:{category}:{q}:{country}:{limit}"
    now = time.time()
    if cache_key in _NEWS_CACHE:
        cached_time, cached_items = _NEWS_CACHE[cache_key]
        if (now - cached_time) < CACHE_TTL and cached_items:
            logger.info("Serving news from cache for %s", cache_key)
            return cached_items

    articles: List[Dict[str, Any]] = []

    # 2. Specific Provider Execution
    if chosen_provider == "newsapi":
        try:
            articles = fetch_from_newsapi(category=category, q=q, country=country, limit=limit)
        except Exception as e:
            logger.warning("Explicit newsapi failed: %s", e)
    elif chosen_provider == "mediastack":
        try:
            articles = fetch_from_mediastack(category=category, q=q, country=country, limit=limit)
        except Exception as e:
            logger.warning("Explicit mediastack failed: %s", e)
    elif chosen_provider == "currents":
        try:
            articles = fetch_from_currents(category=category, q=q, country=country, limit=limit)
        except Exception as e:
            logger.warning("Explicit currents failed: %s", e)
    elif chosen_provider == "google_news_rss":
        try:
            articles = fetch_from_google_news_rss(category=category, q=q, country=country, limit=limit)
        except Exception as e:
            logger.warning("Explicit google_news_rss failed: %s", e)
    elif chosen_provider == "auto":
        # 3. Dynamic Auto Failover
        provider_map = {
            "newsapi": fetch_from_newsapi,
            "mediastack": fetch_from_mediastack,
            "currents": fetch_from_currents,
        }

        # Try configured API key providers first
        configured = get_available_providers()
        for name in configured:
            fn = provider_map.get(name)
            if not fn:
                continue
            try:
                logger.info("Auto news trying configured provider: %s", name)
                res = fn(category=category, q=q, country=country, limit=limit)
                if res:
                    articles = res
                    logger.info("News successfully fetched via %s", name)
                    break
            except Exception as e:
                logger.warning("Provider %s failed during auto failover: %s", name, e)

        # If configured APIs exhausted or none configured, try Google News RSS
        if not articles:
            try:
                logger.info("Fetching real-time news via Google News RSS engine...")
                articles = fetch_from_google_news_rss(category=category, q=q, country=country, limit=limit)
            except Exception as e:
                logger.warning("Google News RSS failed: %s", e)

        # Final resilient fallback: Web Search
        if not articles:
            logger.info("Google News RSS unavailable. Triggering web search news fallback.")
            articles = fetch_from_web_fallback(category=category, q=q, country=country, limit=limit)

    # 4. Deduplicate and Cache
    if articles:
        articles = _deduplicate_articles(articles)
        _NEWS_CACHE[cache_key] = (now, articles)

    return articles

# -----------------------------------------------------------------------------
# NLP Intent & Query Parsers (Hindi, Hinglish, English)
# -----------------------------------------------------------------------------

HINDI_STOP_WORDS = {
    "ki", "ka", "ke", "ko", "me", "mein", "kya", "hai", "hain", "batao", "dikhao",
    "sunao", "taza", "samachar", "khabar", "khabrein", "aaj", "mujhe", "latest",
    "important", "updates", "update", "chahiye", "karo", "do", "aur", "and", "the",
    "a", "an", "about", "on", "in", "of", "for", "from", "please", "top", "all",
    "kuch", "shuru", "se", "par", "par", "yeh", "ye", "vo", "wo", "tell", "give", "show", "me"
}


def extract_news_query(message: str) -> str:
    """Extract clean search keywords from natural Hindi/Hinglish/English user queries."""
    if not message:
        return ""

    raw = message.strip()
    # Strip triggers and common prefixes
    cleaned = re.sub(
        r"(?i)\b(news|headlines?|samachar|khabar|taza\s+khabar|aaj\s+ki\s+khabar|breaking\s+news|current\s+affairs|latest\s+updates?)\b",
        " ",
        raw,
    )
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)

    tokens = [
        w.strip()
        for w in cleaned.split()
        if w.strip().lower() not in HINDI_STOP_WORDS and len(w.strip()) > 1
    ]

    return " ".join(tokens).strip()


def detect_news_category(text: str) -> str:
    """Classify user's query into target news category across Hindi/English keywords."""
    t = (text or "").lower()

    rules: List[Tuple[Tuple[str, ...], str]] = [
        (("sports", "sport", "cricket", "football", "khel", "match", "ipl", "tennis", "hockey", "badminton"), "sports"),
        (("business", "finance", "economy", "market", "stock", "share market", "sensex", "nifty", "vyapar", "paisa", "budget", "inflation"), "business"),
        (("tech", "technology", "ai", "artificial intelligence", "gadgets", "software", "computer", "mobile", "cyber", "hardware", "apps"), "technology"),
        (("science", "space", "isro", "nasa", "vigyan", "discovery", "astronomy", "galaxy", "rocket"), "science"),
        (("health", "medical", "swasthya", "medicine", "hospital", "covid", "disease", "fitness", "doctor", "wellness"), "health"),
        (("entertainment", "bollywood", "hollywood", "movie", "movies", "cinema", "films", "actor", "actress", "celebrity", "gaana", "songs"), "entertainment"),
        (("politics", "election", "chunav", "government", "sarkar", "minister", "parliament", "neta", "modi", "policy", "cabinet"), "politics"),
    ]

    for keywords, category in rules:
        if any(re.search(rf"\b{re.escape(k)}\b", t) for k in keywords):
            return category

    return "general"


def detect_news_country(text: str) -> str:
    """Detect if the query explicitly asks for Indian or International country news."""
    t = (text or "").lower()
    if any(k in t for k in ["india", "bharat", "desh", "hindustan", "delhi", "mumbai"]):
        return "in"
    if any(k in t for k in ["usa", "america", "us news"]):
        return "us"
    if any(k in t for k in ["uk", "britain", "london"]):
        return "gb"
    return DEFAULT_COUNTRY


STATE_AND_CITY_PATTERNS: List[Tuple[str, str]] = [
    # States
    (r"\b(?:madhya\s+pradesh|mp)\b", "Madhya Pradesh"),
    (r"\b(?:uttar\s+pradesh|up)\b", "Uttar Pradesh"),
    (r"\b(?:maharashtra)\b", "Maharashtra"),
    (r"\b(?:rajasthan)\b", "Rajasthan"),
    (r"\b(?:gujarat)\b", "Gujarat"),
    (r"\b(?:bihar)\b", "Bihar"),
    (r"\b(?:west\s+bengal|bengal)\b", "West Bengal"),
    (r"\b(?:karnataka)\b", "Karnataka"),
    (r"\b(?:tamil\s+nadu)\b", "Tamil Nadu"),
    (r"\b(?:punjab)\b", "Punjab"),
    (r"\b(?:haryana)\b", "Haryana"),
    (r"\b(?:kerala)\b", "Kerala"),
    (r"\b(?:odisha|orissa)\b", "Odisha"),
    (r"\b(?:telangana)\b", "Telangana"),
    (r"\b(?:andhra\s+pradesh|andhra)\b", "Andhra Pradesh"),
    (r"\b(?:jharkhand)\b", "Jharkhand"),
    (r"\b(?:assam)\b", "Assam"),
    (r"\b(?:chhattisgarh)\b", "Chhattisgarh"),
    (r"\b(?:uttarakhand)\b", "Uttarakhand"),
    (r"\b(?:himachal\s+pradesh|himachal)\b", "Himachal Pradesh"),
    (r"\b(?:goa)\b", "Goa"),
    (r"\b(?:kashmir|jammu)\b", "Jammu and Kashmir"),

    # Major Cities
    (r"\b(?:indore)\b", "Indore"),
    (r"\b(?:bhopal)\b", "Bhopal"),
    (r"\b(?:gwalior)\b", "Gwalior"),
    (r"\b(?:jabalpur)\b", "Jabalpur"),
    (r"\b(?:ujjain)\b", "Ujjain"),
    (r"\b(?:delhi|new\s+delhi)\b", "Delhi"),
    (r"\b(?:mumbai|bombay)\b", "Mumbai"),
    (r"\b(?:pune)\b", "Pune"),
    (r"\b(?:bengaluru|bangalore)\b", "Bengaluru"),
    (r"\b(?:hyderabad)\b", "Hyderabad"),
    (r"\b(?:chennai|madras)\b", "Chennai"),
    (r"\b(?:kolkata|calcutta)\b", "Kolkata"),
    (r"\b(?:ahmedabad)\b", "Ahmedabad"),
    (r"\b(?:surat)\b", "Surat"),
    (r"\b(?:jaipur)\b", "Jaipur"),
    (r"\b(?:lucknow)\b", "Lucknow"),
    (r"\b(?:kanpur)\b", "Kanpur"),
    (r"\b(?:patna)\b", "Patna"),
    (r"\b(?:chandigarh)\b", "Chandigarh"),
]


def detect_state_or_city(text: str) -> Optional[str]:
    """Detect Indian states or cities mentioned in the query."""
    t = (text or "").lower()
    for pattern, name in STATE_AND_CITY_PATTERNS:
        if re.search(pattern, t, flags=re.IGNORECASE):
            return name
    return None


def extract_limit_from_query(text: str, default_limit: int = 5) -> int:
    """Extract requested article count (e.g. 'top 5 news', '3 headlines')."""
    t = (text or "").lower()
    m = re.search(r"\b(?:top\s*)?(\d{1,2})\s*(?:news|khabar|samachar|badi|headline|stories)\b", t)
    if not m:
        m = re.search(r"\btop\s*(\d{1,2})\b", t)
    if m:
        try:
            val = int(m.group(1))
            return max(1, min(val, 15))
        except Exception:
            pass
    return default_limit


def is_news_source_date_query(text: str) -> bool:
    """Identify if user asks for source, publisher, or publication date of news."""
    t = (text or "").lower()
    # Exclude non-news / educational / general queries
    if any(re.search(rf"\b{re.escape(k)}\b", t) for k in ["course", "courses", "resource", "resources", "tutorial", "tutorials", "learn", "study"]):
        return False

    source_patterns = [
        r"\bsource\b", r"\bsrot\b", r"\bpublisher\b", r"\bpublication\b",
        r"\bpublish\s+date\b", r"\bpublication\s+date\b", r"\bkab\s+publish\b",
        r"\bpublished\s+date\b", r"\btarikh\b", r"\btariq\b", r"\bkab\s+aayi\b",
        r"\boriginal\s+link\b", r"\barticle\s+link\b", r"\bsource\s+batao\b", r"\bdate\s+batao\b"
    ]
    has_source_word = any(re.search(pat, t) for pat in source_patterns)
    if not has_source_word:
        return False
    reference_words = [
        "is news", "this news", "iss news", "ye news", "yeh news",
        "is article", "this article", "khabar ka", "news ka", "article ka",
        "iski date", "iska source", "date batao", "source batao"
    ]
    has_ref = any(r in t for r in reference_words) or ("source" in t and "date" in t)
    return has_source_word and (has_ref or len(t.split()) <= 12)


def resolve_news_source_and_date(
    articles: List[Dict[str, Any]],
    user_query: str = "",
) -> Dict[str, Any]:
    """
    Resolves verified source publisher, original URL, and publication timestamp from conversation history.
    Strictly distinguishes publication time from retrieval time and honestly reports missing dates.
    """
    if not articles:
        return {
            "type": "text",
            "content": (
                "Pradeep ji, conversation context mein abhi koi news article uplabdh nahi hai. "
                "Aap kripya kisi headline ya topic ka naam batayein, ya pehle taaza khabrein maangein "
                "(jaise: *'aaj ki top news batao'*), phir main uska verified source aur publication date nikal kar dunga."
            ),
            "intent": "NEWS_SUMMARY",
        }

    target = articles[0]
    q_lower = (user_query or "").lower()

    idx_map = {
        "pehli": 0, "first": 0, "1st": 0, "1": 0,
        "dusri": 1, "doosri": 1, "second": 1, "2nd": 1, "2": 1,
        "teesri": 2, "third": 2, "3rd": 2, "3": 2,
        "chauthi": 3, "fourth": 3, "4th": 3, "4": 3,
        "paanchvi": 4, "fifth": 4, "5th": 4, "5": 4,
    }
    for word, idx in idx_map.items():
        if re.search(rf"\b{re.escape(word)}\b", q_lower) and idx < len(articles):
            target = articles[idx]
            break

    for a in articles:
        words = [w for w in re.findall(r"\w+", (a.get("title") or "").lower()) if len(w) > 3]
        if words and any(w in q_lower for w in words):
            target = a
            break

    title = target.get("title") or "News Article"
    title = re.sub(r"^\d+\.\s*", "", title)
    source_name = target.get("source_name") or target.get("source") or "Verified News Publisher"
    url = target.get("url") or "#"
    pub_date = target.get("published_at") or target.get("publishedAt")
    retrieved_at = target.get("retrieved_at") or "Real-time query execution"

    if pub_date and str(pub_date).strip() not in ("None", "", "N/A", "Recent"):
        date_display = f"📅 **Publication Date & Time:** {pub_date} *(Verified publisher timestamp)*"
    else:
        date_display = "📅 **Publication Date:** Source feed mein exact publication timestamp uplabdh nahi hai."

    content_lines = [
        f" is news article ka verified source aur publication details yeh raha:\n",
        f"📌 **Headline:** {title}",
        f"🏢 **Source / Publisher:** **{source_name}**",
        f"{date_display}",
        f"⏱️ **Retrieved At:** {retrieved_at}",
    ]
    if url and url != "#":
        content_lines.append(f"🔗 **Original Article Link:** [{source_name} par poori report padhein]({url})")

    return {
        "type": "text",
        "content": "\n".join(content_lines),
        "intent": "NEWS_SUMMARY",
        "article": {
            "title": title,
            "source": source_name,
            "published_at": pub_date,
            "retrieved_at": retrieved_at,
            "url": url,
        }
    }


def is_news_summary_query(text: str) -> bool:
    """Identify if the user is asking to summarize or analyze a recently retrieved news article."""
    t = (text or "").lower()
    if is_news_source_date_query(t):
        return False

    # Exclude non-news domains (coding, learning plans, math, technical concepts, general answers)
    non_news_indicators = [
        "code", "topic", "concept", "answer", "day 1", "day 2", "day 3", "day 4", "day 5", "day 6", "day 7",
        "lesson", "plan", "program", "function", "class", "syntax", "formula", "python", "sql", "fastapi"
    ]
    if any(re.search(rf"\b{re.escape(k)}\b", t) for k in non_news_indicators):
        return False

    summary_words = ["summarize", "summary", "samjhao", "explain", "impact", "visleshan", "analys", "faida", "nuksan", "short summary"]
    news_reference_words = [
        "is news", "this news", "iss news", "ye news", "yeh news",
        "is article", "this article", "article ko", "news ko", "kisi news",
        "khabar ko", "samachar ko", "is khabar", "headline ko"
    ]

    has_summary_intent = any(w in t for w in summary_words)
    has_news_reference = any(r in t for r in news_reference_words) or t.startswith("/summary") or t.startswith("/news summary")

    # If it explicitly references news, allow short queries
    if has_news_reference and has_summary_intent:
        return True

    # If user explicitly asks "kisi news ka short summary banao" or similar with explicit 'news'
    if "news" in t and ("summary" in t or "samjhao" in t):
        return True

    # News follow-up asking about geopolitical, national, or general impact (e.g. "Iska India par kya impact hoga")
    if any(k in t for k in ["impact", "visleshan", "prabhav"]) and any(k in t for k in ["iska", "is par", "iss par", "india", "bharat", "desh"]):
        return True

    return False


def summarize_news_articles(
    articles: List[Dict[str, Any]],
    user_prompt: str = "",
    language: str = "hinglish",
) -> str:
    """
    Summarize and analyze verified news articles using the AI service.
    Ensures zero hallucination by strictly constraining output to retrieved facts.
    """
    if not articles:
        return (
            " conversation context mein abhi koi news article uplabdh nahi hai jise summarize kiya ja sake. "
            "Aap kisi specific news ka text, headline ya link yahan share kar sakte hain, ya pehle taaza khabrein dekhne ke liye maang sakte hain "
            "(jaise: *'aaj ki top news batao'*), phir main uska short summary bana dunga."
        )

    article_text_blocks = []
    for i, a in enumerate(articles[:3], 1):
        article_text_blocks.append(
            f"Article {i}:\n"
            f"- Title: {a.get('title')}\n"
            f"- Source: {a.get('source')}\n"
            f"- Details: {a.get('description') or a.get('content') or 'N/A'}\n"
            f"- URL: {a.get('url')}\n"
        )

    context_str = "\n".join(article_text_blocks)

    system_instruction = (
        "You are Vitya AI News Analyst & Explainer.\n"
        "Your role is to summarize and explain the verified news articles below in simple, engaging Hindi/Hinglish.\n\n"
        "STRICT GUIDELINES:\n"
        "1. Base your answer ONLY on the provided articles. Do NOT fabricate facts, dates, or quotes.\n"
        "2. Break down the key points into 3-4 bullet points with bold subheadings.\n"
        "3. If the user asks about the impact (e.g. on India, economy, or everyday citizens), provide a balanced, logical analysis.\n"
        "4. Keep the tone empathetic, smart, and accessible to general users."
    )

    prompt = f"User Request: {user_prompt or 'Is news ko simple bhasha me samjhao aur iska impact batao.'}\n\nArticles:\n{context_str}"

    try:
        from backend.chats.services.gemini_service import generate_response
        reply = generate_response(prompt, system_instruction=system_instruction)
        if reply and not reply.startswith("Gemini error") and "not configured" not in reply.lower():
            return reply
    except Exception as e:
        logger.warning("LLM news summarization exception: %s", e)

    # Fallback template if LLM is unavailable
    fallback_lines = ["📰 **News Summary:**\n"]
    for a in articles[:3]:
        fallback_lines.append(f"• **{a.get('title')}** ({a.get('source')}):\n  {a.get('description')}\n")
    return "\n".join(fallback_lines)


def generate_copilot_hindi_news_digest(
    articles: List[Dict[str, Any]],
    user_prompt: str = "",
) -> Dict[str, Any]:
    """
    Transforms verified real news articles into a Copilot-style Hindi news digest matching:
    1. Conversational Hindi intro paragraph with today's date & highlights
    2. Section Header: 'IN आज की {N} बड़ी खबरें'
    3. Numbered Hindi titles and clear descriptions
    4. Concluding disclaimer
    """
    if not articles:
        return {
            "intro": "आज के लिए कोई ताज़ा खबर उपलब्ध नहीं है।",
            "header": "आज की बड़ी खबरें",
            "articles": [],
            "disclaimer": "",
        }

    count = len(articles)

    try:
        from backend.chats.services.gemini_service import generate_response
        articles_snippet = []
        for i, a in enumerate(articles, 1):
            articles_snippet.append(
                f"Article {i}:\n"
                f"- Original Title: {a.get('title')}\n"
                f"- Description: {a.get('description')}\n"
                f"- Source: {a.get('source')}\n"
            )

        prompt = (
            "You are Vitya AI Senior News Editor.\n"
            "Generate a professional, polished Hindi news digest based strictly on the verified articles provided below.\n\n"
            "Format Requirements:\n"
            "1. INTRO: A short opening paragraph in polite, natural Hindi starting with today's date (e.g. 'आज 10 अक्टूबर 2026, शनिवार को भारत की प्रमुख खबरों में [mention 3-4 top topics covered]. यहाँ आज की बड़ी खबरें आसान हिंदी में हैं।')\n"
            f"2. HEADER: 'IN आज की {count} बड़ी खबरें'\n"
            f"3. For each of the {count} articles, provide:\n"
            "   - 'title': Numbered punchy Hindi title (e.g. '1. दिल्ली में विरोध प्रदर्शन और हिरासत')\n"
            "   - 'description': Clear 1-2 sentence description in accessible Hindi explaining what happened based strictly on the article.\n"
            "4. DISCLAIMER: 'ये आज की उपलब्ध रिपोर्टों से चुनी गई प्रमुख खबरें हैं; दिनभर की सभी घटनाओं की पूरी सूची नहीं।'\n\n"
            "Strictly return clean valid JSON matching this schema:\n"
            "{\n"
            '  "intro": "...",\n'
            f'  "header": "IN आज की {count} बड़ी खबरें",\n'
            '  "items": [\n'
            '    {"title": "1. ...", "description": "..."}\n'
            '  ],\n'
            '  "disclaimer": "ये आज की उपलब्ध रिपोर्टों से चुनी गई प्रमुख खबरें हैं; दिनभर की सभी घटनाओं की पूरी सूची नहीं。"\n'
            "}\n\n"
            f"Articles:\n{' '.join(articles_snippet)}"
        )

        reply = generate_response(prompt, system_instruction="Output valid JSON only with keys: intro, header, items, disclaimer.")
        if reply and not reply.startswith("Gemini error") and "not configured" not in reply.lower():
            json_text = reply.strip()
            if "```" in json_text:
                json_text = re.sub(r"^```(?:json)?\s*", "", json_text)
                json_text = re.sub(r"\s*```$", "", json_text)
            import json
            parsed = json.loads(json_text)

            items = parsed.get("items", [])
            merged_articles = []
            for i, a in enumerate(articles):
                item_info = items[i] if i < len(items) else {}
                title = item_info.get("title") or (f"{i+1}. {a.get('title')}" if not str(a.get("title", "")).startswith(f"{i+1}.") else a.get("title"))
                desc = item_info.get("description") or a.get("description")
                merged_articles.append({
                    **a,
                    "title": title,
                    "description": desc,
                })

            return {
                "intro": parsed.get("intro") or "आज भारत की प्रमुख खबरों में महत्वपूर्ण अपडेट्स शामिल हैं। यहाँ आज की बड़ी खबरें आसान हिंदी में हैं:",
                "header": parsed.get("header") or f"IN आज की {count} बड़ी खबरें",
                "articles": merged_articles,
                "disclaimer": parsed.get("disclaimer") or "ये आज की उपलब्ध रिपोर्टों से चुनी गई प्रमुख खबरें हैं; दिनभर की सभी घटनाओं की पूरी सूची नहीं।",
            }
    except Exception as exc:
        logger.warning("Error generating AI Hindi news digest: %s", exc)

    # Deterministic fallback when Gemini key is not active
    formatted_articles = []
    for i, a in enumerate(articles, 1):
        t = a.get("title") or "Headline"
        numbered_title = t if re.match(r"^\d+\.", t) else f"{i}. {t}"
        formatted_articles.append({
            **a,
            "title": numbered_title,
        })

    return {
        "intro": "आज भारत की प्रमुख खबरों में महत्वपूर्ण अपडेट्स शामिल हैं। यहाँ आज की बड़ी खबरें आसान हिंदी में हैं:",
        "header": f"IN आज की {count} बड़ी खबरें",
        "articles": formatted_articles,
        "disclaimer": "ये आज की उपलब्ध रिपोर्टों से चुनी गई प्रमुख खबरें हैं; दिनभर की सभी घटनाओं की पूरी सूची नहीं।",
    }