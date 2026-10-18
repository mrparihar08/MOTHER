import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.api.auth import AuthenticatedUser, token_required
from backend.api.database import get_db
from backend.api.models.notifications import (
    Notification,
    PushSubscription,
    NotificationPreference,
)
from backend.api.schemas.notifications import (
    NotificationResponse,
    NotificationListResponse,
    UnreadCountResponse,
    ReadAllResponse,
    PushPublicKeyResponse,
    PushSubscribeRequest,
    PushUnsubscribeRequest,
    NotificationPreferencesResponse,
    NotificationPreferencesUpdate,
    TestPushRequest,
)
from backend.api.services.notification_service import (
    create_notification,
    get_user_notifications,
    get_unread_count,
    mark_notification_as_read,
    mark_all_as_read,
    delete_notification,
    get_or_create_preferences,
)
from backend.api.services.push_worker import get_vapid_public_key

logger = logging.getLogger(__name__)

router = APIRouter()


# ==============================================================================
# NOTIFICATION ENDPOINTS
# ==============================================================================
@router.get("/notifications", response_model=NotificationListResponse)
def list_notifications(
    cursor: Optional[str] = Query(None, description="Cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    unread_only: bool = Query(False, description="Filter unread notifications only"),
    current_user: AuthenticatedUser = Depends(token_required),
    db: Session = Depends(get_db),
):
    """Fetch notifications for the authenticated user with cursor-based pagination."""
    items, next_cursor, unread_count = get_user_notifications(
        db=db,
        user_id=current_user.id,
        cursor=cursor,
        limit=limit,
        unread_only=unread_only,
    )
    return NotificationListResponse(
        items=items,
        next_cursor=next_cursor,
        unread_count=unread_count,
    )


@router.get("/notifications/unread-count", response_model=UnreadCountResponse)
def get_unread_notification_count(
    current_user: AuthenticatedUser = Depends(token_required),
    db: Session = Depends(get_db),
):
    """Retrieve unread notification count for the authenticated user."""
    count = get_unread_count(db=db, user_id=current_user.id)
    return UnreadCountResponse(unread_count=count)


@router.patch("/notifications/{notification_id}/read", response_model=NotificationResponse)
def mark_as_read(
    notification_id: str,
    current_user: AuthenticatedUser = Depends(token_required),
    db: Session = Depends(get_db),
):
    """Mark a notification as read. Verifies ownership."""
    notif = mark_notification_as_read(
        db=db,
        user_id=current_user.id,
        notification_id=notification_id,
    )
    if not notif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return notif


@router.post("/notifications/read-all", response_model=ReadAllResponse)
def mark_all_read(
    current_user: AuthenticatedUser = Depends(token_required),
    db: Session = Depends(get_db),
):
    """Mark all unread notifications of the current user as read."""
    updated = mark_all_as_read(db=db, user_id=current_user.id)
    return ReadAllResponse(updated_count=updated)


@router.delete("/notifications/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_notification(
    notification_id: str,
    current_user: AuthenticatedUser = Depends(token_required),
    db: Session = Depends(get_db),
):
    """Delete a notification owned by the authenticated user."""
    deleted = delete_notification(
        db=db,
        user_id=current_user.id,
        notification_id=notification_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return None


# ==============================================================================
# WEB PUSH SUBSCRIPTION ENDPOINTS
# ==============================================================================
@router.get("/push/public-key", response_model=PushPublicKeyResponse)
def get_public_key():
    """Retrieve the VAPID public key for browser PushManager subscription."""
    key = get_vapid_public_key()
    return PushPublicKeyResponse(public_key=key)


@router.post("/push/subscribe")
def subscribe_push(
    req: PushSubscribeRequest,
    current_user: AuthenticatedUser = Depends(token_required),
    db: Session = Depends(get_db),
):
    """Register or reactivate a Web Push subscription for the authenticated user."""
    if not req.endpoint.startswith("https://"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid push subscription endpoint: HTTPS required",
        )

    # Check for existing subscription by endpoint
    sub = db.query(PushSubscription).filter(PushSubscription.endpoint == req.endpoint).first()

    if sub:
        # Reassign to current user & reactivate
        sub.user_id = current_user.id
        sub.p256dh = req.keys.p256dh
        sub.auth = req.keys.auth
        sub.device_name = req.device_name or sub.device_name
        sub.disabled_at = None
        sub.updated_at = datetime.now(timezone.utc)
    else:
        sub = PushSubscription(
            user_id=current_user.id,
            endpoint=req.endpoint,
            p256dh=req.keys.p256dh,
            auth=req.keys.auth,
            device_name=req.device_name,
        )
        db.add(sub)

    db.commit()
    return {"status": "subscribed", "subscription_id": sub.id}


@router.delete("/push/subscribe")
def unsubscribe_push(
    req: PushUnsubscribeRequest,
    current_user: AuthenticatedUser = Depends(token_required),
    db: Session = Depends(get_db),
):
    """Revoke/disable a Web Push subscription for the authenticated user."""
    sub = (
        db.query(PushSubscription)
        .filter(
            PushSubscription.endpoint == req.endpoint,
            PushSubscription.user_id == current_user.id,
        )
        .first()
    )
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    sub.disabled_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "unsubscribed"}


# ==============================================================================
# NOTIFICATION PREFERENCES ENDPOINTS
# ==============================================================================
@router.get("/notification-preferences", response_model=NotificationPreferencesResponse)
def get_preferences(
    current_user: AuthenticatedUser = Depends(token_required),
    db: Session = Depends(get_db),
):
    """Get the authenticated user's notification preferences."""
    pref = get_or_create_preferences(db, current_user.id)
    return pref


@router.patch("/notification-preferences", response_model=NotificationPreferencesResponse)
def update_preferences(
    req: NotificationPreferencesUpdate,
    current_user: AuthenticatedUser = Depends(token_required),
    db: Session = Depends(get_db),
):
    """Update notification preferences with server-side validation."""
    pref = get_or_create_preferences(db, current_user.id)

    if req.in_app_enabled is not None:
        pref.in_app_enabled = req.in_app_enabled
    if req.push_enabled is not None:
        pref.push_enabled = req.push_enabled
    if req.category_settings is not None:
        # Validate allowed categories
        allowed = {"ai", "finance", "security", "reminders", "system"}
        updated_cats = dict(pref.category_settings or {})
        for cat, val in req.category_settings.items():
            if cat in allowed and isinstance(val, bool):
                updated_cats[cat] = val
        pref.category_settings = updated_cats

    pref.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(pref)
    return pref


# ==============================================================================
# TEST PUSH NOTIFICATION (FOR LIVE VERIFICATION)
# ==============================================================================
@router.post("/notifications/test-send", response_model=NotificationResponse)
def send_test_notification(
    req: TestPushRequest,
    background_tasks: BackgroundTasks,
    current_user: AuthenticatedUser = Depends(token_required),
    db: Session = Depends(get_db),
):
    """Send an immediate test notification and push delivery to verify setup."""
    notif = create_notification(
        db=db,
        user_id=current_user.id,
        type="system",
        title=req.title or "Test Push Notification",
        body=req.body or "Web Push notifications are active on Vitya AI!",
        data={"url": "/dashboard"},
        category="system",
        background_tasks=background_tasks,
    )
    if not notif:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Notification could not be created (check your notification preferences)",
        )
    return notif
