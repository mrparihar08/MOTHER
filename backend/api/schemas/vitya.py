from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------------------
# AUTH
# ---------------------------
class Register(BaseModel):
    name: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1)
    email: EmailStr
    password: str = Field(..., min_length=4)


class Login(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=4)


# ---------------------------
# USER / PROFILE
# ---------------------------
class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    username: Optional[str] = Field(None, min_length=1)
    email: Optional[EmailStr] = None
    profile_pic: Optional[str] = None
    bio: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    name: str
    username: str
    email: EmailStr
    profile_pic: Optional[str] = None
    bio: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------
# INCOME
# ---------------------------
class IncomeCreate(BaseModel):
    amount: float = Field(..., gt=0, description="Amount must be greater than 0")
    source: str = Field(..., min_length=1)
    date: Optional[date] = None


class IncomeUpdate(BaseModel):
    amount: Optional[float] = Field(None, gt=0)
    source: Optional[str] = Field(None, min_length=1)
    date: Optional[date] = None


class IncomeResponse(BaseModel):
    id: int
    amount: float
    source: str
    date: datetime
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------
# EXPENSE
# ---------------------------
class ExpenseCreate(BaseModel):
    amount: float = Field(..., gt=0, description="Amount must be greater than 0")
    category: str = Field(..., min_length=1)
    description: Optional[str] = None
    date: Optional[date] = None


class ExpenseUpdate(BaseModel):
    amount: Optional[float] = Field(None, gt=0)
    category: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = None
    date: Optional[date] = None


class ExpenseResponse(BaseModel):
    id: int
    amount: float
    category: str
    description: Optional[str] = None
    date: datetime
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------
# BUDGET & ALERTS
# ---------------------------
class BudgetCreate(BaseModel):
    category: str = Field(..., min_length=1)
    monthly_limit: float = Field(..., gt=0, description="Monthly budget limit must be greater than 0")


class BudgetUpdate(BaseModel):
    category: Optional[str] = Field(None, min_length=1)
    monthly_limit: Optional[float] = Field(None, gt=0)


class BudgetResponse(BaseModel):
    id: int
    category: str
    monthly_limit: float
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class BudgetAlertStatus(BaseModel):
    category: str
    monthly_limit: float
    current_spend: float
    percentage_used: float
    status: str  # NORMAL, WARNING, EXCEEDED
    message: str


# ---------------------------
# CHAT
# ---------------------------
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    reply: str


class ChatMessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------
# NOTE
# ---------------------------
class NoteCreate(BaseModel):
    content: str = Field(..., min_length=1)


class NoteUpdate(BaseModel):
    content: Optional[str] = Field(None, min_length=1)


class NoteResponse(BaseModel):
    id: int
    content: str
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------
# TASK
# ---------------------------
class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1)


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)


class TaskResponse(BaseModel):
    id: int
    title: str
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)