from sqlalchemy import Column, DateTime, Integer, String, Float, Date, ForeignKey
from sqlalchemy.orm import relationship
from backend.api.database import Base
from datetime import datetime
class User(Base):

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True)
    email = Column(String, unique=True)
    password = Column(String)
    incomes = relationship("Income", back_populates="user")
    expenses = relationship("Expense", back_populates="user")


class Income(Base):

    __tablename__ = "income"

    id = Column(Integer, primary_key=True)
    amount = Column(Float)
    source = Column(String)
    date = Column(DateTime, default=datetime.utcnow) 
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User", back_populates="incomes")


class Expense(Base):

    __tablename__ = "expense"

    id = Column(Integer, primary_key=True,index=True)
    amount = Column(Float)
    category = Column(String)
    description = Column(String)
    date = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User", back_populates="expenses")