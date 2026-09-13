import re
from typing import Optional
from backend.api.models.vitya import ChatMessage
from backend.chats.chatbot import chatbot_reply

from backend.chats.utils.rules import get_reply
from backend.chats.services.gemini_service import generate_response
from backend.chats.services.web_search_service import perform_web_search, format_web_search_context
from backend.chats.services.ai_image_service import generate_ai_image
from backend.chats.services.rag_service import rag_store, format_rag_context


def handle_chatbot(user_message: str, db, current_user, use_web_search: bool = False, conversation_id: Optional[int] = None):
    msg_lower = (user_message or "").lower().strip()

    # 1. AI Image Generation Trigger in Chat
    image_triggers = ["generate image", "create image", "draw image", "make an image", "picture of", "photo of", "/image"]
    if any(trig in msg_lower for trig in image_triggers):
        image_prompt = re.sub(r"(?i)^(?:generate|create|draw|make|show)?\s*(?:an?\s*)?(?:image|photo|picture|visual|/image)\s*(?:of|about|for)?\s*", "", user_message).strip()
        img_url_or_path = generate_ai_image(image_prompt or user_message)
        if img_url_or_path:
            return {
                "type": "image",
                "content": img_url_or_path,
                "url": img_url_or_path,
                "caption": f"🖼️ AI Image: {image_prompt or user_message}",
            }

    # 2. Rule-based Chatbot Reply Check
    reply = chatbot_reply(user_message, db, current_user)

    # 3. Multi-Document RAG Context Retrieval & Conversation History
    rag_context = ""
    history_context = ""

    if conversation_id and db and reply is None:
        try:
            # Multi-turn Chat Memory
            past_msgs = (
                db.query(ChatMessage)
                .filter(ChatMessage.conversation_id == conversation_id)
                .order_by(ChatMessage.id.desc())
                .limit(6)
                .all()
            )
            if past_msgs:
                past_msgs.reverse()
                history_lines = [f"{m.role.capitalize()}: {m.content}" for m in past_msgs]
                history_context = "Recent Conversation History:\n" + "\n".join(history_lines)
        except Exception:
            pass

        try:
            chunks = rag_store.search(conversation_id, user_message, top_k=4)
            if chunks:
                rag_context = format_rag_context(user_message, chunks)
        except Exception:
            pass

    # 4. Real-time Web Search Integration
    search_triggers = ["search", "latest", "stock", "today", "current", "who won", "price", "news", "realtime", "real-time"]
    should_search = use_web_search or any(trig in msg_lower for trig in search_triggers)

    search_context = ""
    sources = []
    if should_search and reply is None:
        try:
            results = perform_web_search(user_message, max_results=5)
            if results:
                search_context = format_web_search_context(user_message, results)
                sources = [{"title": r["title"], "url": r["url"]} for r in results if r.get("url")]
        except Exception:
            pass

    # 5. LLM Prompt Construction (History + RAG + Web Search + User Question)
    if reply is None:
        context_blocks = [c for c in [history_context, rag_context, search_context] if c]
        combined_context = "\n\n".join(context_blocks)
        prompt_with_context = f"{combined_context}\n\nUser Question: {user_message}" if combined_context else user_message
        reply = generate_response(prompt_with_context)


    if reply is None:
        reply = get_reply(user_message)

    if isinstance(reply, dict):
        if sources:
            reply["sources"] = sources
        return reply

    res_dict = {
        "type": "text",
        "content": reply if isinstance(reply, str) else str(reply),
    }
    if sources:
        res_dict["sources"] = sources

    return res_dict