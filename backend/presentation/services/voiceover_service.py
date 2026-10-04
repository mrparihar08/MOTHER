from __future__ import annotations

import hashlib
import logging
import os
import uuid
from pathlib import Path
from typing import Optional
import edge_tts

logger = logging.getLogger(__name__)

VOICEOVER_DIR = Path(os.getenv("PPT_VOICEOVER_DIR", "./outputs/voiceovers")).resolve()
VOICEOVER_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_VOICE_EN = "en-US-AriaNeural"
DEFAULT_VOICE_HI = "hi-IN-SwaraNeural"


def select_voice(language: Optional[str] = None, voice: Optional[str] = None) -> str:
    if voice and voice.strip():
        return voice.strip()
    lang = (language or "en").lower().strip()
    if lang.startswith("hi") or "hindi" in lang:
        return DEFAULT_VOICE_HI
    return DEFAULT_VOICE_EN


async def generate_slide_voiceover(
    text: str,
    language: Optional[str] = "en-US",
    voice: Optional[str] = None,
    slide_index: Optional[int] = None,
) -> tuple[str, Path]:
    """
    Synthesizes slide speech narration into an MP3 file using Microsoft Neural Edge-TTS.
    Returns (filename, full_file_path).
    """
    clean_text = (text or "").strip()
    if not clean_text:
        clean_text = "Slide notes not available for this section."

    selected_voice = select_voice(language, voice)
    
    # Generate content-hash-based filename for caching
    text_hash = hashlib.md5(f"{selected_voice}:{clean_text}".encode("utf-8")).hexdigest()[:12]
    prefix = f"slide_{slide_index + 1}_" if slide_index is not None else "voiceover_"
    filename = f"{prefix}{text_hash}.mp3"
    file_path = VOICEOVER_DIR / filename

    if not file_path.exists():
        communicate = edge_tts.Communicate(clean_text, selected_voice)
        await communicate.save(str(file_path))
        logger.info("Generated new slide voiceover audio: %s", filename)
    else:
        logger.debug("Reusing cached voiceover audio: %s", filename)

    return filename, file_path
