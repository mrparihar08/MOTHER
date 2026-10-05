import os
import pytest
from datetime import timedelta
from fastapi.testclient import TestClient
from fastapi import HTTPException
from jose import jwt

from backend.app.app import app
from backend.api.auth import (
    ALGORITHM,
    SECRET_KEY,
    AuthenticatedUser,
    create_access_token,
    create_refresh_token,
    create_reset_token,
    decode_token,
    optional_current_user,
    token_required,
    verify_refresh_token,
    verify_reset_token,
)
from backend.api.models.vitya import User, Base
from backend.api.database import engine, SessionLocal
from backend.api.routes.users import pwd_context

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Clean up any test users
        db.query(User).filter(User.username.in_(["authtestuser", "refreshtestuser", "resettestuser"])).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_authenticated_user_dataclass():
    u = AuthenticatedUser(id=42, email="user@example.com", username="testuser", name="Test User")
    assert u.id == 42
    assert u.email == "user@example.com"
    assert u.username == "testuser"
    assert u.name == "Test User"


def test_create_and_decode_access_token():
    token = create_access_token({"user_id": 101, "email": "dev@test.com", "username": "devuser"})
    payload = decode_token(token)
    assert payload["user_id"] == 101
    assert payload["email"] == "dev@test.com"
    assert payload["username"] == "devuser"
    assert payload["type"] == "access"
    assert "exp" in payload


def test_create_and_decode_refresh_token():
    token = create_refresh_token({"user_id": 101})
    payload = decode_token(token)
    assert payload["user_id"] == 101
    assert payload["type"] == "refresh"
    assert "exp" in payload


def test_token_required_stateless_success():
    token = create_access_token({"user_id": 999, "email": "stateless@test.com", "username": "stateless"})
    
    # Class mock for credentials
    class DummyCreds:
        credentials = token

    user = token_required(credentials=DummyCreds(), token_param=None)
    assert isinstance(user, AuthenticatedUser)
    assert user.id == 999
    assert user.email == "stateless@test.com"
    assert user.username == "stateless"


def test_token_required_missing_token_401():
    with pytest.raises(HTTPException) as exc:
        token_required(credentials=None, token_param=None)
    assert exc.value.status_code == 401
    assert "Not authenticated" in exc.value.detail


def test_token_required_invalid_signature_401():
    fake_token = jwt.encode({"user_id": 1, "type": "access"}, "wrong-secret-key", algorithm=ALGORITHM)
    class DummyCreds:
        credentials = fake_token

    with pytest.raises(HTTPException) as exc:
        token_required(credentials=DummyCreds(), token_param=None)
    assert exc.value.status_code == 401


def test_token_required_expired_token_401():
    expired_token = create_access_token({"user_id": 1}, expires_delta=timedelta(seconds=-10))
    class DummyCreds:
        credentials = expired_token

    with pytest.raises(HTTPException) as exc:
        token_required(credentials=DummyCreds(), token_param=None)
    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail.lower()


def test_refresh_token_rejected_as_access_token():
    refresh_token = create_refresh_token({"user_id": 101})
    class DummyCreds:
        credentials = refresh_token

    with pytest.raises(HTTPException) as exc:
        token_required(credentials=DummyCreds(), token_param=None)
    assert exc.value.status_code == 401
    assert "access token required" in exc.value.detail.lower()


def test_access_token_rejected_as_refresh_token():
    access_token = create_access_token({"user_id": 101})
    with pytest.raises(HTTPException) as exc:
        verify_refresh_token(access_token)
    assert exc.value.status_code == 401
    assert "refresh token required" in exc.value.detail.lower()


def test_optional_current_user():
    # 1. No token -> returns None
    assert optional_current_user(credentials=None, token_param=None) is None

    # 2. Valid token -> returns AuthenticatedUser
    valid_token = create_access_token({"user_id": 55, "email": "opt@test.com", "username": "optuser"})
    class ValidCreds:
        credentials = valid_token
    user = optional_current_user(credentials=ValidCreds(), token_param=None)
    assert user is not None
    assert user.id == 55
    assert user.username == "optuser"

    # 3. Invalid/corrupted token -> returns None (no 401 error)
    class InvalidCreds:
        credentials = "corrupted.token.value"
    assert optional_current_user(credentials=InvalidCreds(), token_param=None) is None

    # 4. Refresh token passed -> returns None (no 401 error)
    ref_token = create_refresh_token({"user_id": 55})
    class RefCreds:
        credentials = ref_token
    assert optional_current_user(credentials=RefCreds(), token_param=None) is None


