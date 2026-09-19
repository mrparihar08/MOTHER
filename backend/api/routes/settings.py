from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from backend.api.database import get_db
from backend.api.models.vitya import User, UserSettings
from backend.api.schemas.vitya import (
    UserSettingsResponse,
    UserSettingsUpdate,
    ChangePasswordRequest,
    SubscriptionSelectRequest,
)
from backend.api.auth import token_required

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_or_create_settings(user_id: int, db: Session) -> UserSettings:
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not settings:
        settings = UserSettings(
            user_id=user_id,
            theme="dark",
            accent_color="#8b5cf6",
            email_alerts=True,
            security_alerts=True,
            ai_updates=True,
            marketing=False,
            two_factor_enabled=False,
            data_privacy_opt_in=True,
            subscription_plan="Pro User",
            subscription_status="active",
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


# ---------------------------
# GET SETTINGS
# ---------------------------
@router.get("", response_model=UserSettingsResponse)
@router.get("/", response_model=UserSettingsResponse)
def get_user_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    return get_or_create_settings(current_user.id, db)


# ---------------------------
# UPDATE SETTINGS
# ---------------------------
@router.put("", response_model=UserSettingsResponse)
@router.put("/", response_model=UserSettingsResponse)
def update_user_settings(
    update_data: UserSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    settings = get_or_create_settings(current_user.id, db)

    data = update_data.model_dump(exclude_unset=True)
    for field, val in data.items():
        if hasattr(settings, field) and val is not None:
            setattr(settings, field, val)

    db.commit()
    db.refresh(settings)
    return settings


# ---------------------------
# CHANGE PASSWORD
# ---------------------------
@router.post("/change-password")
def change_password(
    req: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    if not pwd_context.verify(req.current_password, current_user.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password",
        )

    if len(req.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 6 characters",
        )

    current_user.password = pwd_context.hash(req.new_password)
    db.commit()
    return {"message": "Password updated successfully"}


# ---------------------------
# SUBSCRIPTION
# ---------------------------
@router.get("/subscription")
def get_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    settings = get_or_create_settings(current_user.id, db)
    return {
        "user_id": current_user.id,
        "plan_name": settings.subscription_plan,
        "status": settings.subscription_status,
        "ai_quota_used": 142,
        "ai_quota_total": 1000 if settings.subscription_plan == "Pro User" else (100 if settings.subscription_plan == "Free Tier" else 10000),
        "storage_used_gb": 1.2,
        "storage_total_gb": 10 if settings.subscription_plan == "Pro User" else (1 if settings.subscription_plan == "Free Tier" else 100),
    }


@router.post("/subscription/select")
def select_subscription(
    req: SubscriptionSelectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    settings = get_or_create_settings(current_user.id, db)
    settings.subscription_plan = req.plan_name.strip()
    settings.subscription_status = "active"
    db.commit()
    db.refresh(settings)
    return {
        "message": f"Successfully activated {settings.subscription_plan} plan!",
        "plan_name": settings.subscription_plan,
        "status": settings.subscription_status,
    }
