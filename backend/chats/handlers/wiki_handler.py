from fastapi import HTTPException
from backend.chats.services.wikipedia_service import get_complete
from backend.chats.services.news_service import extract_wiki_title


def handle_wiki_request(msg: str, user_message: str, force: bool = False):
    if not force and not any(word in (msg or "").lower() for word in ["wiki", "wikipedia"]):
        return None

    try:
        title = extract_wiki_title(user_message) or user_message

        if not title:
            return {"type": "text", "content": "Wikipedia ke liye query do 🤔"}

        data = get_complete(title)

        if not data or data.get("error"):
            from backend.chats.services.wikipedia_service import search
            s = search(title)
            results = s.get("results", [])
            if results:
                data = get_complete(results[0])

        if not data or data.get("error"):
            return {
                "type": "text",
                "content": f"'{title}' ke liye Wikipedia data nahi mila 😢",
            }

        return {
            "type": "wiki",
            "content": {
                "title": data.get("title") or title,
                "summary": data.get("summary") or "No summary available",
                "images": data.get("images", []),
                "url": data.get("url") or "#",
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        return {"type": "text", "content": f"Wikipedia search error: {str(e)}"}