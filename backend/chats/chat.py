import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
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
from backend.chats.handlers.dora_handler import handle_dora_health
from backend.chats.handlers.chatbot_handler import handle_chatbot
from backend.chats.handlers.receipt_handler import handle_receipt_scan
from backend.chats.handlers.multimodal_handler import handle_multimodal_chat

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str = Field(..., description="The user's chat message")
    conversation_id: Optional[int] = Field(None, description="Optional active conversation ID")
    use_web_search: bool = Field(False, description="Explicit flag to trigger real-time Google web search")
    mode: Optional[str] = Field(None, description="Explicit mode override (e.g. 'news', 'wiki', 'file', 'dora')")
    requestType: Optional[str] = Field(None, description="Alternative mode identifier")


class ConversationUpdate(BaseModel):
    title: Optional[str] = Field(None, description="Updated conversation title")


def _extract_assistant_content(res: Any) -> str:
    """Extract a human-readable text representation of any response type for DB storage."""
    if isinstance(res, Response):
        return "Generated file download"

    if isinstance(res, dict):
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
            return raw_c.get("summary") or raw_c.get("text") or str(raw_c)
        if isinstance(raw_c, list):
            return f"Generated {len(raw_c)} items"

        return str(res)

    return str(res) if res else "No response"


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

    res = None

    # 1. Explicit Mode Overrides
    if req_mode in ("news", "headlines"):
        res = handle_news_request(msg, user_message, force=True)
    elif req_mode in ("wiki", "wikipedia"):
        res = handle_wiki_request(msg, user_message, force=True)
    elif req_mode in ("file", "export", "doc", "pdf", "csv", "docx", "pptx"):
        res = handle_file_request(msg, user_message, current_user, force=True)
    elif req_mode in ("dora", "health", "medical", "doctor"):
        res = handle_dora_health(msg, user_message, force=True)

    # 2. Dynamic Slash Command & Auto Intent Dispatch
    if not res:
        if msg.startswith("/news") or msg.startswith("/headlines"):
            res = handle_news_request(msg, user_message, force=True)
        elif msg.startswith("/wiki") or msg.startswith("/wikipedia"):
            res = handle_wiki_request(msg, user_message, force=True)
        elif msg.startswith("/dora"):
            res = handle_dora_health(msg, user_message, force=True)

    # 3. Natural Language Handlers Dispatch
    if not res:
        res = handle_file_request(msg, user_message, current_user)
    if not res:
        res = handle_news_request(msg, user_message)
    if not res:
        res = handle_wiki_request(msg, user_message)
    if not res:
        res = handle_chatbot(
            user_message,
            db,
            current_user,
            use_web_search=request.use_web_search,
            conversation_id=request.conversation_id,
        )

    # Serialize assistant content for DB storage
    assistant_content = _extract_assistant_content(res)
    if not isinstance(res, (dict, Response)):
        res = {"type": "text", "content": assistant_content}

    # 4. Save multi-turn history safely to DB
    try:
        if request.conversation_id:
            conversation = (
                db.query(Conversation)
                .filter(
                    Conversation.id == request.conversation_id,
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
                    content=user_message,
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

    except HTTPException:
        raise
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Unable to save chat history; returning generated reply without DB sync")

    return res


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

    images_data = []
    for f in uploaded_files:
        content = await f.read()
        if content and len(content) > 0:
            images_data.append({
                "data": content,
                "mime_type": f.content_type or "image/jpeg",
                "filename": f.filename or "image.jpg",
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
        result.append(
            {
                "id": c.id,
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
    conversation = Conversation(user_id=current_user.id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return {
        "conversation_id": conversation.id,
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
