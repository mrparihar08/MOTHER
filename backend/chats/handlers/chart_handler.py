import re
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from backend.api.models.vitya import Expense, Income

logger = logging.getLogger(__name__)

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

VISUALIZATION_KEYWORDS = [
    "chart", "graph", "plot", "visualize", "visualise", "visualization", "diagram",
    "bar chart", "pie chart", "line chart", "donut chart", "doughnut", "area chart",
    "scatter", "radar", "heatmap", "waterfall",
    "show karo", "graph me dikhao", "chart me show karo", "graph banao", "chart banao",
    "chart dikhao", "graph dikhao", "percentage chart", "data dikhao",
    "data ko chart me dikhao", "plot karo", "dikhao chart", "bich aaye",
    "distribution", "stats", "breakdown", "data visualize"
]


def contains_any(text: str, words: List[str]) -> bool:
    """Check if any word or phrase in the list is present in the text."""
    t = text.lower()
    return any(w in t for w in words)


def is_visualization_request(text: str) -> bool:
    """
    Check if a query has data visualization intent:
    - Contains explicit visualization keywords
    - Or contains a parseable structured dataset with multiple categories
    """
    if not text or not text.strip():
        return False
    t = text.lower().strip()
    if any(k in t for k in VISUALIZATION_KEYWORDS):
        return True
    _, items = parse_dataset(text)
    return len(items) >= 2


def _parse_amount(raw_num: str, raw_unit: Optional[str] = None) -> float:
    """Convert numeric string and optional multiplier to float."""
    cleaned = raw_num.replace(",", "").strip()
    val = float(cleaned)
    if raw_unit:
        unit = raw_unit.lower().strip()
        val *= MULTIPLIER_MAP.get(unit, 1)
    return val


def clean_label(label: str) -> str:
    """Clean category label, removing noise words while preserving meaningful words and grade letters."""
    noise = {
        'chart', 'graph', 'plot', 'diagram', 'total', 'mere', 'school', 'me', 'mein',
        'hai', 'h', 'aaye', 'or', 'aur', 'and', 'ka', 'ki', 'ke', 'bich', 'in', 'of',
        'for', 'the', 'bhi', 'se', 'ko', 'par', 'pe'
    }
    cleaned_words = []
    for w in re.split(r'[\s_]+', label.strip()):
        wl = w.lower()
        if wl in noise:
            continue
        if wl in {'a', 'an'} and (w.isupper() or len(label.strip().split()) == 1):
            cleaned_words.append(w.upper())
        elif wl in {'a', 'an'}:
            continue
        else:
            cleaned_words.append(w.title())
    return ' '.join(cleaned_words)


def strip_command_noise(text: str) -> str:
    """Strip common command prefixes and suffixes (e.g., 'pie chart banao:', 'ise chart me show karo')."""
    t = text.strip()
    # Strip prefixes
    t = re.sub(
        r'^(?:please\s+)?(?:draw|make|show|plot|create|banao|dikhao|karo|me|mein)?\s*(?:a\s+)?(?:pie|bar|line|donut|doughnut|area|scatter|radar|custom)?\s*(?:chart|graph|plot|diagram)\s*(?:banao|dikhao|karo|me|mein|show)?\s*[:=]?\s*',
        '',
        t,
        flags=re.I
    )
    # Strip suffixes
    t = re.sub(
        r'\s*(?:ka|ki|ke|ko|ise|inhe|isko)?\s*(?:bar|pie|line|donut|area|scatter)?\s*(?:chart|graph|plot|diagram)?\s*(?:me|mein)?\s*(?:banao|dikhao|show\s+karo|plot\s+karo|visualize\s+karo|karo|bana\s+do|dikha\s+do)\s*[.!]?$',
        '',
        t,
        flags=re.I
    )
    return t.strip()


