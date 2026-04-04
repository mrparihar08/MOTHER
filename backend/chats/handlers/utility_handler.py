import re
from datetime import datetime
from sqlalchemy import func

from backend.api.models.vitya import Expense, Income
from backend.api.routes.ai import budget_plan, monthly_trend
from backend.chats.utils.media_and_exports import generate_qr, generate_barcode


def handle_utility_request(message: str, db, current_user):
    text = (message or "").lower().strip()

    if "qr" in text or "qr code" in text:
        qr_text = re.sub(r"\b(qr|code)\b", "", text).strip()
        if not qr_text:
            qr_text = "Hello from Vitya"
        img = generate_qr(qr_text)
        return {"type": "qr", "content": img}

    if "barcode" in text or "barcodes" in text:
        barcode_text = re.sub(r"\b(barcode|barcodes)\b", "", text).strip()
        if not barcode_text:
            barcode_text = "123456789"
        img = generate_barcode(barcode_text)
        return {"type": "barcode", "content": img}

    if "total expense" in text:
        total = (
            db.query(func.sum(Expense.amount))
            .filter(Expense.user_id == current_user.id)
            .scalar()
            or 0
        )
        return {"type": "text", "content": f"Total expense: ₹{total}"}

    if "total income" in text:
        total = (
            db.query(func.sum(Income.amount))
            .filter(Income.user_id == current_user.id)
            .scalar()
            or 0
        )
        return {"type": "text", "content": f"Total income: ₹{total}"}

    if "budget" in text:
        data = budget_plan(current_user=current_user, db=db)
        summary = data.get("summary", {})
        return {
            "type": "text",
            "content": (
                f"Income: {summary.get('total_income', 0)}\n"
                f"Expense: {summary.get('total_expenses', 0)}\n"
                f"Savings: {summary.get('suggested_savings', 0)}"
            ),
        }

    if "monthly" in text and ("report" in text or "trend" in text):
        data = monthly_trend(current_user=current_user, db=db)

        if not data:
            return {"type": "text", "content": "No data available 📊"}

        try:
            valid_items = []
            for item in data:
                try:
                    date_obj = datetime.strptime(item["month"], "%Y-%m")
                    amount_val = float(item["amount"])
                    valid_items.append((date_obj, amount_val))
                except Exception:
                    continue

            if not valid_items:
                return {"type": "text", "content": "No valid monthly data available 📊"}

            valid_items.sort(key=lambda x: x[0])

            response = "📊 Monthly Expense Report\n--------------------------\n"
            total = 0
            highest = ("", float("-inf"))
            lowest = ("", float("inf"))

            for date_obj, amount_val in valid_items:
                month_name = date_obj.strftime("%b %Y")
                total += amount_val

                if amount_val > highest[1]:
                    highest = (month_name, amount_val)
                if amount_val < lowest[1]:
                    lowest = (month_name, amount_val)

                response += f"{month_name}: ₹{amount_val}\n"

            avg = total / len(valid_items)
            response += "--------------------------\n"
            response += f"Total: ₹{round(total, 2)}\n"
            response += f"Average: ₹{round(avg, 2)}\n"
            response += f"\n📈 Highest: {highest[0]} (₹{highest[1]})"
            response += f"\n📉 Lowest: {lowest[0]} (₹{lowest[1]})"

            return {"type": "text", "content": response}

        except Exception:
            return {"type": "text", "content": "Error generating report ❌"}

    return None