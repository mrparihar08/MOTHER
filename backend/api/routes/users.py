from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
import os
import shutil
import logging
import smtplib
from email.message import EmailMessage

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
logger = logging.getLogger(__name__)


def send_password_reset_email(to_email: str, reset_link: str):
    print(f"DEBUG: Reset Link -> {reset_link}")
    logger.info(f"Password reset link generated for {to_email}: {reset_link}")

    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender_email = os.getenv("SMTP_FROM", smtp_user or "noreply@vitya.ai")

    if smtp_host and smtp_user and smtp_password:
        try:
            msg = EmailMessage()
            msg["Subject"] = "Vitya AI - Password Reset Request"
            msg["From"] = sender_email
            msg["To"] = to_email
            msg.set_content(
                f"Hello,\n\n"
                f"You requested a password reset for your Vitya AI account.\n"
                f"Please click the link below to reset your password (valid for 15 minutes):\n\n"
                f"{reset_link}\n\n"
                f"If you did not request this, please ignore this email.\n"
            )
            msg.add_alternative(
                f"""\
<html>
  <body style="font-family: Arial, sans-serif; background-color: #0f172a; color: #f8fafc; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto; background-color: #1e293b; padding: 30px; border-radius: 8px;">
      <h2 style="color: #10b981;">Vitya AI — Password Reset</h2>
      <p>Hello,</p>
      <p>You requested a password reset for your account. Click the button below to reset your password (link expires in 15 minutes):</p>
      <div style="margin: 25px 0;">
        <a href="{reset_link}" style="background-color: #10b981; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;">Reset Password</a>
      </div>
      <p style="font-size: 12px; color: #94a3b8;">Or copy and paste this URL into your browser:<br>{reset_link}</p>
    </div>
  </body>
</html>
""",
                subtype="html",
            )

            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)

            logger.info(f"Password reset email sent to {to_email}")
        except Exception as e:
            logger.error(f"Failed to send password reset email to {to_email}: {e}")

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


def validate_and_save_profile_pic(profile_pic: UploadFile) -> str:
    original_name = profile_pic.filename or "profile.png"
    suffix = Path(original_name).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image format. Allowed formats: JPG, JPEG, PNG, WEBP, GIF",
        )

    content_type = (profile_pic.content_type or "").lower()
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only JPEG, PNG, WEBP, and GIF images are allowed.",
        )

    content = profile_pic.file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds maximum limit of 5MB",
        )
    profile_pic.file.seek(0)

    file_name = f"{uuid4().hex}{suffix}"

    # Attempt Cloud Storage (Supabase Storage) if configured
    try:
        from backend.api.supabase_client import get_supabase_client
        supabase = get_supabase_client()
        bucket = "profiles"
        supabase.storage.from_(bucket).upload(
            file_name,
            content,
            file_options={"content-type": content_type}
        )
        public_url = supabase.storage.from_(bucket).get_public_url(file_name)
        if public_url:
            return public_url
    except Exception:
        pass  # Fallback to local storage if cloud storage is unconfigured

    uploads_dir = Path("uploads/profiles")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    file_path = uploads_dir / file_name

    with file_path.open("wb") as buffer:
        buffer.write(content)

    return f"/uploads/profiles/{file_name}"


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
        current_user.profile_pic = validate_and_save_profile_pic(profile_pic)

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
    reset_link = f"{frontend_url}/reset-password?token={reset_token}"

    send_password_reset_email(user.email, reset_link)

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