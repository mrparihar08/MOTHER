import logging
import json
import uuid
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func

from backend.api.database import get_db
from backend.api.models.vitya import Conversation, ChatMessage
from backend.api.auth import AuthenticatedUser, token_required
from backend.chats.handlers.file_handler import handle_file_request
from backend.chats.handlers.news_handler import handle_news_request
from backend.chats.handlers.wiki_handler import handle_wiki_request
from backend.chats.handlers.dora_handler import handle_dora_health, is_health_query
from backend.chats.handlers.chatbot_handler import handle_chatbot, handle_chatbot_stream
from backend.chats.handlers.receipt_handler import handle_receipt_scan
from backend.chats.handlers.multimodal_handler import handle_multimodal_chat

from backend.chats.utils.intent_router import classify_intent, get_contextual_greeting, Intent

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str = Field(..., description="The user's chat message")
    conversation_id: Optional[int] = Field(None, description="Optional active conversation ID")
    use_web_search: bool = Field(False, description="Explicit flag to trigger real-time Google web search")
    mode: Optional[str] = Field(None, description="Explicit mode override (e.g. 'news', 'wiki', 'file', 'dora')")
    requestType: Optional[str] = Field(None, description="Alternative mode identifier")
    latitude: Optional[float] = Field(None, description="Optional real-time user GPS latitude")
    longitude: Optional[float] = Field(None, description="Optional real-time user GPS longitude")
    city: Optional[str] = Field(None, description="Optional client-detected city name")


class ConversationUpdate(BaseModel):
    title: Optional[str] = Field(None, description="Updated conversation title")


def _extract_assistant_content(res: Any) -> str:
    """Extract a JSON string or human-readable text representation for DB storage."""
    if isinstance(res, Response):
        return "Generated file download"

    if isinstance(res, dict):
        r_type = res.get("type", "")
        chart_types = {
            "bar", "chart", "pie", "donut", "line", "line_chart",
            "area", "composed", "multi_line", "scatter", "radar",
            "heatmap", "waterfall", "stacked", "receipt", "image",
            "qr", "barcode", "wiki", "news", "download_link",
            "shopping", "research", "education", "gov_data"
        }
        # If it's a chart or rich structured response, store the JSON so history can restore it!
        if r_type in chart_types or isinstance(res.get("content"), (list, dict)) or isinstance(res.get("data"), (list, dict)):
            try:
                return json.dumps(res)
            except Exception:
                pass

        # 1. Text summary fallback for rich components (wiki, news)
        if res.get("text_summary"):
            return str(res["text_summary"])

        # 2. Caption for media (image, QR, barcode)
        if res.get("caption"):
            return str(res["caption"])

        # 3. Content field
        raw_c = res.get("content")
        if isinstance(raw_c, str):
            return raw_c
        if isinstance(raw_c, dict):
            return raw_c.get("summary") or raw_c.get("text") or json.dumps(raw_c)
        if isinstance(raw_c, list):
            try:
                return json.dumps(res)
            except Exception:
                return f"Generated {len(raw_c)} items"

        try:
            return json.dumps(res)
        except Exception:
            return str(res)

    return str(res) if res else "No response"


