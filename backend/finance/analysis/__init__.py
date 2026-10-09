"""
Vidya F.E.I Advisor - Analytics, Prediction & Savings Analysis
"""
from backend.finance.analysis.analyse import router as analyse_router
from backend.finance.analysis.savings import router as savings_router

__all__ = ["analyse_router", "savings_router"]
