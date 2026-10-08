# backend/chats/handlers/action_handler.py
"""
Proactive Task & Autonomous Action Agent Engine for Vitya AI.
Handles:
1. Autonomous Calendar & Meeting Scheduling (DB + Google Calendar 1-Click Sync)
2. Autonomous Task & Todo Management (Priority, Deadlines, Status)
3. Autonomous Email Drafting & Dispatch Preparation (Recipients, Polished Body, Review)
4. Today's Agenda & Daily Routine Briefing
"""

import logging
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.api.models.vitya import CalendarEvent, Task, RecurringSubscription
from backend.chats.services.gemini_service import generate_response

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# NLP Entity & Date-Time Parsers
# ---------------------------------------------------------------------------

WEEKDAY_MAP = {
    "somwar": 0, "monday": 0, "mon": 0,
    "mangalwar": 1, "tuesday": 1, "tue": 1,
    "budhwar": 2, "wednesday": 2, "wed": 2,
    "guruwar": 3, "brihaspatiwar": 3, "thursday": 3, "thu": 3,
    "shukrawar": 4, "friday": 4, "fri": 4,
    "shaniwar": 5, "saturday": 5, "sat": 5,
    "raviwar": 6, "itwar": 6, "sunday": 6, "sun": 6,
}

MONTH_MAP = {
    "jan": 1, "january": 1, "janvari": 1,
    "feb": 2, "february": 2, "farvari": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5, "mai": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9, "sept": 9,
    "oct": 10, "october": 10, "aktubar": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12, "disambar": 12,
}


def parse_date_and_time(text: str) -> Tuple[str, str, str]:
    """
    Parses natural language date and time from query.
    Returns: (date_str: 'YYYY-MM-DD', date_label: 'Tomorrow', time_str: '11:00 AM')
    """
    now = datetime.now()
    t = text.lower()

    # 1. Date Extraction
    date_str = now.strftime("%Y-%m-%d")
    date_label = "Today"

    if "parso" in t or "day after tomorrow" in t:
        target_dt = now + timedelta(days=2)
        date_str = target_dt.strftime("%Y-%m-%d")
        date_label = "Day After Tomorrow"
    elif "kal" in t or "tomorrow" in t:
        target_dt = now + timedelta(days=1)
        date_str = target_dt.strftime("%Y-%m-%d")
        date_label = "Tomorrow"
    elif "aaj" in t or "today" in t:
        date_str = now.strftime("%Y-%m-%d")
        date_label = "Today"
    else:
        # Check explicit day of week
        found_day = False
        for day_name, day_idx in WEEKDAY_MAP.items():
            if re.search(rf"\b{re.escape(day_name)}\b", t):
                curr_idx = now.weekday()
                days_ahead = (day_idx - curr_idx) % 7
                if days_ahead == 0:
                    days_ahead = 7
                target_dt = now + timedelta(days=days_ahead)
                date_str = target_dt.strftime("%Y-%m-%d")
                date_label = day_name.capitalize()
                found_day = True
                break

        if not found_day:
            # Check explicit date pattern e.g. "15 Oct", "10/10/2026", "25th November"
            m_date = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-zA-Z]+)(?:\s+(\d{4}))?\b", t)
            if m_date:
                day_val = int(m_date.group(1))
                mon_str = m_date.group(2).lower()
                year_val = int(m_date.group(3)) if m_date.group(3) else now.year
                if mon_str in MONTH_MAP:
                    try:
                        target_dt = datetime(year_val, MONTH_MAP[mon_str], day_val)
                        date_str = target_dt.strftime("%Y-%m-%d")
                        date_label = target_dt.strftime("%d %b %Y")
                    except Exception:
                        pass

    # 2. Time Extraction
    time_str = "10:00 AM"
    # Check "subah X baje", "shaam X baje", "dopahar X baje", "raat X baje"
    if "subah" in t or "morning" in t:
        m_hr = re.search(r"(\d{1,2})(?::(\d{2}))?", t)
        if m_hr:
            hr = int(m_hr.group(1))
            mn = m_hr.group(2) or "00"
            time_str = f"{hr:02d}:{mn} AM"
    elif "dopahar" in t or "afternoon" in t:
        m_hr = re.search(r"(\d{1,2})(?::(\d{2}))?", t)
        if m_hr:
            hr = int(m_hr.group(1))
            mn = m_hr.group(2) or "00"
            hr = hr if hr == 12 else hr + 12 if hr < 12 else hr
            time_str = f"{hr:02d}:{mn} PM"
    elif "shaam" in t or "evening" in t or "raat" in t or "night" in t:
        m_hr = re.search(r"(\d{1,2})(?::(\d{2}))?", t)
        if m_hr:
            hr = int(m_hr.group(1))
            mn = m_hr.group(2) or "00"
            hr = hr if hr >= 12 else hr + 12
            time_str = f"{hr:02d}:{mn} PM"
    elif re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", t):
        m_time = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", t)
        hr = int(m_time.group(1))
        mn = m_time.group(2) or "00"
        period = m_time.group(3).upper()
        time_str = f"{hr:02d}:{mn} {period}"
    elif "baje" in t:
        m_baje = re.search(r"(\d{1,2})(?::(\d{2}))?\s*baje", t)
        if m_baje:
            hr = int(m_baje.group(1))
            mn = m_baje.group(2) or "00"
            period = "PM" if (1 <= hr <= 7) and "subah" not in t else "AM" if hr <= 12 else "PM"
            time_str = f"{hr:02d}:{mn} {period}"

    return date_str, date_label, time_str


