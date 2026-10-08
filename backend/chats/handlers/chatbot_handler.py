import re
import logging
from typing import Any, Dict, List, Optional, Union
from sqlalchemy.orm import Session

from backend.api.models.vitya import ChatMessage
from backend.chats.chatbot import chatbot_reply
from backend.chats.utils.rules import get_reply
from backend.chats.services.gemini_service import generate_response, generate_response_stream
from backend.chats.services.web_search_service import perform_web_search, format_web_search_context
from backend.chats.services.ai_image_service import generate_ai_image
from backend.chats.services.rag_service import rag_store, format_rag_context
from backend.chats.handlers.dora_handler import handle_dora_health, is_health_query

logger = logging.getLogger(__name__)

# Real-time search triggers for timely queries
SEARCH_TRIGGERS = [
    "search", "google", "latest", "today", "current", "current price",
    "stock price", "who won", "score", "live", "weather today", "news",
    "realtime", "real-time", "kya hua", "aaj ka", "aaj ki khabar",
    "president of", "prime minister", "rate today", "gold rate", "crypto"
]

# Image generation command triggers
IMAGE_TRIGGERS = [
    "/image", "generate image", "create image", "draw image", "make an image",
    "make image", "picture of", "photo of", "ai image", "illustration of",
    "tasveer banao", "photo banao", "image banao", "draw a", "draw me"
]


def _clean_image_prompt(raw_text: str) -> str:
    """Extract clean visual prompt by stripping command prefix words."""
    cleaned = re.sub(
        r"(?i)^(?:/image|generate(?:\s+an?)?\s+image|create(?:\s+an?)?\s+image|draw(?:\s+an?)?\s+image|make(?:\s+an?)?\s+image|draw(?:\s+me)?|picture(?:\s+of)?|photo(?:\s+of)?|ai\s+image|tasveer\s+banao|photo\s+banao|image\s+banao)\s*(?:of|about|for|showing|depicting)?\s*",
        "",
        raw_text.strip(),
    ).strip()
    return cleaned or raw_text.strip()


def _is_realtime_query(text: str, explicit_search: bool = False) -> bool:
    """Determine if query needs real-time search context."""
    if explicit_search:
        return True
    t = text.lower()
    return any(re.search(rf"\b{re.escape(k)}\b", t) for k in SEARCH_TRIGGERS)


def _build_history_context(db: Session, conversation_id: int, limit: int = 8) -> str:
    """Retrieve recent multi-turn chat messages formatted for LLM context."""
    try:
        past_msgs = (
            db.query(ChatMessage)
            .filter(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.id.desc())
            .limit(limit)
            .all()
        )
        if past_msgs:
            past_msgs.reverse()
            history_lines = [
                f"{m.role.capitalize()}: {m.content}"
                for m in past_msgs
                if m.content and not m.content.startswith("Generated file download")
            ]
            if history_lines:
                return "Recent Conversation History:\n" + "\n".join(history_lines)
    except Exception as e:
        logger.warning("Failed to fetch conversation history: %s", e)
    return ""


def _build_rag_context(user_message: str, conversation_id: Optional[int], user_id: Optional[int]) -> str:
    """Retrieve multi-document RAG context from active knowledge base."""
    if not conversation_id:
        return ""
    try:
        chunks = rag_store.search(conversation_id, user_message, top_k=4, user_id=user_id)
        if chunks:
            return format_rag_context(user_message, chunks)
    except Exception as e:
        logger.warning("RAG search exception: %s", e)
    return ""


def _build_system_instruction(user_name: Optional[str] = None) -> str:
    """Generate dynamic system prompt with multilingual & persona guidelines."""
    name_str = f"The user's name is {user_name}." if user_name else ""
    return (
        f"You are Vitya AI, an advanced, empathetic, intelligent, and proactive AI companion. {name_str}\n\n"
        "CORE DIRECTIVES:\n"
        "1. GENERAL ASSISTANT: You are a versatile AI assistant capable of answering general knowledge, coding, science, writing, daily tasks, weather, news, and financial questions.\n"
        "2. LANGUAGE & STYLE: Always match the language, tone, and dialect of the user. If the user talks in Hinglish ('mera balance batao', 'kaise ho'), respond naturally and warmly in Hinglish.\n"
        "3. NO UNNECESSARY DISCLAIMERS: Never add medical, health, or financial disclaimers to greetings, small talk, general knowledge, or conversational queries. Answer the user's specific question directly.\n"
        "4. STRUCTURE: Use clean GitHub-flavored Markdown with bold headers, bullet points, and tables where appropriate.\n"
        "5. ACCURACY: When web search or document context is provided, prioritize verified facts and cite relevant sources."
    )


