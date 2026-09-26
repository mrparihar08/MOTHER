from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.database import get_db
from backend.api.models.vitya import SavingsGoal, User
from backend.api.schemas.vitya import (
    SavingsDepositRequest,
    SavingsGoalCreate,
    SavingsGoalResponse,
    SavingsGoalUpdate,
)
from backend.api.auth import token_required

router = APIRouter()


def goal_to_response(goal: SavingsGoal) -> SavingsGoalResponse:
    pct = (goal.current_amount / goal.target_amount * 100.0) if goal.target_amount > 0 else 0.0
    return SavingsGoalResponse(
        id=goal.id,
        user_id=goal.user_id,
        title=goal.title,
        target_amount=goal.target_amount,
        current_amount=goal.current_amount,
        percentage_completed=round(min(100.0, pct), 2),
        category=goal.category,
        target_date=goal.target_date,
        is_completed=goal.is_completed or (goal.current_amount >= goal.target_amount),
        created_at=goal.created_at,
        updated_at=goal.updated_at,
    )


@router.post("", response_model=SavingsGoalResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=SavingsGoalResponse, status_code=status.HTTP_201_CREATED)
def create_savings_goal(
    data: SavingsGoalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    goal = SavingsGoal(
        title=data.title.strip(),
        target_amount=data.target_amount,
        current_amount=data.current_amount or 0.0,
        category=data.category.strip() if data.category else None,
        target_date=data.target_date.strip() if data.target_date else None,
        is_completed=(data.current_amount or 0.0) >= data.target_amount,
        user_id=current_user.id,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal_to_response(goal)


@router.get("", response_model=List[SavingsGoalResponse])
@router.get("/", response_model=List[SavingsGoalResponse])
def get_savings_goals(
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    goals = (
        db.query(SavingsGoal)
        .filter(SavingsGoal.user_id == current_user.id)
        .order_by(SavingsGoal.id.desc())
        .all()
    )
    return [goal_to_response(g) for g in goals]


@router.get("/{goal_id}", response_model=SavingsGoalResponse)
def get_single_savings_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    goal = (
        db.query(SavingsGoal)
        .filter(SavingsGoal.id == goal_id, SavingsGoal.user_id == current_user.id)
        .first()
    )
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Savings goal not found")
    return goal_to_response(goal)


@router.put("/{goal_id}", response_model=SavingsGoalResponse)
def update_savings_goal(
    goal_id: int,
    data: SavingsGoalUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    goal = (
        db.query(SavingsGoal)
        .filter(SavingsGoal.id == goal_id, SavingsGoal.user_id == current_user.id)
        .first()
    )
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Savings goal not found")

    update_dict = data.model_dump(exclude_unset=True)
    for field, val in update_dict.items():
        if val is not None:
            if isinstance(val, str):
                val = val.strip()
            setattr(goal, field, val)

    if goal.current_amount >= goal.target_amount:
        goal.is_completed = True

    db.commit()
    db.refresh(goal)
    return goal_to_response(goal)


@router.delete("/{goal_id}", status_code=status.HTTP_200_OK)
def delete_savings_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    goal = (
        db.query(SavingsGoal)
        .filter(SavingsGoal.id == goal_id, SavingsGoal.user_id == current_user.id)
        .first()
    )
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Savings goal not found")

    db.delete(goal)
    db.commit()
    return {"message": f"Savings goal '{goal.title}' deleted successfully"}


@router.post("/{goal_id}/deposit", response_model=SavingsGoalResponse)
def deposit_to_savings_goal(
    goal_id: int,
    data: SavingsDepositRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    goal = (
        db.query(SavingsGoal)
        .filter(SavingsGoal.id == goal_id, SavingsGoal.user_id == current_user.id)
        .first()
    )
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Savings goal not found")

    goal.current_amount += data.amount
    if goal.current_amount >= goal.target_amount:
        goal.is_completed = True

    db.commit()
    db.refresh(goal)
    return goal_to_response(goal)
