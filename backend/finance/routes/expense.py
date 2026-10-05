from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from backend.api.database import get_db
from backend.api.models.vitya import Expense, User
from backend.api.schemas.vitya import (
    ExpenseCreate,
    ExpenseUpdate,
    ExpenseResponse,
)
from backend.api.auth import token_required

router = APIRouter()


def parse_date_value(val):
    if not val:
        return datetime.now(timezone.utc)
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val
    if hasattr(val, "year") and not hasattr(val, "hour"):
        return datetime.combine(val, datetime.min.time()).replace(tzinfo=timezone.utc)
    if isinstance(val, str):
        val_str = val.strip()
        if not val_str:
            return datetime.now(timezone.utc)
        try:
            dt = datetime.fromisoformat(val_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass
        try:
            dt = datetime.strptime(val_str, "%Y-%m-%d")
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc)


# ---------------------------
# CREATE EXPENSE
# ---------------------------
@router.post("/", response_model=ExpenseResponse)
def add_expense(
    data: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    date_value = parse_date_value(data.date)

    expense = Expense(
        amount=data.amount,
        category=data.category,
        description=data.description,
        date=date_value,
        user_id=current_user.id,
    )

    db.add(expense)
    db.commit()
    db.refresh(expense)

    return expense


# ---------------------------
# GET ALL EXPENSES (Current User)
# ---------------------------
@router.get("/", response_model=list[ExpenseResponse])
def get_all_expenses(
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    expenses = (
        db.query(Expense)
        .filter(Expense.user_id == current_user.id)
        .order_by(Expense.date.desc())
        .all()
    )

    return expenses


# ---------------------------
# GET SINGLE EXPENSE
# ---------------------------
@router.get("/{expense_id}", response_model=ExpenseResponse)
def get_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    expense = (
        db.query(Expense)
        .filter(Expense.id == expense_id, Expense.user_id == current_user.id)
        .first()
    )

    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    return expense


# ---------------------------
# UPDATE EXPENSE
# ---------------------------
@router.put("/{expense_id}", response_model=ExpenseResponse)
def update_expense(
    expense_id: int,
    data: ExpenseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    expense = (
        db.query(Expense)
        .filter(Expense.id == expense_id, Expense.user_id == current_user.id)
        .first()
    )

    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    update_data = data.model_dump(exclude_unset=True)

    if "date" in update_data and update_data["date"] is not None:
        update_data["date"] = parse_date_value(update_data["date"])

    for key, value in update_data.items():
        setattr(expense, key, value)

    db.commit()
    db.refresh(expense)

    return expense


# ---------------------------
# DELETE EXPENSE
# ---------------------------
@router.delete("/{expense_id}")
def delete_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    expense = (
        db.query(Expense)
        .filter(Expense.id == expense_id, Expense.user_id == current_user.id)
        .first()
    )

    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    db.delete(expense)
    db.commit()

    return {"message": "Expense deleted successfully"}