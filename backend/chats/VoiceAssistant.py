from __future__ import annotations

import os
import re
import io
import time
import uuid
import hashlib
import logging
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import edge_tts
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.database import get_db
from backend.api.auth import optional_current_user, AuthenticatedUser
from backend.chats.services.gemini_service import generate_response, get_gemini_client
from backend.chats.services.context_manager import ConversationContextManager

logger = logging.getLogger(__name__)

router = APIRouter()

# Voice outputs directory
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUTS_DIR = ROOT_DIR / "outputs" / "voice_assistant"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Curated high-fidelity neural voices
SUPPORTED_VOICES = {
    "en-US-AriaNeural": {
        "id": "en-US-AriaNeural",
        "name": "Aria",
        "lang": "en-US",
        "gender": "Female",
        "accent": "American",
        "description": "Warm, expressive, and conversational",
        "recommended_for": ["en", "english"]
    },
    "en-US-GuyNeural": {
        "id": "en-US-GuyNeural",
        "name": "Guy",
        "lang": "en-US",
        "gender": "Male",
        "accent": "American",
        "description": "Confident, deep, and professional",
        "recommended_for": ["en", "english"]
    },
    "hi-IN-SwaraNeural": {
        "id": "hi-IN-SwaraNeural",
        "name": "Swara",
        "lang": "hi-IN",
        "gender": "Female",
        "accent": "Indian (Hindi)",
        "description": "Natural, clear, and melodious Hindi & Hinglish",
        "recommended_for": ["hi", "hindi", "hinglish", "auto"]
    },
    "hi-IN-MadhurNeural": {
        "id": "hi-IN-MadhurNeural",
        "name": "Madhur",
        "lang": "hi-IN",
        "gender": "Male",
        "accent": "Indian (Hindi)",
        "description": "Warm, friendly, and engaging Hindi & Hinglish",
        "recommended_for": ["hi", "hindi", "hinglish"]
    },
    "en-IN-NeerjaNeural": {
        "id": "en-IN-NeerjaNeural",
        "name": "Neerja",
        "lang": "en-IN",
        "gender": "Female",
        "accent": "Indian English",
        "description": "Articulate, crisp Indian English",
        "recommended_for": ["en-IN", "hinglish"]
    },
    "en-GB-SoniaNeural": {
        "id": "en-GB-SoniaNeural",
        "name": "Sonia",
        "lang": "en-GB",
        "gender": "Female",
        "accent": "British",
        "description": "Refined, articulate British accent",
        "recommended_for": ["en-GB"]
    }
}

# Conversational system prompt for Vitya voice assistant
VOICE_SYSTEM_PROMPT = """You are Vitya, an advanced, highly intelligent real-time AI Voice Assistant for the Vitya.ai platform.
Your persona is warm, articulate, perceptive, and naturally conversational—resembling ChatGPT Advanced Voice Mode.

CRITICAL UNIFIED CONTEXT & VOICE INSTRUCTIONS:
1. Shared Context & Conversation Memory:
   - You share a single continuous conversation memory with the Vitya Chat interface.
   - Always actively reference and build upon what the user previously discussed, whether in Chat or Voice.
   - When the user asks "What is my name?", "What did I ask you?", "Uske liye...", "Explain the project we discussed", ALWAYS look at the provided conversation history and answer accurately without asking them to repeat themselves!
2. Spoken Delivery:
   - Your responses will be read aloud through text-to-speech. Write for the ear, not the eye.
   - Keep sentences natural, flowing, and rhythmic.
   - Avoid Markdown tables, long bulleted checklists, asterisks, citations, URLs, code blocks, or emojis unless explicitly requested.
   - When explaining code or technical concepts, explain the concept conversationally in plain language.
3. Conciseness:
   - Be crisp and direct. Aim for 1 to 3 spoken sentences for simple questions, and 3 to 5 sentences for complex questions, unless the user asks for a detailed deep-dive.
4. Multilingual Agility (Hindi, English, Hinglish):
   - If the user speaks or types in Hindi (Devanagari or Romanized), respond fluently in natural, warm Hindi/Hinglish.
   - If the user speaks Hinglish (mix of Hindi and English like "Vitya mujhe kal ka plan batao"), reply in natural Hinglish just like an educated, friendly friend.
   - If the user speaks English, respond in articulate, modern English.
   - Mirror the user's language and tone seamlessly.
5. Active Persona:
   - Introduce yourself briefly as Vitya when greeted.
   - You can help with reasoning, productivity, writing, coding, science, general knowledge, daily planning, and creative thinking.
   - Express empathy, enthusiasm, and genuine helpfulness.
"""


