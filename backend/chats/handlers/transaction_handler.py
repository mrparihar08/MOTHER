import re
from datetime import datetime

from backend.api.models.vitya import Expense, Income
from backend.chats.utils.categories import CATEGORY_KEYWORDS

NORMALIZATION_MAP = {
    "kharida": "buy",
    "liya": "buy",
    "diya": "paid",
    "aaya": "received",
    "khana": "food",
    "dawai": "medicine",
}


def normalize(text: str) -> str:
    text = (text or "").lower().strip()
    for k, v in NORMALIZATION_MAP.items():
        text = re.sub(rf"\b{re.escape(k)}\b", v, text)
    return text


def contains_any(text: str, words) -> bool:
    return any(word in text for word in words)


def extract_amount(text: str):
    match = re.search(r"(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else None


def detect_txn_type(text: str):
    income_words = ["salary", "income", "credited", "received", "earn"]
    expense_words = ["spent", "buy", "paid", "expense"]

    income_score = sum(word in text for word in income_words)
    expense_score = sum(word in text for word in expense_words)

    if income_score > expense_score:
        return "income"
    if expense_score > income_score:
        return "expense"
    return None


def detect_category(text: str):
    if "salary" in text:
        return "salary"

    scores = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(
            weight
            for word, weight in keywords.items()
            if re.search(rf"\b{re.escape(word)}\b", text)
        )
        if score:
            scores[category] = score

    return max(scores, key=scores.get) if scores else "other"


def handle_transaction(message: str, db, current_user):
    text = normalize(message)

    amount = extract_amount(text)
    txn_type = detect_txn_type(text)
    category = detect_category(text)

    if amount is not None and txn_type == "expense":
        db.add(
            Expense(
                amount=amount,
                category=category,
                date=datetime.utcnow(),
                user_id=current_user.id,
            )
        )
        db.commit()
        return {"type": "text", "content": f"Expense ₹{amount} added in {category}"}

    if amount is not None and txn_type == "income":
        db.add(
            Income(
                amount=amount,
                source=category,
                date=datetime.utcnow(),
                user_id=current_user.id,
            )
        )
        db.commit()
        return {"type": "text", "content": f"Income ₹{amount} added as {category}"}

    return None