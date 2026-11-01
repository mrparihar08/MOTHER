from google import genai
from google.genai import types
import os
import time
from typing import Optional
from dotenv import load_dotenv

# Ensure root .env is always loaded regardless of current working directory
_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
load_dotenv(os.path.join(_BASE_DIR, ".env"))
load_dotenv()

PRIMARY_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
FALLBACK_MODELS = ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.6-flash", "gemini-flash-latest"]

_client = None


def get_gemini_client(force_new: bool = False):
    global _client
    if _client is not None and not force_new:
        return _client

    load_dotenv(os.path.join(_BASE_DIR, ".env"))
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    try:
        _client = genai.Client(api_key=api_key)
    except Exception as e:
        print(f"Failed to initialize Gemini client: {e}")
        _client = None
    return _client


def _is_transient_network_error(err_str: str) -> bool:
    low = err_str.lower()
    return any(term in low for term in [
        "11001",
        "getaddrinfo",
        "server disconnected",
        "connection reset",
        "broken pipe",
        "timeout",
        "handshake operation timed out"
    ])


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
        for attempt in range(2):
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
                if _is_transient_network_error(last_error) and attempt == 0:
                    time.sleep(1)
                    client = get_gemini_client(force_new=True)
                    continue
                print(f"Model '{model_name}' failed: {e}. Trying next fallback...")
                break

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
        succeeded = False
        for attempt in range(2):
            try:
                stream = client.models.generate_content_stream(
                    model=model_name,
                    contents=user_message,
                    config=config,
                )
                for chunk in stream:
                    if chunk and chunk.text:
                        yield chunk.text
                succeeded = True
                return
            except Exception as e:
                last_error = str(e)
                if _is_transient_network_error(last_error) and attempt == 0:
                    time.sleep(1)
                    client = get_gemini_client(force_new=True)
                    continue
                print(f"Model '{model_name}' stream failed: {e}. Trying next fallback...")
                break
        if succeeded:
            return

    yield f"Gemini stream error: {last_error}"