def generate_conversation_title(text: str) -> str:
    """Generate a clean, meaningful 3-5 word title related to the chat content."""
    if not text or not str(text).strip():
        return "New Chat"

    raw = str(text).strip()
    if raw.startswith("{") and raw.endswith("}"):
        try:
            parsed = json.loads(raw)
            raw = parsed.get("message") or parsed.get("text") or parsed.get("title") or raw
        except Exception:
            pass

    clean = re.sub(r"```[\s\S]*?```", "", raw)
    clean = re.sub(r"[{}\[\]\"\']", "", clean)
    clean = re.sub(r"(?i)^(Gemini stream error:\s*503\s*UNAVAILABLE.*)", "AI Assistant Query", clean)
    clean = clean.replace("\n", " ").strip()

    # Try Gemini AI for natural topic extraction if available
    try:
        from backend.chats.services.gemini_service import generate_response
        prompt = (
            f"Generate a short, concise title (strictly 3 to 5 words, max 35 characters) summarizing this user query: '{clean[:120]}'. "
            "DO NOT include quotes, question marks, period, or intro. Return ONLY the title text in the same language as the query."
        )
        ai_title = generate_response(prompt)
        if ai_title and not ai_title.startswith("Gemini") and "not configured" not in ai_title.lower() and len(ai_title.strip()) <= 45:
            clean_ai = ai_title.strip().strip('"\'*#')
            if clean_ai:
                return clean_ai
    except Exception:
        pass

    # Heuristic parsing for common queries & intents
    t_lower = clean.lower()

    if any(k in t_lower for k in ["expence", "expense", "kharch", "kharcha", "paid", "bought", "spent"]):
        words = [w for w in re.findall(r"\w+", clean) if w.lower() not in {
            "add", "karo", "kar", "do", "aaj", "mene", "maine", "mera", "meri", "mere",
            "expence", "expense", "expenses", "bhi", "liya", "hu", "hai", "me", "mein", "ka", "ki", "ke", "ko"
        }]
        if words:
            return f"Expense: {' '.join(words[:4]).title()}"
        return "Expense Log"

    if any(k in t_lower for k in ["balance", "paisa", "kitna paisa"]):
        return "Account Balance"

    if any(k in t_lower for k in ["weather", "mausam", "temperature", "barish"]):
        words = [w for w in re.findall(r"\w+", clean) if w.lower() not in {"aaj", "ka", "ki", "ke", "kaisa", "hai", "batao", "weather", "mausam"}]
        loc = f" - {words[0].title()}" if words else ""
        return f"Weather{loc}"

    if any(k in t_lower for k in ["news", "samachar", "khabar", "headlines"]):
        return "News & Updates"

    if any(k in t_lower for k in ["budget", "budget status"]):
        return "Budget Planning"

    if any(k in t_lower for k in ["presentation", "ppt", "slide"]):
        return "Presentation Studio"

    if any(k in t_lower for k in ["quickprompts", "import", "export", "react", "javascript", "python", "code", "error"]):
        code_words = re.findall(r"\b[A-Za-z0-9_]+\b", clean)
        significant = [w for w in code_words if len(w) > 2][:4]
        if significant:
            return " ".join(significant).title()

    clean_no_greetings = re.sub(
        r"^(?:hi|hello|hey|namaste|hlo|hii+|bhai|yaar|vitya|ai|please|batao)\b[!,.]*\s*",
        "",
        clean,
        flags=re.IGNORECASE,
    ).strip()

    title_source = clean_no_greetings if len(clean_no_greetings) >= 3 else clean
    words = title_source.split()
    title = " ".join(words[:5])
    if len(title) > 35:
        title = title[:32].rsplit(" ", 1)[0] + "..."
    return title.title() or "New Conversation"



