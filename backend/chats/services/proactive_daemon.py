# backend/chats/services/proactive_daemon.py
"""
Proactive Daemon & Daily Morning Briefing Engine for Vitya AI.
Aggregates:
1. Live Local Weather
2. Today's Scheduled Meetings & Calendar Events
3. Priority Pending Action Items & Tasks
4. Proactive Subscription & Bill Due Date Alerts
5. Budget Overspending Threshold Warnings
6. Contextual Motivational & Financial Wisdom Tips
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from backend.api.models.vitya import CalendarEvent, Task, RecurringSubscription, Budget, Expense
from backend.chats.utils.openweather_util import OpenWeatherClient, WeatherResult

logger = logging.getLogger(__name__)


class ProactiveDaemon:
    """
    Background Intelligence & Proactive Briefing Engine.
    """

    def __init__(self) -> None:
        self.weather_client = OpenWeatherClient()

    def get_live_weather(
        self,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        client_ip: Optional[str] = None,
    ) -> Optional[WeatherResult]:
        """Fetches real-time weather for briefing."""
        try:
            return self.weather_client.get_realtime_weather(lat=lat, lon=lon, client_ip=client_ip)
        except Exception as e:
            logger.debug("Briefing weather fetch error: %s", e)
            return None

    def get_today_events(self, user_id: int, db: Session, date_str: str) -> List[CalendarEvent]:
        """Retrieves today's calendar events."""
        if not user_id:
            return []
        try:
            return (
                db.query(CalendarEvent)
                .filter(CalendarEvent.user_id == user_id, CalendarEvent.date == date_str)
                .order_by(CalendarEvent.time.asc())
                .all()
            )
        except Exception as e:
            logger.warning("Error fetching today's events: %s", e)
            return []

    def get_pending_tasks(self, user_id: int, db: Session, limit: int = 5) -> List[Task]:
        """Retrieves active pending tasks."""
        if not user_id:
            return []
        try:
            return db.query(Task).filter(Task.user_id == user_id).order_by(Task.id.desc()).limit(limit).all()
        except Exception as e:
            logger.warning("Error fetching pending tasks: %s", e)
            return []

    def get_subscription_alerts(self, user_id: int, db: Session) -> List[Dict[str, Any]]:
        """
        Scans for recurring subscriptions due in the next 72 hours.
        """
        if not user_id:
            return []
        alerts = []
        try:
            subs = db.query(RecurringSubscription).filter(
                RecurringSubscription.user_id == user_id,
                RecurringSubscription.status == "active",
            ).all()

            today = datetime.now().date()
            for sub in subs:
                if sub.next_due_date:
                    try:
                        # Attempt standard date parsing
                        due_clean = sub.next_due_date.strip()
                        due_dt = None
                        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
                            try:
                                due_dt = datetime.strptime(due_clean, fmt).date()
                                break
                            except ValueError:
                                continue

                        if due_dt:
                            days_diff = (due_dt - today).days
                            if 0 <= days_diff <= 3:
                                urgency = "TODAY" if days_diff == 0 else "TOMORROW" if days_diff == 1 else f"in {days_diff} days"
                                alerts.append({
                                    "name": sub.name,
                                    "amount": sub.amount,
                                    "due_date": sub.next_due_date,
                                    "urgency": urgency,
                                })
                    except Exception:
                        pass
        except Exception as e:
            logger.warning("Error scanning subscription alerts: %s", e)

        return alerts

    def get_budget_alerts(self, user_id: int, db: Session) -> List[Dict[str, Any]]:
        """
        Detects budget categories that have exceeded 80% or 100% of their monthly limit.
        """
        if not user_id:
            return []
        alerts = []
        try:
            now = datetime.now()
            budgets = db.query(Budget).filter(Budget.user_id == user_id).all()
            for b in budgets:
                spent = (
                    db.query(func.sum(Expense.amount))
                    .filter(
                        Expense.user_id == user_id,
                        Expense.category.ilike(f"%{b.category}%"),
                        extract("year", Expense.date) == now.year,
                        extract("month", Expense.date) == now.month,
                    )
                    .scalar()
                    or 0.0
                )
                if b.monthly_limit > 0:
                    pct = (spent / b.monthly_limit) * 100
                    if pct >= 80:
                        alerts.append({
                            "category": b.category,
                            "spent": float(spent),
                            "limit": float(b.monthly_limit),
                            "pct": round(pct, 1),
                            "is_exceeded": pct >= 100,
                        })
        except Exception as e:
            logger.warning("Error checking budget alerts: %s", e)

        return alerts

    def generate_morning_briefing(
        self,
        current_user: Any,
        db: Session,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        client_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generates the master Morning Briefing & Proactive Agenda card.
        """
        user_id = getattr(current_user, "id", None)
        user_name = getattr(current_user, "name", None) or getattr(current_user, "username", "Friend")
        today = datetime.now()
        today_str = today.strftime("%Y-%m-%d")
        today_display = today.strftime("%A, %d %B %Y")

        weather = self.get_live_weather(lat=lat, lon=lon, client_ip=client_ip)
        events = self.get_today_events(user_id, db, today_str)
        tasks = self.get_pending_tasks(user_id, db)
        sub_alerts = self.get_subscription_alerts(user_id, db)
        budget_alerts = self.get_budget_alerts(user_id, db)

        lines = [
            f"🌅 **Good Morning, {user_name}!** ☕\n"
            f"📆 **Today's Overview:** `{today_display}`\n"
        ]

        # 1. Weather Snapshot
        if weather:
            loc_label = f"{weather.city}, {weather.region or weather.country}".strip(", ")
            lines.append(
                f"🌤️ **Local Weather ({loc_label}):**\n"
                f"• **{weather.temperature:.1f}°C** ({weather.description} {weather.icon}), Humidity {weather.humidity}%, Wind {weather.wind_speed:.1f} km/h\n"
            )

        # 2. Meetings & Events Timeline
        lines.append(f"📅 **Scheduled Meetings ({len(events)}):**")
        if events:
            for ev in events:
                time_badge = f"⏰ `{ev.time}`" if ev.time else "⏰ All Day"
                lines.append(f"• **{ev.title}** ({time_badge})")
        else:
            lines.append("• *Aaj koi meeting scheduled nahi hai. Focus time open hai!* 🎯")

        # 3. Action Items
        lines.append(f"\n📋 **Priority Action Items ({len(tasks)} Pending):**")
        if tasks:
            for t in tasks:
                lines.append(f"• [ ] {t.title}")
        else:
            lines.append("• *Aapki todo list bilkul clear hai!* 🎉")

        # 4. Proactive Bill & Subscription Alerts
        if sub_alerts:
            lines.append(f"\n🔔 **Upcoming Bill & Subscription Alerts:**")
            for sa in sub_alerts:
                lines.append(f"• 💳 **{sa['name']}** due **{sa['urgency']}** (₹{sa['amount']:,.2f})")

        # 5. Budget Threshold Alerts
        if budget_alerts:
            lines.append(f"\n⚠️ **Budget Spend Warnings:**")
            for ba in budget_alerts:
                tag = "🔴 **OVER LIMIT**" if ba["is_exceeded"] else "🟡 **80%+ Spent**"
                lines.append(f"• {tag} `{ba['category']}`: ₹{ba['spent']:,.2f} / ₹{ba['limit']:,.2f} ({ba['pct']}%)")

        # 6. Daily Wisdom / AI Tip
        tips = [
            "Apne top 2 important tasks pehle complete karein.",
            "Roz subah 10 minute planning aapka poora din save kar sakti hai.",
            "Emergency fund buffer hamesha 3 mahine ke expenses ke barabar rakhein.",
            "Har meeting ke baad action items note karna productivity 2x kar deta hai.",
        ]
        chosen_tip = tips[today.day % len(tips)]
        lines.append(f"\n💡 *Vitya Focus Tip: {chosen_tip}*")

        card_content = "\n".join(lines)

        return {
            "type": "daily_agenda",
            "content": card_content,
            "events_count": len(events),
            "tasks_count": len(tasks),
            "sub_alerts_count": len(sub_alerts),
            "budget_alerts_count": len(budget_alerts),
            "weather": {
                "city": weather.city if weather else None,
                "temp": weather.temperature if weather else None,
                "desc": weather.description if weather else None,
            } if weather else None,
            "intent": "AGENDA_BRIEFING",
        }
