from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, Dict, Union
import os
import logging
from jose import jwt, JWTError, ExpiredSignatureError
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
SECRET_KEY = os.getenv("SECRET_KEY") or os.getenv("JWT_SECRET_KEY")

if ENVIRONMENT == "production" and (not SECRET_KEY or SECRET_KEY in {"change-me", "dev-secret-key"}):
    raise RuntimeError("A secure SECRET_KEY environment variable is required in production")

if not SECRET_KEY:
    SECRET_KEY = "dev-secret-key"

ALGORITHM = "HS256"
# 365 Days persistent session (525,600 minutes) to prevent frequent session expiration
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "525600"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "365"))
RESET_TOKEN_EXPIRE_MINUTES = 60

security = HTTPBearer(auto_error=False)
security_optional = HTTPBearer(auto_error=False)


@dataclass
class AuthenticatedUser:
    """Lightweight authenticated user principal populated directly from verified JWT claims."""
    id: int
    email: Optional[str] = None
    username: Optional[str] = None
    name: Optional[str] = None


def create_access_token(
    data: Union[dict, int, AuthenticatedUser],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a short-lived signed JWT access token."""
    if isinstance(data, int):
        to_encode = {"user_id": data}
    elif isinstance(data, AuthenticatedUser):
        to_encode = {
            "user_id": data.id,
            "email": data.email,
            "username": data.username,
            "name": data.name,
        }
    else:
        to_encode = data.copy()

    to_encode["type"] = "access"

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(
    data: Union[dict, int, AuthenticatedUser],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a long-lived signed JWT refresh token."""
    if isinstance(data, int):
        to_encode = {"user_id": data}
    elif isinstance(data, AuthenticatedUser):
        to_encode = {"user_id": data.id}
    else:
        user_id = data.get("user_id", data.get("id"))
        to_encode = {"user_id": user_id}
        if "email" in data:
            to_encode["email"] = data["email"]
        if "username" in data:
            to_encode["username"] = data["username"]

    to_encode["type"] = "refresh"

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """Decode and cryptographically verify a JWT signature and expiration."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def token_required(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    token_param: Optional[str] = Query(None, alias="token"),
) -> AuthenticatedUser:
    """Mandatory JWT authentication dependency. Validates JWT claims statelessly without DB queries."""
    token = None
    if credentials:
        token = credentials.credentials
    elif token_param:
        token = token_param

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(token)
        token_type = payload.get("type", "access")
        if token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type: access token required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return AuthenticatedUser(
            id=int(user_id),
            email=payload.get("email"),
            username=payload.get("username"),
            name=payload.get("name"),
        )
    except HTTPException:
        raise
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please login again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid or expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


def optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
    token_param: Optional[str] = Query(None, alias="token"),
) -> Optional[AuthenticatedUser]:
    """Optional JWT authentication dependency. Returns AuthenticatedUser or None statelessly without raising 401."""
    token = None
    if credentials:
        token = credentials.credentials
    elif token_param:
        token = token_param

    if not token:
        return None

    try:
        payload = decode_token(token)
        token_type = payload.get("type", "access")
        if token_type != "access":
            return None

        user_id = payload.get("user_id")
        if user_id is None:
            return None

        return AuthenticatedUser(
            id=int(user_id),
            email=payload.get("email"),
            username=payload.get("username"),
            name=payload.get("name"),
        )
    except Exception:
        return None


def create_reset_token(email: str) -> str:
    """Create a short-lived password reset token."""
    to_encode = {"sub": email, "purpose": "password_reset"}
    expire = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_reset_token(token: str) -> str:
    """Verify password reset token and return the associated email subject."""
    try:
        payload = decode_token(token)
        if payload.get("purpose") != "password_reset":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token purpose",
            )
        email = payload.get("sub")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token subject",
            )
        return email
    except HTTPException:
        raise
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password reset session expired. Please request a new link.",
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired reset token",
        )


def verify_refresh_token(token: str) -> Dict[str, Any]:
    """Verify refresh token signature, expiration, and token type."""
    try:
        payload = decode_token(token)
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type: refresh token required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload: missing user_id",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    except HTTPException:
        raise
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please login again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid or expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
