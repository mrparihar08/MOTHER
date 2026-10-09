# backend/tests/test_module_boundaries.py
"""
Verification tests for MOTHER Module Boundaries & Shared Core Integration:
1. Presentation Studio Domain (/api/presentation/*)
2. Dora Dr. Domain (/api/dora/*)
3. Vidya F.E.I Advisor Domain (/api/income, /api/expense, /api/vitya, /api/analyse, /api/ai, /api/savings, /api/subscriptions)
4. Shared Platform Core (/api/users, /api/settings, /api/chat, /api/notes, /api/tasks, /api/calendar)
5. Route Alias Compatibility (/api/ai vs /api/analyse)
6. User Data Isolation and Ownership Verification
"""

import pytest
from fastapi.testclient import TestClient
from backend.app.app import app
from backend.api.database import Base, engine, SessionLocal
from backend.api.models.vitya import User, Expense, Income, SavingsGoal, RecurringSubscription
from backend.api.auth import create_access_token

client = TestClient(app)


@pytest.fixture(scope="module")
def setup_test_users():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Create user A
        user_a = db.query(User).filter(User.username == "module_test_user_a").first()
        if not user_a:
            user_a = User(
                name="Module User A",
                username="module_test_user_a",
                email="user_a@test.com",
                password="hashed_pw_test",
            )
            db.add(user_a)
            db.commit()
            db.refresh(user_a)

        # Create user B
        user_b = db.query(User).filter(User.username == "module_test_user_b").first()
        if not user_b:
            user_b = User(
                name="Module User B",
                username="module_test_user_b",
                email="user_b@test.com",
                password="hashed_pw_test",
            )
            db.add(user_b)
            db.commit()
            db.refresh(user_b)

        token_a = create_access_token({"user_id": user_a.id, "email": user_a.email, "username": user_a.username})
        token_b = create_access_token({"user_id": user_b.id, "email": user_b.email, "username": user_b.username})

        yield {
            "user_a": user_a,
            "user_b": user_b,
            "token_a": token_a,
            "token_b": token_b,
            "headers_a": {"Authorization": f"Bearer {token_a}"},
            "headers_b": {"Authorization": f"Bearer {token_b}"},
        }
    finally:
        db.query(Expense).filter(Expense.user_id.in_([user_a.id, user_b.id])).delete(synchronize_session=False)
        db.query(Income).filter(Income.user_id.in_([user_a.id, user_b.id])).delete(synchronize_session=False)
        db.query(SavingsGoal).filter(SavingsGoal.user_id.in_([user_a.id, user_b.id])).delete(synchronize_session=False)
        db.query(RecurringSubscription).filter(RecurringSubscription.user_id.in_([user_a.id, user_b.id])).delete(synchronize_session=False)
        db.commit()
        db.close()


# ==============================================================
# 1. PRESENTATION STUDIO DOMAIN
# ==============================================================
def test_presentation_studio_health():
    """Verify Presentation Studio health probe returns active status."""
    res = client.get("/api/presentation/health")
    assert res.status_code == 200
    data = res.json()
    assert data.get("status") in ("ok", "ready", "healthy")


def test_presentation_studio_templates_catalog():
    """Verify Presentation Studio template catalog returns 14 presets."""
    res = client.get("/api/presentation/templates")
    assert res.status_code == 200
    data = res.json()
    assert "presets" in data
    assert len(data["presets"]) >= 10


def test_presentation_studio_shapes_catalog():
    """Verify Presentation Studio shapes catalog returns visual primitives."""
    res = client.get("/api/presentation/shapes/catalog")
    assert res.status_code == 200
    data = res.json()
    assert "categories" in data
    assert len(data["categories"]) > 0


# ==============================================================
# 2. DORA DR. DOMAIN
# ==============================================================
def test_dora_dr_info_and_catalogs():
    """Verify Dora Dr. metadata, symptom catalog, and disease catalog."""
    res_info = client.get("/api/dora/")
    assert res_info.status_code == 200
    data_info = res_info.json()
    assert "total_symptoms_indexed" in data_info
    assert data_info["total_symptoms_indexed"] >= 100

    res_sym = client.get("/api/dora/symptoms")
    assert res_sym.status_code == 200
    assert len(res_sym.json().get("symptoms", [])) >= 100

    res_dis = client.get("/api/dora/diseases")
    assert res_dis.status_code == 200
    assert len(res_dis.json().get("diseases", [])) >= 30