def handle_chatbot(
    user_message: str,
    db: Session,
    current_user: Any,
    use_web_search: bool = False,
    conversation_id: Optional[int] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    city: Optional[str] = None,
    client_ip: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Main entrypoint for intelligent chat handling:
    1. AI Image generation triggers
    2. Structured financial transactions / charts / utility rules (Weather, Balance, QR)
    3. Multi-turn chat memory + Document RAG context retrieval
    4. Real-time web search with source citations
    5. Gemini LLM response generation with personalized multilingual system instructions
    6. Offline fallback rules
    """
    msg = (user_message or "").strip()
    if not msg:
        return {"type": "text", "content": "Please provide a message."}

    msg_lower = msg.lower()
    user_id = getattr(current_user, "id", None)
    user_name = getattr(current_user, "name", None) or getattr(current_user, "username", None)

    # 1. AI Image Generation Trigger
    if any(trig in msg_lower for trig in IMAGE_TRIGGERS):
        image_prompt = _clean_image_prompt(msg)
        img_url_or_path = generate_ai_image(image_prompt, is_presentation=False)
        if img_url_or_path:
            return {
                "type": "image",
                "content": img_url_or_path,
                "url": img_url_or_path,
                "caption": f"🖼️ {image_prompt}",
                "prompt": image_prompt,
                "model": "Google Imagen 3",
                "aspect_ratio": "16:9",
                "intent": "IMAGE_GENERATION",
                "disclaimer": None,
            }
        else:
            return {
                "type": "text",
                "content": "⚠️ Google Imagen 3 image generate nahi kar paya. Kripya check karein ki `GEMINI_API_KEY` active aur configured hai.",
                "intent": "IMAGE_GENERATION",
            }

    # 2. Rule-based / Financial / Utility Router Check (Transactions, Charts, Weather, Overview, Calculator)
    reply = chatbot_reply(
        msg,
        db,
        current_user,
        latitude=latitude,
        longitude=longitude,
        city=city,
        client_ip=client_ip,
    )
    if reply is not None:
        if isinstance(reply, dict):
            return reply
        return {"type": "text", "content": str(reply)}

    # 4. Multi-Turn Conversation Memory & RAG Context
    history_context = ""
    rag_context = ""
    if conversation_id and db:
        history_context = _build_history_context(db, conversation_id, limit=8)
        rag_context = _build_rag_context(msg, conversation_id, user_id)

    # 5. Real-time Web Search Integration
    sources: List[Dict[str, str]] = []
    search_context = ""
    if _is_realtime_query(msg, explicit_search=use_web_search):
        try:
            search_query = re.sub(r"(?i)^/?(?:search|google)\s*", "", msg).strip() or msg
            results = perform_web_search(search_query, max_results=5)
            if results:
                search_context = format_web_search_context(search_query, results)
                sources = [{"title": r.get("title", "Source"), "url": r.get("url", "")} for r in results if r.get("url")]
        except Exception as e:
            logger.warning("Web search error: %s", e)

    # 6. LLM Generation via Gemini Service
    context_blocks = [c for c in [history_context, rag_context, search_context] if c]
    combined_context = "\n\n".join(context_blocks)
    prompt_with_context = f"{combined_context}\n\nUser Question: {msg}" if combined_context else msg

    system_instruction = _build_system_instruction(user_name=user_name)

    try:
        llm_reply = generate_response(prompt_with_context, system_instruction=system_instruction)
        if llm_reply and not llm_reply.startswith("Gemini error"):
            reply_obj = {
                "type": "text",
                "content": llm_reply,
            }
            if sources:
                reply_obj["sources"] = sources
            return reply_obj
    except Exception as e:
        logger.exception("LLM generation error: %s", e)

    # 7. Offline / Static Rules Fallback
    fallback_text = get_reply(msg)
    if fallback_text:
        return {
            "type": "text",
            "content": fallback_text if isinstance(fallback_text, str) else str(fallback_text),
            "sources": sources if sources else None,
        }

    return {
        "type": "text",
        "content": "Mujhe samajhne me thodi dikkat hui. Aap apna sawal thoda clear ya dusre tarike se pooch sakte hain!",
        "sources": sources if sources else None,
    }


def handle_chatbot_stream(
    user_message: str,
    db: Session,
    current_user: Any,
    use_web_search: bool = False,
    conversation_id: Optional[int] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    city: Optional[str] = None,
    client_ip: Optional[str] = None,
):
    """Streaming generator yielding text chunks for real-time SSE token delivery."""
    msg = (user_message or "").strip()
    if not msg:
        yield "Please provide a message."
        return

    msg_lower = msg.lower()
    user_id = getattr(current_user, "id", None)
    user_name = getattr(current_user, "name", None) or getattr(current_user, "username", None)

    # 1. AI Image Generation Trigger
    if any(trig in msg_lower for trig in IMAGE_TRIGGERS):
        image_prompt = _clean_image_prompt(msg)
        img_url_or_path = generate_ai_image(image_prompt)
        if img_url_or_path:
            yield {
                "structured": True,
                "payload": {
                    "type": "image",
                    "content": img_url_or_path,
                    "url": img_url_or_path,
                    "caption": f"🖼️ AI Image: {image_prompt}",
                    "prompt": image_prompt,
                    "intent": "TASK",
                    "disclaimer": None,
                },
            }
            return

    # 2. Rule-based / Structured reply fallback (Transactions, Charts, Weather, Utilities)
    reply = chatbot_reply(
        msg,
        db,
        current_user,
        latitude=latitude,
        longitude=longitude,
        city=city,
        client_ip=client_ip,
    )
    if reply is not None:
        if isinstance(reply, dict):
            r_type = reply.get("type", "text")
            content = reply.get("content")
            chart_types = {
                "bar", "chart", "pie", "donut", "line", "line_chart",
                "area", "composed", "multi_line", "scatter", "radar",
                "heatmap", "waterfall", "stacked", "receipt", "image",
                "qr", "barcode", "wiki", "news",
            }
            if r_type in chart_types or isinstance(content, (list, dict)):
                yield {"structured": True, "payload": reply}
            else:
                yield str(content if content is not None else reply)
        else:
            yield str(reply)
        return

    # 2. History & RAG Context
    history_context = ""
    rag_context = ""
    if conversation_id and db:
        history_context = _build_history_context(db, conversation_id, limit=8)
        rag_context = _build_rag_context(msg, conversation_id, user_id)

    # 3. Web Search Context
    search_context = ""
    if _is_realtime_query(msg, explicit_search=use_web_search):
        try:
            search_query = re.sub(r"(?i)^/?(?:search|google)\s*", "", msg).strip() or msg
            results = perform_web_search(search_query, max_results=5)
            if results:
                search_context = format_web_search_context(search_query, results)
        except Exception as e:
            logger.warning("Web search error in stream: %s", e)

    context_blocks = [c for c in [history_context, rag_context, search_context] if c]
    combined_context = "\n\n".join(context_blocks)
    prompt_with_context = f"{combined_context}\n\nUser Question: {msg}" if combined_context else msg
    system_instruction = _build_system_instruction(user_name=user_name)

    # 4. Stream Tokens from Gemini
    has_streamed = False
    try:
        for chunk in generate_response_stream(prompt_with_context, system_instruction=system_instruction):
            if chunk:
                has_streamed = True
                yield chunk
    except Exception as e:
        logger.exception("Streaming exception: %s", e)

    if not has_streamed:
        fallback_text = get_reply(msg) or "Mujhe samajhne me thodi dikkat hui. Aap apna sawal thoda clear ya dusre tarike se pooch sakte hain!"
        yield fallback_text