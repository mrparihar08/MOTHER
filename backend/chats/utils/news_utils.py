from __future__ import annotations

import os
import re
import logging
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Provider endpoints
# -----------------------------------------------------------------------------

NEWSAPI_TOP = "https://newsapi.org/v2/top-headlines"
NEWSAPI_SEARCH = "https://newsapi.org/v2/everything"

MEDIASTACK_NEWS = "https://api.mediastack.com/v1/news"

CURRENTS_LATEST = "https://api.currentsapi.services/v1/latest-news"
CURRENTS_SEARCH = "https://api.currentsapi.services/v1/search"

# -----------------------------------------------------------------------------
# Defaults
# -----------------------------------------------------------------------------

DEFAULT_PROVIDER = os.getenv("NEWS_PROVIDER", "auto").strip().lower() or "auto"
DEFAULT_COUNTRY = os.getenv("NEWS_COUNTRY", "in").strip().lower() or "in"
DEFAULT_LANGUAGE = os.getenv("NEWS_LANGUAGE", "en").strip().lower() or "en"

REQUEST_TIMEOUT = float(os.getenv("NEWS_REQUEST_TIMEOUT", "10"))
MAX_LIMIT = int(os.getenv("NEWS_MAX_LIMIT", "150"))
DEFAULT_LIMIT = int(os.getenv("NEWS_DEFAULT_LIMIT", "5"))

SESSION = requests.Session()

# -----------------------------------------------------------------------------
# Category mapping
# -----------------------------------------------------------------------------

