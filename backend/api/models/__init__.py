# backend/api/models/__init__.py
"""
Unified Domain Models Registry:
Clean domain separation for Core, Finance, Chats, Presentation, Dora, and Notifications.
"""

from backend.api.models.core import User, UserSettings, SupportTicket, TimestampMixin, Base
from backend.api.models.finance import Expense, Income, Budget, SavingsGoal, RecurringSubscription
from backend.api.models.chats import Conversation, ChatMessage, Message, generate_conversation_uuid
from backend.api.models.presentation import PresentationBrand, SavedPresentation
from backend.api.models.workspace import Note, Task, CalendarEvent
from backend.api.models.dora import DoraAssessment
from backend.api.models.notifications import (
    Notification,
    PushSubscription,
    NotificationPreference,
    NotificationDelivery,
)

__all__ = [
    "Base",
    "TimestampMixin",
    "User",
    "UserSettings",
    "SupportTicket",
    "Expense",
    "Income",
    "Budget",
    "SavingsGoal",
    "RecurringSubscription",
    "Conversation",
    "ChatMessage",
    "Message",
    "generate_conversation_uuid",
    "PresentationBrand",
    "SavedPresentation",
    "Note",
    "Task",
    "CalendarEvent",
    "DoraAssessment",
    "Notification",
    "PushSubscription",
    "NotificationPreference",
    "NotificationDelivery",
]
