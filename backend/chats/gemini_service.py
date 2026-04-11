import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment")

genai.configure(api_key=API_KEY)

model = genai.GenerativeModel("gemini-1.5-flash")


def generate_response(user_message: str) -> str:
    try:
        response = model.generate_content(user_message)
        if hasattr(response, "text") and response.text:
            return response.text.strip()
        return "No response from Gemini."
    except Exception as e:
        return f"Gemini error: {str(e)}"