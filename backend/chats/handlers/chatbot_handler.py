from backend.chats.chatbot import chatbot_reply
from backend.chats.utils.rules import get_reply
from backend.chats.gemini_service import generate_response


def handle_chatbot(user_message, db, current_user):
    reply = chatbot_reply(user_message, db, current_user)

    if reply is None:
        reply = get_reply(user_message)

    if reply is None:
        reply = generate_response(user_message)

    if isinstance(reply, dict):
        return reply

    return {
        "type": "text",
        "content": reply if isinstance(reply, str) else str(reply),
    }