import pytest
from unittest.mock import MagicMock, patch
from backend.chats.services.email_service import EmailDispatcher
from backend.chats.handlers.action_handler import handle_email_action


def test_email_validation():
    dispatcher = EmailDispatcher()
    assert dispatcher.validate_email("test@example.com") is True
    assert dispatcher.validate_email("user.name+tag@company.co.in") is True
    assert dispatcher.validate_email("invalid-email") is False
    assert dispatcher.validate_email("@missinguser.com") is False
    assert dispatcher.validate_email("") is False


def test_email_drafting():
    dispatcher = EmailDispatcher()
    subject, body = dispatcher.draft_email_content(
        topic="Annual Financial Audit Report Submission",
        recipient="auditor@firm.com",
        sender_name="Preet",
    )
    assert subject is not None and len(subject) > 3
    assert body is not None and "Preet" in body


def test_email_dispatch_simulated():
    dispatcher = EmailDispatcher()
    res = dispatcher.dispatch(
        to_email="client@example.com",
        subject="Project Scope",
        body="Hello, please find the scope attached.",
    )
    assert res["success"] is True
    assert res["status"] == "DRAFT_READY"
    assert "mailto:client@example.com" in res["mailto_url"]


@patch("smtplib.SMTP")
def test_email_dispatch_smtp(mock_smtp):
    mock_server = MagicMock()
    mock_smtp.return_value.__enter__.return_value = mock_server

    dispatcher = EmailDispatcher(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        smtp_user="user@gmail.com",
        smtp_password="password123",
    )
    res = dispatcher.dispatch(
        to_email="colleague@example.com",
        subject="Meeting Follow-up",
        body="Here are the notes.",
    )
    assert res["success"] is True
    assert res["status"] == "DELIVERED"
    assert res["provider"] == "SMTP Direct"
    assert mock_server.send_message.called


def test_handle_email_action_integration():
    mock_db = MagicMock()
    mock_user = MagicMock(id=1, name="Preet")

    res = handle_email_action("Client (client@example.com) ko proposal email bhej do", mock_db, mock_user)
    assert res["type"] in ("email_draft", "email_dispatched")
    assert res["recipient"] == "client@example.com"
    assert res["intent"] == "EMAIL_DISPATCH"
