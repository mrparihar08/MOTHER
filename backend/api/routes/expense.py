from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from backend.api.database import get_db
from backend.api.models.vitya import Expense, User
from backend.api.schemas.vitya import ExpenseCreate
from backend.api.auth import token_required


router = APIRouter()


@router.post("/")
def add_expense(
    data: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required)
):

    # date fallback
    date_value = data.date if data.date else datetime.utcnow()

    try:
        exp = Expense(
            amount=data.amount,
            category=data.category,
            description=data.description,
            date=date_value,
            user_id=current_user.id
        )

        db.add(exp)
        db.commit()
        db.refresh(exp)

        return {
            "message": "Expense added successfully",
            "expense_id": exp.id
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Expense creation failed: {str(e)}"
        )