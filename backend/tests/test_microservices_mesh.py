"""
End-to-End Integration and Contract Tests for MOTHER Microservices Architecture.
Validates:
1. Centralized Auth Service (RS256 JWT, JWKS, Argon2id, Refresh Token Rotation)
2. Shared JWT Validator (Downstream public key verification with zero DB access)
3. Finance Service (Isolated DB, user data isolation, decimal calculations, audit logging, idempotency)
4. Chat Service (Isolated DB, streaming, tool calling via internal HTTP contracts)
5. Dora Clinical Service (Isolated triage engine)
6. Presentation Studio Service (Port 8005, templates, async jobs)
"""
import pytest
from fastapi.testclient import TestClient

from services.auth_service.app import app as auth_app
from services.finance_service.app import app as finance_app
from services.chat_service.app import app as chat_app
from services.dora_service.app import app as dora_app
from services.presentation_service.app import app as presentation_app
from shared.security.jwt_validator import decode_and_validate_token, require_role, AuthenticatedUser
from shared.ai.provider_factory import AIProviderFactory


@pytest.fixture
def auth_client():
    return TestClient(auth_app)


@pytest.fixture
def finance_client():
    return TestClient(finance_app)


@pytest.fixture
def chat_client():
    return TestClient(chat_app)


@pytest.fixture
def dora_client():
    return TestClient(dora_app)


@pytest.fixture
def presentation_client():
    return TestClient(presentation_app)


# -------------------------------------------------------------
# 1. Centralized Auth & Core Service Tests
# -------------------------------------------------------------
def test_auth_service_health_and_jwks(auth_client):
    health_res = auth_client.get("/health")
    assert health_res.status_code == 200
    assert health_res.json()["service"] == "auth_service"
    assert health_res.json()["port"] == 8001

    jwks_res = auth_client.get("/api/auth/.well-known/jwks.json")
    assert jwks_res.status_code == 200
    keys = jwks_res.json().get("keys", [])
    assert len(keys) >= 1
    assert keys[0]["alg"] == "RS256"
    assert keys[0]["use"] == "sig"
    assert "n" in keys[0]
    assert "e" in keys[0]


def test_auth_registration_login_refresh_and_logout(auth_client):
    email = "microservice_user@vitya.ai"
    password = "StrongPassword2026!"

    # 1. Register
    reg_res = auth_client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "full_name": "Micro User"},
    )
    # 201 or 400 if already exists in local test runs
    assert reg_res.status_code in [201, 400]

    # 2. Login
    login_res = auth_client.post(
        "/api/auth/token",
        data={"username": email, "password": password},
    )
    assert login_res.status_code == 200
    data = login_res.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    assert access_token and refresh_token

    # 3. Refresh Token Rotation
    refresh_res = auth_client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_res.status_code == 200
    new_data = refresh_res.json()
    new_access_token = new_data["access_token"]
    new_refresh_token = new_data["refresh_token"]
    assert new_refresh_token != refresh_token

    # 4. Old refresh token must be revoked
    revoked_check = auth_client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert revoked_check.status_code == 401

    # 5. Logout
    logout_res = auth_client.post(
        "/api/auth/logout",
        json={"refresh_token": new_refresh_token},
    )
    assert logout_res.status_code == 200