def detect_language_mode(text: str) -> str:
    """Detect whether query is primarily Hindi, Hinglish, or English."""
    if not text:
        return "en"
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"
    hinglish_markers = [
        r"\bkaise\b", r"\bkya\b", r"\bhai\b", r"\bhain\b", r"\bhoon\b", r"\bhaan\b",
        r"\bnahi\b", r"\bnahin\b", r"\bkaro\b", r"\bkar\b", r"\bkarna\b", r"\bbatao\b",
        r"\baap\b", r"\btum\b", r"\btheek\b", r"\baccha\b", r"\bkripya\b", r"\bshukriya\b",
        r"\bdhanyawad\b", r"\bnamaste\b", r"\bkaisa\b", r"\bkaisi\b", r"\byaar\b",
        r"\bmujhe\b", r"\bhumein\b", r"\baaj\b", r"\bkal\b", r"\bchahiye\b", r"\bhoga\b"
    ]
    matches = sum(1 for m in hinglish_markers if re.search(m, text, re.IGNORECASE))
    if matches >= 1:
        return "hinglish"
    return "en"


def pick_voice_for_query(query: str, requested_voice: Optional[str] = None, language_mode: Optional[str] = "auto") -> str:
    """Select the best neural voice based on language and user preference."""
    if requested_voice and requested_voice in SUPPORTED_VOICES:
        return requested_voice

    detected = detect_language_mode(query) if language_mode == "auto" else language_mode
    if detected in ("hi", "hindi", "hinglish"):
        return "hi-IN-SwaraNeural"
    return "en-US-AriaNeural"


async def synthesize_speech(text: str, voice: str, rate: str = "+0%", pitch: str = "+0Hz") -> Path:
    """Synthesizes text using Edge-TTS into an MP3 file."""
    clean_text = re.sub(r"[\*#_`~>\[\]\(\)]", " ", text).strip()
    clean_text = re.sub(r"\s+", " ", clean_text)
    if not clean_text:
        clean_text = "I'm listening."

    content_key = f"{voice}:{rate}:{pitch}:{clean_text}"
    file_hash = hashlib.sha256(content_key.encode("utf-8")).hexdigest()[:16]
    file_path = OUTPUTS_DIR / f"voice_{file_hash}.mp3"

    if not file_path.exists() or file_path.stat().st_size == 0:
        logger.info(f"Synthesizing voice audio via edge-tts: voice={voice}, length={len(clean_text)}")
        communicate = edge_tts.Communicate(clean_text, voice, rate=rate, pitch=pitch)
        try:
            await asyncio.wait_for(communicate.save(str(file_path)), timeout=6.0)
        except Exception as tts_err:
            logger.warning(f"Edge-TTS synthesis error or timeout: {tts_err}")
            if file_path.exists() and file_path.stat().st_size == 0:
                try:
                    file_path.unlink()
                except Exception:
                    pass
            raise

    return file_path


# Request Models
class VoiceChatMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message text")


class VoiceChatRequest(BaseModel):
    message: str = Field(..., description="The user's spoken or typed prompt")
    conversation_id: Optional[Union[int, str]] = Field(None, description="Active unified conversation ID")
    voice: Optional[str] = Field(None, description="Requested neural voice key")
    language: Optional[str] = Field("auto", description="'auto', 'en', 'hi', or 'hinglish'")
    speed: Optional[str] = Field("+0%", description="Speech rate offset (e.g. '+0%', '+10%', '-10%')")
    history: Optional[List[VoiceChatMessage]] = Field(default_factory=list, description="Optional client-cached turns")


