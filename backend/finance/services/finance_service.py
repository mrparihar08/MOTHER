# backend/finance/services/finance_service.py
"""
Finance Domain Service:
Single source of truth for all Financial transactions, Income, Expense,
and Batch operations with integrity validation.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from backend.api.models.vitya import Expense, Income

logger = logging.getLogger("FINANCE-SERVICE")


def create_expense(
    db: Session,
    user_id: int,
    amount: float,
    category: str,
    description: Optional[str] = None,
    date: Optional[datetime] = None,
) -> Expense:
    """Creates and persists a single Expense record."""
    if amount <= 0:
        raise ValueError("Expense amount must be greater than zero")

    txn_date = date or datetime.now(timezone.utc)
    if txn_date.tzinfo is None:
        txn_date = txn_date.replace(tzinfo=timezone.utc)

    expense = Expense(
        amount=round(float(amount), 2),
        category=(category or "Other").strip(),
        description=(description or "").strip() or None,
        date=txn_date,
        user_id=user_id,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


def create_income(
    db: Session,
    user_id: int,
    amount: float,
    source: str,
    date: Optional[datetime] = None,
) -> Income:
    """Creates and persists a single Income record."""
    if amount <= 0:
        raise ValueError("Income amount must be greater than zero")

    txn_date = date or datetime.now(timezone.utc)
    if txn_date.tzinfo is None:
        txn_date = txn_date.replace(tzinfo=timezone.utc)

    income = Income(
        amount=round(float(amount), 2),
        source=(source or "Salary").strip(),
        date=txn_date,
        user_id=user_id,
    )
    db.add(income)
    db.commit()
    db.refresh(income)
    return income


def create_batch_expenses(
    db: Session,
    user_id: int,
    items: List[Dict[str, Any]],
    date: Optional[datetime] = None,
) -> Tuple[List[Expense], float]:
    """Creates and commits multiple expenses in an atomic transaction."""
    if not items:
        return [], 0.0

    txn_date = date or datetime.now(timezone.utc)
    if txn_date.tzinfo is None:
        txn_date = txn_date.replace(tzinfo=timezone.utc)

    expense_records: List[Expense] = []
    total_amount = 0.0

    try:
        for item in items:
            amt = round(float(item["amount"]), 2)
            desc = str(item.get("description", "")).strip()
            cat = str(item.get("category", "Other")).strip()

            expense = Expense(
                amount=amt,
                category=cat,
                description=desc.capitalize() if desc else None,
                date=txn_date,
                user_id=user_id,
            )
            db.add(expense)
            expense_records.append(expense)
            total_amount += amt

        db.commit()
        for r in expense_records:
            db.refresh(r)

        return expense_records, round(total_amount, 2)
    except Exception as exc:
        db.rollback()
        logger.error("Failed to commit batch expenses: %s", exc)
        raise exc
