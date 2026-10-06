from google import genai
from google.genai import types
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

PRIMARY_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
FALLBACK_MODELS = ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.6-flash", "gemini-flash-latest"]

_client = None


def get_gemini_client():
    global _client
    if _client is not None:
        return _client
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    _client = genai.Client(api_key=api_key)
    return _client


def generate_response(
    user_message: str,
    system_instruction: Optional[str] = None,
    temperature: Optional[float] = None,
) -> str:
    client = get_gemini_client()
    if not client:
        return "Gemini API key is not configured. Please set GEMINI_API_KEY in your .env file."

    models_to_try = [PRIMARY_MODEL] + [m for m in FALLBACK_MODELS if m != PRIMARY_MODEL]

    config_kwargs = {}
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction
    if temperature is not None:
        config_kwargs["temperature"] = temperature

    config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

    last_error = None
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=user_message,
                config=config,
            )
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            last_error = str(e)
            print(f"Model '{model_name}' failed: {e}. Trying next fallback...")
            continue

    return f"Gemini error (All models failed): {last_error}"


def generate_response_stream(
    user_message: str,
    system_instruction: Optional[str] = None,
    temperature: Optional[float] = None,
):
    """Generator yielding text chunks in real-time."""
    client = get_gemini_client()
    if not client:
        yield "Gemini API key is not configured. Please set GEMINI_API_KEY in your .env file."
        return

    models_to_try = [PRIMARY_MODEL] + [m for m in FALLBACK_MODELS if m != PRIMARY_MODEL]

    config_kwargs = {}
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction
    if temperature is not None:
        config_kwargs["temperature"] = temperature

    config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

    last_error = None
    for model_name in models_to_try:
        try:
            stream = client.models.generate_content_stream(
                model=model_name,
                contents=user_message,
                config=config,
            )
            for chunk in stream:
                if chunk and chunk.text:
                    yield chunk.text
            return
        except Exception as e:
            last_error = str(e)
            print(f"Model '{model_name}' stream failed: {e}. Trying next fallback...")
            continue

    yield f"Gemini stream error: {last_error}"