def parse_dataset(text: str) -> Tuple[Optional[int], List[Dict[str, Any]]]:
    """
    Extract structured dataset items and optional stated total from English / Hinglish text.
    Handles:
    1. Percentage distributions: '10 ke 50 % or 15 ke 60 or 8 ke 70 or 5 ke 80 or 2 ke 90 %'
    2. Key-Value pairs: 'Maths: 80, Science: 90, English: 70' or 'boys 25, girls 15'
    3. Amount-Category pairs: '5 students A grade, 10 B grade' or '20 pass, 25 fail'
    4. Time/General categories: 'Food: 500, Travel: 300'
    """
    raw_text = text.strip()

    # 1. Total extraction (e.g., 'Total 50 bachche', 'mere school me 40 bachche h', 'total: 100')
    total_match = re.search(
        r'(?:total\s*(?:of|is|hai|students?|bachche|bachcho)?\s*[:=]?\s*(\d+)(?:\s*(?:bachche|bachcho|students?|log|people|items?))?|'
        r'\b(\d+)\s*(?:bachcho|bachche|students?|log)\s*(?:me\s*se|mein\s*se|h\b|hain\b)|'
        r'\b(?:school|class|batch|group)\s*(?:me|mein)\s*(\d+)\s*(?:bachche|students?)|'
        r'total\s*[:=]?\s*(\d+))',
        raw_text,
        re.I
    )
    stated_total = None
    cleaned_body = raw_text
    if total_match:
        for g in total_match.groups():
            if g and g.isdigit():
                stated_total = int(g)
                break
        if stated_total is not None:
            cleaned_body = re.sub(re.escape(total_match.group(0)) + r'\s*[:=,]?', ' ', cleaned_body, flags=re.I)

    cleaned_body = strip_command_noise(cleaned_body)

    # 2. Hinglish percentage group pattern: '<count> ke <pct>%' or '<count> ke <pct>' or '<count> scored <pct>%'
    pct_dist_pattern = r'(\b\d+)\s*(?:ke|wale|par|scored|got)\s*(\d+(?:\.\d+)?)\s*(?:%|percent|pratishat|\s*ke\s*bich|\s*bich)?'
    p1 = re.findall(pct_dist_pattern, cleaned_body, re.I)
    if len(p1) >= 2:
        res = []
        for count_str, pct_str in p1:
            res.append({'category': f'{pct_str}%', 'amount': float(count_str)})
        return stated_total, res

    # 3. Explicit Category: Amount / Category Amount across clauses
    clauses = re.split(r'[,;\n]+|\b(?:aur|and|or)\b', cleaned_body, flags=re.I)
    cat_amt_res = []
    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue

        # Check: <Category> [: =]? <Amount>
        m_cat_first = re.search(
            r'^([a-zA-Z\s]{1,25})\s*[:=]?\s*(?:₹|rs\.?|inr|\$)?\s*(\d+(?:\.\d+)?)\s*(?:k|l|lac|lakh|cr|crore|%|/-|rs|rupees|bucks|marks|students?|bachche)?$',
            clause,
            re.I
        )
        if m_cat_first:
            cat = clean_label(m_cat_first.group(1))
            val = float(m_cat_first.group(2))
            if cat and len(cat) >= 1 and val >= 0:
                cat_amt_res.append({'category': cat, 'amount': val})
            continue

        # Check: <Amount> <Category> (e.g. '5 students A grade', '20 pass', '500 on Food')
        m_amt_first = re.search(
            r'^(?:₹|rs\.?|inr|\$)?\s*(\d+(?:\.\d+)?)\s*(?:k|l|lac|lakh|cr|crore|%|/-|rs|rupees|students?|bachche|on|for|in|ka|ki|ke)?\s*([a-zA-Z\s]{1,25})$',
            clause,
            re.I
        )
        if m_amt_first:
            val = float(m_amt_first.group(1))
            cat = clean_label(m_amt_first.group(2))
            if cat and len(cat) >= 1 and cat.lower() not in ['students', 'bachche', 'log', 'people']:
                cat_amt_res.append({'category': cat, 'amount': val})
            continue

    if len(cat_amt_res) >= 2:
        return stated_total, cat_amt_res

    # 4. Fallback: general regex for 'Category Amount' or 'Category: Amount'
    fallback_matches = re.findall(r'([a-zA-Z]{2,15})\s*[:=]?\s*(\d+(?:\.\d+)?)', cleaned_body)
    fallback_res = []
    for cat, val in fallback_matches:
        c = clean_label(cat)
        if c and len(c) >= 2:
            fallback_res.append({'category': c, 'amount': float(val)})
    if len(fallback_res) >= 2:
        return stated_total, fallback_res

    return stated_total, []


