"""
Shared AI Request and Response Data Models.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ChatMessageSchema(BaseModel):
    role: str = Field(..., description="Message role: 'user', 'model', 'assistant', 'system'")
    content: str = Field(..., description="Text content of the message")


class AICompletionRequest(BaseModel):
    prompt: Optional[str] = None
    messages: Optional[List[ChatMessageSchema]] = None
    system_instruction: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = 2048
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None


class AICompletionResponse(BaseModel):
    text: str
    model: str
    usage: Optional[Dict[str, int]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    raw_response: Optional[Any] = None
