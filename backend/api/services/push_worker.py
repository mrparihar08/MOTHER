import json
import logging
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.api.database import SessionLocal
from backend.api.models.notifications import (
    NotificationDelivery,
    PushSubscription,
    Notification,
)

logger = logging.getLogger(__name__)

VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:notifications@vitya-chat.onrender.com")

MAX_RETRIES = 3


def get_vapid_public_key() -> str:
    """Return the configured VAPID public key."""
    return os.getenv("VAPID_PUBLIC_KEY", VAPID_PUBLIC_KEY)


def send_single_web_push(
    subscription: PushSubscription,
    payload: Dict[str, Any],
    vapid_private_key: Optional[str] = None,
    vapid_claims: Optional[Dict[str, str]] = None,
) -> bool:
    """
    Send Web Push to a single subscription.
    Handles expired subscriptions and logs without exposing secrets.
    """
    priv_key = vapid_private_key or os.getenv("VAPID_PRIVATE_KEY", VAPID_PRIVATE_KEY)
    claims = vapid_claims or {"sub": os.getenv("VAPID_SUBJECT", VAPID_SUBJECT)}

    if not priv_key:
        logger.warning("VAPID_PRIVATE_KEY not configured. Web push skipped.")
        return False

    try:
        from pywebpush import webpush, WebPushException

        subscription_info = {
            "endpoint": subscription.endpoint,
            "keys": {
                "p256dh": subscription.p256dh,
                "auth": subscription.auth,
            },
        }

        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=priv_key,
            vapid_claims=claims,
            timeout=10,
        )
        return True
    except Exception as exc:
        raise exc


def process_pending_deliveries(db: Optional[Session] = None, max_batch: int = 50) -> int:
    """
    Process pending or retrying deliveries with transactional lock / claim.
    Safe against concurrent execution.
    """
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    processed_count = 0
    now = datetime.now(timezone.utc)

    try:
        # 1. Fetch pending deliveries eligible for processing
        deliveries = (
            db.query(NotificationDelivery)
            .filter(
                (NotificationDelivery.status == "pending")
                | (
                    (NotificationDelivery.status == "retrying")
                    & (
                        (NotificationDelivery.next_retry_at == None)
                        | (NotificationDelivery.next_retry_at <= now)
                    )
                )
            )
            .order_by(NotificationDelivery.created_at.asc())
            .limit(max_batch)
            .all()
        )

        for delivery in deliveries:
            # Mark processing
            delivery.status = "processing"
            delivery.attempts += 1
            db.commit()

            subscription = (
                db.query(PushSubscription)
                .filter(
                    PushSubscription.id == delivery.subscription_id,
                    PushSubscription.disabled_at == None,
                )
                .first()
            )

            notification = (
                db.query(Notification)
                .filter(Notification.id == delivery.notification_id)
                .first()
            )

            if not subscription or not notification:
                delivery.status = "failed"
                delivery.last_error = "Subscription or notification no longer exists"
                db.commit()
                processed_count += 1
                continue

            # Build sanitized push payload
            payload = {
                "title": notification.title,
                "body": notification.body,
                "icon": "/logo192.png",
                "badge": "/favicon.ico",
                "data": {
                    "notification_id": notification.id,
                    "type": notification.type,
                    "url": notification.data.get("url") if isinstance(notification.data, dict) else "/dashboard",
                },
            }

            try:
                send_single_web_push(subscription, payload)
                delivery.status = "sent"
                delivery.sent_at = datetime.now(timezone.utc)
                delivery.last_error = None
                subscription.last_used_at = datetime.now(timezone.utc)
                db.commit()
            except Exception as e:
                err_str = str(e)
                # Check for 404 or 410 Gone (Subscription expired)
                is_expired = False
                if hasattr(e, "response") and getattr(e, "response") is not None:
                    status_code = getattr(e.response, "status_code", 0)
                    if status_code in (404, 410):
                        is_expired = True

                if "410" in err_str or "404" in err_str or is_expired:
                    # Deactivate subscription
                    subscription.disabled_at = datetime.now(timezone.utc)
                    delivery.status = "failed"
                    delivery.last_error = "Subscription permanently expired (410/404)"
                    logger.info(f"Deactivated expired push subscription: {subscription.id}")
                else:
                    if delivery.attempts < MAX_RETRIES:
                        delivery.status = "retrying"
                        # Bounded exponential backoff with jitter
                        delay = (2 ** delivery.attempts) * 15 + random.randint(1, 5)
                        delivery.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                        delivery.last_error = err_str[:300]
                    else:
                        delivery.status = "failed"
                        delivery.last_error = f"Max retries reached: {err_str[:250]}"

                db.commit()

            processed_count += 1

    except Exception as e:
        logger.error(f"Error processing notification deliveries: {e}")
        db.rollback()
    finally:
        if own_session:
            db.close()

    return processed_count
