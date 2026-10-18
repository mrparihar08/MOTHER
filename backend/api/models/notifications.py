import uuid
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from backend.api.database import Base


def generate_uuid():
    return str(uuid.uuid4())


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(64), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    read_at = Column(DateTime(timezone=True), nullable=True, index=True)

    # Relationships
    user = relationship("User", backref="notifications")
    deliveries = relationship("NotificationDelivery", back_populates="notification", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_notifications_user_created", "user_id", "created_at"),
        Index("idx_notifications_user_unread", "user_id", "read_at"),
    )


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    endpoint = Column(Text, nullable=False, index=True)
    p256dh = Column(Text, nullable=False)
    auth = Column(Text, nullable=False)
    device_name = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    disabled_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", backref="push_subscriptions")
    deliveries = relationship("NotificationDelivery", back_populates="subscription", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_push_subscriptions_user", "user_id"),
    )


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    in_app_enabled = Column(Boolean, default=True, nullable=False)
    push_enabled = Column(Boolean, default=True, nullable=False)
    category_settings = Column(
        JSON,
        nullable=False,
        default=lambda: {
            "ai": True,
            "finance": True,
            "security": True,
            "reminders": True,
            "system": True,
        },
    )
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", backref="notification_preference", uselist=False)


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    notification_id = Column(String(36), ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False, index=True)
    subscription_id = Column(String(36), ForeignKey("push_subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), default="pending", nullable=False)  # pending, processing, sent, retrying, failed
    attempts = Column(Integer, default=0, nullable=False)
    next_retry_at = Column(DateTime(timezone=True), nullable=True, index=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    notification = relationship("Notification", back_populates="deliveries")
    subscription = relationship("PushSubscription", back_populates="deliveries")

    __table_args__ = (
        Index("idx_notification_deliveries_pending", "status", "next_retry_at"),
    )
