"""
OpenAI Provider Implementation for Shared AI Infrastructure.
"""
import os
import logging
from typing import AsyncGenerator, Optional

from shared.ai.base_provider import BaseAIProvider
from shared.ai.schemas import AICompletionRequest, AICompletionResponse
from shared.ai.exceptions import AIProviderConfigError, AIModelExecutionError

logger = logging.getLogger("shared.ai.openai")


class OpenAIProvider(BaseAIProvider):
    def __init__(self, api_key: Optional[str] = None, model_name: str = "gpt-4o-mini"):
        key = api_key or os.getenv("OPENAI_API_KEY")
        super().__init__(api_key=key, model_name=model_name)

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def generate_text(self, request: AICompletionRequest) -> AICompletionResponse:
        prompt = request.prompt or (
            request.messages[-1].content if request.messages else "Hello"
        )
        if not self.is_configured():
            return AICompletionResponse(
                text=f"[OpenAI Mock Response]: Processed prompt: {prompt[:50]}...",
                model=self.model_name,
            )

        try:
            import openai
            client = openai.AsyncOpenAI(api_key=self.api_key)
            messages = []
            if request.system_instruction:
                messages.append({"role": "system", "content": request.system_instruction})
            if request.messages:
                for m in request.messages:
                    messages.append({"role": m.role, "content": m.content})
            elif request.prompt:
                messages.append({"role": "user", "content": request.prompt})

            response = await client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
            content = response.choices[0].message.content or ""
            return AICompletionResponse(
                text=content,
                model=self.model_name,
                usage={"total_tokens": response.usage.total_tokens} if response.usage else None,
            )
        except Exception as e:
            raise AIModelExecutionError(f"OpenAI API error: {str(e)}")

    async def stream_text(self, request: AICompletionRequest) -> AsyncGenerator[str, None]:
        prompt = request.prompt or (
            request.messages[-1].content if request.messages else "Hello"
        )
        if not self.is_configured():
            mock_words = ["[OpenAI Mock Stream] ", "Token1 ", "Token2 ", prompt[:20]]
            for word in mock_words:
                yield word
            return

        try:
            import openai
            client = openai.AsyncOpenAI(api_key=self.api_key)
            messages = [{"role": "user", "content": prompt}]
            stream = await client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                stream=True,
            )
            async for chunk in stream:
                content = chunk.choices[0].delta.content or ""
                if content:
                    yield content
        except Exception as e:
            yield f"\n[Stream Error: {str(e)}]"
