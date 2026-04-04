from fastapi import APIRouter, Response, Depends,HTTPException
from sqlalchemy.orm import Session
from backend.api.database import get_db
from backend.api.models.vitya import Expense, Income, User
from sqlalchemy import desc, func

from backend.api.auth import token_required
import io
import base64
import csv
import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv()

matplotlib.use("Agg")

router = APIRouter()

ML_API_BASE = os.environ.get("ML_API_BASE")
ML_REQUEST_TIMEOUT = int(os.environ.get("ML_REQUEST_TIMEOUT", "15"))

# -------------------------------
# CSV EXPORT
# -------------------------------
from fastapi.responses import Response

@router.get("/export/csv")
def download_financial_csv(
    type: str = "expenses",
    current_user: User = Depends(token_required)
):
    output = io.StringIO()
    writer = csv.writer(output)

    if type == "expenses":
        writer.writerow(["ID", "Amount", "Category", "Description", "Date"])
        for e in current_user.expenses:
            writer.writerow([e.id, float(e.amount), e.category, e.description or "", e.date.strftime("%Y-%m-%d") if e.date else ""])
        filename = "expenses.csv"
    else:
        writer.writerow(["ID", "Amount", "Source", "Date"])
        for i in current_user.incomes:
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

@router.get("/csv")
def download_expenses_csv(
    current_user: User = Depends(token_required)
):
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["ID", "Amount", "Category", "Description", "Date"])

    for e in current_user.expenses:
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
@router.get("/csv")
def download_incomes_csv(
    current_user: User = Depends(token_required)
):
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["ID", "Amount", "Source", "Date"])

    for i in current_user.incomes:
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
# -------------------------------
# EXPENSE BAR CHART DATA
# -------------------------------
@router.get("/expenses_chart")
def get_expenses_chart(
    current_user: User = Depends(token_required),
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
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------
# FINANCIAL OVERVIEW
# -------------------------------
@router.get("/financial_overview")
def get_financial_overview(
    current_user: User = Depends(token_required),
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
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------
# TREND GRAPH
# -------------------------------
@router.get("/expense_income_trend")
def get_expense_income_trend(
    current_user: User = Depends(token_required),
    db: Session = Depends(get_db)
):
    try:
        income = db.query(
            func.strftime('%Y-%m', Income.date).label("month"),
            func.sum(Income.amount).label("total")
        ).filter(
            Income.user_id == current_user.id
        ).group_by("month").all()

        expense = db.query(
            func.strftime('%Y-%m', Expense.date).label("month"),
            func.sum(Expense.amount).label("total")
        ).filter(
            Expense.user_id == current_user.id
        ).group_by("month").all()

        return {
            "income": [
                {"month": m + "-01", "amount": float(a)}
                for m, a in income
            ],
            "expense": [
                {"month": m + "-01", "amount": float(a)}
                for m, a in expense
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/graph")
def get_expense_graph(
    current_user: User = Depends(token_required),
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
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/transactions/recent")
def get_recent_transactions(
    current_user: User = Depends(token_required),
):
        items = []

        # Format expenses
        for e in current_user.expenses:
            items.append({
                "_id": e.id,
                "type": "expense",
                "amount": float(e.amount),
                "date": e.date.isoformat(),
                "category": e.category,
                "description": e.description
            })

        # Format incomes
        for i in current_user.incomes:
            items.append({
                "_id": i.id,
                "type": "income",
                "amount": float(i.amount),
                "date": i.date.isoformat(),
                "category": i.source
            })

        # Sort combined data (latest first)
        items.sort(key=lambda x: x["date"], reverse=True)

        return items[:10]

    