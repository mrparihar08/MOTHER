

from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import os

from backend.api.database import get_db
from backend.api.models.vitya import User

SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret-for-dev")
ALGORITHM = "HS256"

security = HTTPBearer()

# ✅ CREATE TOKEN
def create_access_token(data: dict):
    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(hours=24)
    to_encode.update({"exp": expire})

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ✅ VERIFY TOKEN
def token_required(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")

        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")

        current_user = db.query(User).filter(User.id == user_id).first()

        if current_user is None:
            raise HTTPException(status_code=401, detail="User not found")

        return current_user

    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Token is invalid or expired"
        )

# ✅ CREATE RESET TOKEN (Short-lived: 15 mins)
def create_reset_token(email: str):
    to_encode = {"sub": email, "purpose": "password_reset"}
    expire = datetime.now(timezone.utc) + timedelta(minutes=15) # 15 minutes expiry
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# ✅ VERIFY RESET TOKEN
def verify_reset_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("purpose") != "password_reset":
            raise HTTPException(status_code=400, detail="Invalid token purpose")
        return payload.get("sub") # Returns the email
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired reset token")
