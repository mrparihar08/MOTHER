from pydantic import BaseModel
from typing import List, Optional

class Expense(BaseModel):
    date: str
    amount: float
    category: str

class TrainRequest(BaseModel):
    expenses: List[Expense]

class PredictRequest(BaseModel):
    expenses: List[Expense]
    total_income: Optional[float] = None