@router.post("")
@router.post("/")
def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(token_required),
):
    """
    Main Chat Endpoint (Text):
    Dispatches request across File, News, Wiki, Dora (Health), and Chatbot pipelines.
    Persists multi-turn message history safely to the database.
    """
    user_message = (request.message or "").strip()
    if not user_message:
        return {"type": "text", "content": "Message required."}

    msg = user_message.lower().strip()
    req_mode = (request.mode or request.requestType or "").lower().strip()
    user_name = getattr(current_user, "name", None) or getattr(current_user, "username", None)
    is_health = is_health_query(user_message)
    intent = classify_intent(user_message, mode=req_mode, is_health=is_health)

    # Resolve conversation_id upfront if missing to maintain multi-turn context
    resolved_conv_id = request.conversation_id
    if not resolved_conv_id and current_user:
        try:
            latest_c = (
                db.query(Conversation)
                .filter(Conversation.user_id == current_user.id)
                .order_by(Conversation.updated_at.desc(), Conversation.created_at.desc())
                .first()
            )
            if latest_c:
                resolved_conv_id = latest_c.id
        except Exception:
            pass

    res = None

    # 1. GREETING Intent (Guaranteed warm, personalized greeting without disclaimers)
    if intent == Intent.GREETING:
        res = get_contextual_greeting(user_name)

    # 2. Explicit Mode Overrides & Slash Commands
    if not res:
        if req_mode in ("news", "headlines") or msg.startswith("/news") or msg.startswith("/headlines") or intent in (Intent.NEWS, Intent.NEWS_SUMMARY):
            res = handle_news_request(
                msg=msg,
                user_message=user_message,
                db=db,
                conversation_id=resolved_conv_id,
                force=True if (req_mode or msg.startswith("/news") or msg.startswith("/headlines")) else False,
            )
        elif req_mode in ("wiki", "wikipedia") or msg.startswith("/wiki") or msg.startswith("/wikipedia"):
            res = handle_wiki_request(msg, user_message, force=True)
        elif req_mode in ("file", "export", "doc", "pdf", "csv", "docx", "pptx") or msg.startswith("/presentation") or msg.startswith("/ppt") or msg.startswith("/export") or msg.startswith("/download") or msg.startswith("/csv") or msg.startswith("/pdf"):
            res = handle_file_request(msg, user_message, current_user, force=True)
        elif req_mode in ("dora", "health", "medical", "doctor") or msg.startswith("/dora") or intent == Intent.HEALTH:
            res = handle_dora_health(msg, user_message, force=True if (req_mode or msg.startswith("/dora")) else False)
        elif req_mode in ("shop", "shopping", "amazon", "flipkart") or msg.startswith("/shop") or intent == Intent.SHOPPING:
            from backend.chats.handlers.connector_handler import handle_connector_request
            from backend.chats.services.unified_connector import ResultCategory
            res = handle_connector_request(msg, user_message, explicit_category=ResultCategory.SHOPPING, db=db, conversation_id=resolved_conv_id)
        elif req_mode in ("research", "paper", "arxiv") or msg.startswith("/paper") or msg.startswith("/research") or intent == Intent.RESEARCH:
            from backend.chats.handlers.connector_handler import handle_connector_request
            from backend.chats.services.unified_connector import ResultCategory
            res = handle_connector_request(msg, user_message, explicit_category=ResultCategory.RESEARCH, db=db, conversation_id=resolved_conv_id)
        elif req_mode in ("edu", "education", "course", "docs") or msg.startswith("/edu") or msg.startswith("/docs") or intent == Intent.EDUCATION:
            from backend.chats.handlers.connector_handler import handle_connector_request
            from backend.chats.services.unified_connector import ResultCategory
            res = handle_connector_request(msg, user_message, explicit_category=ResultCategory.EDUCATION, db=db, conversation_id=resolved_conv_id)
        elif req_mode in ("gov", "government", "opendata") or msg.startswith("/gov") or intent == Intent.GOVERNMENT_DATA:
            from backend.chats.handlers.connector_handler import handle_connector_request
            from backend.chats.services.unified_connector import ResultCategory
            res = handle_connector_request(msg, user_message, explicit_category=ResultCategory.GOVERNMENT, db=db, conversation_id=resolved_conv_id)

    # 3. Main Intelligent Dispatch (Finance, Charts, Weather, Utilities, RAG, Web Search, Gemini LLM)
    if not res:
        res = handle_chatbot(
            user_message,
            db,
            current_user,
            use_web_search=request.use_web_search,
            conversation_id=resolved_conv_id,
            latitude=request.latitude,
            longitude=request.longitude,
            city=request.city,
        )

    # 4. Attach Intent, Disclaimer & Action Metadata
    if isinstance(res, dict):
        if "intent" not in res:
            res["intent"] = intent.value
        if "disclaimer" not in res:
            res["disclaimer"] = (
                "⚠️ *Disclaimer: DORA provides AI health guidance for informational purposes and does not replace in-person clinical evaluation.*"
                if intent == Intent.HEALTH
                else None
            )
        if "actions" not in res:
            res["actions"] = ["copy", "voice", "more"]

    # Serialize assistant content for DB storage
    assistant_content = _extract_assistant_content(res)
    if not isinstance(res, (dict, Response)):
        res = {"type": "text", "content": assistant_content, "intent": intent.value}

    # 4. Save multi-turn history safely to DB
    try:
        conv_target_id = request.conversation_id or resolved_conv_id
        if conv_target_id:
            conversation = (
                db.query(Conversation)
                .filter(
                    Conversation.id == conv_target_id,
                    Conversation.user_id == current_user.id,
                )
                .first()
            )
            if not conversation and request.conversation_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Conversation not found",
                )
        else:
            conversation = None

        if not conversation:
            smart_title = generate_conversation_title(user_message)
            conversation = Conversation(user_id=current_user.id, title=smart_title)
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
        elif not getattr(conversation, "title", None) or conversation.title == "New Chat":
            conversation.title = generate_conversation_title(user_message)
            db.commit()

        db.add_all(
            [
                ChatMessage(
                    conversation_id=conversation.id,
                    role="user",
                    content=user_message,
                ),
                ChatMessage(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=assistant_content,
                ),
            ]
        )
        if hasattr(conversation, "updated_at"):
            conversation.updated_at = datetime.now(timezone.utc)
        db.commit()

        if isinstance(res, dict):
            res["conversation_id"] = conversation.id

    except HTTPException:
        raise
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Unable to save chat history; returning generated reply without DB sync")

    return res


