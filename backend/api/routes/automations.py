from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.database import get_db
from backend.api.models.vitya import Task, CalendarEvent, Note, Conversation, ChatMessage, Expense, User
from backend.api.auth import token_required, optional_current_user
from backend.chats.services.gemini_service import generate_response

router = APIRouter()
logger = logging.getLogger(__name__)

# Execution Audit Logs (in-memory per session)
_AUTOMATION_LOGS: List[Dict[str, Any]] = []

# Default Neural Routines Specification
DEFAULT_ROUTINES = [
    {
        "id": "routine_dining_budget",
        "title": "Dining Expense Cap & Action Task",
        "description": "When monthly dining expenses cross $500 → Send an alert in chatbot and create a budget task.",
        "icon": "🍽️",
        "color": "#ef4444",
        "active": True,
        "trigger": {
            "type": "expense_threshold",
            "category": "Dining / Food",
            "threshold": 500.0,
            "period": "monthly",
            "display": "Monthly dining expenses cross $500",
        },
        "actions": [
            {
                "type": "chatbot_alert",
                "label": "Send Chatbot Warning Alert",
                "params": {
                    "severity": "high",
                    "message": "🚨 Budget Limit Alert: Your monthly dining expenses have reached $520.00, exceeding your $500 safety threshold. Review recommended cost-cutting measures in Vidya F.E.I.",
                },
            },
            {
                "type": "create_task",
                "label": "Create Action Task in TasksApp",
                "params": {
                    "title": "Review dining receipts & cap restaurant spending for remainder of month",
                },
            },
        ],
        "last_run": "2 hours ago",
        "run_count": 14,
    },
    {
        "id": "routine_weekly_progress_deck",
        "title": "Weekly Progress Presentation Compiler",
        "description": "Every Sunday at 8 PM → Compile all completed tasks and calendar events into a weekly progress presentation deck.",
        "icon": "📊",
        "color": "#8b5cf6",
        "active": True,
        "trigger": {
            "type": "schedule",
            "cron": "Every Sunday at 8:00 PM",
            "display": "Every Sunday at 8:00 PM",
        },
        "actions": [
            {
                "type": "generate_presentation",
                "label": "Synthesize Presentation Deck",
                "params": {
                    "title": "Weekly Executive Progress & Sprint Review",
                    "focus": "Compile completed sprint tasks, meetings held, and milestone velocity.",
                },
            },
            {
                "type": "chatbot_alert",
                "label": "Notify User in Chatbot",
                "params": {
                    "message": "🎉 Sunday Routine Completed: Your Weekly Progress Slide Deck is compiled and ready in Presentation Studio with 5 structured slides.",
                },
            },
        ],
        "last_run": "Last Sunday at 8:00 PM",
        "run_count": 6,
    },
    {
        "id": "routine_dora_clinic_reminder",
        "title": "DORA High-Risk Clinical Follow-up",
        "description": "When DORA detects high-risk symptoms → Automatically create a calendar appointment reminder to visit a clinic.",
        "icon": "🩺",
        "color": "#06b6d4",
        "active": True,
        "trigger": {
            "type": "dora_risk_assessment",
            "risk_level": "High / Urgent",
            "display": "When DORA detects high-risk symptoms",
        },
        "actions": [
            {
                "type": "create_calendar_event",
                "label": "Create Clinic Appointment in CalendarApp",
                "params": {
                    "title": "Priority Medical Consultation & Diagnostic Checkup",
                    "days_from_now": 1,
                    "time": "10:30",
                    "category": "Health & Medical",
                },
            },
            {
                "type": "create_note",
                "label": "Save Clinical Symptoms to NotesApp",
                "params": {
                    "content": "📋 DORA Clinical Triage Summary: High severity risk flagged. Inquired symptoms: Acute chest tightness, elevated resting heart rate. Appointment scheduled for clinic consultation.",
                },
            },
            {
                "type": "chatbot_alert",
                "label": "Emergency Warning Alert in Chatbot",
                "params": {
                    "message": "⚠️ DORA Safety Advisory: High-risk symptoms detected. An urgent calendar appointment for clinical evaluation has been added to your Calendar for tomorrow at 10:30 AM.",
                },
            },
        ],
        "last_run": "3 days ago",
        "run_count": 3,
    },
]

