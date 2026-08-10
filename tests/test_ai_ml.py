from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime

from backend.app.app import app
from backend.api.database import Base, get_db
from backend.api.auth import create_access_token
from backend.api.models.vitya import User, Expense

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

    e1 = Expense(amount=100.0, category="Groceries", user_id=user.id, date=datetime(2025, 1, 1))
    e2 = Expense(amount=150.0, category="Groceries", user_id=user.id, date=datetime(2025, 2, 1))
    e3 = Expense(amount=200.0, category="Groceries", user_id=user.id, date=datetime(2025, 3, 1))
    db.add_all([e1, e2, e3])
    db.commit()

    db.close()
    yield
    Base.metadata.drop_all(bind=engine)


def test_predict_expense_async():
    token = create_access_token({"user_id": 1})
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/ai/predict/Groceries", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["category"] == "Groceries"
    assert "predicted_next_month_expense" in data
    assert data["predicted_next_month_expense"] == 250.0
