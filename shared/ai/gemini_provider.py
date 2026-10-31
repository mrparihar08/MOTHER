"""
Gemini Provider Implementation for Shared AI Infrastructure.
"""
import os
import logging
from typing import AsyncGenerator, Optional

from shared.ai.base_provider import BaseAIProvider
from shared.ai.schemas import AICompletionRequest, AICompletionResponse
from shared.ai.exceptions import AIProviderConfigError, AIModelExecutionError

logger = logging.getLogger("shared.ai.gemini")


class GeminiProvider(BaseAIProvider):
    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-1.5-flash"):
        key = api_key or os.getenv("GEMINI_API_KEY")
        super().__init__(api_key=key, model_name=model_name)
        self._client = None
        self._init_client()

    def _init_client(self):
        if not self.api_key:
            return
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._client = genai.GenerativeModel(self.model_name)
        except Exception as e:
            logger.warning(f"Could not initialize Google GenerativeAI: {e}")
            self._client = None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def generate_text(self, request: AICompletionRequest) -> AICompletionResponse:
        prompt = request.prompt or (
            request.messages[-1].content if request.messages else "Hello"
        )
        if not self._client:
            # Safe mock fallback when API key is unconfigured in test environments
            return AICompletionResponse(
                text=f"[Gemini Mock Response]: Processed prompt: {prompt[:50]}...",
                model=self.model_name,
            )

        try:
            response = self._client.generate_content(prompt)
            return AICompletionResponse(
                text=response.text if hasattr(response, "text") else str(response),
                model=self.model_name,
            )
        except Exception as e:
            raise AIModelExecutionError(f"Gemini API error: {str(e)}")

    async def stream_text(self, request: AICompletionRequest) -> AsyncGenerator[str, None]:
        prompt = request.prompt or (
            request.messages[-1].content if request.messages else "Hello"
        )
        if not self._client:
            mock_words = [f"[Mock Stream] ", "Generating ", "response ", "for: ", prompt[:20]]
            for word in mock_words:
                yield word
            return

        try:
            response = self._client.generate_content(prompt, stream=True)
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            yield f"\n[Stream Error: {str(e)}]"
