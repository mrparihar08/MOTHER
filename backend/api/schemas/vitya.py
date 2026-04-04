from pydantic import BaseModel
from datetime import date

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

