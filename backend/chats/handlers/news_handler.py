from fastapi import HTTPException
import logging

from backend.chats.services.news_service import (
    fetch_news,
    extract_news_query,
    detect_news_category,
)

logger = logging.getLogger(__name__)


def handle_news_request(msg: str, user_message: str):
    text = (msg or "").lower()

    # 🔥 Better intent detection
    triggers = ["news", "headlines", "latest", "update"]
    if not any(t in text for t in triggers):
        return None

    category = detect_news_category(user_message)
    query = extract_news_query(user_message)

    try:
        # 🔥 Explicit provider (currents best)
        data = fetch_news(
            category=category,
            q=query,
            limit=5,
            provider="auto"   # ya "currents" if you want force
        )

    except HTTPException as e:
        logger.error(f"News API error: {e.detail}")
        return {
            "type": "text",
            "content": f"News error: {e.detail}"
        }

    except Exception as e:
        logger.exception("Unexpected error in news handler")
        return {
            "type": "text",
            "content": "Something went wrong while fetching news 😢"
        }

    if not data:
        return {
            "type": "text",
            "content": "Koi news nahi mili 😢 (try different topic)"
        }

    return {
        "type": "news",
        "category": category,
        "query": query,
        "count": len(data),  # 🔥 useful for frontend
        "content": data,
    }