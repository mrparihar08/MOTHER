"""
Shared AI Layer Exceptions.
"""

class AIException(Exception):
    """Base exception for all AI operations."""
    pass

class AIProviderConfigError(AIException):
    """Raised when an AI provider lacks required configuration or API keys."""
    pass

class AIRateLimitError(AIException):
    """Raised when the AI provider throttles or rate limits requests."""
    pass

class AIModelExecutionError(AIException):
    """Raised when the AI model execution fails."""
    pass
