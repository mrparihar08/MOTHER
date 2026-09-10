import importlib
import sys

import pytest


def test_secret_key_is_required_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    sys.modules.pop("backend.api.auth", None)

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        importlib.import_module("backend.api.auth")


def test_password_reset_flow(client):
    from backend.api.auth import create_reset_token

    # 1. Register user
    reg_res = client.post(
        "/api/users/register",
        json={
            "name": "Reset Test User",
            "username": "resetuser",
            "email": "resetuser@example.com",
            "password": "OldPassword123",
        },
    )
    assert reg_res.status_code == 200

    # 2. Login with old password succeeds
    login_old = client.post(
        "/api/users/login",
        json={"username": "resetuser", "password": "OldPassword123"},
    )
    assert login_old.status_code == 200

    # 3. Create reset token and perform reset
    token = create_reset_token("resetuser@example.com")
    reset_res = client.post(
        "/api/users/reset-password",
        json={"token": token, "new_password": "NewPassword456"},
    )
    assert reset_res.status_code == 200
    assert reset_res.json()["message"] == "Password has been reset successfully"

    # 4. Login with old password fails
    fail_old = client.post(
        "/api/users/login",
        json={"username": "resetuser", "password": "OldPassword123"},
    )
    assert fail_old.status_code == 401

    # 5. Login with NEW password succeeds (by username)
    login_new = client.post(
        "/api/users/login",
        json={"username": "resetuser", "password": "NewPassword456"},
    )
    assert login_new.status_code == 200

    # 6. Login with NEW password succeeds (by email)
    login_email = client.post(
        "/api/users/login",
        json={"username": "resetuser@example.com", "password": "NewPassword456"},
    )
    assert login_email.status_code == 200