class TTSRequest(BaseModel):
    text: str = Field(..., description="Text to synthesize")
    voice: Optional[str] = Field("en-US-AriaNeural", description="Voice ID")
    rate: Optional[str] = Field("+0%", description="Playback speed")
    pitch: Optional[str] = Field("+0Hz", description="Pitch adjustment")


# --------------------------------------------------------------------------
# API ENDPOINTS
# --------------------------------------------------------------------------

@router.get("/health")
def voice_assistant_health():
    """Health check for Voice Assistant services."""
    return {
        "status": "healthy",
        "service": "Vitya AI Voice Assistant",
        "features": {
            "edge_tts": True,
            "whisper_stt": True,
            "multilingual": ["en", "hi", "hinglish"],
            "supported_voices_count": len(SUPPORTED_VOICES),
            "unified_context": True,
        }
    }


@router.get("/voices")
def get_voices():
    """Returns the list of available high-fidelity neural voices."""
    return {
        "status": "success",
        "voices": list(SUPPORTED_VOICES.values()),
        "default": "hi-IN-SwaraNeural"
    }


@router.post("/chat")
async def voice_chat_endpoint(
    payload: VoiceChatRequest,
    db: Session = Depends(get_db),
    current_user: Optional[AuthenticatedUser] = Depends(optional_current_user),
):
    """
    Main real-time Voice Assistant conversation turn.
    Shares the exact same conversation context, history, and database persistence as Chat.
    """
    user_prompt = payload.message.strip()
    if not user_prompt:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    detected_lang = detect_language_mode(user_prompt) if payload.language == "auto" else payload.language
    chosen_voice = pick_voice_for_query(user_prompt, payload.voice, payload.language)

    # 1. Resolve effective user_id
    user_id = getattr(current_user, "id", None)
    if not user_id:
        from backend.api.models.vitya import User
        demo_u = db.query(User).filter(User.id == 1).first() or db.query(User).first()
        user_id = demo_u.id if demo_u else 1

    # 2. Resolve or create unified conversation entity
    conversation = ConversationContextManager.resolve_conversation(
        db=db,
        user_id=user_id,
        conversation_id=payload.conversation_id,
        initial_title=user_prompt[:35],
    )

    # 3. Retrieve unified context from database (combines Chat and Voice turns + summary)
    context_data = ConversationContextManager.build_conversation_context(
        db=db,
        conversation=conversation,
        current_query=user_prompt,
        max_recent_turns=12,
    )

    history_context = context_data["context_prompt"]

    # Also incorporate client-provided turns if database is fresh but client has local session turns
    if not history_context and payload.history:
        turns = []
        for turn in payload.history[-6:]:
            role_label = "User" if turn.role == "user" else "Assistant"
            turns.append(f"{role_label}: {turn.content}")
        history_context = "Recent conversation context:\n" + "\n".join(turns)

    if history_context:
        composed_prompt = (
            f"{history_context}\n\n"
            f"User (Voice): {user_prompt}\n"
            f"Vitya (voice response):"
        )
    else:
        composed_prompt = (
            f"User (Voice): {user_prompt}\n"
            f"Vitya (voice response):"
        )

    try:
        reply_text = generate_response(
            user_message=composed_prompt,
            system_instruction=VOICE_SYSTEM_PROMPT,
            temperature=0.7,
        )
    except Exception as e:
        logger.error(f"Voice Assistant LLM generation error: {e}")
        reply_text = (
            "I'm sorry, I encountered a temporary connection issue. Could you please say that again?"
            if detected_lang == "en"
            else "Maaf kijiye, ek temporary connection issue hua. Kya aap dobara bol sakte hain?"
        )

    # Clean text of markdown artifacts for natural, fluid speech
    clean_reply = re.sub(r"```[\s\S]*?```", " [code omitted for speech] ", reply_text)
    clean_reply = re.sub(r"[\*#_`~>\[\]\(\)]", " ", clean_reply)
    clean_reply = re.sub(r"\s+", " ", clean_reply).strip()

    # Synthesize audio with edge-tts
    audio_filename = None
    audio_url = None
    try:
        audio_file_path = await asyncio.wait_for(
            synthesize_speech(
                text=clean_reply,
                voice=chosen_voice,
                rate=payload.speed or "+0%",
            ),
            timeout=7.0
        )
        audio_filename = audio_file_path.name
        audio_url = f"/outputs/voice_assistant/{audio_filename}"
    except Exception as e:
        logger.warning(f"Voice synthesis via edge-tts failed, fallback to client-side speech: {e}")

    # 4. Atomically persist user spoken query and assistant response to shared conversation in DB
    try:
        ConversationContextManager.save_turn(
            db=db,
            conversation=conversation,
            user_id=user_id,
            user_content=user_prompt,
            assistant_content=reply_text,
            input_mode="voice",
            message_status="completed",
            meta_info={
                "audio_url": audio_url,
                "voice": chosen_voice,
                "language": detected_lang,
            },
        )
    except Exception as save_err:
        logger.warning("Failed to save voice turn to DB: %s", save_err)

    disp_id = getattr(conversation, "user_conv_index", None) or conversation.id

    return {
        "status": "success",
        "reply": reply_text,
        "clean_speech_text": clean_reply,
        "language": detected_lang,
        "voice": chosen_voice,
        "audio_url": audio_url,
        "conversation_id": disp_id,
        "id": disp_id,
        "db_id": conversation.id,
        "unique_id": getattr(conversation, "unique_id", None),
        "title": conversation.title,
        "timestamp": time.time(),
    }