@router.post("/stream")
def chat_stream(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(token_required),
):
    """
    Real-time Server-Sent Events (SSE) streaming chat endpoint.
    Streams tokens word-by-word with initial metadata event and final completion event.
    """
    user_message = (request.message or "").strip()
    if not user_message:
        def empty_gen():
            yield f"data: {json.dumps({'error': 'Message required'})}\n\n"
        return StreamingResponse(empty_gen(), media_type="text/event-stream")

    msg = user_message.lower().strip()
    req_mode = (request.mode or request.requestType or "").lower().strip()
    user_name = getattr(current_user, "name", None) or getattr(current_user, "username", None)
    is_health = is_health_query(user_message)
    intent = classify_intent(user_message, mode=req_mode, is_health=is_health)

    # Resolve conversation_id upfront if missing to maintain multi-turn streaming context
    resolved_conv_id = request.conversation_id
    if not resolved_conv_id and current_user:
        try:
            latest_c = (
                db.query(Conversation)
                .filter(Conversation.user_id == current_user.id)
                .order_by(Conversation.updated_at.desc(), Conversation.created_at.desc())
                .first()
            )
            if latest_c:
                resolved_conv_id = latest_c.id
        except Exception:
            pass

    def event_stream():
        # 1. Send initial metadata event with intent and disclaimer
        meta = {
            "type": "meta",
            "intent": intent.value,
            "disclaimer": (
                "⚠️ *Disclaimer: DORA provides AI health guidance for informational purposes and does not replace in-person clinical evaluation.*"
                if intent == Intent.HEALTH
                else None
            ),
        }
        yield f"data: {json.dumps(meta)}\n\n"

        # 2. Stream tokens in real-time or handle structured news
        accumulated_text = []
        structured_payload = None

        is_news_req = (
            req_mode in ("news", "headlines")
            or msg.startswith("/news")
            or msg.startswith("/headlines")
            or intent in (Intent.NEWS, Intent.NEWS_SUMMARY)
        )

        try:
            news_res = None
            if is_news_req:
                from backend.chats.handlers.news_handler import handle_news_request
                news_res = handle_news_request(
                    msg=msg,
                    user_message=user_message,
                    db=db,
                    conversation_id=resolved_conv_id,
                    force=True if (req_mode or msg.startswith("/news") or msg.startswith("/headlines")) else False,
                )

            if news_res is not None:
                if isinstance(news_res, dict) and news_res.get("type") == "news":
                    structured_payload = news_res
                    yield f"data: {json.dumps({'type': 'structured', 'payload': news_res})}\n\n"
                    txt_sum = news_res.get("text_summary") or news_res.get("intro") or ""
                    if txt_sum:
                        accumulated_text.append(txt_sum)
                        yield f"data: {json.dumps({'type': 'token', 'token': txt_sum})}\n\n"
                elif isinstance(news_res, dict) and news_res.get("type") == "text":
                    content = news_res.get("content", "")
                    accumulated_text.append(content)
                    words = content.split(" ")
                    for i, w in enumerate(words):
                        space = " " if i < len(words) - 1 else ""
                        yield f"data: {json.dumps({'type': 'token', 'token': w + space})}\n\n"
                else:
                    if isinstance(news_res, dict):
                        structured_payload = news_res
                        yield f"data: {json.dumps({'type': 'structured', 'payload': news_res})}\n\n"
                    else:
                        text_str = str(news_res)
                        accumulated_text.append(text_str)
                        yield f"data: {json.dumps({'type': 'token', 'token': text_str})}\n\n"
            else:
                for token_chunk in handle_chatbot_stream(
                    user_message=user_message,
                    db=db,
                    current_user=current_user,
                    use_web_search=request.use_web_search,
                    conversation_id=resolved_conv_id,
                    latitude=request.latitude,
                    longitude=request.longitude,
                    city=request.city,
                ):
                    if isinstance(token_chunk, dict) and token_chunk.get("structured"):
                        payload = token_chunk.get("payload", {})
                        structured_payload = payload
                        yield f"data: {json.dumps({'type': 'structured', 'payload': payload})}\n\n"
                    else:
                        text_str = str(token_chunk) if token_chunk is not None else ""
                        accumulated_text.append(text_str)
                        yield f"data: {json.dumps({'type': 'token', 'token': text_str})}\n\n"
        except Exception as e:
            logger.exception("Stream iteration error: %s", e)
            yield f"data: {json.dumps({'type': 'token', 'token': f' [Error: {str(e)}]' })}\n\n"

        # 3. Final completion event and persist conversation
        if structured_payload:
            full_text = _extract_assistant_content(structured_payload)
        else:
            raw_text = "".join(accumulated_text).strip()
            from backend.chats.services.code_validator import sanitize_markdown_response
            full_text = sanitize_markdown_response(raw_text, user_name=user_name)

        conv_id = request.conversation_id or resolved_conv_id
        try:
            if conv_id:
                conversation = db.query(Conversation).filter(Conversation.id == conv_id, Conversation.user_id == current_user.id).first()
            else:
                conversation = None

            if not conversation:
                smart_title = generate_conversation_title(user_message)
                conversation = Conversation(
                    user_id=current_user.id,
                    title=smart_title,
                )
                db.add(conversation)
                db.flush()
                conv_id = conversation.id
            elif not getattr(conversation, "title", None) or conversation.title == "New Chat":
                conversation.title = generate_conversation_title(user_message)

            if conversation:
                user_msg = ChatMessage(conversation_id=conversation.id, role="user", content=user_message)
                bot_msg = ChatMessage(conversation_id=conversation.id, role="assistant", content=full_text)
                db.add_all([user_msg, bot_msg])
                if hasattr(conversation, "updated_at"):
                    conversation.updated_at = datetime.now(timezone.utc)
                db.commit()
        except Exception as e:
            db.rollback()
            logger.warning("Failed to persist streaming chat: %s", e)

        yield f"data: {json.dumps({'type': 'done', 'conversation_id': conv_id, 'full_text': full_text})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/multimodal")
