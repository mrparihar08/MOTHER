# backend/chats/services/finance_client.py
"""
Decoupled Finance Client & Adapter for MOTHER Chatbot.
Isolates Chat from direct Finance ORM manipulation and analysis routes.
Supports in-process service execution with circuit breaker,
as well as external HTTP microservice calls via FINANCE_SERVICE_URL.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import requests

logger = logging.getLogger("FINANCE-CLIENT")
# Optional microservice URL (when Finance runs as an independent microservice)
FINANCE_SERVICE_URL = os.getenv("FINANCE_SERVICE_URL", "").rstrip("/")


class FinanceClient:
    """Client interface for recording and querying financial data from chat interactions."""

    @staticmethod
    def record_expense(
        db: Any,
        user_id: int,
        amount: float,
        category: str,
        description: Optional[str] = None,
        date: Optional[datetime] = None,
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record an expense record through the decoupled finance layer."""
        if FINANCE_SERVICE_URL and token:
            try:
                headers = {"Authorization": f"Bearer {token}"}
                payload = {
                    "amount": amount,
                    "category": category,
                    "description": description,
                    "date": (date or datetime.now(timezone.utc)).isoformat(),
                }
                resp = requests.post(f"{FINANCE_SERVICE_URL}/api/expense/", json=payload, headers=headers, timeout=5)
                if resp.status_code in (200, 201):
                    return resp.json()
            except Exception as exc:
                logger.warning("External finance microservice call failed: %s", exc)

        # In-process decoupled service delegation
        from backend.finance.services.finance_service import create_expense
        rec = create_expense(
            db=db,
            user_id=user_id,
            amount=amount,
            category=category,
            description=description,
            date=date,
        )
        return {
            "id": rec.id,
            "type": "expense",
            "amount": rec.amount,
            "category": rec.category,
            "description": rec.description,
            "date": rec.date.isoformat() if hasattr(rec.date, "isoformat") else str(rec.date),
        }

    @staticmethod
    def record_income(
        db: Any,
        user_id: int,
        amount: float,
        source: str,
        date: Optional[datetime] = None,
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record an income record through the decoupled finance layer."""
        if FINANCE_SERVICE_URL and token:
            try:
                headers = {"Authorization": f"Bearer {token}"}
                payload = {
                    "amount": amount,
                    "source": source,
                    "date": (date or datetime.now(timezone.utc)).isoformat(),
                }
                resp = requests.post(f"{FINANCE_SERVICE_URL}/api/income/", json=payload, headers=headers, timeout=5)
                if resp.status_code in (200, 201):
                    return resp.json()
            except Exception as exc:
                logger.warning("External finance microservice call failed: %s", exc)

        from backend.finance.services.finance_service import create_income
        rec = create_income(
            db=db,
            user_id=user_id,
            amount=amount,
            source=source,
            date=date,
        )
        return {
            "id": rec.id,
            "type": "income",
            "amount": rec.amount,
            "source": rec.source,
            "date": rec.date.isoformat() if hasattr(rec.date, "isoformat") else str(rec.date),
        }

    @staticmethod
    def record_batch_expenses(
        db: Any,
        user_id: int,
        items: List[Dict[str, Any]],
        date: Optional[datetime] = None,
    ) -> Tuple[List[Dict[str, Any]], float]:
        """Record multiple expenses atomically via the finance service layer."""
        from backend.finance.services.finance_service import create_batch_expenses
        records, total_amount = create_batch_expenses(
            db=db,
            user_id=user_id,
            items=items,
            date=date,
        )
        formatted_items = [
            {
                "id": r.id,
                "type": "expense",
                "amount": r.amount,
                "category": r.category,
                "description": r.description,
                "date": r.date.isoformat() if hasattr(r.date, "isoformat") else str(r.date),
            }
            for r in records
        ]
        return formatted_items, total_amount

    @staticmethod
    def get_budget_plan(current_user: Any, db: Any) -> Dict[str, Any]:
        """Safely fetch budget plan with circuit breaker."""
        try:
            from backend.finance.analysis.analyse import budget_plan
            return budget_plan(current_user=current_user, db=db)
        except Exception as exc:
            logger.error("Error retrieving budget plan: %s", exc)
            return {"budget_plan": [], "error": str(exc)}

    @staticmethod
    def get_monthly_trend(current_user: Any, db: Any) -> Dict[str, Any]:
        """Safely fetch monthly spending trend with circuit breaker."""
        try:
            from backend.finance.analysis.analyse import monthly_trend
            return monthly_trend(current_user=current_user, db=db)
        except Exception as exc:
            logger.error("Error retrieving monthly trend: %s", exc)
            return {"trend": [], "error": str(exc)}

    @staticmethod
    def export_csv(report_type: str, current_user: Any, db: Any = None):
        """Safely export financial CSV stream."""
        from backend.finance.routes.vitya import download_expenses_csv, download_incomes_csv
        if report_type == "income":
            return download_incomes_csv(current_user=current_user, db=db)
        return download_expenses_csv(current_user=current_user, db=db)


finance_client = FinanceClient()
