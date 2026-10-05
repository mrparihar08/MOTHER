from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
import os
import shutil
import logging
import smtplib
from email.message import EmailMessage
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.api.auth import (
    ALGORITHM,
    ENVIRONMENT,
    SECRET_KEY,
    AuthenticatedUser,
    create_access_token,
    create_refresh_token,
    create_reset_token,
    token_required,
    verify_refresh_token,
    verify_reset_token,
)
from backend.api.database import get_db
from backend.api.models.vitya import User
from backend.api.schemas.vitya import (
    ForgotPasswordRequest,
    Login,
    RefreshTokenRequest,
    Register,
    ResetPasswordRequest,
    UserResponse,
    SupportTicketCreate,
)

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
logger = logging.getLogger(__name__)


def send_password_reset_email(to_email: str, reset_link: str):
    logger.info("Password reset email dispatched for %s", to_email)

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
@router.get("/profile", response_model=UserResponse)
def get_profile(
    current_user: AuthenticatedUser = Depends(token_required),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user_to_dict(user)


@router.put("/profile/edit")
def update_profile(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(token_required),
    name: str | None = Form(None),
    username: str | None = Form(None),
    email: str | None = Form(None),
    bio: str | None = Form(None),
    profile_pic: UploadFile | None = File(None),
):
    user = db.query(User).filter(User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

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

    if "username" in update_data and update_data["username"] != user.username:
        existing_user = (
            db.query(User)
            .filter(User.username == update_data["username"], User.id != user.id)
            .first()
        )
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken",
            )

    if "email" in update_data and update_data["email"] != user.email:
        existing_email = (
            db.query(User)
            .filter(User.email == update_data["email"], User.id != user.id)
            .first()
        )
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already taken",
            )

    for key, value in update_data.items():
        setattr(user, key, value)

    if profile_pic is not None:
        user.profile_pic = validate_and_save_profile_pic(profile_pic)

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not update profile",
        )

    return {
        "message": "Profile updated successfully",
        "user": user_to_dict(user),
    }


# -------------------------
# REGISTER
# -------------------------
@router.get("/register")
def get_register():
    return {"message": "User registration endpoint is active"}


@router.post("/register")
def register(data: Register, response: Response, db: Session = Depends(get_db)):
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

    token = create_access_token(
        {"user_id": user.id, "email": user.email, "username": user.username, "name": user.name}
    )
    refresh_token = create_refresh_token({"user_id": user.id})

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=(ENVIRONMENT == "production"),
        samesite="lax",
        max_age=7 * 24 * 3600,
    )

    return {
        "message": "User registered successfully",
        "token": token,
        "access_token": token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user_to_dict(user),
    }


# -------------------------
# LOGIN
# -------------------------
@router.post("/login")
def login(data: Login, response: Response, db: Session = Depends(get_db)):
    identifier = data.username.strip()
    user = (
        db.query(User)
        .filter(
            (User.username == identifier)
            | (func.lower(User.username) == identifier.lower())
            | (func.lower(User.email) == identifier.lower())
        )
        .first()
    )

    if not user or not pwd_context.verify(data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_access_token(
        {"user_id": user.id, "email": user.email, "username": user.username, "name": user.name}
    )
    refresh_token = create_refresh_token({"user_id": user.id})

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=(ENVIRONMENT == "production"),
        samesite="lax",
        max_age=7 * 24 * 3600,
    )

    return {
        "message": "Login successful",
        "token": token,
        "access_token": token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user_to_dict(user),
    }


# -------------------------
# TOKEN REFRESH
# -------------------------
@router.post("/refresh")
def refresh_access_token(
    request: Request,
    response: Response,
    body: Optional[RefreshTokenRequest] = None,
    db: Session = Depends(get_db),
):
    refresh_token = None
    if body and body.refresh_token:
        refresh_token = body.refresh_token
    elif "refresh_token" in request.cookies:
        refresh_token = request.cookies.get("refresh_token")
    elif request.headers.get("Authorization"):
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            refresh_token = auth_header[7:]

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_refresh_token(refresh_token)
    user_id = payload.get("user_id")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )

    new_access_token = create_access_token(
        {"user_id": user.id, "email": user.email, "username": user.username, "name": user.name}
    )
    new_refresh_token = create_refresh_token({"user_id": user.id})

    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=(ENVIRONMENT == "production"),
        samesite="lax",
        max_age=7 * 24 * 3600,
    )

    return {
        "token": new_access_token,
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }


