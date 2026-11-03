import io
import json
import pytest
from fastapi.testclient import TestClient
from backend.app.app import app
from backend.api.database import SessionLocal
from backend.api.models.vitya import Conversation, ChatMessage, User
from backend.chats.VoiceAssistant import detect_language_mode, pick_voice_for_query, SUPPORTED_VOICES
from backend.chats.services.context_manager import ConversationContextManager

client = TestClient(app)


def test_language_detection():
    """Verify Hindi, Hinglish, and English detection."""
    assert detect_language_mode("Hello, how are you today?") == "en"
    assert detect_language_mode("नमस्ते, आप कैसे हैं?") == "hi"
    assert detect_language_mode("Vitya mujhe aaj ka plan batao") == "hinglish"
    assert detect_language_mode("Kaise ho aap?") == "hinglish"
    assert detect_language_mode("What is the capital of India?") == "en"


def test_voice_picker():
    """Verify voice auto-selection matches language."""
    v_hi = pick_voice_for_query("Namaste Vitya", language_mode="auto")
    assert v_hi == "hi-IN-SwaraNeural"

    v_en = pick_voice_for_query("Tell me about space exploration", language_mode="auto")
    assert v_en == "en-US-AriaNeural"

    v_custom = pick_voice_for_query("Hello", requested_voice="en-US-GuyNeural")
    assert v_custom == "en-US-GuyNeural"


def test_voice_assistant_health():
    """Check health endpoint."""
    response = client.get("/api/voice-assistant/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["features"]["edge_tts"] is True
    assert data["features"]["supported_voices_count"] == len(SUPPORTED_VOICES)
    assert data["features"]["unified_context"] is True


def test_voice_assistant_voices_list():
    """Check supported voices endpoint returns list of high-quality neural voices."""
    response = client.get("/api/voice-assistant/voices")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["voices"]) >= 6
    voice_ids = [v["id"] for v in data["voices"]]
    assert "en-US-AriaNeural" in voice_ids
    assert "hi-IN-SwaraNeural" in voice_ids
    assert "hi-IN-MadhurNeural" in voice_ids


def test_voice_assistant_chat_validation():
    """Verify validation on empty messages."""
    response = client.post("/api/voice-assistant/chat", json={"message": "   "})
    assert response.status_code == 400


def test_voice_assistant_stt_empty_validation():
    """Verify STT endpoint rejects empty uploads."""
    response = client.post(
        "/api/voice-assistant/stt",
        files={"file": ("recording.webm", io.BytesIO(b""), "audio/webm")}
    )
    assert response.status_code == 400


def test_unified_conversation_context_manager():
    """
    Test centralized ConversationContextManager:
    - Resolves single conversation entity.
    - Saves Chat turn and Voice turn to the same conversation.
    - Builds unified context preserving chronological order and input mode.
    """
    db = SessionLocal()
    try:
        user = db.query(User).first()
        user_id = user.id if user else 1

        conv = ConversationContextManager.resolve_conversation(
            db=db,
            user_id=user_id,
            conversation_id=None,
            initial_title="Unified Context Test"
        )
        assert conv is not None
        assert conv.id is not None

        # Turn 1: User speaks in Chat
        u1, b1 = ConversationContextManager.save_turn(
            db=db,
            conversation=conv,
            user_id=user_id,
            user_content="Mera naam Rahul hai.",
            assistant_content="Namaste Rahul! Main aapki kya madad kar sakta hoon?",
            input_mode="chat",
        )
        assert u1.input_mode == "chat"
        assert b1.input_mode == "chat"

        # Check context after Chat turn
        ctx1 = ConversationContextManager.build_conversation_context(
            db=db,
            conversation=conv,
            current_query="What is my name?",
        )
        assert "Mera naam Rahul hai" in ctx1["context_prompt"]
        assert "User (Chat)" in ctx1["context_prompt"]

        # Turn 2: User speaks in Voice
        u2, b2 = ConversationContextManager.save_turn(
            db=db,
            conversation=conv,
            user_id=user_id,
            user_content="Kal mujhe ek presentation banani hai artificial intelligence par.",
            assistant_content="Sure! I can help you prepare the artificial intelligence presentation.",
            input_mode="voice",
            meta_info={"voice": "hi-IN-SwaraNeural", "audio_url": "/outputs/voice_assistant/sample.mp3"}
        )
        assert u2.input_mode == "voice"
        assert b2.input_mode == "voice"
        assert b2.meta_info is not None

        # Check unified context after Voice turn
        ctx2 = ConversationContextManager.build_conversation_context(
            db=db,
            conversation=conv,
            current_query="Uske liye 5 slides ka outline bana do.",
        )
        # Context must contain both Chat and Voice interactions!
        assert "User (Chat): Mera naam Rahul hai" in ctx2["context_prompt"]
        assert "User (Voice): Kal mujhe ek presentation banani hai artificial intelligence par" in ctx2["context_prompt"]

        # Both user and assistant turns are stored in chat_messages table under the exact same conversation.id
        all_msgs = (
            db.query(ChatMessage)
            .filter(ChatMessage.conversation_id == conv.id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        assert len(all_msgs) >= 4
        modes = [m.input_mode for m in all_msgs]
        assert "chat" in modes
        assert "voice" in modes

    finally:
        db.close()


def test_voice_chat_api_endpoint_persistence():
    """
    Test real API turn via /api/voice-assistant/chat:
    - Creates or binds to a conversation.
    - Saves user voice query and assistant voice response into DB.
    - Returns valid conversation_id and unique_id.
    """
    db = SessionLocal()
    try:
        user = db.query(User).first()
        user_id = user.id if user else 1

        conv = ConversationContextManager.resolve_conversation(
            db=db,
            user_id=user_id,
            conversation_id=None,
            initial_title="API Voice Persistence Test"
        )
        conv_id = conv.id

        # Send Voice request specifying conversation_id
        res = client.post("/api/voice-assistant/chat", json={
            "message": "Hello Vitya, please remember that my favorite language is Python.",
            "conversation_id": conv_id,
            "language": "en"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["conversation_id"] is not None
        assert "reply" in data
        assert "voice" in data

        # Verify message was saved to database under that exact conversation
        saved_msgs = (
            db.query(ChatMessage)
            .filter(ChatMessage.conversation_id == conv_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(2)
            .all()
        )
        assert len(saved_msgs) == 2
        user_voice_msg = [m for m in saved_msgs if m.role == "user"][0]
        bot_voice_msg = [m for m in saved_msgs if m.role == "assistant"][0]

        assert "favorite language is Python" in user_voice_msg.content
        assert user_voice_msg.input_mode == "voice"
        assert bot_voice_msg.input_mode == "voice"

    finally:
        db.close()
