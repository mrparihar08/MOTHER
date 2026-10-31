"""
Finance Service API Routes.
Enforces user isolation, decimal calculations, and audit logging.
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Header
from pydantic import ConfigDict, BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from services.finance_service.database import get_db
from services.finance_service.models import (
    Income,
    Expense,
    Budget,
    SavingsGoal,
    RecurringSubscription,
    FinancialAuditLog,
)
from shared.security.jwt_validator import get_current_user
from shared.security.models import AuthenticatedUser

router = APIRouter()


# Schemas
class IncomeCreate(BaseModel):
    amount: Decimal = Field(..., gt=0)
    source: str = Field(..., min_length=1)
    date: Optional[datetime] = None


class IncomeOut(BaseModel):
    id: int
    amount: float
    source: str
    date: datetime

    model_config = ConfigDict(from_attributes=True)


class ExpenseCreate(BaseModel):
    amount: Decimal = Field(..., gt=0)
    category: str = Field(..., min_length=1)
    description: Optional[str] = None
    date: Optional[datetime] = None


class ExpenseOut(BaseModel):
    id: int
    amount: float
    category: str
    description: Optional[str]
    date: datetime

    model_config = ConfigDict(from_attributes=True)


class BudgetCreate(BaseModel):
    category: str
    monthly_limit: Decimal = Field(..., gt=0)


class BudgetOut(BaseModel):
    id: int
    category: str
    monthly_limit: float

    model_config = ConfigDict(from_attributes=True)


class InternalTransactionRequest(BaseModel):
    user_id: int
    transaction_type: str = Field(..., pattern="^(expense|income)$")
    amount: Decimal = Field(..., gt=0)
    category_or_source: str
    description: Optional[str] = None
    idempotency_key: Optional[str] = None


# Endpoints
@router.get("/incomes", response_model=List[IncomeOut])
def get_incomes(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    incomes = db.query(Income).filter(Income.user_id == current_user.user_id).all()
    return incomes


@router.post("/incomes", response_model=IncomeOut, status_code=status.HTTP_201_CREATED)
def create_income(
    income_in: IncomeCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    inc = Income(
        amount=income_in.amount,
        source=income_in.source,
        date=income_in.date or datetime.utcnow(),
        user_id=current_user.user_id,
    )
    db.add(inc)
    db.commit()
    db.refresh(inc)

    # Audit log
    audit = FinancialAuditLog(
        user_id=current_user.user_id,
        action="CREATE_INCOME",
        resource_type="income",
        resource_id=inc.id,
        amount=income_in.amount,
        details=f"Income from {inc.source}",
    )
    db.add(audit)
    db.commit()

    return inc


@router.get("/expenses", response_model=List[ExpenseOut])
def get_expenses(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    expenses = db.query(Expense).filter(Expense.user_id == current_user.user_id).all()
    return expenses


@router.post("/expenses", response_model=ExpenseOut, status_code=status.HTTP_201_CREATED)
def create_expense(
    exp_in: ExpenseCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exp = Expense(
        amount=exp_in.amount,
        category=exp_in.category,
        description=exp_in.description,
        date=exp_in.date or datetime.utcnow(),
        user_id=current_user.user_id,
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)

    # Audit log
    audit = FinancialAuditLog(
        user_id=current_user.user_id,
        action="CREATE_EXPENSE",
        resource_type="expense",
        resource_id=exp.id,
        amount=exp_in.amount,
        details=f"Expense for {exp.category}: {exp.description or ''}",
    )
    db.add(audit)
    db.commit()

    return exp


@router.delete("/expenses/{expense_id}")
def delete_expense(
    expense_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exp = db.query(Expense).filter(
        Expense.id == expense_id,
        Expense.user_id == current_user.user_id,
    ).first()
    if not exp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")

    db.delete(exp)
    db.commit()
    return {"message": "Expense deleted successfully"}


@router.get("/budgets", response_model=List[BudgetOut])
def get_budgets(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(Budget).filter(Budget.user_id == current_user.user_id).all()


@router.post("/budgets", response_model=BudgetOut, status_code=status.HTTP_201_CREATED)
def create_budget(
    b_in: BudgetCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    budget = Budget(
        category=b_in.category,
        monthly_limit=b_in.monthly_limit,
        user_id=current_user.user_id,
    )
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return budget


@router.get("/summary")
def get_financial_summary(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    total_income = (
        db.query(func.coalesce(func.sum(Income.amount), 0))
        .filter(Income.user_id == current_user.user_id)
        .scalar()
    )
    total_expense = (
        db.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(Expense.user_id == current_user.user_id)
        .scalar()
    )

    balance = float(total_income) - float(total_expense)
    savings_rate = (
        (balance / float(total_income) * 100) if float(total_income) > 0 else 0.0
    )

    return {
        "user_id": current_user.user_id,
        "total_income": float(total_income),
        "total_expense": float(total_expense),
        "net_balance": balance,
        "savings_rate_pct": round(savings_rate, 2),
    }


@router.get("/health-score")
def get_health_score(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    total_income = float(
        db.query(func.coalesce(func.sum(Income.amount), 0))
        .filter(Income.user_id == current_user.user_id)
        .scalar()
    )
    total_expense = float(
        db.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(Expense.user_id == current_user.user_id)
        .scalar()
    )

    if total_income == 0:
        score = 50.0
        feedback = "No income recorded yet. Add your income sources to get an accurate score."
    else:
        burn_ratio = total_expense / total_income
        if burn_ratio <= 0.5:
            score = 90.0
            feedback = "Excellent! You are saving at least 50% of your earnings."
        elif burn_ratio <= 0.8:
            score = 75.0
            feedback = "Good. Your spending is within healthy boundaries."
        else:
            score = 45.0
            feedback = "Caution: Your expenditures exceed 80% of your income."

    return {
        "health_score": score,
        "status": "Healthy" if score >= 70 else "Needs Attention",
        "feedback": feedback,
    }


@router.post("/internal/transaction")
def execute_internal_transaction(
    payload: InternalTransactionRequest,
    db: Session = Depends(get_db),
):
    """
    Internal Service API: Allows Chat Service to record transactions with idempotency protection.
    """
    if payload.idempotency_key:
        existing = (
            db.query(FinancialAuditLog)
            .filter(FinancialAuditLog.idempotency_key == payload.idempotency_key)
            .first()
        )
        if existing:
            return {
                "status": "already_processed",
                "message": "Transaction already executed under this idempotency key.",
                "resource_id": existing.resource_id,
            }

    if payload.transaction_type == "expense":
        exp = Expense(
            amount=payload.amount,
            category=payload.category_or_source,
            description=payload.description or "Logged via AI Chat Assistant",
            user_id=payload.user_id,
        )
        db.add(exp)
        db.commit()
        db.refresh(exp)
        res_id = exp.id
    else:
        inc = Income(
            amount=payload.amount,
            source=payload.category_or_source,
            user_id=payload.user_id,
        )
        db.add(inc)
        db.commit()
        db.refresh(inc)
        res_id = inc.id

    # Record audit log
    audit = FinancialAuditLog(
        user_id=payload.user_id,
        action=f"INTERNAL_{payload.transaction_type.upper()}",
        resource_type=payload.transaction_type,
        resource_id=res_id,
        amount=payload.amount,
        details=payload.description,
        idempotency_key=payload.idempotency_key,
    )
    db.add(audit)
    db.commit()

    return {
        "status": "success",
        "transaction_type": payload.transaction_type,
        "resource_id": res_id,
        "amount": float(payload.amount),
        "category_or_source": payload.category_or_source,
    }
