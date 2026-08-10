from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
import os
import shutil

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
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
)

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(user_id: int):
    payload = {
        "user_id": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=48),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def user_to_dict(user: User):
    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "email": user.email,
        "profile_pic": user.profile_pic,
        "bio": user.bio,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


# -------------------------------
# PROFILE
# -------------------------------
@router.get("/profile")
def get_profile(current_user: User = Depends(token_required)):
    return user_to_dict(current_user)


@router.put("/profile/edit")
def update_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
    name: str | None = Form(None),
    username: str | None = Form(None),
    email: str | None = Form(None),
    bio: str | None = Form(None),
    profile_pic: UploadFile | None = File(None),
):
    update_data = {}

    if name is not None:
        update_data["name"] = name.strip()

    if username is not None:
        update_data["username"] = username.strip()

    if email is not None:
        update_data["email"] = email.strip()

    if bio is not None:
        update_data["bio"] = bio.strip()

    if not update_data and profile_pic is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No data provided for update",
        )

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

    if profile_pic is not None:
        uploads_dir = Path("uploads/profiles")
        uploads_dir.mkdir(parents=True, exist_ok=True)

        original_name = profile_pic.filename or "profile.png"
        suffix = Path(original_name).suffix.lower() or ".png"
        file_name = f"{uuid4().hex}{suffix}"
        file_path = uploads_dir / file_name

        with file_path.open("wb") as buffer:
            shutil.copyfileobj(profile_pic.file, buffer)

        current_user.profile_pic = f"/uploads/profiles/{file_name}"

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
        "user": user_to_dict(current_user),
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
    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    print(f"DEBUG: Reset Link -> {frontend_url}/reset-password?token={reset_token}")

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