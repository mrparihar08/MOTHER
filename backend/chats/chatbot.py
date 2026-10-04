import logging
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from backend.chats.handlers.transaction_handler import handle_transaction
from backend.chats.handlers.chart_handler import handle_chart_request
from backend.chats.handlers.utility_handler import handle_utility_request
from backend.chats.handlers.info_handler import handle_info_request

logger = logging.getLogger(__name__)


def chatbot_reply(message: str, db: Session, current_user: Any) -> Optional[Dict[str, Any]]:
    """
    Tier-2 Rule & Financial Logic Router:
    Priority 1: Transaction Processing (Expense / Income logging)
    Priority 2: Chart & Visualization Generator (Pie, Donut, Line, Waterfall, etc.)
    Priority 3: Utility Commands (QR, Barcode, Weather, Balance, Totals, Budget, Calculator)
    Priority 4: Lightweight Small-talk & Quick Help FAQs
    """
    if not message or not message.strip():
        return None

    # Priority 1: Transaction Logging (Expense / Income)
    try:
        txn_res = handle_transaction(message, db, current_user)
        if txn_res:
            return txn_res
    except Exception as e:
        logger.exception("Error in handle_transaction: %s", e)

    # Priority 2: Visual Charts & Analytics
    try:
        chart_res = handle_chart_request(message, db, current_user)
        if chart_res:
            return chart_res
    except Exception as e:
        logger.exception("Error in handle_chart_request: %s", e)

    # Priority 3: Finance Utilities & Tools
    try:
        util_res = handle_utility_request(message, db, current_user)
        if util_res:
            return util_res
    except Exception as e:
        logger.exception("Error in handle_utility_request: %s", e)

    # Priority 4: Quick Help / Greetings (Non-blocking small talk)
    try:
        info_res = handle_info_request(message)
        if info_res:
            return info_res
    except Exception as e:
        logger.exception("Error in handle_info_request: %s", e)

    return None