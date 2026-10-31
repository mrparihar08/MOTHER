"""
Chat Microservice API Routes.
Provides conversational AI, streaming SSE, and decoupled tool-calling clients.
"""
import re
import json
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from services.chat_service.database import get_db
from services.chat_service.models import Conversation, ChatMessage
from services.chat_service.clients.finance_client import RemoteFinanceClient
from services.chat_service.clients.dora_client import RemoteDoraClient
from shared.security.jwt_validator import get_current_user
from shared.security.models import AuthenticatedUser
from shared.ai.provider_factory import AIProviderFactory
from shared.ai.schemas import AICompletionRequest

router = APIRouter()
finance_client = RemoteFinanceClient()
dora_client = RemoteDoraClient()


# Schemas
class ConversationCreate(BaseModel):
    title: Optional[str] = "New Conversation"


class MessageOut(BaseModel):
    id: int
    role: str
    content: str

    class Config:
        from_attributes = True


class ConversationOut(BaseModel):
    id: int
    unique_id: str
    title: str

    class Config:
        from_attributes = True


class ConversationDetailOut(ConversationOut):
    messages: List[MessageOut] = []


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1)


@router.post("/conversations", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation(
    conv_in: ConversationCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = Conversation(
        title=conv_in.title or "New Conversation",
        user_id=current_user.user_id,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("/conversations", response_model=List[ConversationOut])
def list_conversations(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.user_id)
        .order_by(Conversation.created_at.desc())
        .all()
    )


@router.get("/conversations/{unique_id}", response_model=ConversationDetailOut)
def get_conversation(
    unique_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = (
        db.query(Conversation)
        .filter(
            Conversation.unique_id == unique_id,
            Conversation.user_id == current_user.user_id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conv


@router.post("/conversations/{unique_id}/messages")
async def send_message(
    unique_id: str,
    req: SendMessageRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = (
        db.query(Conversation)
        .filter(
            Conversation.unique_id == unique_id,
            Conversation.user_id == current_user.user_id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # 1. Save user message
    user_msg = ChatMessage(conversation_id=conv.id, role="user", content=req.content)
    db.add(user_msg)
    db.commit()

    # 2. Check for tool-calling intents (Finance or Dora)
    content_lower = req.content.lower()

    # Finance Tool Call: e.g. "add 500 for lunch" or "spent 200 on groceries"
    finance_match = re.search(
        r"(?:add|spent|record|paid)\s+(?:₹|\$|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s+(?:for|on|in)\s+([a-zA-Z\s]+)",
        content_lower,
    )
    if finance_match:
        amount = float(finance_match.group(1))
        category = finance_match.group(2).strip()
        idem_key = f"chat-{conv.id}-{uuid.uuid4().hex[:8]}"

        result = finance_client.record_transaction(
            user_id=current_user.user_id,
            transaction_type="expense",
            amount=amount,
            category_or_source=category.capitalize(),
            description=f"Logged via Chat: '{req.content}'",
            idempotency_key=idem_key,
        )

        reply_text = f"I've recorded an expense of ₹{amount:.2f} for {category.capitalize()} in your Finance ledger."
        ai_msg = ChatMessage(conversation_id=conv.id, role="assistant", content=reply_text)
        db.add(ai_msg)
        db.commit()
        return {"response": reply_text, "tool_called": "finance", "result": result}

    # Health Tool Call: e.g. "symptoms: fever, cough" or "I feel sick with fever"
    if any(k in content_lower for k in ["symptom", "fever", "cough", "headache", "pain"]):
        symptoms = [w.strip() for w in re.findall(r"\b(?:fever|cough|headache|fatigue|cold|vomiting)\b", content_lower)]
        if symptoms:
            dora_res = dora_client.predict_disease(symptoms=symptoms)
            preds = dora_res.get("predictions", [])
            if preds:
                top = preds[0]
                reply_text = f"Based on your symptoms ({', '.join(symptoms)}), Dora suggests possible: {top.get('disease')} (Confidence: {top.get('confidence')}). Note: This is informational, please consult a medical doctor."
            else:
                reply_text = "I noted your symptoms. Please consult a qualified physician for an accurate diagnosis."

            ai_msg = ChatMessage(conversation_id=conv.id, role="assistant", content=reply_text)
            db.add(ai_msg)
            db.commit()
            return {"response": reply_text, "tool_called": "dora", "result": dora_res}

    # Standard conversational AI generation via Shared AI Provider
    ai_provider = AIProviderFactory.get_provider()
    completion = await ai_provider.generate_text(
        AICompletionRequest(prompt=req.content, system_instruction="You are MOTHER AI, an intelligent personal assistant.")
    )
    reply_text = completion.text

    ai_msg = ChatMessage(conversation_id=conv.id, role="assistant", content=reply_text)
    db.add(ai_msg)
    db.commit()

    return {"response": reply_text, "model": completion.model}


@router.get("/conversations/{unique_id}/stream")
async def stream_conversation(
    unique_id: str,
    prompt: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Server-Sent Events (SSE) streaming endpoint."""
    conv = (
        db.query(Conversation)
        .filter(
            Conversation.unique_id == unique_id,
            Conversation.user_id == current_user.user_id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    ai_provider = AIProviderFactory.get_provider()

    async def event_generator():
        yield f"data: {json.dumps({'event': 'start', 'unique_id': unique_id})}\n\n"
        async for chunk in ai_provider.stream_text(AICompletionRequest(prompt=prompt)):
            yield f"data: {json.dumps({'event': 'chunk', 'text': chunk})}\n\n"
        yield f"data: {json.dumps({'event': 'end'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
