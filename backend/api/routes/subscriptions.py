from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.database import get_db
from backend.api.models.vitya import RecurringSubscription, User
from backend.api.schemas.vitya import (
    SubscriptionCreate,
    SubscriptionResponse,
    SubscriptionSummaryResponse,
    SubscriptionUpdate,
)
from backend.api.auth import token_required

router = APIRouter()


@router.post("", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
def create_subscription(
    data: SubscriptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    sub = RecurringSubscription(
        name=data.name.strip(),
        amount=data.amount,
        billing_cycle=data.billing_cycle.strip().lower() if data.billing_cycle else "monthly",
        category=data.category.strip() if data.category else "Entertainment",
        next_due_date=data.next_due_date.strip() if data.next_due_date else None,
        auto_renew=data.auto_renew if data.auto_renew is not None else True,
        status="active",
        user_id=current_user.id,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


@router.get("", response_model=List[SubscriptionResponse])
@router.get("/", response_model=List[SubscriptionResponse])
def get_subscriptions(
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    subs = (
        db.query(RecurringSubscription)
        .filter(RecurringSubscription.user_id == current_user.id)
        .order_by(RecurringSubscription.id.desc())
        .all()
    )
    return subs


@router.get("/summary", response_model=SubscriptionSummaryResponse)
def get_subscriptions_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    subs = (
        db.query(RecurringSubscription)
        .filter(
            RecurringSubscription.user_id == current_user.id,
            RecurringSubscription.status == "active"
        )
        .all()
    )

    monthly_total = 0.0
    for s in subs:
        cycle = (s.billing_cycle or "monthly").lower()
        if cycle == "yearly":
            monthly_total += s.amount / 12.0
        elif cycle == "weekly":
            monthly_total += s.amount * 4.33
        else:
            monthly_total += s.amount

    yearly_total = monthly_total * 12.0

    return SubscriptionSummaryResponse(
        total_monthly_committed=round(monthly_total, 2),
        total_yearly_committed=round(yearly_total, 2),
        active_count=len(subs),
        subscriptions=[
            SubscriptionResponse.model_validate(s) for s in subs
        ],
    )


@router.get("/{subscription_id}", response_model=SubscriptionResponse)
def get_single_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    sub = (
        db.query(RecurringSubscription)
        .filter(RecurringSubscription.id == subscription_id, RecurringSubscription.user_id == current_user.id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
    return sub


@router.put("/{subscription_id}", response_model=SubscriptionResponse)
def update_subscription(
    subscription_id: int,
    data: SubscriptionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    sub = (
        db.query(RecurringSubscription)
        .filter(RecurringSubscription.id == subscription_id, RecurringSubscription.user_id == current_user.id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")

    update_dict = data.model_dump(exclude_unset=True)
    for field, val in update_dict.items():
        if val is not None:
            if isinstance(val, str):
                val = val.strip()
            setattr(sub, field, val)

    db.commit()
    db.refresh(sub)
    return sub


@router.delete("/{subscription_id}", status_code=status.HTTP_200_OK)
def delete_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    sub = (
        db.query(RecurringSubscription)
        .filter(RecurringSubscription.id == subscription_id, RecurringSubscription.user_id == current_user.id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")

    db.delete(sub)
    db.commit()
    return {"message": f"Subscription '{sub.name}' deleted successfully"}
