# news_utils.py
import os
import re
import requests
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

BASE_TOP = "https://newsapi.org/v2/top-headlines"
BASE_SEARCH = "https://newsapi.org/v2/everything"


def get_news_api_key():
    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="NEWS_API_KEY missing")
    return api_key


def fetch_news(category: str = "general", q: str = "", limit: int = 5):
    api_key = get_news_api_key()

    category = (category or "general").strip().lower() or "general"
    q = (q or "").strip()
    limit = max(1, min(int(limit or 5), 20))

    try:
        if q:
            url = BASE_SEARCH
            params = {
                "q": q,
                "language": "en",
                "sortBy": "publishedAt",
                "apiKey": api_key
            }
        else:
            url = BASE_TOP
            params = {
                "country": "in",
                "category": category,
                "apiKey": api_key
            }

        res = requests.get(url, params=params, timeout=10)

        if res.status_code != 200:
            try:
                error_data = res.json()
            except Exception:
                error_data = {}
            raise HTTPException(
                status_code=res.status_code,
                detail=error_data.get("message", "News fetch error")
            )

        articles = res.json().get("articles", [])[:limit]

        return [
            {
                "title": a.get("title"),
                "description": a.get("description"),
                "url": a.get("url"),
                "image": a.get("urlToImage"),
                "publishedAt": a.get("publishedAt"),
                "source": a.get("source", {}).get("name")
            }
            for a in articles
        ]

    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="News timeout")
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=500, detail="Network error")


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
        "tell me what is"
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

    if "sports" in t:
        return "sports"
    if "business" in t:
        return "business"
    if "health" in t:
        return "health"
    if "entertainment" in t or "movie" in t or "movies" in t:
        return "entertainment"
    if "science" in t:
        return "science"
    if "technology" in t or "tech" in t or "ai" in t:
        return "technology"

    return "general"