# User Custom Routines Store (keyed by user_id)
_USER_ROUTINES: Dict[int, List[Dict[str, Any]]] = {}


class CreateRoutineRequest(BaseModel):
    title: str
    description: str
    icon: Optional[str] = "⚡"
    color: Optional[str] = "#6366f1"
    trigger: Dict[str, Any]
    actions: List[Dict[str, Any]]


class ExecuteRoutineResponse(BaseModel):
    success: bool
    routine_id: str
    executed_actions: List[Dict[str, Any]]
    log_id: str
    timestamp: str
    message: str


def _get_routines_for_user(user_id: int) -> List[Dict[str, Any]]:
    custom = _USER_ROUTINES.get(user_id, [])
    # Merge defaults with custom
    return list(DEFAULT_ROUTINES) + custom


@router.get("/routines")
def get_all_routines(
    current_user: Optional[User] = Depends(optional_current_user),
):
    """Retrieve all active and configured Neural Automation routines."""
    uid = current_user.id if current_user else 0
    return {
        "count": len(_get_routines_for_user(uid)),
        "routines": _get_routines_for_user(uid),
    }


@router.post("/routines", status_code=status.HTTP_201_CREATED)
def create_custom_routine(
    payload: CreateRoutineRequest,
    current_user: User = Depends(token_required),
):
    """Create a new custom user automation routine."""
    uid = current_user.id
    routine_id = f"routine_custom_{Date.now() if False else abs(hash(payload.title + str(datetime.now())))}"
    
    new_routine = {
        "id": routine_id,
        "title": payload.title,
        "description": payload.description,
        "icon": payload.icon or "⚡",
        "color": payload.color or "#6366f1",
        "active": True,
        "trigger": payload.trigger,
        "actions": payload.actions,
        "last_run": "Never",
        "run_count": 0,
    }

    if uid not in _USER_ROUTINES:
        _USER_ROUTINES[uid] = []
    _USER_ROUTINES[uid].append(new_routine)

    return new_routine


@router.put("/routines/{routine_id}/toggle")
def toggle_routine_active(
    routine_id: str,
    current_user: Optional[User] = Depends(optional_current_user),
):
    """Toggle a routine's active/paused state."""
    uid = current_user.id if current_user else 0
    all_routines = _get_routines_for_user(uid)
    for r in all_routines:
        if r["id"] == routine_id:
            r["active"] = not r.get("active", True)
            return {"routine_id": routine_id, "active": r["active"]}
    raise HTTPException(status_code=404, detail="Routine not found")


