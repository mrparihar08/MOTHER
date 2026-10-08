# backend/tests/test_chart_intent.py
"""
Automated test suite for Data Visualization Intent Classification,
Dataset Extraction, Total Validation, and Financial Routing Safety in Vitya AI.
"""

import pytest
from unittest.mock import MagicMock
from sqlalchemy.orm import Session

from backend.chats.chatbot import chatbot_reply
from backend.chats.handlers.chart_handler import (
    handle_chart_request,
    parse_dataset,
    detect_chart_type,
    is_visualization_request,
)
from backend.chats.handlers.transaction_handler import handle_transaction
from backend.chats.utils.intent_router import classify_intent, Intent


class DummyUser:
    id = 1
    name = "TestUser"
    username = "testuser"


@pytest.fixture
def mock_db():
    db = MagicMock(spec=Session)
    db.add = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()
    db.rollback = MagicMock()
    db.query = MagicMock()
    return db


def test_scenario_1_school_percentage_distribution(mock_db):
    """
    Scenario 1: Critical Bug Reproduction & Fix
    Input: "mere school me 40 bachche h 10 ke 50 % or 15 ke 60 or 8 ke 70 or 5 ke 80 or 2 ke 90 % ke bich aaye h ise chart me show karo"
    Requirements:
    - Intent classified as DATA_VISUALIZATION
    - Chart type detected as bar
    - Total students extracted as 40
    - 5 categories extracted: 50%: 10, 60%: 15, 70%: 8, 80%: 5, 90%: 2
    - Sum verified: 10 + 15 + 8 + 5 + 2 == 40
    - MUST NOT create any transaction in database
    """
    user = DummyUser()
    message = "mere school me 40 bachche h 10 ke 50 % or 15 ke 60 or 8 ke 70 or 5 ke 80 or 2 ke 90 % ke bich aaye h ise chart me show karo"

    # 1. Intent check
    intent = classify_intent(message)
    assert intent == Intent.DATA_VISUALIZATION

    # 2. Safety check: transaction handler MUST reject this query
    txn_res = handle_transaction(message, mock_db, user)
    assert txn_res is None
    assert mock_db.add.call_count == 0

    # 3. Chatbot router response
    res = chatbot_reply(message, mock_db, user)
    assert res is not None
    assert res.get("type") in ["bar", "chart"]
    assert res.get("intent") == "DATA_VISUALIZATION"

    content = res.get("content", [])
    assert len(content) == 5

    # Check categories and amounts
    expected = [
        {"category": "50%", "amount": 10.0},
        {"category": "60%", "amount": 15.0},
        {"category": "70%", "amount": 8.0},
        {"category": "80%", "amount": 5.0},
        {"category": "90%", "amount": 2.0},
    ]
    for exp in expected:
        match = next((item for item in content if item["category"] == exp["category"]), None)
        assert match is not None, f"Missing category {exp['category']}"
        assert match["amount"] == exp["amount"], f"Incorrect amount for {exp['category']}"

    # Verify total
    metadata = res.get("metadata", {})
    assert metadata.get("stated_total") == 40
    assert metadata.get("total_sum") == 40.0
    assert metadata.get("dataset_status") == "valid"


def test_scenario_2_explicit_pie_chart(mock_db):
    """
    Scenario 2: Explicit Pie Chart with Categories
    Input: "pie chart banao: boys 25, girls 15"
    Requirements:
    - Intent classified as DATA_VISUALIZATION
    - Chart type detected as pie/donut
    - Categories extracted: Boys: 25, Girls: 15
    - NO transaction added
    """
    user = DummyUser()
    message = "pie chart banao: boys 25, girls 15"

    intent = classify_intent(message)
    assert intent == Intent.DATA_VISUALIZATION

    txn_res = handle_transaction(message, mock_db, user)
    assert txn_res is None
    assert mock_db.add.call_count == 0

    res = chatbot_reply(message, mock_db, user)
    assert res is not None
    assert res.get("type") in ["pie", "donut"]
    content = res.get("content", [])
    assert len(content) == 2
    assert any(item["category"] == "Boys" and item["amount"] == 25.0 for item in content)
    assert any(item["category"] == "Girls" and item["amount"] == 15.0 for item in content)


