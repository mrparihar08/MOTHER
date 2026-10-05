from fastapi import APIRouter, Response, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from backend.api.database import get_db
from backend.api.models.vitya import Expense, Income, User
from sqlalchemy import desc, extract, func

from backend.api.auth import AuthenticatedUser, token_required
import io
import base64
import csv
import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import os
from dotenv import load_dotenv

import logging

load_dotenv()

matplotlib.use("Agg")

logger = logging.getLogger(__name__)
router = APIRouter()

ML_API_BASE = os.environ.get("ML_API_BASE")
ML_REQUEST_TIMEOUT = int(os.environ.get("ML_REQUEST_TIMEOUT", "15"))

# -------------------------------
# CSV EXPORT
# -------------------------------
@router.get("/export/csv")
def download_financial_csv(
    type: str = "expenses",
    current_user: AuthenticatedUser = Depends(token_required),
    db: Session = Depends(get_db)
):
    if not isinstance(db, Session):
        from backend.api.database import SessionLocal
        db = SessionLocal()
        close_db = True
    else:
        close_db = False

    try:
        output = io.StringIO()
        writer = csv.writer(output)

        if type == "expenses":
            writer.writerow(["ID", "Amount", "Category", "Description", "Date"])
            expenses = db.query(Expense).filter(Expense.user_id == current_user.id).all()
            for e in expenses:
                writer.writerow([e.id, float(e.amount), e.category, e.description or "", e.date.strftime("%Y-%m-%d") if e.date else ""])
            filename = "expenses.csv"
        else:
            writer.writerow(["ID", "Amount", "Source", "Date"])
            incomes = db.query(Income).filter(Income.user_id == current_user.id).all()
            for i in incomes:
                writer.writerow([i.id, float(i.amount), i.source, i.date.strftime("%Y-%m-%d") if i.date else ""])
            filename = "incomes.csv"

        output.seek(0)
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    finally:
        if close_db:
            db.close()

@router.get("/csv/expenses")
def download_expenses_csv(
    current_user: AuthenticatedUser = Depends(token_required),
    db: Session = Depends(get_db)
):
    if not isinstance(db, Session):
        from backend.api.database import SessionLocal
        db = SessionLocal()
        close_db = True
    else:
        close_db = False

    try:
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(["ID", "Amount", "Category", "Description", "Date"])

        expenses = db.query(Expense).filter(Expense.user_id == current_user.id).all()
        for e in expenses:
            writer.writerow([
                e.id,
                float(e.amount),
                e.category,
                e.description or "",
                e.date.strftime("%Y-%m-%d") if e.date else ""
            ])

        output.seek(0)

        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=expenses.csv"
            }
        )
    finally:
        if close_db:
            db.close()

@router.get("/csv/incomes")
def download_incomes_csv(
    current_user: AuthenticatedUser = Depends(token_required),
    db: Session = Depends(get_db)
):
    if not isinstance(db, Session):
        from backend.api.database import SessionLocal
        db = SessionLocal()
        close_db = True
    else:
        close_db = False

    try:
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(["ID", "Amount", "Source", "Date"])

        incomes = db.query(Income).filter(Income.user_id == current_user.id).all()
        for i in incomes:
            writer.writerow([
                i.id,
                float(i.amount),
                i.source,
                i.date.strftime("%Y-%m-%d") if i.date else ""
            ])

        output.seek(0)

        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=incomes.csv"
            }
        )
    finally:
        if close_db:
            db.close()

