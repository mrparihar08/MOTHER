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


def _normalize_common_article(a: Dict[str, Any], provider: str = "generic") -> Dict[str, Any]:
    """Transform diverse API schemas into Vitya.ai's standard article representation."""
    source = a.get("source")
    source_name = None

    if isinstance(source, dict):
        source_name = source.get("name") or source.get("id")
    elif isinstance(source, str):
        source_name = source
    else:
        source_name = a.get("author") or "News"

    title = (a.get("title") or "Headline").strip()
    url = (a.get("url") or a.get("link") or "#").strip()
    art_id = hashlib.md5(f"{title}_{url}".encode("utf-8")).hexdigest()[:12]

    category_val = a.get("category") or "general"
    img_candidate = _first_non_empty(a.get("urlToImage"), a.get("image"), a.get("thumbnail"), a.get("imageUrl"))
    if not img_candidate:
        img_candidate = CATEGORY_FALLBACK_IMAGES.get(category_val, CATEGORY_FALLBACK_IMAGES["general"])

    return {
        "id": art_id,
        "title": title,
        "description": (a.get("description") or a.get("summary") or a.get("snippet") or "").strip(),
        "url": url,
        "image": img_candidate,
        "publishedAt": _first_non_empty(a.get("publishedAt"), a.get("published"), a.get("published_at"), a.get("date")),
        "source": source_name or "Verified Source",
        "author": a.get("author"),
        "category": category_val,
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


def fetch_from_web_fallback(
    category: str = "general",
    q: str = "",
    country: str = "in",
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Resilient fallback that queries real-time web news if dedicated APIs are unconfigured or down."""
    try:
        from backend.chats.services.web_search_service import perform_web_search

        search_query = f"{q or category} latest news headlines {country}"
        results = perform_web_search(search_query, max_results=limit)
        if not results:
            return []

        articles = []
        for item in results[:limit]:
            title = item.get("title") or "News Headline"
            url = item.get("link") or item.get("url") or "#"
            articles.append({
                "id": hashlib.md5(f"{title}_{url}".encode("utf-8")).hexdigest()[:12],
                "title": title,
                "description": item.get("snippet") or "Recent news headline update.",
                "url": url,
                "image": None,
                "publishedAt": "Recent",
                "source": "Web News",
                "author": None,
                "category": category,
                "provider": "web_fallback",
            })
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
    - Provider-specific calls (newsapi, mediastack, currents)
    - 'auto' multi-provider failover with automatic fallback
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
    elif chosen_provider == "auto":
        # 3. Dynamic Auto Failover
        provider_map = {
            "newsapi": fetch_from_newsapi,
            "mediastack": fetch_from_mediastack,
            "currents": fetch_from_currents,
        }

        # Try configured providers first
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

        # If configured APIs exhausted or none configured, try Web Fallback
        if not articles:
            logger.info("External news APIs unavailable. Triggering resilient web search news fallback.")
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


def is_news_summary_query(text: str) -> bool:
    """Identify if the user is asking to summarize or analyze a recently retrieved news article."""
    t = (text or "").lower()
    summary_words = ["summarize", "summary", "samjhao", "explain", "impact", "visleshan", "analys", "faida", "nuksan", "hindi me samjhao"]
    reference_words = ["is news", "this news", "is article", "this article", "isko", "iska", "article ko", "news ko"]

    has_summary_intent = any(w in t for w in summary_words)
    has_reference = any(r in t for r in reference_words) or t.startswith("summarize") or t.startswith("/summary")

    return has_summary_intent and (has_reference or len(t.split()) <= 8)


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
        return "⚠️ Samjhane ke liye koi news article available nahi hai."

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