@router.post("/tts")
async def tts_endpoint(payload: TTSRequest):
    """Direct text-to-speech synthesis endpoint."""
    voice = payload.voice or "en-US-AriaNeural"
    if voice not in SUPPORTED_VOICES:
        voice = "en-US-AriaNeural"

    try:
        audio_path = await synthesize_speech(
            text=payload.text,
            voice=voice,
            rate=payload.rate or "+0%",
            pitch=payload.pitch or "+0Hz",
        )
        return FileResponse(
            path=str(audio_path),
            media_type="audio/mpeg",
            filename=audio_path.name,
        )
    except Exception as e:
        logger.error(f"TTS endpoint error: {e}")
        raise HTTPException(status_code=500, detail=f"Speech synthesis failed: {str(e)}")


@router.post("/stt")
async def stt_endpoint(file: UploadFile = File(...)):
    """
    Speech-to-text fallback endpoint using Whisper when browser Web Speech API is not supported.
    """
    if not file:
        raise HTTPException(status_code=400, detail="No audio file uploaded")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    import tempfile
    temp_path = None
    try:
        suffix = Path(file.filename or "recording.webm").suffix or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            temp_path = tmp.name

        try:
            from backend.api.routes.voice_notes_routes import get_whisper_model
            whisper_model = get_whisper_model("tiny")
            if whisper_model:
                result = whisper_model.transcribe(temp_path, fp16=False)
                transcript = result.get("text", "").strip()
                detected_lang = result.get("language", "en")
                return {
                    "status": "success",
                    "text": transcript,
                    "language": detected_lang,
                }
        except Exception as we:
            logger.warning(f"Local whisper transcription failed: {we}")

        client = get_gemini_client()
        if client:
            try:
                from google.genai import types
                audio_part = types.Part.from_bytes(data=content, mime_type=file.content_type or "audio/webm")
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[
                        audio_part,
                        "Transcribe the spoken words in this audio exactly. Return only the transcription text, nothing else."
                    ]
                )
                return {
                    "status": "success",
                    "text": (response.text or "").strip(),
                    "language": "auto"
                }
            except Exception as ge:
                logger.warning(f"Gemini multimodal STT failed: {ge}")

        return {
            "status": "error",
            "message": "Speech recognition engine unavailable on server.",
            "text": ""
        }
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
