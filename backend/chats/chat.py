from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.database import get_db
from backend.api.models.vitya import User
from backend.api.auth import token_required

from backend.chats.handlers.file_handler import handle_file_request
from backend.chats.handlers.news_handler import handle_news_request
from backend.chats.handlers.wiki_handler import handle_wiki_request
from backend.chats.handlers.chatbot_handler import handle_chatbot

router = APIRouter()

class ChatRequest(BaseModel):
    message: str


@router.post("/")
def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    user_message = (request.message or "").strip()
    if not user_message:
        return {"type": "text", "content": "Message required."}

    msg = user_message.lower().strip()

    res = handle_file_request(msg, user_message, current_user)
    if res:
        return res

    res = handle_news_request(msg, user_message)
    if res:
        return res

    res = handle_wiki_request(msg, user_message)
    if res:
        return res

    return handle_chatbot(user_message, db, current_user)