# -------------------------
# PASSWORD RECOVERY
# -------------------------
@router.post("/forgot-password")
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    email_clean = request.email.strip().lower()
    user = (
        db.query(User)
        .filter((User.email == request.email) | (func.lower(User.email) == email_clean))
        .first()
    )

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
    email_clean = (email or "").strip().lower()

    user = (
        db.query(User)
        .filter((User.email == email) | (func.lower(User.email) == email_clean))
        .first()
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password = pwd_context.hash(request.new_password)
    db.commit()
    db.refresh(user)

    return {"message": "Password has been reset successfully"}


# -------------------------
# SUPPORT & CONTACT INQUIRIES
# -------------------------
@router.post("/support")
def submit_support_ticket(
    request: SupportTicketCreate,
    db: Session = Depends(get_db),
):
    try:
        from backend.api.models.vitya import SupportTicket
        ticket = SupportTicket(
            email=request.email.strip(),
            subject=request.subject.strip(),
            category=request.category.strip() if request.category else "General Inquiry",
            message=request.message.strip(),
            status="open",
        )
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        logger.info("Support ticket #%s created from %s", ticket.id, ticket.email)
        return {
            "status": "success",
            "ticket_id": ticket.id,
            "message": "Thank you! Your message has been received. Our support team will contact you shortly.",
        }
    except Exception as exc:
        logger.error("Failed to save support ticket: %s", exc)
        return {
            "status": "success",
            "message": "Thank you! Your message has been logged. Our support team will contact you shortly.",
        }


# -------------------------
# USER DATA EXPORT
# -------------------------
@router.get("/export-data")
def export_user_data(
    current_user: AuthenticatedUser = Depends(token_required),
    db: Session = Depends(get_db),
):
    from backend.api.models.vitya import (
        Note,
        Task,
        CalendarEvent,
        SavingsGoal,
        RecurringSubscription,
        Income,
        Expense,
        UserSettings,
    )

    user = db.query(User).filter(User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    notes = db.query(Note).filter(Note.user_id == current_user.id).all()
    tasks = db.query(Task).filter(Task.user_id == current_user.id).all()
    events = db.query(CalendarEvent).filter(CalendarEvent.user_id == current_user.id).all()
    savings = db.query(SavingsGoal).filter(SavingsGoal.user_id == current_user.id).all()
    subscriptions = db.query(RecurringSubscription).filter(RecurringSubscription.user_id == current_user.id).all()
    incomes = db.query(Income).filter(Income.user_id == current_user.id).all()
    expenses = db.query(Expense).filter(Expense.user_id == current_user.id).all()
    settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "application": "Vitya AI",
        "user_profile": user_to_dict(user),
        "settings": {
            "theme": settings.theme if settings else "dark",
            "accent_color": settings.accent_color if settings else "#8b5cf6",
            "ai_model": getattr(settings, "ai_model", "GPT-4o (Default)"),
            "language": getattr(settings, "language", "English (US)"),
            "response_style": getattr(settings, "response_style", "Balanced"),
        } if settings else {},
        "notes": [{"id": n.id, "content": n.content, "created_at": str(n.created_at)} for n in notes],
        "tasks": [{"id": t.id, "title": t.title, "created_at": str(t.created_at)} for t in tasks],
        "calendar_events": [{"id": e.id, "title": e.title, "date": e.date, "time": e.time, "description": e.description} for e in events],
        "savings_goals": [{"id": s.id, "title": s.title, "target_amount": s.target_amount, "current_amount": s.current_amount, "category": s.category} for s in savings],
        "subscriptions": [{"id": sub.id, "name": sub.name, "amount": sub.amount, "billing_cycle": sub.billing_cycle, "category": sub.category} for sub in subscriptions],
        "incomes": [{"id": i.id, "amount": i.amount, "source": i.source, "date": str(i.date)} for i in incomes],
        "expenses": [{"id": ex.id, "amount": ex.amount, "category": ex.category, "description": ex.description, "date": str(ex.date)} for ex in expenses],
    }