@router.post("/vision")
async def chat_multimodal(
    message: Optional[str] = Form(""),
    conversation_id: Optional[int] = Form(None),
    use_web_search: bool = Form(False),
    mode: Optional[str] = Form(None),
    files: List[UploadFile] = File(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(token_required),
):
    """
    Universal Multimodal Chat Endpoint:
    Accepts text prompt along with one or more uploaded images (bills, handwritten notes, charts, photos, etc.).
    Uses Gemini Vision to understand, analyze, OCR, and answer queries without database auto-mutations.
    """
    uploaded_files: List[UploadFile] = []
    if files:
        uploaded_files.extend(files)
    if file:
        uploaded_files.append(file)

    if not uploaded_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one image file is required for multimodal analysis.",
        )

    upload_dir = Path("uploads") / "chat_images"
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved_image_urls = []

    images_data = []
    for f in uploaded_files:
        content = await f.read()
        if content and len(content) > 0:
            filename = f.filename or "image.jpg"
            clean_filename = f"img_{uuid.uuid4().hex[:12]}_{''.join(c for c in filename if c.isalnum() or c in '._-')}"
            file_path = upload_dir / clean_filename
            try:
                with open(file_path, "wb") as fh:
                    fh.write(content)
                saved_image_urls.append(f"/uploads/chat_images/{clean_filename}")
            except Exception as e:
                logger.warning(f"Could not save chat image file: {e}")

            images_data.append({
                "data": content,
                "mime_type": f.content_type or "image/jpeg",
                "filename": filename,
            })

    if not images_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded files were empty.",
        )

    user_text = (message or "").strip()
    res = handle_multimodal_chat(
        user_message=user_text,
        images_data=images_data,
        db=db,
        current_user=current_user,
        conversation_id=conversation_id,
        use_web_search=use_web_search,
    )

    assistant_content = _extract_assistant_content(res)
    if saved_image_urls:
        history_user_text = json.dumps({
            "type": "multimodal_user",
            "text": user_text,
            "images": saved_image_urls,
        })
    else:
        history_user_text = f"🖼️ [Image Attached] {user_text}".strip() if user_text else "🖼️ [Image Attached]"

    # Persist multi-turn conversation
    try:
        if conversation_id:
            conversation = (
                db.query(Conversation)
                .filter(
                    Conversation.id == conversation_id,
                    Conversation.user_id == current_user.id,
                )
                .first()
            )
            if not conversation:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Conversation not found",
                )
        else:
            conversation = (
                db.query(Conversation)
                .filter(Conversation.user_id == current_user.id)
                .order_by(Conversation.created_at.desc())
                .first()
            )
            if not conversation:
                conversation = Conversation(user_id=current_user.id)
                db.add(conversation)
                db.commit()
                db.refresh(conversation)

        db.add_all(
            [
                ChatMessage(
                    conversation_id=conversation.id,
                    role="user",
                    content=history_user_text,
                ),
                ChatMessage(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=assistant_content,
                ),
            ]
        )
        db.commit()

        if isinstance(res, dict):
            res["conversation_id"] = conversation.id
            if saved_image_urls:
                res["saved_images"] = saved_image_urls

    except HTTPException:
        raise
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Unable to save multimodal chat history")

    return res