def extract_chart_data(text: str) -> List[Dict[str, Any]]:
    """Legacy wrapper for extract_chart_data, returning only dataset items."""
    _, items = parse_dataset(text)
    return items


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
    text = (message or "").strip()
    if not text:
        return None

    # Intent check: ensure the message actually asks for a chart or data visualization
    if not is_visualization_request(text):
        return None

    # 1. Custom inline user data (e.g., '10 ke 50 % or 15 ke 60', 'Maths: 80, Science: 90')
    stated_total, custom_data = parse_dataset(text)
    if len(custom_data) >= 2:
        chart_type = detect_chart_type(text)
        total_sum = sum(d["amount"] for d in custom_data)
        
        # Validation note if user provided a total
        dataset_status = "valid"
        validation_note = ""
        if stated_total is not None:
            if stated_total == int(total_sum):
                validation_note = f" (Total: {stated_total} verified ✅)"
            else:
                dataset_status = "mismatch"
                validation_note = f"\n\n⚠️ **Note:** Aapne total **{stated_total}** bataya tha, lekin categories ka total **{int(total_sum) if total_sum.is_integer() else total_sum}** ban raha hai."

        msg_content = f"📊 Maine aapke data ka **{chart_type.capitalize()} Chart** bana diya hai.{validation_note}"
        title = "Data Visualization"
        if "school" in text.lower() or "bachche" in text.lower() or "student" in text.lower():
            title = "Student Distribution"
        elif "marks" in text.lower() or "score" in text.lower() or "grade" in text.lower():
            title = "Performance Breakdown"
        else:
            title = f"Custom {chart_type.capitalize()} Chart"

        return {
            "type": chart_type,
            "content": custom_data,
            "title": title,
            "message": msg_content,
            "text_summary": msg_content,
            "intent": "DATA_VISUALIZATION",
            "is_currency": False,
            "metadata": {
                "stated_total": stated_total,
                "total_sum": total_sum,
                "dataset_status": dataset_status,
            }
        }

    # Extract time filtering if requested
    year_filter, month_filter = _get_time_filter(text)
    chart_type = detect_chart_type(text)

    try:
        # 2. Scatter plot (Income vs Expense correlation across months)
        if chart_type == "scatter" or "scatter" in text.lower():
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
            return {
                "type": "scatter",
                "content": scatter_data,
                "title": "Income vs Expense Correlation",
                "intent": "DATA_VISUALIZATION",
            }

        # 3. Waterfall (Cashflow: Total Income -> Total Expenses -> Net Savings)
        if chart_type == "waterfall" or "waterfall" in text.lower() or "cash flow" in text.lower():
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
            return {
                "type": "waterfall",
                "content": waterfall_data,
                "title": "Cash Flow Waterfall",
                "intent": "DATA_VISUALIZATION",
            }

        # 4. Multi-series / Trend Charts (Area, Stacked, Composed, Multi-line, Line Trend)
        if chart_type in ["area", "stacked", "composed", "multi_line", "line_chart"]:
            trend_data = _fetch_trend_data(current_user, db)
            if not trend_data["income"] and not trend_data["expense"]:
                return {
                    "type": "text",
                    "content": "📈 Trend chart ke liye monthly data nahi mila. Kripya expenses aur income add karein."
                }
            title_map = {
                "line_chart": "Monthly Expense & Income Trend",
                "multi_line": "Income vs Expense Trend",
                "area": "Monthly Spending Area Trend",
                "composed": "Monthly Financial Breakdown",
                "stacked": "Stacked Monthly Distribution",
            }
            return {
                "type": chart_type,
                "content": trend_data,
                "title": title_map.get(chart_type, "Monthly Trend Analytics"),
                "intent": "DATA_VISUALIZATION",
            }

        # 5. Category-based Charts (Pie, Donut, Radar, Heatmap, Bar)
        category_data = _fetch_category_expenses(current_user, db, year=year_filter, month=month_filter)
        if not category_data:
            period_str = f" ({month_filter}/{year_filter})" if month_filter else " in the selected period" if year_filter else ""
            return {
                "type": "text",
                "content": f"📊 Abhi tak koi expense data nahi mila{period_str}. Expense log karne ke liye jaise: 'spent 500 on dinner' likhein."
            }

        title_map = {
            "pie": "Expense Category Distribution",
            "donut": "Expense Breakdown (Donut)",
            "radar": "Spending Category Radar",
            "heatmap": "Expense Density Heatmap",
            "bar": "Expense by Category",
        }
        return {
            "type": chart_type,
            "content": category_data,
            "title": title_map.get(chart_type, "Expense Analytics"),
            "intent": "DATA_VISUALIZATION",
        }

    except Exception as e:
        logger.exception("Error in handle_chart_request: %s", e)
        return {
            "type": "text",
            "content": f"⚠️ Chart generate karte waqt error aaya: {str(e)}"
        }