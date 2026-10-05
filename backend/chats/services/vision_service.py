from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import os
import logging
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

PRIMARY_VISION_MODEL = os.getenv("GEMINI_VISION_MODEL") or os.getenv("GEMINI_MODEL") or "gemini-3.5-flash-lite"
FALLBACK_VISION_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-1.5-flash",
]


class BaseVisionProvider(ABC):
    """Abstract base class for vision and multimodal AI providers."""

    @abstractmethod
    def analyze_multimodal(
        self,
        images_data: List[Dict[str, Any]],  # list of {"data": bytes, "mime_type": str}
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        """Analyze one or more images with an accompanying user prompt."""
        pass


class GeminiVisionProvider(BaseVisionProvider):
    """Concrete Google Gemini Multimodal Vision Provider."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self._client = None

    def get_client(self):
        if self._client is not None:
            return self._client
        if not self.api_key:
            self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            return None
        self._client = genai.Client(api_key=self.api_key)
        return self._client

    def analyze_multimodal(
        self,
        images_data: List[Dict[str, Any]],
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        client = self.get_client()
        if not client:
            return {
                "success": False,
                "error": "Gemini API key is not configured. Please set GEMINI_API_KEY in your .env file.",
                "text": "Gemini API key is not configured. Please set GEMINI_API_KEY in your environment.",
            }

        # Build content parts: prompt + image parts
        contents = [prompt]
        for img in images_data:
            img_bytes = img.get("data")
            mime_type = img.get("mime_type", "image/jpeg")
            if img_bytes:
                part = types.Part.from_bytes(data=img_bytes, mime_type=mime_type)
                contents.append(part)

        config_kwargs: Dict[str, Any] = {
            "temperature": temperature,
        }
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction

        config = types.GenerateContentConfig(**config_kwargs)

        models_to_try = [PRIMARY_VISION_MODEL] + [m for m in FALLBACK_VISION_MODELS if m != PRIMARY_VISION_MODEL]
        last_error = None

        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
                if response and response.text:
                    return {
                        "success": True,
                        "text": response.text.strip(),
                        "model_used": model_name,
                    }
            except Exception as e:
                last_error = str(e)
                logger.warning("Vision model '%s' failed: %s. Trying fallback...", model_name, e)
                continue

        error_msg = f"Vision API error (All models failed): {last_error}"
        logger.error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "text": "Maaf kijiye, image ko process karne me takleef hui. Kripya image dobara upload karein ya thodi der baad try karein.",
        }


# Global provider registry
_provider_instance: Optional[BaseVisionProvider] = None


def get_vision_provider() -> BaseVisionProvider:
    """Return the active vision provider singleton."""
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = GeminiVisionProvider()
    return _provider_instance


def set_vision_provider(provider: BaseVisionProvider) -> None:
    """Set custom vision provider (useful for testing or switching AI backends)."""
    global _provider_instance
    _provider_instance = provider
