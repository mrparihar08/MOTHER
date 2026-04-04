from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
import numpy as np
from sklearn.linear_model import LinearRegression
from datetime import datetime

from backend.api.database import get_db
from backend.api.models.vitya import Expense, Income
from backend.api.auth import token_required

router = APIRouter()


# ================= PREDICTION ================= #
@router.get("/predict/{category}")
def predict_expense(category: str, current_user=Depends(token_required), db: Session = Depends(get_db)):

    expenses = db.query(Expense).filter(
        Expense.user_id == current_user.id,
        Expense.category == category
    ).order_by(Expense.date).all()

    if len(expenses) < 3:
        raise HTTPException(status_code=400, detail="Not enough data")

    amounts = [float(e.amount) for e in expenses]

    X = np.arange(len(amounts)).reshape(-1, 1)
    y = np.array(amounts)

    model = LinearRegression()
    model.fit(X, y)

    prediction = model.predict([[len(amounts)]])[0]

    return {
        "category": category,
        "predicted_next_month_expense": round(float(prediction), 2)
    }


# ================= OVERSPENDING ================= #
@router.get("/overspending/{category}")
def detect_overspending(category: str, current_user=Depends(token_required), db: Session = Depends(get_db)):

    expenses = db.query(Expense).filter(
        Expense.user_id == current_user.id,
        Expense.category == category
    ).order_by(Expense.date).all()

    if len(expenses) < 3:
        raise HTTPException(status_code=400, detail="Not enough data")

    amounts = [float(e.amount) for e in expenses]

    avg = sum(amounts) / len(amounts)
    last = amounts[-1]

    return {
        "average_spending": round(avg, 2),
        "last_spending": round(last, 2),
        "overspending": last > avg * 1.5
    }


# ================= WASTE ANALYSIS ================= #
@router.get("/waste-analysis")
def waste_analysis(current_user=Depends(token_required), db: Session = Depends(get_db)):

    expenses = db.query(
        Expense.category,
        func.sum(Expense.amount).label("total")
    ).filter(
        Expense.user_id == current_user.id
    ).group_by(Expense.category).all()

    if not expenses:
        return []

    totals = [float(total) for _, total in expenses]
    avg = sum(totals) / len(totals)

    result = []
    for category, total in expenses:
        total = float(total)

        status = "normal"
        if total > avg * 1.5:
            status = "high_spending"

        result.append({
            "category": category,
            "total_spent": round(total, 2),
            "status": status
        })

    return result


# ================= BUDGET ================= #
@router.get("/budget-plan")
def budget_plan(current_user=Depends(token_required), db: Session = Depends(get_db)):

    income = db.query(func.sum(Income.amount))\
        .filter(Income.user_id == current_user.id).scalar() or 0

    if income <= 0:
        raise HTTPException(status_code=404, detail="No income data")

    expenses = db.query(
        Expense.category,
        func.sum(Expense.amount).label("total")
    ).filter(
        Expense.user_id == current_user.id
    ).group_by(Expense.category).all()

    if not expenses:
        raise HTTPException(status_code=404, detail="No expense data")

    total_expenses = sum(float(t) for _, t in expenses)

    # smart savings
    savings_rate = 0.1 if income < 20000 else 0.2 if income < 50000 else 0.3

    savings = income * savings_rate
    usable = income - savings

    MIN_PERCENT = 0.05
    plan = []

    for category, amount in expenses:
        amount = float(amount)

        share = amount / total_expenses if total_expenses else 0
        share = max(share, MIN_PERCENT)

        budget = share * usable

        status = "ok"
        if amount > budget:
            status = "overspending"
        elif amount < budget * 0.5:
            status = "underutilized"

        plan.append({
            "category": category,
            "previous_spending": round(amount, 2),
            "suggested_budget": round(budget, 2),
            "status": status
        })

    # normalize
    total_budget = sum(p["suggested_budget"] for p in plan)

    if total_budget:
        factor = usable / total_budget
        for p in plan:
            p["suggested_budget"] = round(p["suggested_budget"] * factor, 2)

    return {
        "summary": {
            "total_income": income,
            "total_expenses": total_expenses,
            "usable_funds": round(usable, 2),
            "suggested_savings": round(savings, 2),
            "savings_rate": savings_rate
        },
        "budget_plan": plan
    }


# ================= ADVISOR ================= #
@router.get("/advisor/{category}")
def financial_advisor(category: str, current_user=Depends(token_required), db: Session = Depends(get_db)):

    expenses = db.query(Expense).filter(
        Expense.user_id == current_user.id,
        Expense.category == category
    ).order_by(Expense.date).all()

    if len(expenses) < 3:
        return {"message": "Not enough data"}

    amounts = [float(e.amount) for e in expenses]

    avg = sum(amounts) / len(amounts)
    last = amounts[-1]

    if last > avg:
        advice = "Spending increasing. Reduce expenses."
    elif last < avg:
        advice = "Good control on spending."
    else:
        advice = "Spending stable."

    return {
        "category": category,
        "average_spending": round(avg, 2),
        "last_expense": round(last, 2),
        "recommended_budget": round(avg * 1.2, 2),
        "advice": advice
    }


# ================= MONTHLY TREND ================= #
@router.get("/monthly-trend")
def monthly_trend(current_user=Depends(token_required), db: Session = Depends(get_db)):

    try:
        data = db.query(
            func.strftime("%Y-%m", Expense.date).label("month"),
            func.sum(Expense.amount).label("amount")
        ).filter(
            Expense.user_id == current_user.id
        ).group_by("month").all()

        if not data:
            return []

        return [
            {"month": m, "amount": float(a or 0)}
            for m, a in data
        ]

    except Exception as e:
        print("MONTHLY TREND ERROR:", e)
        return []

# ================= ANOMALY ================= #
@router.get("/anomaly/{category}")
def anomaly_detection(category: str, current_user=Depends(token_required), db: Session = Depends(get_db)):

    expenses = db.query(Expense).filter(
        Expense.user_id == current_user.id,
        Expense.category == category
    ).all()

    amounts = [float(e.amount) for e in expenses]

    if len(amounts) < 5:
        return {"message": "Not enough data"}

    avg = sum(amounts) / len(amounts)

    anomalies = [
        {"amount": e.amount, "date": e.date}
        for e in expenses if e.amount > avg * 2
    ]

    return {
        "average_expense": round(avg, 2),
        "anomalies": anomalies
    }