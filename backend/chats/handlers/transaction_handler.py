import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from backend.api.models.vitya import Expense, Income
from backend.chats.utils.categories import CATEGORY_KEYWORDS

# Extended normalization & slang mapping (Hinglish -> Standard English/Intent)
NORMALIZATION_MAP = {
    # Actions - Expense
    "kharida": "buy",
    "kharid": "buy",
    "kharide": "buy",
    "liya": "buy",
    "liye": "buy",
    "diya": "paid",
    "diye": "paid",
    "bhara": "paid",
    "bhare": "paid",
    "bhari": "paid",
    "chukaaye": "paid",
    "bheja": "paid",
    "bheje": "paid",
    "kharch": "spent",
    "kharcha": "spent",
    "kharcha kiya": "spent",
    "khaye": "food",
    "khaya": "food",
    "mangwaya": "order",
    "mangwayi": "order",
    "uda diye": "spent",

    # Actions - Income
    "aaya": "received",
    "aaye": "received",
    "aayi": "received",
    "mila": "received",
    "mile": "received",
    "mili": "received",
    "kamaya": "earn",
    "kamaye": "earn",
    "mil gaya": "received",
    "credit hua": "credited",

    # Common Categories / Words
    "khana": "food",
    "dawai": "medicine",
    "dawa": "medicine",
    "nashta": "breakfast",
    "kiraya": "rent",
    "bijli": "electricity",
    "pani": "water",
    "petrol": "petrol",
    "diesel": "diesel",
    "rashan": "groceries",
    "ration": "groceries",
    "padhai": "education",
    "dudh": "milk",
    "doodh": "milk",
    "sabji": "vegetables",
    "sabzi": "vegetables",
}

# Multiplier mapping for Indian & International number formats
MULTIPLIER_MAP = {
    "k": 1_000,
    "l": 100_000,
    "lac": 100_000,
    "lakh": 100_000,
    "lakhs": 100_000,
    "cr": 10_000_000,
    "crore": 10_000_000,
    "crores": 10_000_000,
}

CATEGORY_ICONS = {
    "Food": "🍔",
    "Transport": "🚗",
    "Entertainment": "🎬",
    "Utilities": "💡",
    "Health": "💊",
    "Salary": "💰",
    "Shopping": "🛍️",
    "Housing": "🏠",
    "Fitness": "🏋️",
    "Education": "📚",
    "Finance": "📈",
    "Gifts": "🎁",
    "Family": "👨‍👩‍👧",
    "Other": "📝",
}


def normalize(text: str) -> str:
    """Normalize Hinglish text to standard keywords and lowercased string."""
    text = (text or "").lower().strip()
    # Replace multi-word expressions first
    for k in sorted(NORMALIZATION_MAP.keys(), key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(k)}\b", NORMALIZATION_MAP[k], text)
    return text


def extract_amount(text: str) -> Optional[float]:
    """
    Extract transaction amount from diverse formats:
    - ₹500, Rs. 500, INR 500, 500/-
    - 500 rs, 500 rupees, 500 rupaye, 500 bucks, 500ka, 500ki
    - 1.5k, 50k, 2.5 lakh, 1.2 cr
    - 1,500.50, 25000
    """
    # 1. Pattern with multipliers (e.g. 1.5k, 2.5 lakh, 50k, 2 cr)
    multiplier_pattern = r"(?:₹|rs\.?|inr|\$)?\s*(\d+(?:\.\d+)?)\s*(k|l|lac|lakh|lakhs|cr|crore|crores)\b"
    m_mult = re.search(multiplier_pattern, text, re.IGNORECASE)
    if m_mult:
        base_val = float(m_mult.group(1))
        unit = m_mult.group(2).lower()
        multiplier = MULTIPLIER_MAP.get(unit, 1)
        return float(base_val * multiplier)

    # 2. Pattern with explicit currency indicator before or after amount
    explicit_pattern = (
        r"(?:(?:₹|rs\.?|inr|\$)\s*([\d,]+(?:\.\d+)?)|"  # ₹500, rs 500
        r"([\d,]+(?:\.\d+)?)\s*(?:/[-=]|rs\.?|inr|\$|rupees|rupaye|rupay|bucks|ka\b|ki\b|ke\b))"  # 500/-, 500 rs, 500ka
    )
    m_exp = re.search(explicit_pattern, text, re.IGNORECASE)
    if m_exp:
        raw_val = m_exp.group(1) or m_exp.group(2)
        if raw_val:
            cleaned_val = raw_val.replace(",", "")
            try:
                return float(cleaned_val)
            except ValueError:
                pass

    # 3. Fallback: match standalone number if it looks like an amount (1 to 8 digits, optional decimal)
    # Avoid matching 4-digit years (e.g., 2024, 2025, 2026) unless accompanied by currency
    numbers = re.findall(r"\b\d+(?:,\d+)*(?:\.\d+)?\b", text)
    for num_str in numbers:
        cleaned = num_str.replace(",", "")
        try:
            val = float(cleaned)
            # Skip likely years or single small digits without context if not intended
            if 1900 <= val <= 2100 and "." not in cleaned:
                continue
            return val
        except ValueError:
            continue

    return None


