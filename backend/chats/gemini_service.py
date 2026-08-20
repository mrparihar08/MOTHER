from google import genai
import os
from dotenv import load_dotenv

load_dotenv()

# Primary and Fallback Models
PRIMARY_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
FALLBACK_MODELS = ["gemini-3.5-flash-lite", "gemini-2.5-flash"]

_client = None

def get_gemini_client():
    global _client
    if _client is not None:
        return _client
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    _client = genai.Client(api_key=api_key)
    return _client


def generate_response(user_message: str) -> str:
    client = get_gemini_client()
    if not client:
        return "Gemini API key is not configured. Please set GEMINI_API_KEY in your .env file."

    models_to_try = [PRIMARY_MODEL] + [m for m in FALLBACK_MODELS if m != PRIMARY_MODEL]

    last_error = None
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=user_message
            )
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            last_error = str(e)
            print(f"Model '{model_name}' failed: {e}. Trying next fallback...")
            continue

    return f"Gemini error (All models failed): {last_error}"