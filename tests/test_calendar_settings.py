from backend.api.auth import create_access_token
from backend.api.models.vitya import User


def test_calendar_crud(client):
    reg = client.post(
        "/api/users/register",
        json={
            "name": "Calendar User",
            "username": "caluser",
            "email": "caluser@example.com",
            "password": "Password123",
        },
    )
    token = reg.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create event
    res = client.post(
        "/api/calendar/",
        json={"title": "Client Meeting", "date": "2026-10-01", "time": "11:00 AM"},
        headers=headers,
    )
    assert res.status_code == 201
    event_id = res.json()["id"]
    assert res.json()["title"] == "Client Meeting"

    # 2. Get events
    get_res = client.get("/api/calendar/", headers=headers)
    assert get_res.status_code == 200
    assert len(get_res.json()) >= 1

    # 3. Update event
    up_res = client.put(
        f"/api/calendar/{event_id}",
        json={"title": "Quarterly Review"},
        headers=headers,
    )
    assert up_res.status_code == 200
    assert up_res.json()["title"] == "Quarterly Review"

    # 4. Delete event
    del_res = client.delete(f"/api/calendar/{event_id}", headers=headers)
    assert del_res.status_code == 200


def test_user_settings_and_subscription(client):
    reg = client.post(
        "/api/users/register",
        json={
            "name": "Settings User",
            "username": "setuser",
            "email": "setuser@example.com",
            "password": "Password123",
        },
    )
    token = reg.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Get default settings
    get_res = client.get("/api/settings/", headers=headers)
    assert get_res.status_code == 200
    assert "theme" in get_res.json()

    # 2. Update settings
    put_res = client.put(
        "/api/settings/",
        json={"theme": "midnight", "two_factor_enabled": True},
        headers=headers,
    )
    assert put_res.status_code == 200
    assert put_res.json()["theme"] == "midnight"
    assert put_res.json()["two_factor_enabled"] is True

    # 3. Change password
    pwd_res = client.post(
        "/api/settings/change-password",
        json={"current_password": "Password123", "new_password": "NewPassword789"},
        headers=headers,
    )
    assert pwd_res.status_code == 200

    # 4. Subscription info & select
    sub_res = client.get("/api/settings/subscription", headers=headers)
    assert sub_res.status_code == 200
    assert "plan_name" in sub_res.json()

    upgrade_res = client.post(
        "/api/settings/subscription/select",
        json={"plan_name": "Enterprise"},
        headers=headers,
    )
    assert upgrade_res.status_code == 200
    assert upgrade_res.json()["plan_name"] == "Enterprise"
