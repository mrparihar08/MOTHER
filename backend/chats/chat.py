import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from backend.api.database import get_db
from backend.api.models.vitya import User, Conversation, ChatMessage
from backend.api.auth import token_required

from backend.chats.handlers.file_handler import handle_file_request
from backend.chats.handlers.news_handler import handle_news_request
from backend.chats.handlers.wiki_handler import handle_wiki_request
from backend.chats.handlers.chatbot_handler import handle_chatbot

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None


@router.post("/")
def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    user_message = (request.message or "").strip()
    if not user_message:
        return {"type": "text", "content": "Message required."}

    # 1. Process the reply first. This keeps chat available even if the optional
    # history tables are unavailable or the database connection is down.
    msg = user_message.lower().strip()

    res = handle_file_request(msg, user_message, current_user)
    if not res:
        res = handle_news_request(msg, user_message)
    if not res:
        res = handle_wiki_request(msg, user_message)
    if not res:
        res = handle_chatbot(user_message, db, current_user)

    # File handlers can return StreamingResponse objects.  Keep these responses
    # intact so downloads work exactly as they did before chat history was added.
    if isinstance(res, Response):
        assistant_content = "Generated file download"
    # Format output & extract text for DB
    elif isinstance(res, dict):
        assistant_content = res.get("content") or str(res)
    else:
        assistant_content = str(res) if res else "No response"
        res = {"type": "text", "content": assistant_content}

    # 2. Save history without allowing a history/database failure to break a reply.
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
        logger.exception("Unable to save chat history; returning the generated reply")

    return res


@router.get("/history")
def get_chat_history(
    conversation_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
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
        return {"conversation_id": None, "messages": []}

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    return {
        "conversation_id": conversation.id,
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
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.created_at.desc())
        .all()
    )
    result = []
    for c in conversations:
        last_msg = (
            db.query(ChatMessage)
            .filter(ChatMessage.conversation_id == c.id)
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        result.append(
            {
                "id": c.id,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "last_message": last_msg.content if last_msg else "",
            }
        )
    return result


@router.post("/new")
def create_new_conversation(
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    conversation = Conversation(user_id=current_user.id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return {
        "conversation_id": conversation.id,
        "message": "New conversation created",
    }


@router.delete("/history")
def clear_chat_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .all()
    )
    for c in conversations:
        db.delete(c)
    db.commit()
    return {"message": "Chat history cleared successfully"}
