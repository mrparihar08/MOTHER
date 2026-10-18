import os
import unittest.mock as mock
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.database import Base, get_db
from backend.api.models.vitya import User
from backend.api.models.notifications import (
    Notification,
    PushSubscription,
    NotificationPreference,
    NotificationDelivery,
)
from backend.api.auth import create_access_token
from backend.app.app import app
from backend.api.services.notification_service import create_notification
from backend.api.services.push_worker import process_pending_deliveries


from sqlalchemy.pool import StaticPool

@pytest.fixture
def test_setup():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    # Create 2 test users for cross-user isolation tests
    user1 = User(id=1, name="User One", username="user1", email="user1@example.com", password="pwd")
    user2 = User(id=2, name="User Two", username="user2", email="user2@example.com", password="pwd")
    session.add_all([user1, user2])
    session.commit()
    session.refresh(user1)
    session.refresh(user2)

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    token1 = create_access_token({"user_id": user1.id, "email": user1.email, "username": user1.username})
    token2 = create_access_token({"user_id": user2.id, "email": user2.email, "username": user2.username})

    headers1 = {"Authorization": f"Bearer {token1}"}
    headers2 = {"Authorization": f"Bearer {token2}"}

    yield {
        "session": session,
        "client": client,
        "user1": user1,
        "user2": user2,
        "headers1": headers1,
        "headers2": headers2,
    }

    app.dependency_overrides.clear()
    session.close()


def test_unauthorized_requests_rejected(test_setup):
    client = test_setup["client"]
    res = client.get("/api/v1/notifications")
    assert res.status_code == 401


def test_notification_creation_and_unread_count(test_setup):
    session = test_setup["session"]
    client = test_setup["client"]
    user1 = test_setup["user1"]
    headers1 = test_setup["headers1"]

    # Initial count should be 0
    res = client.get("/api/v1/notifications/unread-count", headers=headers1)
    assert res.status_code == 200
    assert res.json()["unread_count"] == 0

    # Create 2 notifications
    n1 = create_notification(session, user1.id, "system", "Title 1", "Body 1")
    n2 = create_notification(session, user1.id, "ai", "Title 2", "Body 2")
    assert n1 is not None
    assert n2 is not None

    res = client.get("/api/v1/notifications/unread-count", headers=headers1)
    assert res.status_code == 200
    assert res.json()["unread_count"] == 2


def test_cursor_pagination(test_setup):
    session = test_setup["session"]
    client = test_setup["client"]
    user1 = test_setup["user1"]
    headers1 = test_setup["headers1"]

    from datetime import timedelta
    base_time = datetime.now(timezone.utc)
    for i in range(5):
        n = Notification(
            id=f"notif-cursor-{i}",
            user_id=user1.id,
            type="system",
            title=f"Title {i}",
            body=f"Body {i}",
            created_at=base_time + timedelta(seconds=i),
        )
        session.add(n)
    session.commit()

    res = client.get("/api/v1/notifications?limit=2", headers=headers1)
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) == 2
    assert data["next_cursor"] is not None

    # Next page
    res2 = client.get(f"/api/v1/notifications?limit=2&cursor={data['next_cursor']}", headers=headers1)
    assert res2.status_code == 200
    data2 = res2.json()
    assert len(data2["items"]) == 2
    assert data2["items"][0]["id"] != data["items"][0]["id"]


def test_mark_as_read_and_ownership_isolation(test_setup):
    session = test_setup["session"]
    client = test_setup["client"]
    user1 = test_setup["user1"]
    headers1 = test_setup["headers1"]
    headers2 = test_setup["headers2"]

    n1 = create_notification(session, user1.id, "system", "Test Title", "Test Body")

    # User 2 tries to mark User 1's notification as read -> 404
    res_cross = client.patch(f"/api/v1/notifications/{n1.id}/read", headers=headers2)
    assert res_cross.status_code == 404

    # User 1 marks own notification -> 200
    res_own = client.patch(f"/api/v1/notifications/{n1.id}/read", headers=headers1)
    assert res_own.status_code == 200
    assert res_own.json()["read_at"] is not None

    # Unread count decremented
    res_count = client.get("/api/v1/notifications/unread-count", headers=headers1)
    assert res_count.json()["unread_count"] == 0


def test_mark_all_read(test_setup):
    session = test_setup["session"]
    client = test_setup["client"]
    user1 = test_setup["user1"]
    user2 = test_setup["user2"]
    headers1 = test_setup["headers1"]
    headers2 = test_setup["headers2"]

    create_notification(session, user1.id, "system", "U1 Notif 1", "Body")
    create_notification(session, user1.id, "system", "U1 Notif 2", "Body")
    create_notification(session, user2.id, "system", "U2 Notif 1", "Body")

    # User 1 marks all as read
    res = client.post("/api/v1/notifications/read-all", headers=headers1)
    assert res.status_code == 200
    assert res.json()["updated_count"] == 2

    # User 1 has 0 unread
    assert client.get("/api/v1/notifications/unread-count", headers=headers1).json()["unread_count"] == 0
    # User 2 still has 1 unread
    assert client.get("/api/v1/notifications/unread-count", headers=headers2).json()["unread_count"] == 1


