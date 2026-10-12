import json
import logging
import re
from typing import Any, Dict, List, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.api.models.vitya import ChatMessage
from backend.chats.services.news_service import (
    fetch_news,
    extract_news_query,
    detect_news_category,
    detect_news_country,
    detect_state_or_city,
    extract_limit_from_query,
    is_news_source_date_query,
    resolve_news_source_and_date,
    is_news_summary_query,
    summarize_news_articles,
    generate_copilot_hindi_news_digest,
)
from backend.chats.utils.intent_router import is_news_query

logger = logging.getLogger(__name__)

# Extended news trigger keywords (English + Hindi + Hinglish)
NEWS_TRIGGERS = [
    "/news", "/headlines", "news", "headlines", "headline", "samachar",
    "khabar", "taza khabar", "aaj ki khabar", "aaj ka samachar",
    "breaking news", "current affairs", "latest updates", "latest update",
    "trending news", "world news", "top stories",
    "kya hua", "kya huaa", "aaj kya hua", "aaj kya huaa",
    "bharat me kya hua", "bharat me kya huaa", "aaj bharat me kya huaa",
    "desh me kya hua", "desh me kya huaa", "badi khabrein", "badi khabar",
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

# In-memory context cache for active conversation sessions
_CONVERSATION_NEWS_CONTEXT: Dict[int, List[Dict[str, Any]]] = {}
_LAST_RETRIEVED_NEWS: List[Dict[str, Any]] = []


def _clean_news_message(raw_msg: str) -> str:
    """Strip news command prefixes, slashes, and common filler words to extract query."""
    cleaned = re.sub(
        r"(?i)^(?:/news|/headlines|news(?:\s+about|\s+on|\s+for)?|headlines(?:\s+of)?|taza\s+khabar|samachar|khabar|aaj\s+ki\s+khabar|aaj\s+bharat\s+me\s+kya\s+huaa?|bharat\s+me\s+kya\s+huaa?|aaj\s+kya\s+huaa?|kya\s+huaa?)\s*",
        "",
        raw_msg.strip(),
    ).strip(" :-.,")
    return cleaned


def _find_recent_news_articles(db: Optional[Session], conversation_id: Optional[int]) -> List[Dict[str, Any]]:
    """Retrieve recently fetched news articles from memory or conversation history."""
    if conversation_id and conversation_id in _CONVERSATION_NEWS_CONTEXT:
        cached = _CONVERSATION_NEWS_CONTEXT[conversation_id]
        if cached:
            return cached

    if _LAST_RETRIEVED_NEWS:
        return _LAST_RETRIEVED_NEWS

    if not db or not conversation_id:
        return []

    try:
        past_msgs = (
            db.query(ChatMessage)
            .filter(ChatMessage.conversation_id == conversation_id, ChatMessage.role == "assistant")
            .order_by(ChatMessage.id.desc())
            .limit(8)
            .all()
        )
        for msg in past_msgs:
            if not msg.content:
                continue
            try:
                parsed = json.loads(msg.content)
                if isinstance(parsed, dict):
                    items = parsed.get("content") or parsed.get("articles") or parsed.get("data")
                    if isinstance(items, list) and items:
                        if isinstance(items[0], dict) and (items[0].get("title") or items[0].get("source")):
                            return items
            except Exception:
                continue
    except Exception as e:
        logger.warning("Error fetching recent news from history: %s", e)
    return []


def handle_news_request(
    msg: str,
    user_message: str,
    db: Optional[Session] = None,
    conversation_id: Optional[int] = None,
    force: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Handles news, headline, source/date verification, and news summarization/explanation requests from chat.
    Supports topic search, state/city extraction, category detection, multi-provider fallback,
    contextual follow-ups, and polished Hindi Copilot-style news digest generation.
    """
    global _LAST_RETRIEVED_NEWS
    raw_text = (user_message or "").strip()
    text = (msg or "").lower().strip()

    # 1. Check if user is asking for Source and Publication Date verification
    is_source_date = is_news_source_date_query(raw_text)

    # 2. Check if user is asking to summarize/explain news
    is_summary = is_news_summary_query(raw_text)

    # 3. Check standard news triggers
    has_news_trigger = (
        is_news_query(raw_text)
        or is_news_query(text)
        or any(re.search(rf"\b{re.escape(t)}\b", text) for t in NEWS_TRIGGERS)
        or text.startswith("/news")
        or text.startswith("/headlines")
    )

    if not force and not has_news_trigger and not is_summary and not is_source_date:
        return None

    # Handle Source and Publication Date Verification follow-ups
    if is_source_date:
        recent_articles = _find_recent_news_articles(db, conversation_id)
        return resolve_news_source_and_date(recent_articles, user_query=raw_text)

    # Handle News Summary / Impact Analysis follow-ups
    if is_summary:
        recent_articles = _find_recent_news_articles(db, conversation_id)
        quoted_match = re.search(r'["\']([^"\']{5,})["\']', raw_text) or re.search(r':\s*["\']?([^"\']{5,})["\']?$', raw_text)
        target_articles = []

        if quoted_match:
            quoted_title = quoted_match.group(1).strip().lower()
            matched = [a for a in recent_articles if quoted_title in (a.get("title") or "").lower()]
            if matched:
                target_articles = matched
            else:
                fetched = fetch_news(q=quoted_match.group(1).strip()[:50], limit=3, provider="auto")
                if fetched:
                    target_articles = fetched
                else:
                    target_articles = [{"title": quoted_match.group(1).strip(), "source": "News Reference", "description": raw_text}]
        elif recent_articles:
            # Check if user mentioned index (e.g. "pehli news", "2nd news")
            idx_map = {"pehli": 0, "first": 0, "1st": 0, "dusri": 1, "doosri": 1, "second": 1, "2nd": 1, "teesri": 2, "third": 2}
            chosen_idx = 0
            for w, idx in idx_map.items():
                if re.search(rf"\b{re.escape(w)}\b", text) and idx < len(recent_articles):
                    chosen_idx = idx
                    break
            target_articles = [recent_articles[chosen_idx]]
        else:
            # No recent articles found in conversation context
            return {
                "type": "text",
                "content": (
                    "Aap, conversation context mein abhi koi news article uplabdh nahi hai jise summarize kiya ja sake. "
                    "Aap kisi news ka headline, text, ya link yahan share kar sakte hain, ya pehle taaza khabrein maang sakte hain "
                    "(jaise: *'aaj ki top news batao'*), phir main uska short summary bana dunga."
                ),
                "intent": "NEWS_SUMMARY",
            }

        summary_text = summarize_news_articles(target_articles, user_prompt=raw_text, language="hinglish")
        return {
            "type": "text",
            "content": summary_text,
            "intent": "NEWS_SUMMARY",
            "articles_referenced": [a.get("title") for a in target_articles if a.get("title")],
        }

    # Extract clean topic/query, state/city, category & target country
    clean_msg = _clean_news_message(raw_text)
    state_or_city = detect_state_or_city(clean_msg or raw_text)
    category = detect_news_category(clean_msg or raw_text)
    country = detect_news_country(raw_text)
    limit = extract_limit_from_query(raw_text, default_limit=5)

    if state_or_city:
        query = state_or_city
        country = "in"
    elif "ai" in text.split() or "artificial intelligence" in text:
        query = "Artificial Intelligence"
        category = "technology"
    elif any(k in text for k in ["aaj bharat mein kya hua", "bharat me kya hua", "bharat mein kya hua", "desh me kya hua"]):
        query = ""
        country = "in"
        category = "general"
    else:
        query = extract_news_query(clean_msg) if clean_msg else ""

    if force and not query and clean_msg:
        query = clean_msg

    emoji = CATEGORY_EMOJIS.get(category, "📰")

    try:
        data = fetch_news(
            category=category,
            q=query,
            country=country,
            limit=limit,
            provider="auto",
        )
    except HTTPException as e:
        logger.error("News API HTTP exception: %s", e.detail)
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
            "content": f"{emoji} Maaf kijiye, is samay '{query or category}' se judi koi verified taaza khabar nahi mil saki. Aap kisi doosre topic ya category (e.g. 'tech news', 'sports headlines', 'Madhya Pradesh news') ke sath try kar sakte hain.",
        }

    digest = generate_copilot_hindi_news_digest(data, user_prompt=raw_text)
    final_articles = digest.get("articles") or data

    # Update conversation memory context
    if conversation_id:
        _CONVERSATION_NEWS_CONTEXT[conversation_id] = final_articles
    _LAST_RETRIEVED_NEWS = final_articles

    # Generate quick markdown summary for text-only fallbacks
    header_title = digest.get("header") or f"Top {category.capitalize()} Headlines"
    summary_lines = [f"{emoji} **{header_title}:**\n"]
    if digest.get("intro"):
        summary_lines.insert(0, f"{digest['intro']}\n")
    for i, item in enumerate(final_articles[:limit], 1):
        title = item.get("title") or "Headline"
        src = item.get("source_name") or item.get("source") or "News"
        url = item.get("url") or "#"
        summary_lines.append(f"{title} - *{src}* [Link]({url})")

    text_summary = "\n".join(summary_lines)

    return {
        "type": "news",
        "category": category,
        "query": query,
        "country": country,
        "count": len(final_articles),
        "intro": digest.get("intro"),
        "header": digest.get("header"),
        "disclaimer": digest.get("disclaimer"),
        "content": final_articles,
        "text_summary": text_summary,
    }