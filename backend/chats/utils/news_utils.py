# news_utils.py
import os
import re
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

NEWSAPI_TOP = "https://newsapi.org/v2/top-headlines"
NEWSAPI_SEARCH = "https://newsapi.org/v2/everything"

MEDIASTACK_NEWS = "https://api.mediastack.com/v1/news"

DEFAULT_PROVIDER = os.getenv("NEWS_PROVIDER", "auto").strip().lower()
DEFAULT_COUNTRY = os.getenv("NEWS_COUNTRY", "in").strip().lower() or "in"


def get_api_key(provider: str) -> str:
    provider = (provider or "").strip().lower()

    if provider == "mediastack":
        api_key = os.getenv("MEDIASTACK_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="MEDIASTACK_API_KEY missing")
        return api_key

    if provider == "newsapi":
        api_key = os.getenv("NEWS_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="NEWS_API_KEY missing")
        return api_key

    raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")


def normalize_newsapi_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "title": a.get("title"),
            "description": a.get("description"),
            "url": a.get("url"),
            "image": a.get("urlToImage"),
            "publishedAt": a.get("publishedAt"),
            "source": a.get("source", {}).get("name"),
            "author": a.get("author"),
            "content": a.get("content"),
        }
        for a in articles
    ]


def normalize_mediastack_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "title": a.get("title"),
            "description": a.get("description"),
            "url": a.get("url"),
            "image": a.get("image"),
            "publishedAt": a.get("published_at"),
            "source": a.get("source"),
            "author": a.get("author"),
            "category": a.get("category"),
            "language": a.get("language"),
            "country": a.get("country"),
        }
        for a in articles
    ]


def _raise_if_bad_response(res: requests.Response) -> None:
    if res.status_code == 200:
        return

    try:
        data = res.json()
    except Exception:
        data = {}

    detail = (
        data.get("message")
        or data.get("error", {}).get("message")
        or "News fetch error"
    )
    raise HTTPException(status_code=res.status_code, detail=detail)


def fetch_from_newsapi(category: str = "general", q: str = "", limit: int = 5) -> List[Dict[str, Any]]:
    api_key = get_api_key("newsapi")

    category = (category or "general").strip().lower() or "general"
    q = (q or "").strip()
    limit = max(1, min(int(limit or 5), 100))

    if q:
        url = NEWSAPI_SEARCH
        params = {
            "q": q,
            "language": "en",
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

    try:
        res = requests.get(url, params=params, timeout=10)
        _raise_if_bad_response(res)
        articles = res.json().get("articles", [])
        return normalize_newsapi_articles(articles[:limit])

    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="News timeout")
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=500, detail="Network error")


def fetch_from_mediastack(category: str = "general", q: str = "", limit: int = 5) -> List[Dict[str, Any]]:
    api_key = get_api_key("mediastack")

    category = (category or "general").strip().lower() or "general"
    q = (q or "").strip()
    limit = max(1, min(int(limit or 5), 100))

    params = {
        "access_key": api_key,
        "languages": "en",
        "limit": limit,
        "sort": "published_desc",
    }

    # MediaStack uses a single /news endpoint with filters such as countries,
    # categories, languages, keywords, sort, limit, and offset.
    if q:
        params["keywords"] = q
    else:
        params["countries"] = DEFAULT_COUNTRY
        params["categories"] = category

    try:
        res = requests.get(MEDIASTACK_NEWS, params=params, timeout=10)
        _raise_if_bad_response(res)

        payload = res.json()
        articles = payload.get("data", [])
        return normalize_mediastack_articles(articles[:limit])

    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="News timeout")
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=500, detail="Network error")


def fetch_news(
    category: str = "general",
    q: str = "",
    limit: int = 5,
    provider: Optional[str] = None,
):
    """
    provider:
      - newsapi
      - mediastack
      - auto (tries NEWS_PROVIDER env, or newsapi, then mediastack)
    """
    chosen = (provider or DEFAULT_PROVIDER).strip().lower()

    if chosen == "newsapi":
        return fetch_from_newsapi(category=category, q=q, limit=limit)

    if chosen == "mediastack":
        return fetch_from_mediastack(category=category, q=q, limit=limit)

    if chosen == "auto":
        # Try NewsAPI first, then MediaStack if NewsAPI key is missing/fails.
        try:
            return fetch_from_newsapi(category=category, q=q, limit=limit)
        except HTTPException:
            return fetch_from_mediastack(category=category, q=q, limit=limit)

    raise HTTPException(status_code=400, detail="Invalid NEWS_PROVIDER")


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

    lower = re.sub(r"^(show me|tell me|give me|latest|latest news|news about)\s+", "", lower).strip()

    if "news" in lower:
        lower = lower.replace("news", "").strip()

    stop_words = {"about", "the", "a", "an", "today", "please", "of"}
    words = [w for w in lower.split() if w not in stop_words]

    return " ".join(words).strip()


def detect_news_category(text: str) -> str:
    t = (text or "").lower()

    if "sports" in t or "football" in t or "soccer" in t or "cricket" in t or "tennis" in t:
        return "sports"
    if "business" in t or "finance" in t or "economy" in t or "stock" in t:
        return "business"   
    if "health" in t or "covid" in t or "corona" in t or "virus" in t or "medicine" in t or "medical" in t:
        return "health"
    if "entertainment" in t or "movie" in t or "movies" in t or "music" in t or "celebrity" in t or "tv" in t or "show" in t:
        return "entertainment"
    if "science" in t or "space" in t or "nasa" in t or "research" in t or "discovery" in t or "technology" in t:
        return "science"
    if "technology" in t or "tech" in t or "ai" in t or "gadgets" in t or "innovation" in t or "software" in t or "hardware" in t:
        return "technology"
    if "politics" in t or "election" in t or "government" in t or "policy" in t or "diplomacy" in t or "international relations" in t:
        return "politics"
    if "world" in t or "international" in t or "global" in t or "foreign" in t or "diplomacy" in t:
        return "general"
    if "general" in t or "news" in t or "headlines" in t or "latest" in t:
        return "general"
    if "government" in t or "policy" in t or "diplomacy" in t or "international relations" in t:
        return "politics"
    

    return "general"