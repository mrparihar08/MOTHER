from backend.chats.handlers.transaction_handler import handle_transaction
from backend.chats.handlers.chart_handler import handle_chart_request
from backend.chats.handlers.utility_handler import handle_utility_request
from backend.chats.handlers.info_handler import handle_info_request


def chatbot_reply(message: str, db, current_user):
    text = (message or "").lower().strip()

    # Priority 1: transaction add
    res = handle_transaction(message, db, current_user)
    if res:
        return res

    # Priority 2: charts
    res = handle_chart_request(message, db, current_user)
    if res:
        return res

    # Priority 3: utilities
    res = handle_utility_request(message, db, current_user)
    if res:
        return res

    # Priority 4: info/help/chat replies
    res = handle_info_request(message)
    if res:
        return res

    return {
        "type": "text",
        "content": "Sorry, I didn't understand that. You can tell me about your expenses and income, or ask for reports and advice!",
    }