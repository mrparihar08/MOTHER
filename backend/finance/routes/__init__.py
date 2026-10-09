"""
Vidya F.E.I Advisor - Transaction & Telemetry Routes
"""
from backend.finance.routes.income import router as income_router
from backend.finance.routes.expense import router as expense_router
from backend.finance.routes.vitya import router as vitya_router

__all__ = ["income_router", "expense_router", "vitya_router"]
