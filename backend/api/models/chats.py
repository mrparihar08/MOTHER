# backend/api/models/chats.py
"""
Chat Domain Models:
Conversations, Messages, Chat History, and RAG Knowledge Base.
"""

from backend.api.models.vitya import (
    Conversation,
    ChatMessage,
    Message,
    generate_conversation_uuid,
    RAGDocument,
    RAGDocumentChunk,
)

__all__ = [
    "Conversation",
    "ChatMessage",
    "Message",
    "generate_conversation_uuid",
    "RAGDocument",
    "RAGDocumentChunk",
]
