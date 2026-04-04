from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from sqlalchemy.exc import IntegrityError
from jose import jwt
from passlib.context import CryptContext

from backend.api.database import get_db
from backend.api.models.vitya import User
from backend.api.schemas.vitya import Register, Login, ForgotPasswordRequest, ResetPasswordRequest
from backend.api.auth import SECRET_KEY, ALGORITHM, token_required, create_reset_token, verify_reset_token

router = APIRouter()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# -------------------------------
# PROFILE
# -------------------------------
@router.get("/profile")
def get_profile(current_user: User = Depends(token_required)):

    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email
    }
# -------------------------
# REGISTER
# -------------------------
@router.get("/register")
def get_reguster():
    return {"message": "User registration endpoint is active"}

@router.post("/register")
def register(data: Register, db: Session = Depends(get_db)):
    # check username
    existing_user = db.query(User).filter(User.username == data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )

    # check email
    existing_email = db.query(User).filter(User.email == data.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already taken"
        )

    hashed_password = pwd_context.hash(data.password)

    user = User(
        username=data.username,
        email=data.email,
        password=hashed_password
    )

    db.add(user)

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already exists"
        )

    payload = {
        "user_id": user.id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=48)
    }

    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    return {
        "message": "User registered successfully",
        "token": token
    }


# -------------------------
# LOGIN
# -------------------------
@router.post("/login")
def login(data: Login, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    if not pwd_context.verify(data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    payload = {
        "user_id": user.id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=48)
    }

    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    return {
        "message": "Login successful",
        "token": token
    }

# -------------------------
# PASSWORD RECOVERY
# -------------------------
@router.post("/forgot-password")
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()

    if not user:
        return {"message": "If an account exists with this email, a reset link has been sent."}

    reset_token = create_reset_token(user.email)
    
    # In production, integrate an email service here.
    print(f"DEBUG: Reset Link -> http://localhost:3000/reset-password?token={reset_token}")

    return {"message": "If an account exists with this email, a reset link has been sent."}

@router.post("/reset-password")
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    email = verify_reset_token(request.token)
    user = db.query(User).filter(User.email == email).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password = pwd_context.hash(request.new_password)
    db.commit()

    return {"message": "Password has been reset successfully"}
