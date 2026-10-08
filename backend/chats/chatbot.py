import logging
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from backend.chats.handlers.chart_handler import handle_chart_request, is_visualization_request
from backend.chats.handlers.transaction_handler import handle_transaction
from backend.chats.handlers.utility_handler import handle_utility_request
from backend.chats.handlers.info_handler import handle_info_request

logger = logging.getLogger(__name__)


def chatbot_reply(
    message: str,
    db: Session,
    current_user: Any,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    city: Optional[str] = None,
    client_ip: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Tier-2 Rule & Logic Router:
    Priority 1: Data Visualization / Chart Generator (Percentage & dataset distributions, Bar, Pie, Line, etc.)
    Priority 2: Transaction Processing (Expense / Income logging with strict financial validation)
    Priority 3: Utility Commands (QR, Barcode, Weather, Balance, Totals, Budget, Calculator)
    Priority 4: Lightweight Small-talk & Quick Help FAQs
    """
    if not message or not message.strip():
        return None

    # Priority 1: Data Visualization & Analytics Requests
    if is_visualization_request(message):
        try:
            chart_res = handle_chart_request(message, db, current_user)
            if chart_res:
                return chart_res
        except Exception as e:
            logger.exception("Error in handle_chart_request: %s", e)

    # Priority 2: Transaction Logging (Expense / Income)
    try:
        txn_res = handle_transaction(message, db, current_user)
        if txn_res:
            return txn_res
    except Exception as e:
        logger.exception("Error in handle_transaction: %s", e)

    # Fallback Priority 2.5: Chart Request without obvious keywords (e.g. multi-month query)
    try:
        chart_res = handle_chart_request(message, db, current_user)
        if chart_res:
            return chart_res
    except Exception as e:
        logger.exception("Error in handle_chart_request fallback: %s", e)

    # Priority 3: Finance Utilities & Tools (Weather, QR, Barcode, Balance, Health score)
    try:
        util_res = handle_utility_request(
            message,
            db,
            current_user,
            latitude=latitude,
            longitude=longitude,
            city=city,
            client_ip=client_ip,
        )
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