def extract_date(text: str) -> datetime:
    """Extract relative date (today, yesterday, etc.) or default to current UTC timestamp."""
    now = datetime.now(timezone.utc)
    text_lower = text.lower()

    if any(w in text_lower for w in ["yesterday", "kal", "beeta kal", "last day"]):
        return now - timedelta(days=1)
    if any(w in text_lower for w in ["parso", "day before yesterday"]):
        return now - timedelta(days=2)

    return now


def detect_txn_type(text: str, category: Optional[str] = None) -> Optional[str]:
    """Detect whether transaction is an 'income' or 'expense'."""
    income_words = [
        "salary", "income", "credited", "received", "earn", "earned",
        "stipend", "cashback", "refund", "deposit", "bonus", "profit",
        "dividend", "incentive", "aaya", "mila"
    ]
    expense_words = [
        "spent", "spend", "buy", "bought", "paid", "pay", "expense",
        "order", "ordered", "bill", "recharge", "loss", "fee", "fees",
        "rent", "emi", "kiraya", "petrol", "food", "dinner", "lunch"
    ]

    income_score = sum(bool(re.search(rf"\b{re.escape(w)}\b", text)) for w in income_words)
    expense_score = sum(bool(re.search(rf"\b{re.escape(w)}\b", text)) for w in expense_words)

    if income_score > expense_score:
        return "income"
    if expense_score > income_score:
        return "expense"

    # Contextual inference from category
    if category == "Salary":
        return "income"

    # In finance chat contexts, unspecified amounts with an item/category are almost always expenses
    if category and category not in ["Salary", "Other"]:
        return "expense"

    # Default fallback if amount exists
    return "expense" if expense_score >= income_score else "income"


def detect_category(text: str) -> str:
    """Classify text into a standard Category matching CATEGORY_KEYWORDS."""
    if "salary" in text or "stipend" in text:
        return "Salary"

    scores: Dict[str, float] = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = 0.0
        # Direct category name match
        if re.search(rf"\b{re.escape(category.lower())}\b", text):
            score += 3.0

        for word, weight in keywords.items():
            if re.search(rf"\b{re.escape(word.lower())}\b", text):
                score += weight

        if score > 0:
            scores[category] = score

    if scores:
        best_category = max(scores, key=scores.get)
        return best_category

    return "Other"


def clean_description(raw_text: str, amount: float, category: str) -> str:
    """Generate a clean description note from the user message."""
    desc = raw_text.strip()
    # Remove obvious amount and filler prefixes/suffixes
    amt_str = str(int(amount) if amount.is_integer() else amount)
    patterns_to_remove = [
        rf"(?:₹|rs\.?|inr|\$)?\s*\b{re.escape(amt_str)}\b(?:\s*(?:k\b|lac\b|lakh\b|cr\b|crore\b|/[-=]|rs\.?\b|rupees?\b|rupaye?\b|bucks?\b))?",
        r"\b(spent on|paid for|bought|buy|spent|received|aaya|mila|mile|diya|diye|liya|liye|add|note|likh|likho|kharcha|kare|hua|hui|kiya|khaya|mangwaya)\b",
        r"\b(yesterday|today|kal|aaj|parso|beeta kal)\b",
        r"\b(ka|ki|ke|ko|se|me|mein|par|pe|in|for|on|at)\b",
    ]
    cleaned = desc
    for pat in patterns_to_remove:
        cleaned = re.sub(pat, " ", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")
    if not cleaned or len(cleaned) < 2:
        return f"{category} transaction"
    return cleaned.capitalize()


def handle_transaction(message: str, db, current_user) -> Optional[Dict[str, Any]]:
    """
    Main entrypoint for chat-based transaction processing.
    Parses amount, transaction type, category, date, and description.
    Persists to the database and returns structured response.
    """
    if not message or not message.strip():
        return None

    normalized_text = normalize(message)
    amount = extract_amount(message) or extract_amount(normalized_text)

    if amount is None or amount <= 0:
        return None

    category = detect_category(normalized_text)
    txn_type = detect_txn_type(normalized_text, category)
    txn_date = extract_date(message)
    description = clean_description(message, amount, category)
    icon = CATEGORY_ICONS.get(category, "💳")

    try:
        if txn_type == "expense":
            expense_record = Expense(
                amount=amount,
                category=category,
                description=description,
                date=txn_date,
                user_id=current_user.id,
            )
            db.add(expense_record)
            db.commit()
            db.refresh(expense_record)

            return {
                "type": "text",
                "content": f"✅ {icon} **Expense Added:** ₹{amount:,.2f} under **{category}** ({description})",
                "data": {
                    "id": expense_record.id,
                    "type": "expense",
                    "amount": amount,
                    "category": category,
                    "description": description,
                    "date": txn_date.isoformat(),
                }
            }

        elif txn_type == "income":
            income_record = Income(
                amount=amount,
                source=category if category != "Other" else description,
                date=txn_date,
                user_id=current_user.id,
            )
            db.add(income_record)
            db.commit()
            db.refresh(income_record)

            return {
                "type": "text",
                "content": f"💰 **Income Added:** ₹{amount:,.2f} from **{category}** ({description})",
                "data": {
                    "id": income_record.id,
                    "type": "income",
                    "amount": amount,
                    "source": category,
                    "description": description,
                    "date": txn_date.isoformat(),
                }
            }

    except Exception as e:
        db.rollback()
        return {
            "type": "text",
            "content": f"⚠️ Failed to save transaction: {str(e)}",
            "error": True,
        }

    return None