def test_scenario_3_genuine_expense_transaction(mock_db):
    """
    Scenario 3: Genuine Financial Expense
    Input: "maine ₹500 khane par kharch kiye"
    Requirements:
    - Intent classified as EXPENSE
    - Expense logged under Food category with amount 500
    - Transaction saved in DB
    """
    user = DummyUser()
    message = "maine ₹500 khane par kharch kiye"

    intent = classify_intent(message)
    assert intent == Intent.EXPENSE

    res = handle_transaction(message, mock_db, user)
    assert res is not None
    assert mock_db.add.call_count == 1
    data = res.get("data", {})
    assert data.get("type") == "expense"
    assert data.get("amount") == 500.0
    assert data.get("category") == "Food"


def test_scenario_4_genuine_income_transaction(mock_db):
    """
    Scenario 4: Genuine Financial Income
    Input: "salary 25000 credited"
    Requirements:
    - Intent classified as INCOME
    - Income logged under Salary source with amount 25000
    - Transaction saved in DB
    """
    user = DummyUser()
    message = "salary 25000 credited"

    intent = classify_intent(message)
    assert intent == Intent.INCOME

    res = handle_transaction(message, mock_db, user)
    assert res is not None
    assert mock_db.add.call_count == 1
    data = res.get("data", {})
    assert data.get("type") == "income"
    assert data.get("amount") == 25000.0
    assert data.get("source") == "Salary"


def test_scenario_5_non_financial_text_with_numbers(mock_db):
    """
    Scenario 5: Non-financial text with numbers
    Input: "mere paas 5 kitabein hain"
    Requirements:
    - MUST NOT create any transaction
    """
    user = DummyUser()
    message = "mere paas 5 kitabein hain"

    txn_res = handle_transaction(message, mock_db, user)
    assert txn_res is None
    assert mock_db.add.call_count == 0


def test_scenario_6_custom_subject_marks_chart(mock_db):
    """
    Scenario 6: Custom Subject Marks Graph
    Input: "Maths: 80, Science: 90, English: 70 ka graph banao"
    Requirements:
    - Intent is DATA_VISUALIZATION
    - 3 categories extracted: Maths: 80, Science: 90, English: 70
    - NO transaction created
    """
    user = DummyUser()
    message = "Maths: 80, Science: 90, English: 70 ka graph banao"

    intent = classify_intent(message)
    assert intent == Intent.DATA_VISUALIZATION

    txn_res = handle_transaction(message, mock_db, user)
    assert txn_res is None
    assert mock_db.add.call_count == 0

    res = chatbot_reply(message, mock_db, user)
    assert res is not None
    assert res.get("intent") == "DATA_VISUALIZATION"
    content = res.get("content", [])
    assert len(content) == 3
    assert any(item["category"] == "Maths" and item["amount"] == 80.0 for item in content)
    assert any(item["category"] == "Science" and item["amount"] == 90.0 for item in content)
    assert any(item["category"] == "English" and item["amount"] == 70.0 for item in content)


def test_scenario_7_total_mismatch_detection(mock_db):
    """
    Scenario 7: Total Mismatch Handling
    Input: "Total 50 bachche: 20 pass, 25 fail ka chart dikhao" (Stated total 50, but 20+25=45)
    Requirements:
    - Stated total is 50
    - Extracted items sum is 45
    - Dataset status is mismatch
    - Message contains note informing the user about the discrepancy
    - NO transaction created
    """
    user = DummyUser()
    message = "Total 50 bachche: 20 pass, 25 fail ka chart dikhao"

    intent = classify_intent(message)
    assert intent == Intent.DATA_VISUALIZATION

    txn_res = handle_transaction(message, mock_db, user)
    assert txn_res is None
    assert mock_db.add.call_count == 0

    res = chatbot_reply(message, mock_db, user)
    assert res is not None
    metadata = res.get("metadata", {})
    assert metadata.get("stated_total") == 50
    assert metadata.get("total_sum") == 45.0
    assert metadata.get("dataset_status") == "mismatch"
    assert "total **50**" in res.get("message", "").lower() or "50" in res.get("message", "")
    assert "45" in res.get("message", "")
