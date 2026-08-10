from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.app import app
from backend.api.database import Base, get_db
from backend.api.auth import create_access_token
from backend.api.models.vitya import User, Expense, Income

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    user = User(name="Test User", username="testuser", email="test@example.com", password="hashed_pass")
    db.add(user)
    db.commit()
    db.refresh(user)

    e = Expense(amount=100.0, category="Food", description="Lunch", user_id=user.id)
    i = Income(amount=500.0, source="Salary", user_id=user.id)
    db.add_all([e, i])
    db.commit()

    db.close()
    yield
    Base.metadata.drop_all(bind=engine)


def test_csv_routes_distinct():
    token = create_access_token({"user_id": 1})
    headers = {"Authorization": f"Bearer {token}"}

    res_exp = client.get("/api/vitya/csv/expenses", headers=headers)
    assert res_exp.status_code == 200
    assert "attachment; filename=expenses.csv" in res_exp.headers["content-disposition"]
    assert "Food" in res_exp.text

    res_inc = client.get("/api/vitya/csv/incomes", headers=headers)
    assert res_inc.status_code == 200
    assert "attachment; filename=incomes.csv" in res_inc.headers["content-disposition"]
    assert "Salary" in res_inc.text


def test_forgot_password_frontend_url(monkeypatch, capsys):
    monkeypatch.setenv("FRONTEND_URL", "https://vitya-app.com")

    res = client.post("/api/users/forgot-password", json={"email": "test@example.com"})
    assert res.status_code == 200

    captured = capsys.readouterr()
    assert "https://vitya-app.com/reset-password?token=" in captured.out
