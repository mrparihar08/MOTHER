# Re-export from shared platform core service for backward-compatibility
from backend.api.services.gemini_service import (
    PRIMARY_MODEL,
    FALLBACK_MODELS,
    get_gemini_client,
    generate_response,
    generate_response_stream,
)

__all__ = [
    "PRIMARY_MODEL",
    "FALLBACK_MODELS",
    "get_gemini_client",
    "generate_response",
    "generate_response_stream",
]
