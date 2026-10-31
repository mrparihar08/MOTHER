"""
API Endpoints for Centralized Auth & Core Service.
"""
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import ConfigDict, BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from services.auth_service.database import get_db
from services.auth_service.models import AuthUser, RefreshToken
from services.auth_service.crypto import (
    RSAKeyManager,
    verify_password,
    get_password_hash,
)
from shared.security.jwt_validator import get_current_user
from shared.security.models import AuthenticatedUser

router = APIRouter()
key_manager = RSAKeyManager.get_instance()


# Pydantic Schemas
class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = None


class UserProfileResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str
    user: UserProfileResponse


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None


@router.get("/.well-known/jwks.json")
def get_jwks():
    """Returns the JSON Web Key Set for asymmetric RS256 token verification."""
    return key_manager.get_jwks()


@router.post("/register", response_model=UserProfileResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: UserRegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(AuthUser).filter(AuthUser.email == user_data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists",
        )

    user = AuthUser(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        role="user",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/token", response_model=TokenResponse)
@router.post("/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(AuthUser).filter(AuthUser.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    access_token = key_manager.create_access_token(
        user_id=user.id,
        email=user.email,
        roles=[user.role],
    )
    refresh_token_str = key_manager.create_refresh_token(user_id=user.id)

    # Persist refresh token in auth database
    rf = RefreshToken(
        token=refresh_token_str,
        user_id=user.id,
        expires_at=datetime.utcnow(),
    )
    db.add(rf)
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_str,
        user=UserProfileResponse.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(request: RefreshTokenRequest, db: Session = Depends(get_db)):
    rf_entry = db.query(RefreshToken).filter(
        RefreshToken.token == request.refresh_token,
        RefreshToken.revoked == False,
    ).first()

    if not rf_entry:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked refresh token",
        )

    user = db.query(AuthUser).filter(AuthUser.id == rf_entry.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User associated with token no longer active",
        )

    # Rotate refresh token
    rf_entry.revoked = True
    new_access_token = key_manager.create_access_token(
        user_id=user.id,
        email=user.email,
        roles=[user.role],
    )
    new_refresh_token_str = key_manager.create_refresh_token(user_id=user.id)

    new_rf = RefreshToken(
        token=new_refresh_token_str,
        user_id=user.id,
        expires_at=datetime.utcnow(),
    )
    db.add(new_rf)
    db.commit()

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token_str,
        user=UserProfileResponse.model_validate(user),
    )


@router.post("/logout")
def logout(request: RefreshTokenRequest, db: Session = Depends(get_db)):
    rf_entry = db.query(RefreshToken).filter(RefreshToken.token == request.refresh_token).first()
    if rf_entry:
        rf_entry.revoked = True
        db.commit()
    return {"message": "Successfully logged out and session revoked."}


@router.get("/me", response_model=UserProfileResponse)
def get_me(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = db.query(AuthUser).filter(AuthUser.id == current_user.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.put("/profile", response_model=UserProfileResponse)
def update_profile(
    profile_data: ProfileUpdateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = db.query(AuthUser).filter(AuthUser.id == current_user.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if profile_data.full_name is not None:
        user.full_name = profile_data.full_name
    if profile_data.avatar_url is not None:
        user.avatar_url = profile_data.avatar_url

    db.commit()
    db.refresh(user)
    return user
