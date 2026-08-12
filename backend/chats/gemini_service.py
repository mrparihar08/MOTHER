from google import genai
import os
from dotenv import load_dotenv

load_dotenv()

MODEL_NAME = "gemini-flash-latest"  # ✅ safe fallback

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
        return "Gemini API key is not configured."

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=user_message
        )

        return (response.text or "No response from Gemini").strip()

    except Exception as e:
        return f"Gemini error: {str(e)}"