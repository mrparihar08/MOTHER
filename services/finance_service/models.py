"""
Finance Service Domain Models (Isolated schema without foreign keys to Auth DB).
"""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Float, Numeric, DateTime, Boolean, Text

from services.finance_service.database import Base


class Income(Base):
    __tablename__ = "incomes"

    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Numeric(precision=12, scale=2), nullable=False)
    source = Column(String(100), nullable=False)
    date = Column(DateTime, default=datetime.utcnow, nullable=False)
    user_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Numeric(precision=12, scale=2), nullable=False)
    category = Column(String(100), nullable=False, index=True)
    description = Column(String(255), nullable=True)
    date = Column(DateTime, default=datetime.utcnow, nullable=False)
    user_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(100), nullable=False)
    monthly_limit = Column(Numeric(precision=12, scale=2), nullable=False)
    user_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SavingsGoal(Base):
    __tablename__ = "savings_goals"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    target_amount = Column(Numeric(precision=12, scale=2), nullable=False)
    current_amount = Column(Numeric(precision=12, scale=2), default=0.0)
    deadline = Column(DateTime, nullable=True)
    user_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RecurringSubscription(Base):
    __tablename__ = "recurring_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    amount = Column(Numeric(precision=12, scale=2), nullable=False)
    billing_cycle = Column(String(50), default="monthly")
    next_billing_date = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    user_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FinancialAuditLog(Base):
    __tablename__ = "financial_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    action = Column(String(50), nullable=False)
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(Integer, nullable=True)
    amount = Column(Numeric(precision=12, scale=2), nullable=True)
    details = Column(Text, nullable=True)
    idempotency_key = Column(String(100), nullable=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
