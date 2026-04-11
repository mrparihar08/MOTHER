import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment")

client = genai.Client(api_key=API_KEY)

def get_supported_flash_model() -> str:
    for m in client.models.list():
        methods = getattr(m, "supported_generation_methods", []) or []
        name = getattr(m, "name", "")
        if "generateContent" in methods and "flash" in name:
            return name.replace("models/", "")
    raise RuntimeError("No supported Flash model found for this API key/project.")

MODEL_NAME = get_supported_flash_model()

def generate_response(user_message: str) -> str:
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=user_message
        )
        return (response.text or "No response from Gemini.").strip()
    except Exception as e:
        return f"Gemini error: {str(e)}"