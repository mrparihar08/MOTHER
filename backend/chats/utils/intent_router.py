# backend/chats/utils/intent_router.py
"""
Context-Aware Intent Classification & Response Routing Engine for Vitya AI.
Ensures appropriate dispatch and context-aware disclaimers across all query types.
"""

import re
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum


class Intent(str, Enum):
    GREETING = "GREETING"
    CASUAL_CONVERSATION = "CASUAL_CONVERSATION"
    FINANCE = "FINANCE"
    EXPENSE = "EXPENSE"
    INCOME = "INCOME"
    BUDGET = "BUDGET"
    ANALYTICS = "ANALYTICS"
    HEALTH = "HEALTH"
    WEATHER = "WEATHER"
    IMAGE_ANALYSIS = "IMAGE_ANALYSIS"
    DOCUMENT_ANALYSIS = "DOCUMENT_ANALYSIS"
    CHART_ANALYSIS = "CHART_ANALYSIS"
    DATA_VISUALIZATION = "DATA_VISUALIZATION"
    ACTION_CALENDAR = "CALENDAR_EVENT"
    ACTION_TASK = "TASK_MANAGEMENT"
    ACTION_EMAIL = "EMAIL_DISPATCH"
    ACTION_AGENDA = "AGENDA_BRIEFING"
    NEWS = "NEWS"
    WIKIPEDIA = "WIKIPEDIA"
    GENERAL_KNOWLEDGE = "GENERAL_KNOWLEDGE"
    TASK = "TASK"
    UNKNOWN = "UNKNOWN"


# Distinct Greeting Patterns
GREETING_PATTERNS = [
    r"^(?:hi|hello|hey|namaste|helo|hlo|hii+|hola|yo|good\s+(?:morning|afternoon|evening|day|night))\b(?:\s+(?:vitya|ai|bot|friend|yaar|bhai))?[!.]*$",
    r"^(?:hi|hello|hey|namaste)\s+vitya[!.]*$",
    r"^wassup\b",
]

# Casual Conversation Patterns
CASUAL_PATTERNS = [
    r"\b(?:how\s+are\s+you|kaise\s+ho|kya\s+hal\s+hai|kya\s+chal\s+raha\s+hai|how\s+do\s+you\s+do)\b",
    r"\b(?:who\s+are\s+you|tum\s+kaun\s+ho|what\s+is\s+your\s+name|aapka\s+naam\s+kya\s+hai)\b",
    r"\b(?:what\s+can\s+you\s+do|aap\s+kya\s+kar\s+sakte\s+ho|features|help\s+me)\b",
    r"\b(?:tell\s+me\s+a\s+joke|joke\s+sunao|make\s+me\s+laugh)\b",
    r"\b(?:thank\s+you|thanks|dhanyawad|shukriya|thx)\b",
    r"\b(?:bye|goodbye|see\s+you|alvida|tata|cya)\b",
]

# High Priority Visualization & Chart Patterns
VISUALIZATION_PATTERNS = [
    r"\b(?:chart|graph|plot|visualize|visualise|diagram)\b",
    r"\b(?:bar\s+chart|pie\s+chart|line\s+chart|donut\s+chart|area\s+chart|scatter\s+plot|radar\s+chart|waterfall)\b",
    r"\b(?:show\s+karo|graph\s+me\s+dikhao|chart\s+me\s+show\s+karo|graph\s+banao|chart\s+banao|chart\s+dikhao|percentage\s+chart|data\s+dikhao|data\s+ko\s+chart\s+me\s+dikhao)\b",
    r"\b(?:bich\s+aaye|distribution|stats\s+dikhao|trend\s+dikhao)\b",
]

# Financial / Analytics / Balance Patterns
FINANCE_PATTERNS = [
    r"\b(?:balance|total\s+balance|mera\s+balance|kitna\s+paisa|current\s+balance|bank\s+balance)\b",
    r"\b(?:financial\s+overview|cashflow|net\s+worth|savings\s+rate|total\s+savings)\b",
    r"\b(?:financial\s+health|health\s+score|finance\s+score|audit\s+score)\b",
]

# Expense Patterns
EXPENSE_PATTERNS = [
    r"\b(?:spent|kharch|kharcha|expense|expenses|paid|bought|purchase|petrol|swiggy|zomato|bill|uber|ola)\b",
    r"\b(?:mere\s+expenses|show\s+expenses|list\s+expenses|recent\s+expenses|last\s+expenses)\b",
]

# Income Patterns
INCOME_PATTERNS = [
    r"\b(?:salary|income|credited|cashback|earned|kamaya|kamayi|stipend|bonus|received\s+money|tankhwah)\b",
    r"\b(?:show\s+income|meri\s+income|income\s+history|list\s+income)\b",
]

# Budget Patterns
BUDGET_PATTERNS = [
    r"\b(?:budget|monthly\s+budget|budget\s+status|set\s+budget|create\s+budget|budget\s+banao)\b",
]

