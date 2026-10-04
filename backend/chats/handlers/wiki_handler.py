import re
import logging
from typing import Any, Dict, Optional
from fastapi import HTTPException

from backend.chats.services.wikipedia_service import get_complete, search

logger = logging.getLogger(__name__)

# Extended Wikipedia command & question triggers
WIKI_TRIGGERS = [
    "/wiki", "/wikipedia", "wiki", "wikipedia", "who is", "who was",
    "what is", "what was", "tell me about", "tell me who is",
    "tell me what is", "explain", "ke baare me batao", "ke baare me"
]


def _clean_wiki_title(raw_text: str) -> str:
    """Extract and clean the target entity/subject from natural queries."""
    msg = (raw_text or "").strip()

    # Strip prefixes
    prefixes_pat = r"(?i)^(?:/wiki|/wikipedia|wiki:?|wikipedia:?|who\s+(?:is|was)|what\s+(?:is|was)|tell\s+me\s+(?:about|who\s+is|what\s+is)?|explain|batao\s+(?:about|who\s+is|what\s+is)?)\s*"
    cleaned = re.sub(prefixes_pat, "", msg).strip()

    # Strip suffixes (Hinglish: "ke baare me batao", "ke baare me jankari")
    suffixes_pat = r"(?i)\s*(?:ke\s+baare\s+me\s+(?:batao|jankari\s+do|likho)?|ke\s+baare\s+me|kya\s+hai|kaun\s+hai|kon\s+hai|batao)$"
    cleaned = re.sub(suffixes_pat, "", cleaned).strip()

    return cleaned.strip(" :-?.,\"'")


def handle_wiki_request(msg: str, user_message: str, force: bool = False) -> Optional[Dict[str, Any]]:
    """
    Handles Wikipedia encyclopedia knowledge requests.
    Supports smart query extraction, fuzzy search fallbacks, and structured multi-media output.
    """
    raw_text = (user_message or "").strip()
    text = (msg or "").lower().strip()

    has_wiki_trigger = (
        text.startswith("/wiki")
        or text.startswith("/wikipedia")
        or any(re.search(rf"\b{re.escape(w)}\b", text) for w in ["wiki", "wikipedia"])
    )

    if not force and not has_wiki_trigger:
        return None

    title = _clean_wiki_title(raw_text) or raw_text

    if not title or len(title) < 2:
        return {
            "type": "text",
            "content": "📚 Wikipedia par search karne ke liye topic ya naam batayein (e.g. '/wiki Artificial Intelligence' ya 'who is Albert Einstein').",
        }

    try:
        data = get_complete(title)

        # Disambiguation or Page not found fallback: try search
        if not data or data.get("error"):
            s = search(title)
            results = s.get("results", []) if isinstance(s, dict) else []
            if results:
                for candidate in results[:3]:
                    candidate_data = get_complete(candidate)
                    if candidate_data and not candidate_data.get("error"):
                        data = candidate_data
                        break

        # If still error, return friendly feedback with options if disambiguation
        if not data or data.get("error"):
            error_type = data.get("error") if isinstance(data, dict) else None
            options = data.get("options", []) if isinstance(data, dict) else []

            if options:
                opts_str = ", ".join(f"**{opt}**" for opt in options[:5])
                return {
                    "type": "text",
                    "content": f"🔍 '{title}' ke kai matlab ho sakte hain. Kripya inme se ek choose karein: {opts_str}.",
                }

            return {
                "type": "text",
                "content": f"📚 '{title}' ke liye Wikipedia par jankari nahi mili 😢. Kripya spelling check karein ya dusra naam try karein.",
            }

        page_title = data.get("title") or title
        summary = data.get("summary") or "No summary available."
        url = data.get("url") or f"https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')}"
        images = [img for img in data.get("images", []) if img.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]

        # Markdown formatted summary for chat / text fallback
        text_summary = f"📖 **[{page_title}]({url})**\n\n{summary}\n\n🔗 [Read full article on Wikipedia]({url})"

        return {
            "type": "wiki",
            "content": {
                "title": page_title,
                "summary": summary,
                "images": images[:3],
                "url": url,
            },
            "text_summary": text_summary,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Wikipedia search exception: %s", e)
        return {
            "type": "text",
            "content": f"⚠️ Wikipedia search error: {str(e)}",
            "error": True,
        }