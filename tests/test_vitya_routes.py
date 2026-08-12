import pytest
from backend.api.auth import create_access_token
from backend.api.models.vitya import User, Expense, Income


@pytest.fixture
def test_user_data(db_session):
    user = User(name="Test User", username="testuser", email="test@example.com", password="hashed_pass")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    e = Expense(amount=100.0, category="Food", description="Lunch", user_id=user.id)
    i = Income(amount=500.0, source="Salary", user_id=user.id)
    db_session.add_all([e, i])
    db_session.commit()
    return user


def test_csv_routes_distinct(client, test_user_data):
    token = create_access_token({"user_id": test_user_data.id})
    headers = {"Authorization": f"Bearer {token}"}

    res_exp = client.get("/api/vitya/csv/expenses", headers=headers)
    assert res_exp.status_code == 200
    assert "attachment; filename=expenses.csv" in res_exp.headers["content-disposition"]
    assert "Food" in res_exp.text

    res_inc = client.get("/api/vitya/csv/incomes", headers=headers)
    assert res_inc.status_code == 200
    assert "attachment; filename=incomes.csv" in res_inc.headers["content-disposition"]
    assert "Salary" in res_inc.text


def test_forgot_password_frontend_url(client, test_user_data, monkeypatch, capsys):
    monkeypatch.setenv("FRONTEND_URL", "https://vitya-app.com")

    res = client.post("/api/users/forgot-password", json={"email": "test@example.com"})
    assert res.status_code == 200

    captured = capsys.readouterr()
    assert "https://vitya-app.com/reset-password?token=" in captured.out