# Weather Patterns
WEATHER_PATTERNS = [
    r"\b(?:weather|mausam|temperature|rain|humidity|forecast|hawa|barish|garmi|sardi|temp\s+in)\b",
]

# Image Generation & Analysis Patterns
IMAGE_GEN_PATTERNS = [
    r"^(?:/image|generate\s+image|create\s+image|draw\s+image|photo\s+of|tasveer\s+banao|image\s+banao)\b",
]


def classify_intent(
    message: str,
    mode: Optional[str] = None,
    has_images: bool = False,
    has_docs: bool = False,
    is_health: bool = False,
) -> Intent:
    """Classifies user query into a primary intent category."""
    if has_images:
        return Intent.IMAGE_ANALYSIS

    if has_docs:
        return Intent.DOCUMENT_ANALYSIS

    # Explicit Mode Overrides
    if mode:
        m = mode.lower().strip()
        if m in ("dora", "health", "medical"):
            return Intent.HEALTH
        if m in ("news", "headlines"):
            return Intent.NEWS
        if m in ("wiki", "wikipedia"):
            return Intent.WIKIPEDIA
        if m in ("file", "ppt", "presentation"):
            return Intent.TASK

    if not message:
        return Intent.UNKNOWN

    text = message.strip()
    text_lower = text.lower()

    # Slash commands
    if text_lower.startswith("/dora"):
        return Intent.HEALTH
    if text_lower.startswith("/news"):
        return Intent.NEWS
    if text_lower.startswith("/wiki"):
        return Intent.WIKIPEDIA
    if text_lower.startswith("/presentation") or text_lower.startswith("/ppt"):
        return Intent.TASK
    if any(re.search(pat, text_lower) for pat in IMAGE_GEN_PATTERNS):
        return Intent.TASK

    # 1. Check Exact Greetings First
    for pat in GREETING_PATTERNS:
        if re.search(pat, text_lower):
            return Intent.GREETING

    # 2. Check Genuine Health Queries
    if is_health:
        return Intent.HEALTH

    # 3. Check Weather
    for pat in WEATHER_PATTERNS:
        if re.search(pat, text_lower):
            return Intent.WEATHER

    # 4. Check Autonomous Actions (Agenda, Calendar, Tasks, Emails)
    if any(k in text_lower for k in ["aaj ka schedule", "today schedule", "today's schedule", "morning briefing", "daily routine", "mera schedule"]):
        return Intent.ACTION_AGENDA

    if any(k in text_lower for k in ["schedule meeting", "meeting schedule", "add event", "calendar me add", "event banao", "schedule karo", "schedule kar do", "appointment"]):
        return Intent.ACTION_CALENDAR

    if any(k in text_lower for k in ["task add", "add task", "todo add", "add todo", "create task", "task banao", "priority task", "show tasks", "list tasks", "mere tasks"]):
        return Intent.ACTION_TASK

    if any(k in text_lower for k in ["send email", "email send", "email bhej do", "mail bhej do", "draft email", "client ko mail", "client ko email"]) or (
        "@" in text_lower and any(m in text_lower for m in ["email", "mail", "send", "bhej"])
    ):
        return Intent.ACTION_EMAIL

    # 5. Check Data Visualizations & Charts (High Priority ahead of Financial transactions)
    for pat in VISUALIZATION_PATTERNS:
        if re.search(pat, text_lower):
            return Intent.DATA_VISUALIZATION

    # 5. Check Budget
    for pat in BUDGET_PATTERNS:
        if re.search(pat, text_lower):
            return Intent.BUDGET

    # 6. Check Expense & Income
    for pat in EXPENSE_PATTERNS:
        if re.search(pat, text_lower):
            return Intent.EXPENSE

    for pat in INCOME_PATTERNS:
        if re.search(pat, text_lower):
            return Intent.INCOME

    # 7. Check General Finance & Analytics
    for pat in FINANCE_PATTERNS:
        if re.search(pat, text_lower):
            return Intent.FINANCE

    # 8. Check Casual Smalltalk
    for pat in CASUAL_PATTERNS:
        if re.search(pat, text_lower):
            return Intent.CASUAL_CONVERSATION

    # 9. General Knowledge / Task
    return Intent.GENERAL_KNOWLEDGE


def get_contextual_greeting(user_name: Optional[str] = None) -> Dict[str, Any]:
    """Generates a warm, natural personalized greeting without any disclaimers."""
    name_display = f" {user_name}" if user_name else ""
    return {
        "type": "text",
        "content": f"Hi{name_display} 👋\nMain Vitya hoon. Aaj main aapki kis cheez mein help karun?",
        "intent": Intent.GREETING.value,
        "disclaimer": None,
        "suggestions": [
            "💳 Check Balance",
            "💸 Log Expense",
            "📊 Show Charts",
            "💰 Monthly Budget",
            "🌦️ Check Weather",
        ],
        "actions": ["copy", "voice", "more"],
    }
