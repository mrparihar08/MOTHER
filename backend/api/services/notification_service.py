import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import BackgroundTasks
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.api.models.notifications import (
    Notification,
    PushSubscription,
    NotificationPreference,
    NotificationDelivery,
)
from backend.api.services.push_worker import process_pending_deliveries

logger = logging.getLogger(__name__)


def get_or_create_preferences(db: Session, user_id: int) -> NotificationPreference:
    """Retrieve existing notification preferences or initialize sensible defaults."""
    pref = db.query(NotificationPreference).filter(NotificationPreference.user_id == user_id).first()
    if not pref:
        pref = NotificationPreference(
            user_id=user_id,
            in_app_enabled=True,
            push_enabled=True,
            category_settings={
                "ai": True,
                "finance": True,
                "security": True,
                "reminders": True,
                "system": True,
            },
        )
        db.add(pref)
        db.commit()
        db.refresh(pref)
    return pref


def create_notification(
    db: Session,
    user_id: int,
    type: str,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
    category: str = "system",
    background_tasks: Optional[BackgroundTasks] = None,
) -> Optional[Notification]:
    """
    Internal notification creation service.
    Validates preferences, inserts notification, registers push deliveries,
    and dispatches background delivery worker.
    """
    try:
        # 1. Check user notification preferences
        pref = get_or_create_preferences(db, user_id)
        if not pref.in_app_enabled:
            logger.info(f"In-app notifications disabled for user {user_id}. Skipping.")
            return None

        cat_settings = pref.category_settings or {}
        if not cat_settings.get(category, True):
            logger.info(f"Category '{category}' disabled for user {user_id}. Skipping.")
            return None

        # 2. Sanitize data payload (Never store sensitive auth tokens/passwords)
        safe_data = {}
        if data and isinstance(data, dict):
            for k, v in data.items():
                if k.lower() not in {"password", "token", "secret", "authorization", "bearer"}:
                    safe_data[k] = v

        # 3. Create Notification
        notif_id = str(uuid.uuid4())
        notification = Notification(
            id=notif_id,
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            data=safe_data,
        )
        db.add(notification)
        db.commit()
        db.refresh(notification)

        # 4. Create Push Delivery Records if push enabled
        if pref.push_enabled and cat_settings.get("push", True):
            active_subs = (
                db.query(PushSubscription)
                .filter(
                    PushSubscription.user_id == user_id,
                    PushSubscription.disabled_at == None,
                )
                .all()
            )

            for sub in active_subs:
                delivery = NotificationDelivery(
                    id=str(uuid.uuid4()),
                    notification_id=notification.id,
                    subscription_id=sub.id,
                    status="pending",
                )
                db.add(delivery)

            if active_subs:
                db.commit()

                # Dispatch push worker in background tasks
                if background_tasks:
                    background_tasks.add_task(process_pending_deliveries)
                else:
                    import threading
                    threading.Thread(target=process_pending_deliveries, daemon=True).start()

        return notification
    except Exception as e:
        logger.error(f"Failed to create notification for user {user_id}: {e}")
        db.rollback()
        return None


def get_user_notifications(
    db: Session,
    user_id: int,
    cursor: Optional[str] = None,
    limit: int = 20,
    unread_only: bool = False,
) -> Tuple[List[Notification], Optional[str], int]:
    """
    Fetch cursor-paginated notifications for authenticated user.
    Enforces strict user isolation.
    """
    query = db.query(Notification).filter(Notification.user_id == user_id)

    if unread_only:
        query = query.filter(Notification.read_at == None)

    if cursor:
        cursor_notif = db.query(Notification).filter(Notification.id == cursor, Notification.user_id == user_id).first()
        if cursor_notif:
            query = query.filter(
                (Notification.created_at < cursor_notif.created_at)
                | (
                    (Notification.created_at == cursor_notif.created_at)
                    & (Notification.id < cursor_notif.id)
                )
            )

    items = query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit + 1).all()

    next_cursor = None
    if len(items) > limit:
        next_cursor = items[limit - 1].id
        items = items[:limit]

    unread_count = (
        db.query(func.count(Notification.id))
        .filter(Notification.user_id == user_id, Notification.read_at == None)
        .scalar()
        or 0
    )

    return items, next_cursor, unread_count


def get_unread_count(db: Session, user_id: int) -> int:
    """Return count of unread notifications for authenticated user."""
    return (
        db.query(func.count(Notification.id))
        .filter(Notification.user_id == user_id, Notification.read_at == None)
        .scalar()
        or 0
    )


def mark_notification_as_read(
    db: Session, user_id: int, notification_id: str
) -> Optional[Notification]:
    """Mark a notification as read with ownership verification."""
    notif = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user_id)
        .first()
    )
    if not notif:
        return None

    if notif.read_at is None:
        notif.read_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(notif)
    return notif


def mark_all_as_read(db: Session, user_id: int) -> int:
    """Mark all unread notifications of the user as read."""
    now = datetime.now(timezone.utc)
    updated = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.read_at == None)
        .update({Notification.read_at: now}, synchronize_session=False)
    )
    db.commit()
    return updated


def delete_notification(db: Session, user_id: int, notification_id: str) -> bool:
    """Delete a notification with strict ownership verification."""
    notif = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user_id)
        .first()
    )
    if not notif:
        return False

    db.delete(notif)
    db.commit()
    return True
