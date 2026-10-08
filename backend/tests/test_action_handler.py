import pytest
from unittest.mock import MagicMock
from backend.chats.handlers.action_handler import (
    parse_date_and_time,
    build_google_calendar_url,
    is_agent_action,
    handle_calendar_action,
    handle_task_action,
    handle_email_action,
    handle_daily_agenda,
    handle_agent_action,
)
from backend.api.models.vitya import CalendarEvent, Task


def test_parse_date_and_time():
    d_str, d_label, t_str = parse_date_and_time("Kal subah 11 baje Rahul ke sath meeting")
    assert d_str is not None
    assert d_label == "Tomorrow"
    assert "11:00 AM" in t_str


def test_is_agent_action():
    assert is_agent_action("Kal subah 11 baje Rahul ke sath project review meeting schedule kar do") is True
    assert is_agent_action("Friday tak GST return file karne ka high priority task add kar do") is True
    assert is_agent_action("Client (client@example.com) ko proposal summary email bhej do") is True
    assert is_agent_action("aaj ka schedule batao") is True
    assert is_agent_action("hello vitya") is False


def test_build_google_calendar_url():
    url = build_google_calendar_url("Project Review", "2026-10-09", "11:00 AM", "Discussion with Rahul")
    assert "calendar.google.com" in url
    assert "Project+Review" in url or "Project%20Review" in url


def test_handle_calendar_action_create():
    mock_db = MagicMock()
    mock_user = MagicMock(id=1, name="TestUser")

    res = handle_calendar_action("Kal subah 11 baje Team Sync meeting schedule karo", mock_db, mock_user)
    assert res["type"] == "calendar_event"
    assert "Team Sync" in res["title"]
    assert "gcal_url" in res
    assert mock_db.add.called
    assert mock_db.commit.called


def test_handle_task_action_create():
    mock_db = MagicMock()
    mock_user = MagicMock(id=1, name="TestUser")

    res = handle_task_action("Friday tak GST return file karne ka high priority task add karo", mock_db, mock_user)
    assert res["type"] == "task_item"
    assert "GST return" in res["title"]
    assert "High Priority" in res["priority"]
    assert mock_db.add.called
    assert mock_db.commit.called


def test_handle_email_action():
    mock_db = MagicMock()
    mock_user = MagicMock(id=1, name="Preet")

    res = handle_email_action("Client (client@example.com) ko proposal email bhej do", mock_db, mock_user)
    assert res["type"] == "email_draft"
    assert res["recipient"] == "client@example.com"
    assert "mailto_url" in res
    assert "mailto:client@example.com" in res["mailto_url"]


def test_handle_daily_agenda():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
    mock_db.query.return_value.filter.return_value.all.return_value = []
    
    class SimpleUser:
        id = 1
        name = "Preet"
        username = "preet"

    res = handle_daily_agenda(mock_db, SimpleUser())
    assert res["type"] == "daily_agenda"
    assert "Today's Overview" in res["content"]
    assert "Scheduled Meetings" in res["content"]
