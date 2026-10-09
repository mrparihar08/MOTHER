"""
Vidya F.E.I Advisor Domain Package
Finance, Expense, Income, Savings, and AI Financial Intelligence
"""
from backend.finance.routes.income import router as income_router
from backend.finance.routes.expense import router as expense_router
from backend.finance.routes.vitya import router as vitya_router
from backend.finance.analysis.analyse import router as analyse_router
from backend.finance.analysis.savings import router as savings_router
from backend.api.routes.subscriptions import router as subscriptions_router

__all__ = [
    "income_router",
    "expense_router",
    "vitya_router",
    "analyse_router",
    "savings_router",
    "subscriptions_router",
]
