import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from backend.chats.services.proactive_daemon import ProactiveDaemon


class DummyUser:
    def __init__(self, id=1, name="Preet", username="preet"):
        self.id = id
        self.name = name
        self.username = username


class DummySubscription:
    def __init__(self, name="Netflix 4K", amount=649.0, next_due_date="2026-10-09", status="active"):
        self.name = name
        self.amount = amount
        self.next_due_date = next_due_date
        self.status = status


class DummyBudget:
    def __init__(self, category="Dining Out", monthly_limit=5000.0):
        self.category = category
        self.monthly_limit = monthly_limit


def test_proactive_daemon_morning_briefing():
    daemon = ProactiveDaemon()
    mock_db = MagicMock()
    user = DummyUser()

    # Mock empty queries
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
    mock_db.query.return_value.filter.return_value.all.return_value = []

    res = daemon.generate_morning_briefing(user, mock_db)
    assert res["type"] == "daily_agenda"
    assert "Good Morning, Preet" in res["content"]
    assert "Today's Overview" in res["content"]
    assert "Scheduled Meetings" in res["content"]
    assert "Priority Action Items" in res["content"]


def test_subscription_alerts_detection():
    daemon = ProactiveDaemon()
    mock_db = MagicMock()

    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    sub = DummySubscription(name="Netflix 4K", amount=649.0, next_due_date=tomorrow_str)
    mock_db.query.return_value.filter.return_value.all.return_value = [sub]

    alerts = daemon.get_subscription_alerts(user_id=1, db=mock_db)
    assert len(alerts) == 1
    assert alerts[0]["name"] == "Netflix 4K"
    assert alerts[0]["urgency"] == "TOMORROW"


def test_budget_alerts_detection():
    daemon = ProactiveDaemon()
    mock_db = MagicMock()

    budget = DummyBudget(category="Dining Out", monthly_limit=5000.0)
    mock_db.query.return_value.filter.return_value.all.return_value = [budget]
    mock_db.query.return_value.filter.return_value.scalar.return_value = 4500.0  # 90%

    alerts = daemon.get_budget_alerts(user_id=1, db=mock_db)
    assert len(alerts) == 1
    assert alerts[0]["category"] == "Dining Out"
    assert alerts[0]["pct"] == 90.0
    assert alerts[0]["is_exceeded"] is False
