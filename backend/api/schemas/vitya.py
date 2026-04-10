from pydantic import BaseModel
from datetime import date, datetime

class Register(BaseModel):
    username: str
    email: str
    password: str

class Login(BaseModel):
    username: str
    password: str

class IncomeCreate(BaseModel):

    amount: float
    source: str
    date: date

class ExpenseCreate(BaseModel):

    amount: float
    category: str
    description: str
    date: date

class ChatRequest(BaseModel):
    message: str    

class ChatResponse(BaseModel):
    reply: str  


class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class NoteCreate(BaseModel):
    content: str

class NoteUpdate(BaseModel):
    content: str
class NoteResponse(BaseModel):
    id: int
    content: str
    created_at: datetime

    class Config:
        from_attributes = True
class TaskCreate(BaseModel):
    title: str

class TaskUpdate(BaseModel):
    title: str
class TaskResponse(BaseModel):
    id: int
    title: str
    created_at: datetime

    class Config:
        from_attributes = True        