def build_google_calendar_url(title: str, date_str: str, time_str: str, details: str = "") -> str:
    """Generates direct 1-click Google Calendar Add Event link."""
    try:
        dt_start = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M %p")
        dt_end = dt_start + timedelta(hours=1)
        fmt = "%Y%m%dT%H%M%S"
        dates_param = f"{dt_start.strftime(fmt)}/{dt_end.strftime(fmt)}"
    except Exception:
        clean_d = date_str.replace("-", "")
        dates_param = f"{clean_d}T100000/{clean_d}T110000"

    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": dates_param,
        "details": details or f"Scheduled via Vitya AI Assistant",
    }
    return f"https://calendar.google.com/calendar/render?{urllib.parse.urlencode(params)}"


# ---------------------------------------------------------------------------
# Action Classification & Triggers
# ---------------------------------------------------------------------------

CALENDAR_TRIGGERS = [
    "schedule", "meeting", "appointment", "calendar", "event banao",
    "schedule karo", "schedule kar do", "meeting add karo", "event add karo",
    "reminder set karo", "calender", "session schedule"
]

TASK_TRIGGERS = [
    "task add", "add task", "todo add", "add todo", "task create",
    "create task", "task banao", "todo banao", "priority task",
    "complete task", "task complete", "mere tasks", "show tasks", "list tasks",
    "tasks dikhao", "todo list", "tasks list"
]

EMAIL_TRIGGERS = [
    "send email", "email send", "email bhej do", "mail bhej do",
    "email likho", "draft email", "email draft", "mail send karo",
    "proposal email", "client ko mail", "client ko email"
]

AGENDA_TRIGGERS = [
    "aaj ka schedule", "today schedule", "today's schedule", "aaj ke events",
    "today's agenda", "morning briefing", "daily routine", "mera schedule",
    "aaj kya karna hai", "today agenda", "whats my day like"
]


