import pytest
from datetime import datetime
from backend.api.auth import create_access_token
from backend.api.models.vitya import User, Expense


@pytest.fixture
def test_expense_data(db_session):
    user = User(name="Test User", username="testuser", email="test@example.com", password="hashed_pass")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    e1 = Expense(amount=100.0, category="Groceries", user_id=user.id, date=datetime(2025, 1, 1))
    e2 = Expense(amount=150.0, category="Groceries", user_id=user.id, date=datetime(2025, 2, 1))
    e3 = Expense(amount=200.0, category="Groceries", user_id=user.id, date=datetime(2025, 3, 1))
    db_session.add_all([e1, e2, e3])
    db_session.commit()
    return user


def test_predict_expense_async(client, test_expense_data):
    token = create_access_token({"user_id": test_expense_data.id})
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/ai/predict/Groceries", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["category"] == "Groceries"
    assert "predicted_next_month_expense" in data
    assert data["predicted_next_month_expense"] == 250.0
