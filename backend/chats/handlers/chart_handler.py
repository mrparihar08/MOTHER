import re
from sqlalchemy import func

from backend.api.models.vitya import Expense, Income
from backend.api.routes.ai import monthly_trend
from backend.api.routes.vitya import (
    get_expense_graph,
    get_expense_income_trend,
    get_expenses_chart,
)


def contains_any(text: str, words) -> bool:
    return any(word in text for word in words)


def extract_chart_data(text: str):
    pairs = re.findall(
        r'\b([a-zA-Z]+)\b\s*[:=]?\s*(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)',
        text,
    )
    return [
        {"category": category.capitalize(), "amount": float(amount)}
        for category, amount in pairs
    ]


def detect_chart_type(text: str):
    if contains_any(text, ["multi line", "compare", "vs"]):
        return "multi_line"
    if contains_any(text, ["composed", "combined", "mix"]):
        return "composed"
    if "stack" in text:
        return "stacked"
    if "pie" in text:
        return "pie"
    if "donut" in text:
        return "donut"
    if "line" in text:
        return "line_chart"
    if "area" in text:
        return "area"
    if "scatter" in text:
        return "scatter"
    if "radar" in text:
        return "radar"
    if "heatmap" in text:
        return "heatmap"
    if "waterfall" in text:
        return "waterfall"
    return "bar"


def build_trend_chart_data(current_user, db):
    return get_expense_income_trend(current_user=current_user, db=db) or []


def handle_chart_request(message: str, db, current_user):
    text = (message or "").lower().strip()

    custom_data = extract_chart_data(text)
    if len(custom_data) >= 2:
        return {
            "type": detect_chart_type(text),
            "content": custom_data,
        }

    if "scatter" in text:
        trend = build_trend_chart_data(current_user, db)
        scatter_data = [
            {
                "x": item.get("income", 0),
                "y": item.get("expense", 0),
                "name": item.get("month") or item.get("date") or "",
            }
            for item in trend
        ]
        return {"type": "scatter", "content": scatter_data}

    if "radar" in text:
        data = get_expense_graph(current_user=current_user, db=db)
        return {"type": "radar", "content": data or []}

    if "heatmap" in text:
        data = get_expenses_chart(current_user=current_user, db=db)
        return {"type": "heatmap", "content": data or []}

    if "waterfall" in text:
        income = (
            db.query(func.sum(Income.amount))
            .filter(Income.user_id == current_user.id)
            .scalar()
            or 0
        )

        expense = (
            db.query(func.sum(Expense.amount))
            .filter(Expense.user_id == current_user.id)
            .scalar()
            or 0
        )

        data = [
            {"name": "Income", "amount": income},
            {"name": "Expense", "amount": -expense},
            {"name": "Savings", "amount": income - expense},
        ]
        return {"type": "waterfall", "content": data}

    if "area" in text:
        return {"type": "area", "content": build_trend_chart_data(current_user, db)}

    if "stack" in text:
        return {"type": "stacked", "content": build_trend_chart_data(current_user, db)}

    if contains_any(text, ["composed", "combined", "mix"]):
        return {"type": "composed", "content": build_trend_chart_data(current_user, db)}

    if contains_any(text, ["compare", "vs", "multi line"]):
        return {"type": "multi_line", "content": build_trend_chart_data(current_user, db)}

    if "pie" in text or "donut" in text:
        data = get_expense_graph(current_user=current_user, db=db)
        return {"type": detect_chart_type(text), "content": data or []}

    if "line" in text or "trend" in text:
        data = get_expense_income_trend(current_user=current_user, db=db)
        return {"type": "line_chart", "content": data or []}

    if "chart" in text or "graph" in text:
        data = get_expenses_chart(current_user=current_user, db=db)
        return {"type": "bar", "content": data or []}

    return None