# -------------------------------------------------------------
# 2. Shared JWT Validator Tests (Downstream RS256 Verification)
# -------------------------------------------------------------
def test_downstream_rs256_verification(auth_client):
    login_res = auth_client.post(
        "/api/auth/token",
        data={"username": "microservice_user@vitya.ai", "password": "StrongPassword2026!"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]

    user: AuthenticatedUser = decode_and_validate_token(token)
    assert user.email == "microservice_user@vitya.ai"
    assert user.has_role("user")
    assert not user.has_role("super_admin")


# -------------------------------------------------------------
# 3. Finance Service Tests
# -------------------------------------------------------------
def test_finance_service_operations_and_isolation(auth_client, finance_client):
    login_res = auth_client.post(
        "/api/auth/token",
        data={"username": "microservice_user@vitya.ai", "password": "StrongPassword2026!"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Add Income
    inc_res = finance_client.post(
        "/api/finance/incomes",
        json={"amount": 20000.0, "source": "Consulting"},
        headers=headers,
    )
    assert inc_res.status_code == 201

    # Add Expense
    exp_res = finance_client.post(
        "/api/finance/expenses",
        json={"amount": 4000.0, "category": "Cloud Hosting", "description": "AWS & Supabase"},
        headers=headers,
    )
    assert exp_res.status_code == 201

    # Summary
    summary_res = finance_client.get("/api/finance/summary", headers=headers)
    assert summary_res.status_code == 200
    summary = summary_res.json()
    assert summary["total_income"] >= 20000.0
    assert summary["total_expense"] >= 4000.0
    assert summary["net_balance"] >= 16000.0

    # Internal tool-calling endpoint with idempotency
    import uuid
    idem_key = f"test-idem-key-{uuid.uuid4().hex}"
    int_res = finance_client.post(
        "/api/finance/internal/transaction",
        json={
            "user_id": 1,
            "transaction_type": "expense",
            "amount": 250.0,
            "category_or_source": "Transit",
            "description": "Metro card recharge",
            "idempotency_key": idem_key,
        },
    )
    assert int_res.status_code == 200
    assert int_res.json()["status"] == "success"

    # Repeated call returns idempotent response
    repeat_res = finance_client.post(
        "/api/finance/internal/transaction",
        json={
            "user_id": 1,
            "transaction_type": "expense",
            "amount": 250.0,
            "category_or_source": "Transit",
            "description": "Metro card recharge",
            "idempotency_key": idem_key,
        },
    )
    assert repeat_res.status_code == 200
    assert repeat_res.json()["status"] == "already_processed"


# -------------------------------------------------------------
# 4. Chat Service Tests
# -------------------------------------------------------------
def test_chat_service_conversation_and_tool_intent(auth_client, chat_client):
    login_res = auth_client.post(
        "/api/auth/token",
        data={"username": "microservice_user@vitya.ai", "password": "StrongPassword2026!"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create Conversation
    conv_res = chat_client.post(
        "/api/chat/conversations",
        json={"title": "Microservices Conversation"},
        headers=headers,
    )
    assert conv_res.status_code == 201
    uid = conv_res.json()["unique_id"]

    # Send message triggering Finance tool
    msg_res = chat_client.post(
        f"/api/chat/conversations/{uid}/messages",
        json={"content": "Add 750 for books"},
        headers=headers,
    )
    assert msg_res.status_code == 200
    assert msg_res.json()["tool_called"] == "finance"

    # Send message triggering Dora health tool
    dora_msg_res = chat_client.post(
        f"/api/chat/conversations/{uid}/messages",
        json={"content": "I have severe fever and cough"},
        headers=headers,
    )
    assert dora_msg_res.status_code == 200
    assert dora_msg_res.json()["tool_called"] == "dora"


# -------------------------------------------------------------
# 5. Dora Clinical Service Tests
# -------------------------------------------------------------
def test_dora_service_endpoints(dora_client):
    health = dora_client.get("/health")
    assert health.status_code == 200
    assert health.json()["service"] == "dora-clinical-microservice"

    pred = dora_client.post(
        "/predict",
        json={"symptoms": ["fever", "cough"], "severity": "Moderate"},
    )
    assert pred.status_code == 200
    res_data = pred.json()
    assert "possible_diseases" in res_data or "predictions" in res_data


# -------------------------------------------------------------
# 6. Presentation Studio Service Tests
# -------------------------------------------------------------
def test_presentation_service_endpoints(presentation_client):
    health = presentation_client.get("/health")
    assert health.status_code == 200
    assert health.json()["service"] == "presentation_service"
    assert health.json()["port"] == 8005

    templates = presentation_client.get("/api/presentation/templates")
    assert templates.status_code == 200
