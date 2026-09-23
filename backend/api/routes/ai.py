from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from sqlalchemy import extract, func
import numpy as np
from sklearn.linear_model import LinearRegression
from datetime import datetime

from backend.api.database import get_db
from backend.api.models.vitya import Expense, Income, Budget
from backend.api.schemas.vitya import BudgetCreate, BudgetResponse, BudgetAlertStatus
from backend.api.auth import token_required

router = APIRouter()



def _fit_and_predict_linear_model(amounts: list[float]) -> float:
    X = np.arange(len(amounts)).reshape(-1, 1)
    y = np.array(amounts)

    model = LinearRegression()
    model.fit(X, y)

    prediction = model.predict([[len(amounts)]])[0]
    return float(prediction)


# ================= PREDICTION ================= #
@router.get("/predict/{category}")
async def predict_expense(category: str, current_user=Depends(token_required), db: Session = Depends(get_db)):

    expenses = db.query(Expense).filter(
        Expense.user_id == current_user.id,
        Expense.category == category
    ).order_by(Expense.date).all()

    if len(expenses) < 3:
        return {
            "status": "insufficient_data",
            "category": category,
            "predicted_next_month_expense": None,
            "message": "At least 3 expense records are required for trend prediction.",
            "current_count": len(expenses),
        }

    amounts = [float(e.amount) for e in expenses]

    prediction = await run_in_threadpool(_fit_and_predict_linear_model, amounts)

    return {
        "status": "ok",
        "category": category,
        "predicted_next_month_expense": round(prediction, 2),
        "current_count": len(expenses),
    }


# ================= OVERSPENDING ================= #
@router.get("/overspending/{category}")
def detect_overspending(category: str, current_user=Depends(token_required), db: Session = Depends(get_db)):

    expenses = db.query(Expense).filter(
        Expense.user_id == current_user.id,
        Expense.category == category
    ).order_by(Expense.date).all()

    if len(expenses) < 3:
        return {
            "status": "insufficient_data",
            "category": category,
            "average_spending": None,
            "last_spending": None,
            "overspending": False,
            "message": "At least 3 expense records are required for overspending analysis.",
            "current_count": len(expenses),
        }

    amounts = [float(e.amount) for e in expenses]

    avg = sum(amounts) / len(amounts)
    last = amounts[-1]

    return {
        "status": "ok",
        "category": category,
        "average_spending": round(avg, 2),
        "last_spending": round(last, 2),
        "overspending": last > avg * 1.5,
        "current_count": len(expenses),
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
            extract('year', Expense.date).label("year"),
            extract('month', Expense.date).label("month"),
            func.sum(Expense.amount).label("amount")
        ).filter(
            Expense.user_id == current_user.id
        ).group_by(
            extract('year', Expense.date),
            extract('month', Expense.date)
        ).order_by(
            extract('year', Expense.date),
            extract('month', Expense.date)
        ).all()

        if not data:
            return []

        return [
            {"month": f"{int(yr):04d}-{int(mo):02d}", "amount": float(a or 0)}
            for yr, mo, a in data if yr is not None and mo is not None
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


# ================= BUDGET CAP & ALERTS ================= #
@router.post("/budget-cap", response_model=BudgetResponse)
def create_or_update_budget_cap(
    data: BudgetCreate,
    current_user=Depends(token_required),
    db: Session = Depends(get_db),
):
    existing = db.query(Budget).filter(
        Budget.user_id == current_user.id,
        Budget.category == data.category
    ).first()

    if existing:
        existing.monthly_limit = data.monthly_limit
        db.commit()
        db.refresh(existing)
        return existing

    new_budget = Budget(
        category=data.category,
        monthly_limit=data.monthly_limit,
        user_id=current_user.id
    )
    db.add(new_budget)
    db.commit()
    db.refresh(new_budget)
    return new_budget


@router.get("/budget-cap", response_model=list[BudgetResponse])
def get_user_budget_caps(
    current_user=Depends(token_required),
    db: Session = Depends(get_db),
):
    return db.query(Budget).filter(Budget.user_id == current_user.id).all()


@router.get("/budget-alerts", response_model=list[BudgetAlertStatus])
def get_budget_alerts(
    current_user=Depends(token_required),
    db: Session = Depends(get_db),
):
    budgets = db.query(Budget).filter(Budget.user_id == current_user.id).all()
    if not budgets:
        return []

    results = []
    for b in budgets:
        # Sum total spending in category for current user
        total_spend = db.query(func.sum(Expense.amount)).filter(
            Expense.user_id == current_user.id,
            Expense.category == b.category
        ).scalar() or 0.0

        total_spend = float(total_spend)
        pct = (total_spend / b.monthly_limit) * 100.0 if b.monthly_limit > 0 else 0.0

        if pct >= 100.0:
            status = "EXCEEDED"
            message = f"Alert: You have exceeded your monthly limit for {b.category} by ₹{round(total_spend - b.monthly_limit, 2)}!"
        elif pct >= 80.0:
            status = "WARNING"
            message = f"Warning: You have reached {round(pct, 1)}% of your monthly budget for {b.category}."
        else:
            status = "NORMAL"
            message = f"Within budget. {round(pct, 1)}% of limit used for {b.category}."

        results.append(BudgetAlertStatus(
            category=b.category,
            monthly_limit=b.monthly_limit,
            current_spend=round(total_spend, 2),
            percentage_used=round(pct, 2),
            status=status,
            message=message
        ))

    return results