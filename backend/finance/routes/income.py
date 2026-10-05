from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from backend.api.database import get_db
from backend.api.models.vitya import Income, User
from backend.api.schemas.vitya import (
    IncomeCreate,
    IncomeUpdate,
    IncomeResponse,
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
# CREATE INCOME
# ---------------------------
@router.post("/", response_model=IncomeResponse)
def add_income(
    data: IncomeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    date_value = parse_date_value(data.date)

    income = Income(
        amount=data.amount,
        source=data.source,
        date=date_value,
        user_id=current_user.id,
    )

    db.add(income)
    db.commit()
    db.refresh(income)

    return income


# ---------------------------
# GET ALL INCOME (Current User)
# ---------------------------
@router.get("/", response_model=list[IncomeResponse])
def get_all_income(
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    incomes = (
        db.query(Income)
        .filter(Income.user_id == current_user.id)
        .order_by(Income.date.desc())
        .all()
    )

    return incomes


# ---------------------------
# GET SINGLE INCOME
# ---------------------------
@router.get("/{income_id}", response_model=IncomeResponse)
def get_income(
    income_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    income = (
        db.query(Income)
        .filter(Income.id == income_id, Income.user_id == current_user.id)
        .first()
    )

    if not income:
        raise HTTPException(status_code=404, detail="Income not found")

    return income


# ---------------------------
# UPDATE INCOME
# ---------------------------
@router.put("/{income_id}", response_model=IncomeResponse)
def update_income(
    income_id: int,
    data: IncomeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    income = (
        db.query(Income)
        .filter(Income.id == income_id, Income.user_id == current_user.id)
        .first()
    )

    if not income:
        raise HTTPException(status_code=404, detail="Income not found")

    update_data = data.model_dump(exclude_unset=True)

    if "date" in update_data and update_data["date"] is not None:
        update_data["date"] = parse_date_value(update_data["date"])

    for key, value in update_data.items():
        setattr(income, key, value)

    db.commit()
    db.refresh(income)

    return income


# ---------------------------
# DELETE INCOME
# ---------------------------
@router.delete("/{income_id}")
def delete_income(
    income_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    income = (
        db.query(Income)
        .filter(Income.id == income_id, Income.user_id == current_user.id)
        .first()
    )

    if not income:
        raise HTTPException(status_code=404, detail="Income not found")

    db.delete(income)
    db.commit()

    return {"message": "Income deleted successfully"}