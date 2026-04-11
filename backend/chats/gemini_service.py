from google import genai
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY not found")

client = genai.Client(api_key=API_KEY)

MODEL_NAME = "gemini-flash-latest"  # ✅ safe fallback


def generate_response(user_message: str) -> str:
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=user_message
        )

        return (response.text or "No response from Gemini").strip()

    except Exception as e:
        return f"Gemini error: {str(e)}"