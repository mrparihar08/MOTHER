"""
MOTHER Shared Platform Core Package
Authentication, Database, User Models, and Core Infrastructure Services
"""
from backend.api.database import Base, engine, get_db
from backend.api.auth import token_required, optional_current_user, AuthenticatedUser

__all__ = [
    "Base",
    "engine",
    "get_db",
    "token_required",
    "optional_current_user",
    "AuthenticatedUser",
]
