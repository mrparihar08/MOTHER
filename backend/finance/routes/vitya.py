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


# =========================================================================
# MONTE CARLO INVESTMENT & RETIREMENT SIMULATOR
# =========================================================================

from pydantic import BaseModel, Field

class MonteCarloRequest(BaseModel):
    current_portfolio: float = Field(500000.0, description="Current investable net worth / portfolio")
    monthly_savings: float = Field(35000.0, description="Monthly amount added to investments")
    monthly_expenses: float = Field(40000.0, description="Current monthly living expenses")
    target_corpus: Optional[float] = Field(None, description="Target retirement corpus (defaults to 25x annual expenses)")
    expected_return: float = Field(0.11, description="Expected annual return rate (e.g. 0.11 for 11%)")
    volatility: float = Field(0.15, description="Annual market standard deviation (e.g. 0.15 for 15%)")
    inflation: float = Field(0.05, description="Annual inflation rate (e.g. 0.05 for 5%)")
    years: int = Field(25, ge=5, le=50, description="Years to simulate")
    simulations: int = Field(1000, ge=100, le=5000, description="Number of Monte Carlo paths")


@router.post("/monte-carlo-simulation")
def simulate_monte_carlo(req: MonteCarloRequest):
    """
    High-Performance Monte Carlo Investment & Retirement Simulator:
    Simulates 1,000 geometric Brownian motion market paths based on the user's
    savings rate, projecting 10th (bear), 50th (median), and 90th (bull) percentiles,
    probability of retirement success, timeline to financial independence, and emergency fund runway.
    """
    try:
        import numpy as np

        num_sims = req.simulations
        years = req.years
        w0 = max(1000.0, float(req.current_portfolio))
        annual_savings = float(req.monthly_savings) * 12.0
        monthly_exp = max(5000.0, float(req.monthly_expenses))
        annual_exp = monthly_exp * 12.0

        # Standard 4% rule / 25x Annual Expenses target
        target_corpus = float(req.target_corpus) if req.target_corpus and req.target_corpus > 0 else (annual_exp * 25.0)

        mu = float(req.expected_return)
        sigma = float(req.volatility)
        infl = float(req.inflation)
        real_mu = ((1.0 + mu) / (1.0 + infl)) - 1.0

        # Vectorized Monte Carlo generation
        # matrix of size (num_sims, years)
        random_returns = np.random.normal(real_mu, sigma, size=(num_sims, years))

        # Paths array: shape (num_sims, years + 1)
        paths = np.zeros((num_sims, years + 1))
        paths[:, 0] = w0

        for t in range(years):
            # Compound prior wealth with year's return + add annual savings
            paths[:, t + 1] = (paths[:, t] + annual_savings) * np.maximum(0.1, 1.0 + random_returns[:, t])

        # Compute Percentiles across each year
        years_range = list(range(years + 1))
        p10 = np.percentile(paths, 10, axis=0)
        p25 = np.percentile(paths, 25, axis=0)
        p50 = np.percentile(paths, 50, axis=0)
        p75 = np.percentile(paths, 75, axis=0)
        p90 = np.percentile(paths, 90, axis=0)

        chart_data = []
        current_year = datetime.now().year
        for idx, yr in enumerate(years_range):
            chart_data.append({
                "year": current_year + yr,
                "timelineYear": f"Yr {yr}",
                "bear10": round(float(p10[idx]), 2),
                "lower25": round(float(p25[idx]), 2),
                "median50": round(float(p50[idx]), 2),
                "upper75": round(float(p75[idx]), 2),
                "bull90": round(float(p90[idx]), 2),
                "targetCorpus": round(target_corpus, 2),
            })

        # Probability of achieving or exceeding target corpus at horizon
        final_wealths = paths[:, -1]
        success_count = np.sum(final_wealths >= target_corpus)
        success_probability = round(float(success_count / num_sims) * 100.0, 1)

        # Projected year when median wealth hits target
        retirement_years_needed = None
        for yr, val in enumerate(p50):
            if val >= target_corpus:
                retirement_years_needed = yr
                break

        projected_retirement_year = (current_year + retirement_years_needed) if retirement_years_needed is not None else None

        # Emergency Fund Runway Calculation (Months of survival if income ceases)
        emergency_fund_runway_months = round(float(w0 / monthly_exp), 1)

        # Safety Health Assessment
        if emergency_fund_runway_months >= 12:
            runway_status = "Fortress (12+ Months Reserve)"
            runway_badge = "success"
        elif emergency_fund_runway_months >= 6:
            runway_status = "Healthy Buffer (6-12 Months)"
            runway_badge = "success"
        elif emergency_fund_runway_months >= 3:
            runway_status = "Adequate (3-6 Months)"
            runway_badge = "warning"
        else:
            runway_status = "Critical Alert (< 3 Months Reserve)"
            runway_badge = "danger"

        return {
            "success": True,
            "target_corpus": round(target_corpus, 2),
            "current_portfolio": round(w0, 2),
            "monthly_savings": round(req.monthly_savings, 2),
            "monthly_expenses": round(monthly_exp, 2),
            "success_probability_pct": success_probability,
            "projected_retirement_year": projected_retirement_year,
            "years_to_financial_freedom": retirement_years_needed,
            "emergency_fund_runway_months": emergency_fund_runway_months,
            "runway_status": runway_status,
            "runway_badge": runway_badge,
            "median_final_wealth": round(float(p50[-1]), 2),
            "bear_final_wealth": round(float(p10[-1]), 2),
            "bull_final_wealth": round(float(p90[-1]), 2),
            "chart_data": chart_data,
        }
    except Exception as e:
        logger.exception("Error in simulate_monte_carlo: %s", e)
        raise HTTPException(status_code=500, detail=f"Simulation error: {str(e)}")