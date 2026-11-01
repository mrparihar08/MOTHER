# backend/api/models/core.py
"""
Shared Core Domain Models:
Users, Identity, UserSettings, and Support.
"""

from backend.api.models.vitya import (
    Base,
    TimestampMixin,
    User,
    UserSettings,
    SupportTicket,
)

__all__ = [
    "Base",
    "TimestampMixin",
    "User",
    "UserSettings",
    "SupportTicket",
]
