import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from backend.api.models.vitya import Expense, Income
from backend.chats.utils.categories import CATEGORY_KEYWORDS

# Multiplier mapping for numbers (e.g., 1.5k, 20k, 2 lakh)
MULTIPLIER_MAP = {
    "k": 1_000,
    "l": 100_000,
    "lac": 100_000,
    "lakh": 100_000,
    "lakhs": 100_000,
    "cr": 10_000_000,
    "crore": 10_000_000,
}


def contains_any(text: str, words: List[str]) -> bool:
    """Check if any word in the list is present in the text."""
    return any(w in text for w in words)


def _parse_amount(raw_num: str, raw_unit: Optional[str] = None) -> float:
    """Convert numeric string and optional multiplier to float."""
    cleaned = raw_num.replace(",", "").strip()
    val = float(cleaned)
    if raw_unit:
        unit = raw_unit.lower().strip()
        val *= MULTIPLIER_MAP.get(unit, 1)
    return val


def _clean_chart_category(cat: str) -> str:
    """Strip common command prefixes and noise words from category name."""
    c = cat.strip()
    c = re.sub(
        r"^(?:draw|make|show|plot|create|please|banao|dikhao|ka|ki|ke|for|of|in|the|a|an|\s)+\b",
        "",
        c,
        flags=re.IGNORECASE,
    ).strip()
    c = re.sub(
        r"\b(?:chart|graph|plot|pie|donut|bar|line|trend|diagram)\b",
        "",
        c,
        flags=re.IGNORECASE,
    ).strip()
    c = re.sub(
        r"^(?:for|of|in|on|ka|ki|ke|\s)+",
        "",
        c,
        flags=re.IGNORECASE,
    ).strip()
    return c.title()


def extract_chart_data(text: str) -> List[Dict[str, Any]]:
    """
    Extract category-amount pairs from user message.
    Supports formats:
    - 'Food: 500, Travel: 300, Shopping: 1200'
    - 'Food = 1.5k, Gym = 2k, Rent = 15k'
    - 'Food 500, Travel 300, Rent 1000'
    - '500 on Food, 300 for Travel, 1000 on Rent'
    """
    results: List[Dict[str, Any]] = []

    # 1. Format: Category [: =]? ₹?Amount (e.g. "Food: ₹500", "Fast Food = 1.5k", "Travel 300")
    cat_amount_pattern = (
        r"\b([a-zA-Z\s]{2,25}?)\s*[:=]?\s*(?:₹|rs\.?|inr|\$)?\s*"
        r"([\d,]+(?:\.\d+)?)\s*(k|l|lac|lakh|cr|crore|/-|rs|rupees|bucks)?(?=[,\n;]|$|\s+[a-zA-Z])"
    )
    matches = re.findall(cat_amount_pattern, text, re.IGNORECASE)
    for cat, amt_str, unit in matches:
        cat_clean = _clean_chart_category(cat)
        if not cat_clean or len(cat_clean) < 2:
            continue
        try:
            amt = _parse_amount(amt_str, unit)
            if amt > 0:
                results.append({"category": cat_clean, "amount": amt})
        except ValueError:
            continue

    if len(results) >= 2:
        return results

    # 2. Format: Amount on/for Category (e.g. "500 on Food, 300 on Travel")
    amount_cat_pattern = (
        r"(?:₹|rs\.?|inr|\$)?\s*([\d,]+(?:\.\d+)?)\s*(k|l|lac|lakh|cr|crore)?\s*(?:on|for|in|ka|ki|ke)?\s*"
        r"([a-zA-Z\s]{2,25}?)(?=[,\n;]|$)"
    )
    alt_matches = re.findall(amount_cat_pattern, text, re.IGNORECASE)
    alt_results: List[Dict[str, Any]] = []
    for amt_str, unit, cat in alt_matches:
        cat_clean = _clean_chart_category(cat)
        if not cat_clean or len(cat_clean) < 2:
            continue
        try:
            amt = _parse_amount(amt_str, unit)
            if amt > 0:
                alt_results.append({"category": cat_clean, "amount": amt})
        except ValueError:
            continue

    return alt_results if len(alt_results) >= 2 else []