def test_delete_notification_and_ownership(test_setup):
    session = test_setup["session"]
    client = test_setup["client"]
    user1 = test_setup["user1"]
    headers1 = test_setup["headers1"]
    headers2 = test_setup["headers2"]

    n1 = create_notification(session, user1.id, "system", "Delete Me", "Body")

    # User 2 cannot delete User 1's notification
    res_cross = client.delete(f"/api/v1/notifications/{n1.id}", headers=headers2)
    assert res_cross.status_code == 404

    # User 1 deletes own notification -> 204
    res_own = client.delete(f"/api/v1/notifications/{n1.id}", headers=headers1)
    assert res_own.status_code == 204

    # Verify deleted
    assert session.query(Notification).filter(Notification.id == n1.id).first() is None


def test_push_subscription_and_duplicate_handling(test_setup):
    session = test_setup["session"]
    client = test_setup["client"]
    headers1 = test_setup["headers1"]

    sub_data = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/test-endpoint-123",
        "keys": {
            "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QT9t0AxdSSS3xR-dew0u0em15UNbS5zVG2-W1",
            "auth": "tBHItJI5svbpez7KI4CCXg",
        },
        "device_name": "Chrome Desktop",
    }

    # 1. Subscribe
    res = client.post("/api/v1/push/subscribe", json=sub_data, headers=headers1)
    assert res.status_code == 200
    assert res.json()["status"] == "subscribed"

    # Verify 1 record
    subs = session.query(PushSubscription).all()
    assert len(subs) == 1
    assert subs[0].endpoint == sub_data["endpoint"]

    # 2. Resubscribe with same endpoint -> Should update, not duplicate
    sub_data["device_name"] = "Chrome Desktop Updated"
    res2 = client.post("/api/v1/push/subscribe", json=sub_data, headers=headers1)
    assert res2.status_code == 200

    subs_after = session.query(PushSubscription).all()
    assert len(subs_after) == 1
    assert subs_after[0].device_name == "Chrome Desktop Updated"

    # 3. Unsubscribe
    res3 = client.request("DELETE", "/api/v1/push/subscribe", json={"endpoint": sub_data["endpoint"]}, headers=headers1)
    assert res3.status_code == 200
    assert res3.json()["status"] == "unsubscribed"

    sub_disabled = session.query(PushSubscription).first()
    assert sub_disabled.disabled_at is not None


def test_notification_preference_enforcement(test_setup):
    session = test_setup["session"]
    client = test_setup["client"]
    user1 = test_setup["user1"]
    headers1 = test_setup["headers1"]

    # Get initial preferences
    res = client.get("/api/v1/notification-preferences", headers=headers1)
    assert res.status_code == 200
    assert res.json()["in_app_enabled"] is True

    # Disable 'finance' category
    res_update = client.patch(
        "/api/v1/notification-preferences",
        json={"category_settings": {"finance": False}},
        headers=headers1,
    )
    assert res_update.status_code == 200
    assert res_update.json()["category_settings"]["finance"] is False

    # Attempt to create a 'finance' notification
    notif = create_notification(session, user1.id, "receipt_scanned", "Receipt", "Body", category="finance")
    # Should be None because category is disabled
    assert notif is None

    # But 'ai' category is still enabled
    notif_ai = create_notification(session, user1.id, "presentation_ready", "Deck", "Body", category="ai")
    assert notif_ai is not None


def test_push_worker_delivery_and_expiry(test_setup):
    session = test_setup["session"]
    user1 = test_setup["user1"]

    # Create active subscription
    sub = PushSubscription(
        user_id=user1.id,
        endpoint="https://fcm.googleapis.com/fcm/send/expired-test",
        p256dh="mock_p256dh",
        auth="mock_auth",
    )
    session.add(sub)
    session.commit()

    # Create notification and delivery
    notif = create_notification(session, user1.id, "system", "Worker Test", "Test Delivery")
    delivery = session.query(NotificationDelivery).filter(NotificationDelivery.notification_id == notif.id).first()
    assert delivery is not None
    assert delivery.status == "pending"

    # Mock expired subscription error (410 Gone)
    with mock.patch("backend.api.services.push_worker.send_single_web_push") as mock_send:
        mock_send.side_effect = Exception("410 Gone: Push subscription has expired or unsubscribed")
        processed = process_pending_deliveries(db=session)
        assert processed >= 1

    session.refresh(delivery)
    session.refresh(sub)
    assert delivery.status == "failed"
    assert "expired" in delivery.last_error.lower()
    # Subscription should be deactivated
    assert sub.disabled_at is not None