CATEGORY_ALIASES = {
    "general": "general",
    "world": "general",
    "news": "general",
    "top": "general",
    "breaking": "general",

    "business": "economy_business_finance",
    "finance": "economy_business_finance",
    "economy": "economy_business_finance",
    "stock": "economy_business_finance",

    "technology": "science_technology",
    "tech": "science_technology",
    "science": "science_technology",
    "ai": "science_technology",
    "software": "science_technology",
    "hardware": "science_technology",

    "politics": "politics_government",
    "government": "politics_government",
    "election": "politics_government",
    "policy": "politics_government",
    "diplomacy": "politics_government",

    "entertainment": "arts_culture_entertainment",
    "movie": "arts_culture_entertainment",
    "movies": "arts_culture_entertainment",
    "music": "arts_culture_entertainment",
    "tv": "arts_culture_entertainment",
    "show": "arts_culture_entertainment",

    "sports": "sport",
    "sport": "sport",
    "football": "sport",
    "soccer": "sport",
    "cricket": "sport",
    "tennis": "sport",

    "health": "health",
    "medicine": "health",
    "medical": "health",
    "covid": "health",

    "lifestyle": "lifestyle_leisure",
    "food": "lifestyle_leisure",
    "travel": "lifestyle_leisure",
    "lifestyle": "lifestyle_leisure",

    "crime": "crime_law_justice",
    "law": "crime_law_justice",
    "justice": "crime_law_justice",

    "education": "education",
    "environment": "environment",
    "realestate": "real_estate",
    "real_estate": "real_estate",
    "automotive": "automotive",
}

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def get_api_key(provider: str) -> str:
    provider = (provider or "").strip().lower()

    if provider == "currents":
        api_key = os.getenv("CURRENTS_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="CURRENTS_API_KEY missing")
        return api_key

    if provider == "newsapi":
        api_key = os.getenv("NEWS_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="NEWS_API_KEY missing")
        return api_key

    if provider == "mediastack":
        api_key = os.getenv("MEDIASTACK_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="MEDIASTACK_API_KEY missing")
        return api_key

    raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")


def _clean_limit(limit: int) -> int:
    try:
        return max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    except Exception:
        return DEFAULT_LIMIT


def _normalize_category(category: str) -> str:
    raw = (category or "general").strip().lower().replace("-", "_").replace(" ", "_")
    return CATEGORY_ALIASES.get(raw, raw or "general")


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


def _raise_if_bad_response(res: requests.Response) -> None:
    if res.status_code == 200:
        return

    data = _safe_json(res)

    detail = _first_non_empty(
        data.get("message"),
        data.get("msg"),
        data.get("error", {}).get("message") if isinstance(data.get("error"), dict) else None,
        data.get("error"),
        data.get("detail"),
        f"News fetch error ({res.status_code})",
    )

    raise HTTPException(status_code=res.status_code, detail=str(detail))


def _request(url: str, *, params: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    try:
        res = SESSION.get(url, params=params, headers=headers or {}, timeout=REQUEST_TIMEOUT)
        _raise_if_bad_response(res)
        return _safe_json(res)
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="News timeout")
    except requests.exceptions.RequestException as exc:
        logger.exception("News network error: %s", exc)
        raise HTTPException(status_code=500, detail="Network error")


def _normalize_common_article(a: Dict[str, Any]) -> Dict[str, Any]:
    source = a.get("source")
    source_name = None

    if isinstance(source, dict):
        source_name = source.get("name") or source.get("id")
    else:
        source_name = source

    return {
        "title": a.get("title"),
        "description": a.get("description"),
        "url": a.get("url"),
        "image": _first_non_empty(a.get("urlToImage"), a.get("image"), a.get("thumbnail")),
        "publishedAt": _first_non_empty(a.get("publishedAt"), a.get("published"), a.get("published_at"), a.get("date")),
        "source": source_name,
        "author": a.get("author"),
        "content": a.get("content"),
        "category": a.get("category"),
        "language": a.get("language"),
        "country": a.get("country"),
    }


def normalize_newsapi_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [_normalize_common_article(a) for a in articles or []]


def normalize_mediastack_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = []
    for a in articles or []:
        normalized.append(
            {
                "title": a.get("title"),
                "description": a.get("description"),
                "url": a.get("url"),
                "image": a.get("image"),
                "publishedAt": a.get("published_at"),
                "source": a.get("source"),
                "author": a.get("author"),
                "content": a.get("description"),
                "category": a.get("category"),
                "language": a.get("language"),
                "country": a.get("country"),
            }
        )
    return normalized


def normalize_currents_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = []
    for a in articles or []:
        normalized.append(
            {
                "title": a.get("title"),
                "description": _first_non_empty(a.get("description"), a.get("summary")),
                "url": a.get("url"),
                "image": _first_non_empty(a.get("image"), a.get("thumbnail"), a.get("urlToImage")),
                "publishedAt": _first_non_empty(a.get("published"), a.get("published_at"), a.get("date")),
                "source": _first_non_empty(
                    a.get("source"),
                    a.get("author"),
                    a.get("publisher"),
                    a.get("origin"),
                ),
                "author": a.get("author"),
                "content": a.get("content"),
                "category": a.get("category"),
                "language": a.get("language"),
                "country": a.get("country"),
            }
        )
    return normalized


def _extract_articles(payload: Dict[str, Any], provider: str) -> List[Dict[str, Any]]:
    if provider == "newsapi":
        items = payload.get("articles", [])
    elif provider == "mediastack":
        items = payload.get("data", [])
    elif provider == "currents":
        items = _first_non_empty(
            payload.get("news"),
            payload.get("articles"),
            payload.get("data"),
            [],
        )
    else:
        items = []

    return items if isinstance(items, list) else []


# -----------------------------------------------------------------------------
# Fetchers
# -----------------------------------------------------------------------------

def fetch_from_newsapi(category: str = "general", q: str = "", limit: int = 5) -> List[Dict[str, Any]]:
    api_key = get_api_key("newsapi")

    category = (category or "general").strip().lower() or "general"
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
            "country": DEFAULT_COUNTRY,
            "category": category,
            "pageSize": limit,
            "apiKey": api_key,
        }

    payload = _request(url, params=params)
    articles = _extract_articles(payload, "newsapi")
    return normalize_newsapi_articles(articles[:limit])


def fetch_from_mediastack(category: str = "general", q: str = "", limit: int = 5) -> List[Dict[str, Any]]:
    api_key = get_api_key("mediastack")

    category = (category or "general").strip().lower() or "general"
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
        params["countries"] = DEFAULT_COUNTRY
        params["categories"] = category

    payload = _request(MEDIASTACK_NEWS, params=params)
    articles = _extract_articles(payload, "mediastack")
    return normalize_mediastack_articles(articles[:limit])


def fetch_from_currents(category: str = "general", q: str = "", limit: int = 5) -> List[Dict[str, Any]]:
    api_key = get_api_key("currents")

    category = _normalize_category(category)
    q = (q or "").strip()
    limit = _clean_limit(limit)

    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    if q:
        url = CURRENTS_SEARCH
        params = {
            "keywords": q,
            "language": DEFAULT_LANGUAGE,
            "page_size": limit,
            "page_number": 1,
            "apiKey": api_key,
        }
        if category and category != "general":
            params["category"] = category
    else:
        url = CURRENTS_LATEST
        params = {
            "language": DEFAULT_LANGUAGE,
            "country": DEFAULT_COUNTRY,
            "category": category,
            "page_size": limit,
            "page_number": 1,
            "apiKey": api_key,
        }

    payload = _request(url, params=params, headers=headers)
    articles = _extract_articles(payload, "currents")
    return normalize_currents_articles(articles[:limit])


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def fetch_news(
    category: str = "general",
    q: str = "",
    limit: int = 5,
    provider: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    provider:
      - currents
      - newsapi
      - mediastack
      - auto (tries NEWS_PROVIDER env, or currents, then newsapi, then mediastack)
    """
    chosen = (provider or DEFAULT_PROVIDER).strip().lower()

    category = (category or "general").strip()
    q = (q or "").strip()
    limit = _clean_limit(limit)

    if chosen == "currents":
        return fetch_from_currents(category=category, q=q, limit=limit)

    if chosen == "newsapi":
        return fetch_from_newsapi(category=category, q=q, limit=limit)

    if chosen == "mediastack":
        return fetch_from_mediastack(category=category, q=q, limit=limit)

    if chosen == "auto":
        last_error: Optional[HTTPException] = None

        for fn in (fetch_from_currents, fetch_from_newsapi, fetch_from_mediastack):
            try:
                return fn(category=category, q=q, limit=limit)
            except HTTPException as exc:
                last_error = exc
                continue

        if last_error is not None:
            raise last_error

        raise HTTPException(status_code=500, detail="All news providers failed")

    raise HTTPException(status_code=400, detail="Invalid NEWS_PROVIDER")


# -----------------------------------------------------------------------------
# Query helpers
# -----------------------------------------------------------------------------

def extract_wiki_title(message: str) -> str:
    msg = (message or "").strip()
    lower = msg.lower()

    prefixes = [
        "wiki",
        "wikipedia",
        "who is",
        "what is",
        "tell me about",
        "tell me who is",
        "tell me what is",
    ]

    for prefix in prefixes:
        if lower.startswith(prefix):
            cleaned = msg[len(prefix):].strip(" :-?.,")
            return cleaned

    return msg.strip(" :-?.,") if msg else ""


def extract_news_query(message: str) -> str:
    msg = (message or "").strip()
    lower = msg.lower()

    lower = re.sub(
        r"^(show me|tell me|give me|latest|latest news|news about|news on)\s+",
        "",
        lower,
    ).strip()

    lower = re.sub(r"\bnews\b", "", lower).strip()

    stop_words = {
        "about", "the", "a", "an", "today", "please", "of", "for", "from", "on", "in"
    }
    words = [w for w in lower.split() if w not in stop_words]

    return " ".join(words).strip()


def detect_news_category(text: str) -> str:
    t = (text or "").lower()

    rules: List[Tuple[Tuple[str, ...], str]] = [
        (("sports", "sport", "football", "soccer", "cricket", "tennis"), "sports"),
        (("business", "finance", "economy", "stock", "market", "trading"), "business"),
        (("health", "covid", "corona", "virus", "medicine", "medical"), "health"),
        (("entertainment", "movie", "movies", "music", "celebrity", "tv", "show"), "entertainment"),
        (("science", "space", "nasa", "research", "discovery"), "science"),
        (("technology", "tech", "ai", "gadgets", "innovation", "software", "hardware"), "technology"),
        (("politics", "election", "government", "policy", "diplomacy"), "politics"),
        (("world", "international", "global", "foreign"), "general"),
        (("general", "news", "headlines", "latest"), "general"),
    ]

    for keywords, category in rules:
        if any(k in t for k in keywords):
            return category

    return "general"