def detect_chart_type(text: str) -> str:
    """Detect chart visualizer type with comprehensive Hinglish & English keywords."""
    t = text.lower()

    if contains_any(t, ["multi line", "multiline", "compare", "vs", "versus", "comparison", "income vs expense"]):
        return "multi_line"
    if contains_any(t, ["composed", "combined", "mix", "combo", "bar and line"]):
        return "composed"
    if contains_any(t, ["stack", "stacked", "split bar"]):
        return "stacked"
    if contains_any(t, ["pie", "donut", "doughnut", "circle", "gola", "hissa", "batwara", "share", "distribution"]):
        return "donut" if "donut" in t or "doughnut" in t else "pie"
    if contains_any(t, ["line", "trend", "timeline", "growth", "progress", "monthly", "month-wise", "history"]):
        return "line_chart"
    if contains_any(t, ["area", "filled area", "shaded"]):
        return "area"
    if contains_any(t, ["scatter", "correlation", "dot plot"]):
        return "scatter"
    if contains_any(t, ["radar", "spider", "web chart"]):
        return "radar"
    if contains_any(t, ["heatmap", "heat map", "matrix", "density"]):
        return "heatmap"
    if contains_any(t, ["waterfall", "cash flow", "cashflow", "inflow outflow", "net flow", "savings flow"]):
        return "waterfall"

    return "bar"


def _get_time_filter(text: str) -> Tuple[Optional[int], Optional[int]]:
    """Extract year and month filter from message if requested (e.g. 'this month', 'last month')."""
    now = datetime.now(timezone.utc)
    t = text.lower()

    if any(k in t for k in ["this month", "current month", "iss mahine", "is mahine", "aaj ka mahina"]):
        return now.year, now.month
    if any(k in t for k in ["last month", "previous month", "pichle mahine", "beete mahine"]):
        last_month = now.month - 1 if now.month > 1 else 12
        year = now.year if now.month > 1 else now.year - 1
        return year, last_month
    if any(k in t for k in ["this year", "iss saal", "is saal", "current year"]):
        return now.year, None

    return None, None


def _fetch_category_expenses(current_user, db: Session, year: Optional[int] = None, month: Optional[int] = None) -> List[Dict[str, Any]]:
    """Direct database query for expense totals grouped by category."""
    query = db.query(
        Expense.category,
        func.sum(Expense.amount).label("amount")
    ).filter(Expense.user_id == current_user.id)

    if year:
        query = query.filter(extract("year", Expense.date) == year)
    if month:
        query = query.filter(extract("month", Expense.date) == month)

    data = query.group_by(Expense.category).all()
    return [{"category": cat or "Other", "amount": float(amt or 0)} for cat, amt in data]


def _fetch_trend_data(current_user, db: Session) -> Dict[str, List[Dict[str, Any]]]:
    """Direct database query for monthly income and expense trends."""
    income_data = db.query(
        extract("year", Income.date).label("year"),
        extract("month", Income.date).label("month"),
        func.sum(Income.amount).label("total")
    ).filter(
        Income.user_id == current_user.id
    ).group_by(
        extract("year", Income.date),
        extract("month", Income.date)
    ).order_by(
        extract("year", Income.date),
        extract("month", Income.date)
    ).all()

    expense_data = db.query(
        extract("year", Expense.date).label("year"),
        extract("month", Expense.date).label("month"),
        func.sum(Expense.amount).label("total")
    ).filter(
        Expense.user_id == current_user.id
    ).group_by(
        extract("year", Expense.date),
        extract("month", Expense.date)
    ).order_by(
        extract("year", Expense.date),
        extract("month", Expense.date)
    ).all()

    return {
        "income": [
            {"month": f"{int(yr):04d}-{int(mo):02d}-01", "amount": float(tot or 0)}
            for yr, mo, tot in income_data if yr is not None and mo is not None
        ],
        "expense": [
            {"month": f"{int(yr):04d}-{int(mo):02d}-01", "amount": float(tot or 0)}
            for yr, mo, tot in expense_data if yr is not None and mo is not None
        ]
    }


