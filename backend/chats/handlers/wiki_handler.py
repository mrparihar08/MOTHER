from fastapi import HTTPException
from backend.chats.services.wikipedia_service import get_complete
from backend.chats.services.news_service import extract_wiki_title


def handle_wiki_request(msg, user_message):
    if not any(word in msg for word in ["wiki", "wikipedia", "who is", "what is", "tell me about"]):
        return None

    try:
        title = extract_wiki_title(user_message)

        if not title:
            return {"type": "text", "content": "Wikipedia ke liye query do 🤔"}

        data = get_complete(title)

        if not data or data.get("error"):
            return {
                "type": "text",
                "content": f"'{title}' ke liye Wikipedia data nahi mila 😢",
            }

        return {
            "type": "wiki",
            "content": {
                "title": data.get("title"),
                "summary": data.get("summary"),
                "images": data.get("images", []),
                "url": data.get("url"),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))