def test_password_reset_token_lifecycle():
    email = "resetuser@example.com"
    token = create_reset_token(email)

    verified_email = verify_reset_token(token)
    assert verified_email == email

    # Expired reset token
    expired_token = create_reset_token(email)
    payload = decode_token(expired_token)
    payload["exp"] = 1000000000 # Past timestamp
    expired_jwt = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    with pytest.raises(HTTPException) as exc:
        verify_reset_token(expired_jwt)
    assert exc.value.status_code == 401

    # Wrong purpose
    bad_purpose_jwt = jwt.encode({"sub": email, "purpose": "other", "exp": 2000000000}, SECRET_KEY, algorithm=ALGORITHM)
    with pytest.raises(HTTPException) as exc:
        verify_reset_token(bad_purpose_jwt)
    assert exc.value.status_code == 400


def test_full_auth_api_flow():
    # 1. Register
    reg_payload = {
        "name": "Auth Test User",
        "username": "authtestuser",
        "email": "authtest@example.com",
        "password": "SecurePassword123!",
    }
    reg_res = client.post("/api/users/register", json=reg_payload)
    assert reg_res.status_code == 200
    reg_data = reg_res.json()
    assert "token" in reg_data
    assert "access_token" in reg_data
    assert "refresh_token" in reg_data
    access_token = reg_data["access_token"]
    refresh_token = reg_data["refresh_token"]

    # Verify password was hashed and not saved in plaintext
    db = SessionLocal()
    user_row = db.query(User).filter(User.username == "authtestuser").first()
    assert user_row is not None
    assert user_row.password != "SecurePassword123!"
    assert pwd_context.verify("SecurePassword123!", user_row.password)
    db.close()

    # 2. Login
    login_payload = {
        "username": "authtestuser",
        "password": "SecurePassword123!",
    }
    login_res = client.post("/api/users/login", json=login_payload)
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert "token" in login_data
    assert "access_token" in login_data

    # 3. Access Protected Route with Bearer Token
    headers = {"Authorization": f"Bearer {access_token}"}
    profile_res = client.get("/api/users/profile", headers=headers)
    assert profile_res.status_code == 200
    profile_data = profile_res.json()
    assert profile_data["username"] == "authtestuser"
    assert profile_data["email"] == "authtest@example.com"

    # 4. Access Protected Route without Token -> 401
    unauth_res = client.get("/api/users/profile")
    assert unauth_res.status_code == 401

    # 5. Access Protected Route with Refresh Token -> 401
    bad_headers = {"Authorization": f"Bearer {refresh_token}"}
    bad_token_res = client.get("/api/users/profile", headers=bad_headers)
    assert bad_token_res.status_code == 401

    # 6. Refresh Access Token using Refresh Token
    ref_res = client.post("/api/users/refresh", json={"refresh_token": refresh_token})
    assert ref_res.status_code == 200
    ref_data = ref_res.json()
    assert "access_token" in ref_data
    new_access_token = ref_data["access_token"]

    # Verify new access token works on protected endpoints
    new_headers = {"Authorization": f"Bearer {new_access_token}"}
    profile_res2 = client.get("/api/users/profile", headers=new_headers)
    assert profile_res2.status_code == 200
    assert profile_res2.json()["username"] == "authtestuser"

    # 7. Password Reset Endpoint Flow
    reset_token = create_reset_token("authtest@example.com")
    reset_res = client.post(
        "/api/users/reset-password",
        json={"token": reset_token, "new_password": "BrandNewPassword999!"},
    )
    assert reset_res.status_code == 200

    # 8. Login with new password
    login_new = client.post("/api/users/login", json={"username": "authtestuser", "password": "BrandNewPassword999!"})
    assert login_new.status_code == 200