@router.get("/history")
def get_chat_history(
    conversation_id: Optional[int] = Query(None, description="ID of the conversation to load"),
    limit: int = Query(100, ge=1, le=500, description="Max messages to retrieve"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(token_required),
):
    """Retrieve message history for a specific conversation or user's latest conversation."""
    if conversation_id:
        conversation = (
            db.query(Conversation)
            .filter(
                Conversation.id == conversation_id,
                Conversation.user_id == current_user.id,
            )
            .first()
        )
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
    else:
        conversation = (
            db.query(Conversation)
            .filter(Conversation.user_id == current_user.id)
            .order_by(Conversation.created_at.desc())
            .first()
        )

    if not conversation:
        return {"conversation_id": None, "total": 0, "messages": []}

    total_count = (
        db.query(func.count(ChatMessage.id))
        .filter(ChatMessage.conversation_id == conversation.id)
        .scalar() or 0
    )

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation.id)
        .order_by(ChatMessage.created_at.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "conversation_id": conversation.id,
        "total": total_count,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


@router.get("/conversations")
def get_conversations(
    limit: int = Query(50, ge=1, le=100, description="Max conversations to retrieve"),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(token_required),
):
    """Retrieve list of all active conversations with latest message snippet and message count."""
    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.created_at.desc())
        .limit(limit)
        .all()
    )
    if not conversations:
        return []

    conv_ids = [c.id for c in conversations]

    # Batch query latest messages
    latest_messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id.in_(conv_ids))
        .order_by(ChatMessage.created_at.desc())
        .all()
    )
    last_msg_map = {}
    for m in latest_messages:
        if m.conversation_id not in last_msg_map:
            last_msg_map[m.conversation_id] = m.content

    # Batch query message counts per conversation
    counts = (
        db.query(ChatMessage.conversation_id, func.count(ChatMessage.id))
        .filter(ChatMessage.conversation_id.in_(conv_ids))
        .group_by(ChatMessage.conversation_id)
        .all()
    )
    count_map = {cid: cnt for cid, cnt in counts}

    result = []
    for c in conversations:
        conv_title = getattr(c, "title", None)
        if not conv_title or conv_title == "New Chat":
            msg_text = last_msg_map.get(c.id, "")
            if msg_text:
                conv_title = generate_conversation_title(msg_text)
                try:
                    c.title = conv_title
                    db.commit()
                except Exception:
                    pass
            else:
                conv_title = f"Chat #{c.id}"

        result.append(
            {
                "id": c.id,
                "title": conv_title,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if hasattr(c, "updated_at") and c.updated_at else None,
                "message_count": count_map.get(c.id, 0),
                "last_message": last_msg_map.get(c.id, ""),
            }
        )
    return result