def handle_chart_request(message: str, db: Session, current_user) -> Optional[Dict[str, Any]]:
    """
    Main entrypoint for chat chart requests.
    Supports user custom inline data or real user financial stats from the database.
    """
    text = (message or "").lower().strip()
    if not text:
        return None

    # Intent check: ensure the message actually asks for a chart or data visualization
    chart_keywords = [
        "chart", "graph", "plot", "pie", "donut", "doughnut", "bar", "line",
        "trend", "scatter", "radar", "heatmap", "waterfall", "compare", "vs",
        "breakdown", "distribution", "stats", "visualize", "dikhao"
    ]
    if not any(w in text for w in chart_keywords):
        return None

    # 1. Custom inline user data (e.g., 'Make a pie chart: Food 500, Gym 1000, Rent 5000')
    custom_data = extract_chart_data(text)
    if len(custom_data) >= 2:
        chart_type = detect_chart_type(text)
        return {
            "type": chart_type,
            "content": custom_data,
            "title": f"Custom {chart_type.capitalize()} Chart",
        }

    # Extract time filtering if requested
    year_filter, month_filter = _get_time_filter(text)
    chart_type = detect_chart_type(text)

    try:
        # 2. Scatter plot (Income vs Expense correlation across months)
        if chart_type == "scatter" or "scatter" in text:
            trend = _fetch_trend_data(current_user, db)
            income_map = {item.get("month"): item.get("amount", 0) for item in trend.get("income", [])}
            expense_map = {item.get("month"): item.get("amount", 0) for item in trend.get("expense", [])}
            all_months = sorted(set(income_map.keys()) | set(expense_map.keys()))

            if not all_months:
                return {
                    "type": "text",
                    "content": "📊 Scatter chart ke liye data nahi mila. Pehle kuch Income aur Expenses add karein."
                }

            scatter_data = [
                {
                    "x": income_map.get(m, 0),
                    "y": expense_map.get(m, 0),
                    "name": m or "",
                }
                for m in all_months
            ]
            return {"type": "scatter", "content": scatter_data}

        # 3. Waterfall (Cashflow: Total Income -> Total Expenses -> Net Savings)
        if chart_type == "waterfall" or "waterfall" in text or "cash flow" in text:
            income_total = (
                db.query(func.sum(Income.amount))
                .filter(Income.user_id == current_user.id)
                .scalar() or 0.0
            )
            expense_total = (
                db.query(func.sum(Expense.amount))
                .filter(Expense.user_id == current_user.id)
                .scalar() or 0.0
            )

            if income_total == 0 and expense_total == 0:
                return {
                    "type": "text",
                    "content": "📊 Waterfall chart ke liye balance data nahi mila. Transactions add karein."
                }

            waterfall_data = [
                {"name": "Total Income", "amount": float(income_total)},
                {"name": "Total Expenses", "amount": -float(expense_total)},
                {"name": "Net Savings", "amount": float(income_total - expense_total)},
            ]
            return {"type": "waterfall", "content": waterfall_data}

        # 4. Multi-series / Trend Charts (Area, Stacked, Composed, Multi-line, Line Trend)
        if chart_type in ["area", "stacked", "composed", "multi_line", "line_chart"]:
            trend_data = _fetch_trend_data(current_user, db)
            if not trend_data["income"] and not trend_data["expense"]:
                return {
                    "type": "text",
                    "content": "📈 Trend chart ke liye monthly data nahi mila. Kripya expenses aur income add karein."
                }
            return {"type": chart_type, "content": trend_data}

        # 5. Category-based Charts (Pie, Donut, Radar, Heatmap, Bar)
        category_data = _fetch_category_expenses(current_user, db, year=year_filter, month=month_filter)
        if not category_data:
            period_str = f" ({month_filter}/{year_filter})" if month_filter else " in the selected period" if year_filter else ""
            return {
                "type": "text",
                "content": f"📊 Abhi tak koi expense data nahi mila{period_str}. Expense log karne ke liye jaise: 'spent 500 on dinner' likhein."
            }

        return {
            "type": chart_type,
            "content": category_data,
        }

    except Exception as e:
        return {
            "type": "text",
            "content": f"⚠️ Chart generate karte waqt error aaya: {str(e)}"
        }