def is_agent_action(message: str) -> bool:
    """Detects if message is an autonomous action (Calendar, Task, Email, Agenda)."""
    if not message:
        return False
    t = message.lower().strip()
    return (
        any(re.search(rf"\b{re.escape(k)}\b", t) for k in CALENDAR_TRIGGERS)
        or any(re.search(rf"\b{re.escape(k)}\b", t) for k in TASK_TRIGGERS)
        or any(re.search(rf"\b{re.escape(k)}\b", t) for k in EMAIL_TRIGGERS)
        or any(k in t for k in AGENDA_TRIGGERS)
        or bool(re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", t) and any(m in t for m in ["email", "mail", "send", "bhej"]))
    )


# ---------------------------------------------------------------------------
# Action Handlers
# ---------------------------------------------------------------------------

def handle_calendar_action(text: str, db: Session, current_user: Any) -> Dict[str, Any]:
    """
    Schedules and manages calendar events directly in the database.
    """
    user_id = getattr(current_user, "id", None)
    t = text.lower()

    # 1. Query: List Calendar Events
    if any(q in t for q in ["show events", "list events", "mere events", "upcoming events", "events dikhao", "calendar dikhao"]):
        events = db.query(CalendarEvent).filter(CalendarEvent.user_id == user_id).order_by(CalendarEvent.date.asc()).limit(10).all()
        if not events:
            return {
                "type": "text",
                "content": "📅 Aapke calendar me abhi koi upcoming events scheduled nahi hain.\n\nAap bol sakte hain: *'Kal subah 11 baje Team Sync meeting schedule karo'*.",
                "intent": "CALENDAR_EVENT",
            }
        lines = ["📅 **Aapke Upcoming Calendar Events:**\n"]
        for ev in events:
            time_tag = f"⏰ `{ev.time}`" if ev.time else ""
            lines.append(f"• **{ev.title}** — 📆 `{ev.date}` {time_tag}")
            if ev.description:
                lines.append(f"  _{ev.description}_")
        return {
            "type": "text",
            "content": "\n".join(lines),
            "intent": "CALENDAR_EVENT",
        }

    # 2. Command: Create & Schedule Event
    date_str, date_label, time_str = parse_date_and_time(text)

    # Clean Title extraction
    title = re.sub(
        r"(?i)^(?:schedule(?:\s+a)?\s+meeting|meeting(?:\s+schedule)?|schedule|add\s+event|event\s+banao|schedule\s+karo|schedule\s+kar\s+do|appointment\s+set\s+karo|reminder\s+set\s+karo)\s*(?:for|with|of|:)?\s*",
        "",
        text.strip(),
    ).strip()
    # Strip timing words from title
    title = re.sub(r"(?i)\b(?:kal|aaj|parso|tomorrow|today|subah|shaam|dopahar|raat|morning|evening|afternoon|\d{1,2}(?::\d{2})?\s*(?:am|pm|baje)|baje|schedule\s+karo|schedule\s+kar\s+do|meeting\s+karo|ko|me|par|tak)\b", "", title).strip()
    title = re.sub(r"^[,\s\.\-:]+|[,\s\.\-:]+$", "", title) or "Scheduled Meeting / Discussion"

    # Save to Database
    event = CalendarEvent(
        title=title,
        date=date_str,
        time=time_str,
        description=f"Autonomous event scheduled via Vitya AI ({date_label})",
        user_id=user_id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    gcal_url = build_google_calendar_url(title, date_str, time_str, event.description)

    card_content = (
        f"✅ **Event Scheduled Successfully!** 📅\n\n"
        f"• **Title:** **{title}**\n"
        f"• **Date:** 📆 `{date_str}` ({date_label})\n"
        f"• **Time:** ⏰ `{time_str}`\n"
        f"• **Status:** 🟢 Confirmed in Vitya Calendar\n\n"
        f"🔗 [**➕ Add to Google Calendar**]({gcal_url})"
    )

    return {
        "type": "calendar_event",
        "content": card_content,
        "event_id": event.id,
        "title": title,
        "date": date_str,
        "time": time_str,
        "gcal_url": gcal_url,
        "intent": "CALENDAR_EVENT",
        "actions": ["copy", "voice"],
    }


def handle_task_action(text: str, db: Session, current_user: Any) -> Dict[str, Any]:
    """
    Creates and lists todo tasks with priority and status directly in database.
    """
    user_id = getattr(current_user, "id", None)
    t = text.lower()

    # 1. Query: List Tasks
    if any(q in t for q in ["show tasks", "list tasks", "mere tasks", "tasks dikhao", "todo list", "pending tasks", "tasks list"]):
        tasks = db.query(Task).filter(Task.user_id == user_id).order_by(Task.id.desc()).limit(15).all()
        if not tasks:
            return {
                "type": "text",
                "content": "📋 Aapki **Task / Todo List** bilkul clear hai! Koi pending task nahi hai.\n\nNaya task add karne ke liye bolen: *'Friday tak GST return file karne ka high priority task add karo'*.",
                "intent": "TASK_MANAGEMENT",
            }
        lines = [f"📋 **Aapke Active Tasks ({len(tasks)}):**\n"]
        for task in tasks:
            lines.append(f"• [ ] **{task.title}** (ID: `#{task.id}`)")
        return {
            "type": "text",
            "content": "\n".join(lines),
            "intent": "TASK_MANAGEMENT",
        }

    # 2. Command: Create Task
    priority = "🔴 High Priority" if any(p in t for p in ["high", "urgent", "zaruri", "urgent priority", "important"]) else "🟡 Medium Priority" if "medium" in t else "🟢 Normal Priority"
    date_str, date_label, _ = parse_date_and_time(text)

    # Clean title
    task_title = re.sub(
        r"(?i)^(?:add\s+task|task\s+add(?:\s+karo)?|create\s+task|task\s+banao|todo\s+add|todo\s+banao)\s*(?:for|to|of|:)?\s*",
        "",
        text.strip(),
    ).strip()
    task_title = re.sub(r"(?i)\b(?:task\s+add\s+karo|task\s+add\s+kar\s+do|ka\s+task\s+add\s+karo|high\s+priority\s+task|urgent\s+task|task|todo)\b", "", task_title).strip()
    task_title = re.sub(r"^[,\s\.\-:]+|[,\s\.\-:]+$", "", task_title) or "Pending Action Item"

    formatted_title = f"{task_title} [{priority}] (Due: {date_label})"

    task = Task(
        title=formatted_title,
        user_id=user_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    card_content = (
        f"📋 **Task Registered Successfully!**\n\n"
        f"• **Task:** **{task_title}**\n"
        f"• **Priority:** {priority}\n"
        f"• **Target Deadline:** 🎯 `{date_str}` ({date_label})\n"
        f"• **Status:** ⏳ Pending Execution (Task ID: `#{task.id}`)"
    )

    return {
        "type": "task_item",
        "content": card_content,
        "task_id": task.id,
        "title": task_title,
        "priority": priority,
        "due_date": date_str,
        "intent": "TASK_MANAGEMENT",
    }


from backend.chats.services.email_service import EmailDispatcher


def handle_email_action(text: str, db: Session, current_user: Any) -> Dict[str, Any]:
    """
    Parses recipient, subject and crafts professional polished email draft or dispatches via SMTP/API.
    """
    user_name = getattr(current_user, "name", "User")
    t = text.strip()
    t_lower = t.lower()

    # Extract email address
    email_match = re.search(r"\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,})\b", t)
    recipient = email_match.group(1) if email_match else "recipient@example.com"

    # Extract topic / intent
    clean_topic = re.sub(r"(?i)^(?:send\s+email|email\s+send|email\s+bhej\s+do|mail\s+bhej\s+do|email\s+likho|draft\s+email)\s*(?:to|for|ko|:)?\s*", "", t)
    clean_topic = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "", clean_topic).strip()
    clean_topic = clean_topic or "Business Proposal and Project Update"

    dispatcher = EmailDispatcher()
    subject, body = dispatcher.draft_email_content(clean_topic, recipient, sender_name=user_name)

    # Check for Autonomous Send trigger
    is_autonomous_send = any(k in t_lower for k in ["seedhe bhej do", "confirm send", "auto send", "direct send", "send now", "turant bhej do"])

    dispatch_res = None
    if is_autonomous_send and dispatcher.is_live_configured():
        dispatch_res = dispatcher.dispatch(recipient, subject, body, from_name=f"{user_name} (via Vitya AI)")

    if dispatch_res and dispatch_res.get("status") == "DELIVERED":
        card_content = (
            f"🚀 **Email Dispatched Successfully!** ✉️\n\n"
            f"• **To:** `{recipient}`\n"
            f"• **Subject:** **{subject}**\n"
            f"• **Provider:** `{dispatch_res.get('provider')}`\n"
            f"• **Status:** 🟢 Delivered\n\n"
            f"```text\n{body}\n```"
        )
        return {
            "type": "email_dispatched",
            "content": card_content,
            "recipient": recipient,
            "subject": subject,
            "status": "DELIVERED",
            "intent": "EMAIL_DISPATCH",
        }

    mailto_link = f"mailto:{recipient}?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(body)}"

    card_content = (
        f"✉️ **Autonomous Email Draft Ready!**\n\n"
        f"• **To:** `{recipient}`\n"
        f"• **Subject:** **{subject}**\n\n"
        f"```text\n{body}\n```\n"
        f"💡 *Action:* Click below to review and dispatch directly from your email client:\n"
        f"👉 [**📤 Open in Email Client / Send Now**]({mailto_link})\n\n"
        f"*(Direct Auto-Send karne ke liye message me 'confirm send' ya 'seedhe bhej do' likhein)*"
    )

    return {
        "type": "email_draft",
        "content": card_content,
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "mailto_url": mailto_link,
        "intent": "EMAIL_DISPATCH",
    }


from backend.chats.services.proactive_daemon import ProactiveDaemon


def handle_daily_agenda(
    db: Session,
    current_user: Any,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    client_ip: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generates an integrated Daily Routine / Morning Briefing via ProactiveDaemon.
    """
    daemon = ProactiveDaemon()
    return daemon.generate_morning_briefing(current_user, db, lat=lat, lon=lon, client_ip=client_ip)


def handle_agent_action(
    message: str,
    db: Session,
    current_user: Any,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    client_ip: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Top-level router for Autonomous Agent Actions.
    """
    if not message:
        return None

    raw_text = message.strip()
    t = raw_text.lower()

    # 1. Agenda & Daily Schedule Briefing
    if any(k in t for k in AGENDA_TRIGGERS):
        return handle_daily_agenda(db, current_user, lat=latitude, lon=longitude, client_ip=client_ip)

    # 2. Email Drafting & Dispatch
    if any(re.search(rf"\b{re.escape(k)}\b", t) for k in EMAIL_TRIGGERS) or (
        "@" in t and any(m in t for m in ["email", "mail", "send", "bhej"])
    ):
        return handle_email_action(raw_text, db, current_user)

    # 3. Calendar & Meeting Scheduling
    if any(re.search(rf"\b{re.escape(k)}\b", t) for k in CALENDAR_TRIGGERS):
        return handle_calendar_action(raw_text, db, current_user)

    # 4. Task & Todo Management
    if any(re.search(rf"\b{re.escape(k)}\b", t) for k in TASK_TRIGGERS):
        return handle_task_action(raw_text, db, current_user)

    return None
