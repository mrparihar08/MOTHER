"""
Abstract Base Provider for AI integrations.
"""
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any, List, Optional
from shared.ai.schemas import AICompletionRequest, AICompletionResponse


class BaseAIProvider(ABC):
    """Abstract interface that all AI providers (Gemini, OpenAI, etc.) must implement."""

    def __init__(self, api_key: Optional[str] = None, model_name: str = "default"):
        self.api_key = api_key
        self.model_name = model_name

    @abstractmethod
    async def generate_text(self, request: AICompletionRequest) -> AICompletionResponse:
        """Generate a complete text response."""
        pass

    @abstractmethod
    async def stream_text(self, request: AICompletionRequest) -> AsyncGenerator[str, None]:
        """Stream generated text chunks."""
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if provider has active and valid API credentials."""
        pass
