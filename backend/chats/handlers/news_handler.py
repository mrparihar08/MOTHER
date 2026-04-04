from fastapi import HTTPException
from backend.chats.utils.news_utils import (
    fetch_news,
    extract_news_query,
    detect_news_category,
)


def handle_news_request(msg, user_message):
    if "news" not in msg:
        return None

    category = detect_news_category(user_message)
    query = extract_news_query(user_message)

    try:
        data = fetch_news(category=category, q=query, limit=5)
    except HTTPException:
        raise
    except Exception:
        return {"type": "text", "content": "News fetch error 😢"}

    if not data:
        return {"type": "text", "content": "News nahi mili 😢"}

    return {
        "type": "news",
        "category": category,
        "query": query,
        "content": data,
    }