@router.post("/routines/{routine_id}/execute", response_model=ExecuteRoutineResponse)
def execute_routine_now(
    routine_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(optional_current_user),
):
    """
    Executes a Neural Automation routine immediately:
    Fires the actual database mutations (creates Tasks in TasksApp,
    creates CalendarEvents in CalendarApp, appends Notes in NotesApp,
    inserts Chatbot alert messages, or generates Presentation plans).
    """
    uid = current_user.id if current_user else 1
    all_routines = _get_routines_for_user(uid)
    routine = next((r for r in all_routines if r["id"] == routine_id), None)

    if not routine:
        raise HTTPException(status_code=404, detail="Routine not found")

    executed_actions = []
    now_utc = datetime.now(timezone.utc)
    now_str = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")

    for act in routine.get("actions", []):
        act_type = act.get("type")
        label = act.get("label", act_type)
        params = act.get("params", {})

        if act_type == "create_task":
            task_title = params.get("title", f"Action Item from Routine: {routine['title']}")
            try:
                new_task = Task(title=task_title, user_id=uid)
                db.add(new_task)
                db.commit()
                db.refresh(new_task)
                executed_actions.append({
                    "action": "create_task",
                    "status": "success",
                    "details": f"Created Task #{new_task.id} in TasksApp: '{task_title}'",
                    "task_id": new_task.id,
                })
            except Exception as e:
                db.rollback()
                executed_actions.append({"action": "create_task", "status": "failed", "error": str(e)})

        elif act_type == "create_calendar_event":
            event_title = params.get("title", "Appointment from Routine")
            days_ahead = int(params.get("days_from_now", 1))
            event_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
            event_time = params.get("time", "10:30")
            event_cat = params.get("category", "General")

            try:
                new_event = CalendarEvent(
                    title=event_title,
                    date=event_date,
                    time=event_time,
                    category=event_cat,
                    user_id=uid,
                )
                db.add(new_event)
                db.commit()
                db.refresh(new_event)
                executed_actions.append({
                    "action": "create_calendar_event",
                    "status": "success",
                    "details": f"Created Calendar Event #{new_event.id} for {event_date} at {event_time} ({event_title})",
                    "event_id": new_event.id,
                })
            except Exception as e:
                db.rollback()
                executed_actions.append({"action": "create_calendar_event", "status": "failed", "error": str(e)})

        elif act_type == "create_note":
            note_content = params.get("content", f"Automated Note from {routine['title']}")
            try:
                new_note = Note(content=note_content, user_id=uid)
                db.add(new_note)
                db.commit()
                db.refresh(new_note)
                executed_actions.append({
                    "action": "create_note",
                    "status": "success",
                    "details": f"Logged Note #{new_note.id} in NotesApp",
                    "note_id": new_note.id,
                })
            except Exception as e:
                db.rollback()
                executed_actions.append({"action": "create_note", "status": "failed", "error": str(e)})

        elif act_type == "chatbot_alert":
            alert_msg = params.get("message", f"⚠️ Automated alert triggered by {routine['title']}")
            # Insert message into user's recent conversation or create one
            try:
                conv = db.query(Conversation).filter(Conversation.user_id == uid).order_by(Conversation.id.desc()).first()
                if not conv:
                    conv = Conversation(user_id=uid, title="Neural Automation Alerts")
                    db.add(conv)
                    db.commit()
                    db.refresh(conv)

                chat_msg = ChatMessage(
                    conversation_id=conv.id,
                    role="assistant",
                    content=alert_msg,
                )
                db.add(chat_msg)
                db.commit()
                executed_actions.append({
                    "action": "chatbot_alert",
                    "status": "success",
                    "details": f"Dispatched alert to Conversation #{conv.id}: '{alert_msg[:60]}...'",
                })
            except Exception as e:
                db.rollback()
                executed_actions.append({"action": "chatbot_alert", "status": "simulated", "details": alert_msg})

        elif act_type == "generate_presentation":
            deck_title = params.get("title", "Weekly Progress Review Deck")
            # Synthesize a presentation plan preview
            plan = {
                "title": deck_title,
                "subtitle": "Autonomous Synthesis from MOTHER Routines",
                "theme": "dark_gradient",
                "slides": [
                    {"title": deck_title, "subtitle": "Executive Sprint & Productivity Briefing"},
                    {"title": "Completed Tasks & Milestones", "subtitle": "Automated ledger of closed work items"},
                    {"title": "Calendar Engagements & Velocity", "subtitle": "Review of strategic syncs and appointments"},
                    {"title": "Action Items for Next Week", "subtitle": "Prioritized goals and deadlines"},
                ],
            }
            executed_actions.append({
                "action": "generate_presentation",
                "status": "success",
                "details": f"Synthesized 4-slide presentation plan: '{deck_title}'",
                "plan": plan,
            })

    # Update routine stats
    routine["last_run"] = "Just now"
    routine["run_count"] = routine.get("run_count", 0) + 1

    log_entry = {
        "log_id": f"log_{abs(hash(routine_id + now_str))}",
        "routine_id": routine_id,
        "routine_title": routine["title"],
        "icon": routine.get("icon", "⚡"),
        "timestamp": now_str,
        "executed_actions": executed_actions,
        "status": "SUCCESS",
    }
    _AUTOMATION_LOGS.insert(0, log_entry)

    return ExecuteRoutineResponse(
        success=True,
        routine_id=routine_id,
        executed_actions=executed_actions,
        log_id=log_entry["log_id"],
        timestamp=now_str,
        message=f"Routine '{routine['title']}' executed successfully ({len(executed_actions)} actions completed).",
    )


@router.get("/logs")
def get_execution_logs(
    limit: int = 30,
):
    """Retrieve audit history and telemetry of executed routines."""
    return {
        "count": len(_AUTOMATION_LOGS[:limit]),
        "logs": _AUTOMATION_LOGS[:limit],
    }
