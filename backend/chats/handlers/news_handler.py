import re
import logging
from typing import Any, Dict, List, Optional
from fastapi import HTTPException

from backend.chats.services.news_service import (
    fetch_news,
    extract_news_query,
    detect_news_category,
)

logger = logging.getLogger(__name__)

# Extended news trigger keywords (English + Hinglish + Common slang)
NEWS_TRIGGERS = [
    "/news", "/headlines", "news", "headlines", "headline", "samachar",
    "khabar", "taza khabar", "aaj ki khabar", "aaj ka samachar",
    "breaking news", "current affairs", "latest updates", "latest update",
    "kya chal raha hai", "trending news", "world news", "top stories"
]

CATEGORY_EMOJIS = {
    "sports": "🏏",
    "business": "📈",
    "technology": "💻",
    "health": "🩺",
    "entertainment": "🎬",
    "science": "🚀",
    "politics": "🏛️",
    "general": "📰",
}


def _clean_news_message(raw_msg: str) -> str:
    """Strip news command prefixes and slashes to extract query."""
    cleaned = re.sub(
        r"(?i)^(?:/news|/headlines|news(?:\s+about|\s+on|\s+for)?|headlines(?:\s+of)?|taza\s+khabar|samachar|khabar|aaj\s+ki\s+khabar)\s*",
        "",
        raw_msg.strip(),
    ).strip(" :-.,")
    return cleaned


def handle_news_request(msg: str, user_message: str, force: bool = False) -> Optional[Dict[str, Any]]:
    """
    Handles news and headline requests from chat.
    Supports topic search, category detection, provider fallback, and rich structured output.
    """
    raw_text = (user_message or "").strip()
    text = (msg or "").lower().strip()

    # Intent check
    has_news_trigger = any(re.search(rf"\b{re.escape(t)}\b", text) for t in NEWS_TRIGGERS) or text.startswith("/news") or text.startswith("/headlines")
    if not force and not has_news_trigger:
        return None

    # Extract clean topic/query & category
    clean_msg = _clean_news_message(raw_text)
    category = detect_news_category(clean_msg or raw_text)
    query = extract_news_query(clean_msg) if clean_msg else ""

    if force and not query and clean_msg:
        query = clean_msg

    emoji = CATEGORY_EMOJIS.get(category, "📰")

    try:
        data = fetch_news(
            category=category,
            q=query,
            limit=5,
            provider="auto",
        )

    except HTTPException as e:
        logger.error("News API error: %s", e.detail)
        return {
            "type": "text",
            "content": f"⚠️ News service temporarily unavailable: {e.detail}",
            "error": True,
        }

    except Exception as e:
        logger.exception("Unexpected error in news handler: %s", e)
        return {
            "type": "text",
            "content": "⚠️ Samachar fetch karte waqt error aaya. Kripya thodi der baad try karein.",
            "error": True,
        }

    if not data:
        topic_str = f" related to '{query}'" if query else f" in {category.capitalize()}"
        return {
            "type": "text",
            "content": f"{emoji} Koi taaza news nahi mili{topic_str}. Aap kisi doosre topic ya category (e.g. 'tech news', 'sports headlines') ke sath try kar sakte hain.",
        }

    # Generate quick markdown summary for text-only fallbacks
    summary_lines = [f"{emoji} **Top {category.capitalize()} Headlines:**\n"]
    for i, item in enumerate(data[:5], 1):
        title = item.get("title") or "Headline"
        src = item.get("source") or "News"
        url = item.get("url") or "#"
        summary_lines.append(f"{i}. [{title}]({url}) - *{src}*")

    text_summary = "\n".join(summary_lines)

    return {
        "type": "news",
        "category": category,
        "query": query,
        "count": len(data),
        "content": data,
        "text_summary": text_summary,
    }