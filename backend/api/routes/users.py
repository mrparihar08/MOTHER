from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.api.auth import (
    ALGORITHM,
    SECRET_KEY,
    create_reset_token,
    token_required,
    verify_reset_token,
)
from backend.api.database import get_db
from backend.api.models.vitya import User
from backend.api.schemas.vitya import (
    ForgotPasswordRequest,
    Login,
    Register,
    ResetPasswordRequest,
    UserUpdate,
)

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(user_id: int):
    payload = {
        "user_id": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=48),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# -------------------------------
# PROFILE
# -------------------------------
@router.get("/profile")
def get_profile(current_user: User = Depends(token_required)):
    return {
        "id": current_user.id,
        "name": current_user.name,
        "username": current_user.username,
        "email": current_user.email,
        "profile_pic": current_user.profile_pic,
        "bio": current_user.bio,
        "created_at": current_user.created_at,
        "updated_at": current_user.updated_at,
    }


@router.put("/profile/edit")
def update_profile(
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    update_data = data.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No data provided for update",
        )

    # username unique check
    if "username" in update_data and update_data["username"] != current_user.username:
        existing_user = (
            db.query(User)
            .filter(User.username == update_data["username"], User.id != current_user.id)
            .first()
        )
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken",
            )

    # email unique check
    if "email" in update_data and update_data["email"] != current_user.email:
        existing_email = (
            db.query(User)
            .filter(User.email == update_data["email"], User.id != current_user.id)
            .first()
        )
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already taken",
            )

    for key, value in update_data.items():
        setattr(current_user, key, value)

    try:
        db.commit()
        db.refresh(current_user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not update profile",
        )

    return {
        "message": "Profile updated successfully",
        "user": {
            "id": current_user.id,
            "name": current_user.name,
            "username": current_user.username,
            "email": current_user.email,
            "profile_pic": current_user.profile_pic,
            "bio": current_user.bio,
            "created_at": current_user.created_at,
            "updated_at": current_user.updated_at,
        },
    }


# -------------------------
# REGISTER
# -------------------------
@router.get("/register")
def get_register():
    return {"message": "User registration endpoint is active"}


@router.post("/register")
def register(data: Register, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.username == data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken",
        )

    existing_email = db.query(User).filter(User.email == data.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already taken",
        )

    hashed_password = pwd_context.hash(data.password)

    user = User(
        name=data.name,
        username=data.username,
        email=data.email,
        password=hashed_password,
    )

    db.add(user)

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already exists",
        )

    token = create_access_token(user.id)

    return {
        "message": "User registered successfully",
        "token": token,
    }


# -------------------------
# LOGIN
# -------------------------
@router.post("/login")
def login(data: Login, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()

    if not user or not pwd_context.verify(data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_access_token(user.id)

    return {
        "message": "Login successful",
        "token": token,
    }


# -------------------------
# PASSWORD RECOVERY
# -------------------------
@router.post("/forgot-password")
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()

    if not user:
        return {
            "message": "If an account exists with this email, a reset link has been sent."
        }

    reset_token = create_reset_token(user.email)

    # In production, send email instead of print
    print(f"DEBUG: Reset Link -> http://localhost:3000/reset-password?token={reset_token}")

    return {
        "message": "If an account exists with this email, a reset link has been sent."
    }


@router.post("/reset-password")
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    email = verify_reset_token(request.token)
    user = db.query(User).filter(User.email == email).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password = pwd_context.hash(request.new_password)
    db.commit()
    db.refresh(user)

    return {"message": "Password has been reset successfully"}