@router.post("/new")
def create_new_conversation(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(token_required),
):
    """Create a new empty conversation session."""
    conversation = Conversation(user_id=current_user.id, title="New Chat")
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return {
        "conversation_id": conversation.id,
        "title": conversation.title,
        "message": "New conversation created successfully",
        "created_at": conversation.created_at.isoformat() if conversation.created_at else None,
    }


@router.delete("/history")
def clear_chat_history(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(token_required),
):
    """Delete all conversations and chat messages for the current user."""
    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .all()
    )
    for c in conversations:
        db.delete(c)
    db.commit()
    return {"message": "Chat history cleared successfully"}


@router.post("/receipt")
async def scan_receipt_endpoint(
    file: UploadFile = File(..., description="Receipt image file (JPEG, PNG, WEBP)"),
    auto_save: bool = Query(True, description="Whether to automatically log as Expense in database"),
    conversation_id: Optional[int] = Query(None, description="Optional conversation ID to save assistant message"),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(token_required),
):
    """
    AI Multimodal Receipt Scanner:
    Uploads a bill/receipt photo, extracts merchant, total amount, category, date, and line items using Gemini Vision,
    and automatically logs it into the user's Expense account.
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be a valid image (JPEG, PNG, WEBP).",
        )

    image_bytes = await file.read()
    if not image_bytes or len(image_bytes) < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded image is empty or invalid.",
        )

    res = handle_receipt_scan(
        image_bytes=image_bytes,
        mime_type=file.content_type,
        db=db,
        current_user=current_user,
        auto_save=auto_save,
    )

    # Optionally persist to conversation history
    if conversation_id and isinstance(res, dict):
        try:
            db.add_all(
                [
                    ChatMessage(
                        conversation_id=conversation_id,
                        role="user",
                        content=f"🧾 Uploaded receipt: {file.filename or 'bill.jpg'}",
                    ),
                    ChatMessage(
                        conversation_id=conversation_id,
                        role="assistant",
                        content=res.get("content", "Scanned receipt"),
                    ),
                ]
            )
            db.commit()
            res["conversation_id"] = conversation_id
        except Exception as e:
            db.rollback()
            logger.warning("Failed to append receipt scan to chat history: %s", e)

    return res


@router.patch("/conversation/{conversation_id}")
def update_conversation_title(
    conversation_id: int,
    data: ConversationUpdate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(token_required),
):
    """Update title or metadata of a conversation."""
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    if data.title:
        if hasattr(conversation, "title"):
            setattr(conversation, "title", data.title.strip())
            db.commit()
            db.refresh(conversation)

    return {
        "conversation_id": conversation.id,
        "message": "Conversation updated successfully",
    }


@router.delete("/conversation/{conversation_id}")
def delete_single_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(token_required),
):
    """Delete a single specific conversation and its cascaded chat messages."""
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    db.delete(conversation)
    db.commit()
    return {
        "message": f"Conversation #{conversation_id} deleted successfully",
        "conversation_id": conversation_id,
    }


class ChatExportRequest(BaseModel):
    format: Optional[str] = "pdf"
    messages: Optional[List[Dict[str, Any]]] = None
    conversation_id: Optional[int] = None


@router.post("/export")
def export_chat_endpoint(
    req: ChatExportRequest,
    current_user: AuthenticatedUser = Depends(token_required),
    db: Session = Depends(get_db),
):
    """Export chat messages as PDF or text file."""
    import io

    export_messages = []
    if req.messages and len(req.messages) > 0:
        for m in req.messages:
            sender = m.get("sender") or m.get("role") or "User"
            content = m.get("text") or m.get("content") or ""
            if isinstance(content, dict):
                content = content.get("text") or content.get("content") or json.dumps(content)
            export_messages.append((sender, str(content)))
    elif req.conversation_id:
        msgs = (
            db.query(ChatMessage)
            .join(Conversation)
            .filter(
                Conversation.id == req.conversation_id,
                Conversation.user_id == current_user.id,
            )
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        for m in msgs:
            export_messages.append((m.role.capitalize(), m.content))
    else:
        export_messages.append(("Vitya AI", "No messages provided for export."))

    export_fmt = (req.format or "pdf").lower().strip()

    if export_fmt == "pdf":
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
            from reportlab.lib import colors

            buf = io.BytesIO()
            doc = SimpleDocTemplate(buf, pagesize=letter, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
            styles = getSampleStyleSheet()

            title_style = ParagraphStyle(
                "DocTitle",
                parent=styles["Heading1"],
                fontSize=20,
                leading=24,
                textColor=colors.HexColor("#4f46e5"),
                spaceAfter=15,
            )
            meta_style = ParagraphStyle(
                "DocMeta",
                parent=styles["Normal"],
                fontSize=10,
                leading=14,
                textColor=colors.HexColor("#64748b"),
                spaceAfter=20,
            )
            user_style = ParagraphStyle(
                "UserBubble",
                parent=styles["Normal"],
                fontSize=11,
                leading=16,
                textColor=colors.HexColor("#1e293b"),
                spaceAfter=12,
            )
            ai_style = ParagraphStyle(
                "AiBubble",
                parent=styles["Normal"],
                fontSize=11,
                leading=16,
                textColor=colors.HexColor("#0f172a"),
                spaceAfter=15,
            )

            story = [
                Paragraph("<b>Vitya AI — Conversation Export</b>", title_style),
                Paragraph(f"Exported on: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}", meta_style),
                Spacer(1, 10),
            ]

            for sender, text in export_messages:
                clean_text = text.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
                is_user = sender.lower() in ("user", "human")
                prefix = f"<b>👤 You:</b><br/>" if is_user else f"<b>🤖 Vitya AI:</b><br/>"
                style = user_style if is_user else ai_style
                story.append(Paragraph(f"{prefix}{clean_text}", style))
                story.append(Spacer(1, 8))

            doc.build(story)
            pdf_bytes = buf.getvalue()
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": 'attachment; filename="vitya_chat_export.pdf"'},
            )
        except Exception as e:
            logger.warning("PDF export fallback to text due to error: %s", e)

    # Fallback / TXT export
    txt_lines = [
        "Vitya AI - Conversation Export",
        f"Exported at: {datetime.now(timezone.utc).isoformat()}",
        "=" * 40,
        "",
    ]
    for sender, text in export_messages:
        txt_lines.append(f"[{sender}]:\n{text}\n")
    return Response(
        content="\n".join(txt_lines),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="vitya_chat_export.txt"'},
    )

