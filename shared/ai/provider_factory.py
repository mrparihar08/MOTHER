"""
AI Provider Factory for dynamic model resolution.
"""
import os
from typing import Optional
from shared.ai.base_provider import BaseAIProvider
from shared.ai.gemini_provider import GeminiProvider
from shared.ai.openai_provider import OpenAIProvider
from shared.ai.exceptions import AIProviderConfigError


class AIProviderFactory:
    """Factory creating AI providers based on name or environment preference."""

    @staticmethod
    def get_provider(
        provider_name: Optional[str] = None,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> BaseAIProvider:
        name = (provider_name or os.getenv("DEFAULT_AI_PROVIDER", "gemini")).lower()

        if "openai" in name or "gpt" in (model_name or ""):
            return OpenAIProvider(
                api_key=api_key or os.getenv("OPENAI_API_KEY"),
                model_name=model_name or "gpt-4o-mini",
            )
        elif "gemini" in name or "google" in name:
            return GeminiProvider(
                api_key=api_key or os.getenv("GEMINI_API_KEY"),
                model_name=model_name or "gemini-1.5-flash",
            )
        else:
            # Default to Gemini
            return GeminiProvider(
                api_key=api_key or os.getenv("GEMINI_API_KEY"),
                model_name=model_name or "gemini-1.5-flash",
            )
