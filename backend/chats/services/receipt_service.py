import json
import logging
import re
from typing import Any, Dict, Optional, Union
from google.genai import types

from backend.chats.services.gemini_service import get_gemini_client, PRIMARY_MODEL, FALLBACK_MODELS

logger = logging.getLogger(__name__)


def parse_receipt_image(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
) -> Dict[str, Any]:
    """
    Analyzes an uploaded receipt/invoice image using Gemini Multimodal Vision.
    Extracts structured JSON: merchant, total amount, category, date, line items, and currency.
    """
    client = get_gemini_client()
    if not client:
        return {
            "success": False,
            "error": "Gemini API key is not configured.",
        }

    prompt = (
        "You are an expert financial receipt & invoice analyzer for the Vitya expense tracking app.\n"
        "Examine this receipt/bill image carefully and extract the financial details in strict JSON format.\n\n"
        "Return ONLY a JSON object with this exact schema (no markdown fences, no extra text):\n"
        "{\n"
        '  "merchant": "Store or Vendor name (e.g. Starbucks, Zomato, Apollo Pharmacy)",\n'
        '  "amount": 450.0,\n'
        '  "currency": "INR",\n'
        '  "date": "YYYY-MM-DD (or null if missing)",\n'
        '  "category": "One of: Food, Transport, Housing, Entertainment, Utilities, Health, Shopping, Fitness, Education, Finance, Other",\n'
        '  "description": "Brief 3-6 word summary of items",\n'
        '  "items": [\n'
        '     {"name": "Item name", "price": 120.0, "qty": 1}\n'
        '  ],\n'
        '  "tax": 18.0,\n'
        '  "confidence": 0.95\n'
        '}'
    )

    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    models_to_try = [PRIMARY_MODEL] + [m for m in FALLBACK_MODELS if m != PRIMARY_MODEL]

    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[prompt, image_part],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )

            if response and response.text:
                raw_text = response.text.strip()
                # Clean any stray markdown fences
                raw_text = re.sub(r"^```json\s*", "", raw_text)
                raw_text = re.sub(r"\s*```$", "", raw_text)

                data = json.loads(raw_text)
                data["success"] = True
                return data

        except Exception as e:
            logger.warning("Receipt vision model '%s' error: %s", model_name, e)
            continue

    return {
        "success": False,
        "error": "Unable to extract receipt details from image.",
    }
