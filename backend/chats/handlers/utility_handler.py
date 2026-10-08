import re
import math
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from backend.api.models.vitya import Expense, Income, Budget, RecurringSubscription, SavingsGoal
from backend.finance.analysis.analyse import budget_plan, monthly_trend
from backend.api.services.ai_service import compute_financial_health_score
from backend.chats.utils.media_and_exports import generate_qr, generate_barcode
from backend.chats.utils.openweather_util import (
    OpenWeatherClient,
    OpenWeatherError,
    extract_weather_target,
    format_weather_markdown,
)


def _safe_eval_math(expr: str) -> Optional[float]:
    """Safely calculate simple mathematical expressions without eval()."""
    cleaned = expr.replace("x", "*").replace("X", "*").replace("^", "**").strip()
    if not re.match(r"^[\d\s\+\-\*\/\(\)\.\%]+$", cleaned):
        return None
    try:
        # Limited namespace for safe execution
        allowed_names = {"__builtins__": None, "math": math}
        res = eval(cleaned, allowed_names, {})
        return float(res) if isinstance(res, (int, float)) else None
    except Exception:
        return None


def _clean_weather_city(text: str) -> str:
    """Extract clean city name from natural weather query."""
    return extract_weather_target(text) or ""


def handle_utility_request(
    message: str,
    db: Session,
    current_user: Any,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    city: Optional[str] = None,
    client_ip: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Handles utility commands & finance quick actions:
    1. QR Code & Barcode generation
    2. Weather & temperature queries
    3. Total expenses, income, available balance
    4. Smart budget & savings plan overview
    5. Monthly expense breakdown & financial report
    6. Recurring Subscriptions (List & Manage)
    7. Savings Goals (Progress & Targets)
    8. Financial Health Score & Audit
    9. Inline math calculator
    """
    raw_text = (message or "").strip()
    text = raw_text.lower()
    if not text:
        return None

    now = datetime.now(timezone.utc)
    user_id = getattr(current_user, "id", None)

    # 1. MATH CALCULATOR (e.g. "calc 50000 * 0.18" or "calculate 25000 - 12000")
    if text.startswith("calc ") or text.startswith("/calc ") or text.startswith("calculate "):
        math_expr = re.sub(r"(?i)^/?(?:calc|calculate)\s*", "", raw_text).strip()
        result = _safe_eval_math(math_expr)
        if result is not None:
            return {
                "type": "text",
                "content": f"🔢 **Calculation:** `{math_expr}` = **₹{result:,.2f}**" if result.is_integer() is False else f"🔢 **Calculation:** `{math_expr}` = **{int(result):,}**",
            }

    # 2. QR CODE GENERATOR
    if text.startswith("/qr") or "qr code" in text or text.startswith("qr ") or "make qr" in text or "generate qr" in text:
        qr_data = re.sub(r"(?i)^(?:/qr|qr(?:\s+code)?|generate\s+qr(?:\s+code)?|make\s+qr(?:\s+code)?)\s*(?:for|of|with|:)?\s*", "", raw_text).strip()
        if not qr_data or len(qr_data) < 2:
            qr_data = f"Vitya Finance Profile - {getattr(current_user, 'name', 'User')}"

        img_b64 = generate_qr(qr_data)
        return {
            "type": "qr",
            "content": img_b64,
            "data_url": f"data:image/png;base64,{img_b64}",
            "caption": f"📱 QR Code generated for: `{qr_data}`",
        }

    # 3. BARCODE GENERATOR
    if text.startswith("/barcode") or "barcode" in text or "barcodes" in text:
        barcode_data = re.sub(r"(?i)^(?:/barcode|barcode|barcodes|generate\s+barcode|make\s+barcode)\s*(?:for|of|with|:)?\s*", "", raw_text).strip()
        if not barcode_data:
            barcode_data = str(int(now.timestamp()))

        clean_code = re.sub(r"[^\w\-]", "", barcode_data) or "1234567890"
        img_b64 = generate_barcode(clean_code)
        return {
            "type": "barcode",
            "content": img_b64,
            "data_url": f"data:image/png;base64,{img_b64}",
            "caption": f"📊 Barcode generated for: `{clean_code}`",
        }

    # 4. WEATHER INFORMATION
    if any(k in text for k in ["weather", "temperature", "mausam", "barish", "forecast", "climate", "temp "]) or text.endswith(" temp") or text == "temp":
        try:
            target_city = city or extract_weather_target(raw_text)
            weather_client = OpenWeatherClient()
            result = weather_client.get_weather_text_for_chatbot(
                city=target_city,
                lat=latitude,
                lon=longitude,
                client_ip=client_ip,
            )
            return {
                "type": "text",
                "content": result,
                "intent": "WEATHER",
            }
        except OpenWeatherError as e:
            return {"type": "text", "content": f"🌦️ Weather lookup: {str(e)}", "intent": "WEATHER"}
        except Exception as e:
            return {"type": "text", "content": f"🌦️ Mausam jankari error: {str(e)}", "intent": "WEATHER"}

    # 5. RECURRING SUBSCRIPTIONS (e.g. "my subscriptions", "netflix renew kab hoga")
    if any(k in text for k in ["subscription", "subscriptions", "recurring", "monthly bill", "netflix renew", "spotify bill"]):
        subs = db.query(RecurringSubscription).filter(RecurringSubscription.user_id == user_id).all()
        if not subs:
            return {
                "type": "text",
                "content": "📅 Aapki koi active **Recurring Subscriptions** registered nahi hain. Aap Netflix, Prime, Spotify, Gym jaise memberships add kar sakte hain.",
            }

        total_sub_monthly = sum(s.amount for s in subs if s.status == "active")
        sub_lines = [
            f"📅 **Your Active Subscriptions ({len(subs)}):**\n",
            "| Service | Amount | Cycle | Next Due | Status |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
        for s in subs:
            status_icon = "🟢 Active" if s.status == "active" else "⏸️ Paused"
            due_str = s.next_due_date or "N/A"
            sub_lines.append(f"| **{s.name}** | ₹{s.amount:,.2f} | {s.billing_cycle.title()} | {due_str} | {status_icon} |")

        sub_lines.append(f"\n• **Total Recurring Cost:** ₹{total_sub_monthly:,.2f}/month")
        return {"type": "text", "content": "\n".join(sub_lines)}

    # 6. SAVINGS GOALS (e.g. "my savings goals", "goals progress", "bachat ke goals")
    if any(k in text for k in ["savings goal", "savings goals", "my goals", "goal progress", "bachat goal", "bachat ke goals"]):
        goals = db.query(SavingsGoal).filter(SavingsGoal.user_id == user_id).all()
        if not goals:
            return {
                "type": "text",
                "content": "🎯 Aapne abhi tak koi **Savings Goal** set nahi kiya hai. Jaise: *Emergency Fund*, *New Car*, ya *Vacation Trip* ka target set kar sakte hain.",
            }

        goal_lines = ["🎯 **Your Savings Goals Progress:**\n"]
        for g in goals:
            pct = (g.current_amount / g.target_amount * 100) if g.target_amount > 0 else 0
            bar_len = int(pct // 10)
            progress_bar = "🟩" * min(bar_len, 10) + "⬜" * max(0, 10 - bar_len)
            status_tag = "✅ Completed" if g.is_completed or pct >= 100 else f"{pct:.1f}%"
            goal_lines.append(
                f"• **{g.title}** ({g.category or 'General'})\n"
                f"  `{progress_bar}` **{status_tag}**\n"
                f"  Saved: ₹{g.current_amount:,.2f} / ₹{g.target_amount:,.2f} (Target: {g.target_date or 'Ongoing'})\n"
            )

        return {"type": "text", "content": "\n".join(goal_lines)}

    # 7. FINANCIAL HEALTH SCORE & AUDIT
    if any(k in text for k in ["health score", "financial health", "my score", "financial audit", "audit score"]):
        try:
            health_data = compute_financial_health_score(current_user, db)
            score = health_data.score
            rating = health_data.rating
            breakdown = health_data.breakdown

            health_lines = [
                f"🩺 **Financial Health Assessment:**\n",
                f"• **Overall Score:** **{score}/100** ({rating})",
                f"• **Savings Health:** {breakdown.savings_score:.1f}/30",
                f"• **Expense Control:** {breakdown.expense_ratio_score:.1f}/25",
                f"• **Budget Discipline:** {breakdown.budget_adherence_score:.1f}/20",
                f"• **Emergency Buffer:** {breakdown.emergency_buffer_score:.1f}/15",
                f"• **Stability:** {breakdown.cashflow_stability_score:.1f}/10\n",
            ]
            if health_data.recommendations:
                health_lines.append("**💡 Top Recommendations:**")
                for rec in health_data.recommendations[:3]:
                    health_lines.append(f"• {rec}")

            return {"type": "text", "content": "\n".join(health_lines)}
        except Exception as e:
            return {"type": "text", "content": f"🩺 Health score calculate karne ke liye thoda aur transaction data add karein."}

    # 8. FINANCIAL SNAPSHOT: TOTAL EXPENSES
    if any(k in text for k in ["total expense", "total spend", "kul kharcha", "mera kharcha", "kitna kharch hua"]):
        is_this_month = any(m in text for m in ["this month", "iss mahine", "is mahine", "current month"])
        query = db.query(func.sum(Expense.amount)).filter(Expense.user_id == user_id)
        if is_this_month:
            query = query.filter(
                extract("year", Expense.date) == now.year,
                extract("month", Expense.date) == now.month,
            )

        total_expense = query.scalar() or 0.0
        period_label = "This Month" if is_this_month else "All Time"
        return {
            "type": "text",
            "content": f"💳 **Total Expenses ({period_label}):** ₹{float(total_expense):,.2f}",
        }

    # 9. FINANCIAL SNAPSHOT: TOTAL INCOME
    if any(k in text for k in ["total income", "total earning", "kul aamdani", "kitna kamaya", "total earnings"]):
        is_this_month = any(m in text for m in ["this month", "iss mahine", "is mahine", "current month"])
        query = db.query(func.sum(Income.amount)).filter(Income.user_id == user_id)
        if is_this_month:
            query = query.filter(
                extract("year", Income.date) == now.year,
                extract("month", Income.date) == now.month,
            )

        total_income = query.scalar() or 0.0
        period_label = "This Month" if is_this_month else "All Time"
        return {
            "type": "text",
            "content": f"💰 **Total Income ({period_label}):** ₹{float(total_income):,.2f}",
        }

    # 10. FINANCIAL SNAPSHOT: BALANCE & NET SAVINGS
    if any(k in text for k in ["balance", "available balance", "net savings", "kitna bacha", "bachat", "my balance"]):
        total_income = db.query(func.sum(Income.amount)).filter(Income.user_id == user_id).scalar() or 0.0
        total_expense = db.query(func.sum(Expense.amount)).filter(Expense.user_id == user_id).scalar() or 0.0
        net_balance = float(total_income) - float(total_expense)
        balance_icon = "🟢" if net_balance >= 0 else "🔴"

        return {
            "type": "text",
            "content": (
                f"💼 **Financial Summary:**\n\n"
                f"• **Total Income:** ₹{float(total_income):,.2f}\n"
                f"• **Total Expense:** ₹{float(total_expense):,.2f}\n"
                f"• **Available Balance:** {balance_icon} **₹{net_balance:,.2f}**"
            ),
        }

    # 11. BUDGET OVERVIEW & HEALTH
    if any(k in text for k in ["budget plan", "budget status", "budget overview", "budget alert", "mera budget"]) or text == "budget":
        try:
            data = budget_plan(current_user=current_user, db=db)
            summary = data.get("summary", {})
            plan_items = data.get("budget_plan", [])

            lines = [
                "📊 **Smart Budget & Savings Plan:**\n",
                f"• **Total Income:** ₹{summary.get('total_income', 0):,.2f}",
                f"• **Total Expenses:** ₹{summary.get('total_expenses', 0):,.2f}",
                f"• **Usable Funds:** ₹{summary.get('usable_funds', 0):,.2f}",
                f"• **Suggested Savings:** ₹{summary.get('suggested_savings', 0):,.2f} ({int(summary.get('savings_rate', 0.2) * 100)}%)\n",
            ]

            if plan_items:
                lines.append("**Category Limits:**")
                for p in plan_items[:5]:
                    status_emoji = "🔴" if p.get("status") == "overspending" else "🟢"
                    lines.append(f"• {status_emoji} **{p.get('category')}**: Spent ₹{p.get('previous_spending', 0):,.2f} / Suggested Limit ₹{p.get('suggested_budget', 0):,.2f}")

            return {"type": "text", "content": "\n".join(lines)}

        except Exception as e:
            return {
                "type": "text",
                "content": "📊 Budget plan generate karne ke liye thoda aur expense/income data add karein.",
            }

    # 12. MONTHLY EXPENSE REPORT & BREAKDOWN
    if ("monthly" in text and any(k in text for k in ["report", "trend", "summary", "hisab", "kharcha"])) or text in ["monthly report", "monthly trend"]:
        data = monthly_trend(current_user=current_user, db=db)
        if not data:
            return {"type": "text", "content": "📊 Monthly report ke liye data available nahi hai. Pehle kuch expenses log karein."}

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
                return {"type": "text", "content": "📊 Monthly data valid nahi mila."}

            valid_items.sort(key=lambda x: x[0])

            total = sum(amt for _, amt in valid_items)
            avg = total / len(valid_items)
            highest = max(valid_items, key=lambda x: x[1])
            lowest = min(valid_items, key=lambda x: x[1])

            report_lines = [
                "📊 **Monthly Expense Breakdown:**\n",
                "| Month | Expense Amount |",
                "| :--- | :--- |",
            ]
            for date_obj, amount_val in valid_items:
                month_name = date_obj.strftime("%B %Y")
                report_lines.append(f"| {month_name} | ₹{amount_val:,.2f} |")

            report_lines.append(f"\n• **Total Spent:** ₹{total:,.2f}")
            report_lines.append(f"• **Monthly Average:** ₹{avg:,.2f}")
            report_lines.append(f"• 📈 **Peak Month:** {highest[0].strftime('%B %Y')} (₹{highest[1]:,.2f})")
            report_lines.append(f"• 📉 **Lowest Month:** {lowest[0].strftime('%B %Y')} (₹{lowest[1]:,.2f})")

            return {"type": "text", "content": "\n".join(report_lines)}

        except Exception as e:
            return {"type": "text", "content": f"⚠️ Report generate karte waqt error: {str(e)}"}

    return None