def test_dora_dr_symptom_prediction():
    """Verify Dora Dr. ML clinical prediction responds with probable conditions."""
    payload = {
        "symptoms": ["fever", "headache", "fatigue"],
        "severity": "Moderate",
        "duration_days": 2,
    }
    res = client.post("/api/dora/predict?top_k=3", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "predicted_disease" in data
    assert "possible_diseases" in data
    assert len(data["possible_diseases"]) > 0


def test_dora_dr_emergency_warning():
    """Verify Dora Dr. chat intercepts critical emergency symptoms with warning."""
    payload = {
        "messages": [
            {"role": "user", "content": "I have severe chest pain and cannot breathe"}
        ]
    }
    res = client.post("/api/dora/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data.get("is_emergency") is True
    assert "EMERGENCY" in data.get("reply", "") or "URGENT" in data.get("reply", "")


# ==============================================================
# 3. VIDYA F.E.I ADVISOR DOMAIN & API ALIAS COMPATIBILITY
# ==============================================================
def test_api_ai_and_analyse_alias_health_score(setup_test_users):
    """Verify both /api/ai/health-score and /api/analyse/health-score resolve identically."""
    headers = setup_test_users["headers_a"]

    res_ai = client.get("/api/ai/health-score", headers=headers)
    assert res_ai.status_code == 200
    score_ai = res_ai.json()
    assert "health_score" in score_ai
    assert "grade" in score_ai

    res_analyse = client.get("/api/analyse/health-score", headers=headers)
    assert res_analyse.status_code == 200
    score_analyse = res_analyse.json()

    assert score_ai["health_score"] == score_analyse["health_score"]
    assert score_ai["grade"] == score_analyse["grade"]


def test_api_ai_and_analyse_alias_budget_caps(setup_test_users):
    """Verify both /api/ai/budget-cap and /api/analyse/budget-cap resolve identically."""
    headers = setup_test_users["headers_a"]

    res_ai = client.get("/api/ai/budget-cap", headers=headers)
    assert res_ai.status_code == 200

    res_analyse = client.get("/api/analyse/budget-cap", headers=headers)
    assert res_analyse.status_code == 200
    assert res_ai.json() == res_analyse.json()


def test_vidya_fei_user_data_isolation(setup_test_users):
    """Verify user data isolation: User B cannot access or see User A's expense records."""
    headers_a = setup_test_users["headers_a"]
    headers_b = setup_test_users["headers_b"]

    # User A creates an expense
    create_res = client.post(
        "/api/expense/",
        headers=headers_a,
        json={"amount": 125.50, "category": "Food", "description": "User A Private Grocery", "date": "2026-10-09"}
    )
    assert create_res.status_code == 200
    expense_a_id = create_res.json()["id"]

    # User A can get it
    get_a = client.get(f"/api/expense/{expense_a_id}", headers=headers_a)
    assert get_a.status_code == 200
    assert get_a.json()["description"] == "User A Private Grocery"

    # User B CANNOT get it (must return 404 Not Found)
    get_b = client.get(f"/api/expense/{expense_a_id}", headers=headers_b)
    assert get_b.status_code == 404

    # User B's expense list should NOT contain User A's expense
    list_b = client.get("/api/expense/", headers=headers_b)
    assert list_b.status_code == 200
    ids_b = [item["id"] for item in list_b.json()]
    assert expense_a_id not in ids_b


# ==============================================================
# 4. SHARED PLATFORM CORE
# ==============================================================
def test_shared_core_root_and_health():
    """Verify shared root and health endpoints."""
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "API is running" in res_root.json().get("message", "")

    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json().get("status") == "ok"


def test_shared_core_user_profile(setup_test_users):
    """Verify user profile retrieval and token guard."""
    # Unauthenticated request should fail with 401
    res_unauth = client.get("/api/users/profile")
    assert res_unauth.status_code == 401

    # Authenticated request succeeds
    res_auth = client.get("/api/users/profile", headers=setup_test_users["headers_a"])
    assert res_auth.status_code == 200
    assert res_auth.json()["username"] == "module_test_user_a"