# -------------------------------
# EXPENSE BAR CHART DATA
# -------------------------------
@router.get("/expenses_chart")
def get_expenses_chart(
    current_user: AuthenticatedUser = Depends(token_required),
    db: Session = Depends(get_db)
):
    try:
        data = db.query(
            Expense.category,
            func.sum(Expense.amount).label("amount")
        ).filter(
            Expense.user_id == current_user.id
        ).group_by(Expense.category).all()

        return [
            {"category": cat, "amount": float(amount)}
            for cat, amount in data
        ]

    except Exception as e:
        logger.exception("Error in get_expenses_chart: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# -------------------------------
# FINANCIAL OVERVIEW
# -------------------------------
@router.get("/financial_overview")
def get_financial_overview(
    current_user: AuthenticatedUser = Depends(token_required),
    db: Session = Depends(get_db)
):
    try:
        total_income = db.query(func.sum(Income.amount)).filter(
            Income.user_id == current_user.id
        ).scalar() or 0

        total_expenses = db.query(func.sum(Expense.amount)).filter(
            Expense.user_id == current_user.id
        ).scalar() or 0

        distribution_data = db.query(
            Expense.category,
            func.sum(Expense.amount)
        ).filter(
            Expense.user_id == current_user.id
        ).group_by(Expense.category).all()

        distribution = {
            cat: float(amount)
            for cat, amount in distribution_data
        }

        return {
            "total_income": float(total_income),
            "total_expenses": float(total_expenses),
            "available_balance": float(total_income) - float(total_expenses),
            "expense_distribution": distribution
        }

    except Exception as e:
        logger.exception("Error in get_financial_overview: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# -------------------------------
# TREND GRAPH
# -------------------------------
@router.get("/expense_income_trend")
def get_expense_income_trend(
    current_user: AuthenticatedUser = Depends(token_required),
    db: Session = Depends(get_db)
):
    try:
        income = db.query(
            extract('year', Income.date).label("year"),
            extract('month', Income.date).label("month"),
            func.sum(Income.amount).label("total")
        ).filter(
            Income.user_id == current_user.id
        ).group_by(
            extract('year', Income.date),
            extract('month', Income.date)
        ).order_by(
            extract('year', Income.date),
            extract('month', Income.date)
        ).all()

        expense = db.query(
            extract('year', Expense.date).label("year"),
            extract('month', Expense.date).label("month"),
            func.sum(Expense.amount).label("total")
        ).filter(
            Expense.user_id == current_user.id
        ).group_by(
            extract('year', Expense.date),
            extract('month', Expense.date)
        ).order_by(
            extract('year', Expense.date),
            extract('month', Expense.date)
        ).all()

        return {
            "income": [
                {"month": f"{int(yr):04d}-{int(mo):02d}-01", "amount": float(a or 0)}
                for yr, mo, a in income if yr is not None and mo is not None
            ],
            "expense": [
                {"month": f"{int(yr):04d}-{int(mo):02d}-01", "amount": float(a or 0)}
                for yr, mo, a in expense if yr is not None and mo is not None
            ]
        }

    except Exception as e:
        logger.exception("Error in get_expense_income_trend: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
    
@router.get("/graph")
def get_expense_graph(
    current_user: AuthenticatedUser = Depends(token_required),
    db: Session = Depends(get_db)
):
    try:
        data = db.query(
            Expense.category,
            func.sum(Expense.amount).label("amount")
        ).filter(
            Expense.user_id == current_user.id
        ).group_by(Expense.category).all()

        chart_data = [
            {"category": cat, "amount": float(amount)}
            for cat, amount in data
        ]

        return chart_data

    except Exception as e:
        logger.exception("Error in get_expense_graph: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
    
@router.get("/transactions/recent")
def get_recent_transactions(
    current_user: AuthenticatedUser = Depends(token_required),
    db: Session = Depends(get_db),
):
    try:
        recent_expenses = (
            db.query(Expense)
            .filter(Expense.user_id == current_user.id)
            .order_by(desc(Expense.date))
            .limit(10)
            .all()
        )

        recent_incomes = (
            db.query(Income)
            .filter(Income.user_id == current_user.id)
            .order_by(desc(Income.date))
            .limit(10)
            .all()
        )

        items = []
        for e in recent_expenses:
            date_str = e.date.isoformat() if hasattr(e.date, "isoformat") else str(e.date)
            items.append({
                "id": e.id,
                "_id": e.id,
                "type": "expense",
                "amount": float(e.amount),
                "date": date_str,
                "category": e.category,
                "description": e.description
            })

        for i in recent_incomes:
            date_str = i.date.isoformat() if hasattr(i.date, "isoformat") else str(i.date)
            items.append({
                "id": i.id,
                "_id": i.id,
                "type": "income",
                "amount": float(i.amount),
                "date": date_str,
                "category": i.source
            })

        items.sort(key=lambda x: x["date"], reverse=True)
        return items[:10]

    except Exception as e:
        logger.exception("Error in get_recent_transactions: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")