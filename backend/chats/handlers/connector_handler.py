from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.chats.services.unified_connector import (
    ResultCategory,
    orchestrator,
)

logger = logging.getLogger(__name__)

# Trigger patterns for each domain
SHOPPING_PATTERNS = [
    r"\b(?:amazon|flipkart|buy|kharidna|price\s+of|kitne\s+ka\s+hai|offers|deal|discount|compare\s+price|shopping)\b",
    r"\b(?:on\s+amazon|on\s+flipkart|amazon\s+aur\s+flipkart|product\s+options)\b",
]

RESEARCH_PATTERNS = [
    r"\b(?:research\s+paper|arxiv|academic\s+paper|scientific\s+paper|journal\s+article|literature\s+review)\b",
    r"\b(?:research\s+papers\s+find|papers\s+on|study\s+on)\b",
]

EDUCATION_PATTERNS = [
    r"\b(?:course|tutorial|documentation|official\s+docs|learn\s+python|freecodecamp|mit\s+ocw|coursera|free\s+course)\b",
    r"\b(?:docs\s+dikhao|ki\s+official\s+documentation|sikhna\s+hai|resources\s+batao)\b",
]

GOVERNMENT_PATTERNS = [
    r"\b(?:government\s+data|official\s+data|data\.gov|world\s+bank|sarkari\s+data|census|gdp\s+of\s+india|inflation\s+rate)\b",
    r"\b(?:government\s+ke\s+official\s+data|official\s+statistics|gov\s+portal)\b",
]


def detect_connector_category(text: str) -> Optional[ResultCategory]:
    t = (text or "").lower()
    for pat in SHOPPING_PATTERNS:
        if re.search(pat, t):
            return ResultCategory.SHOPPING

    for pat in RESEARCH_PATTERNS:
        if re.search(pat, t):
            return ResultCategory.RESEARCH

    for pat in GOVERNMENT_PATTERNS:
        if re.search(pat, t):
            return ResultCategory.GOVERNMENT

    for pat in EDUCATION_PATTERNS:
        if re.search(pat, t):
            return ResultCategory.EDUCATION

    return None


def clean_search_query(text: str, category: ResultCategory) -> str:
    """Strip intent commands and Hinglish filler words to obtain pure target query."""
    q = (text or "").strip()
    if category == ResultCategory.SHOPPING:
        q = re.sub(r"(?i)\b(?:amazon\s+aur\s+flipkart\s+par|amazon\s+par|flipkart\s+par|price\s+batao|options\s+compare\s+karo|buy\s+online|kharidna\s+hai|ka\s+price|compare)\b", " ", q)
    elif category == ResultCategory.RESEARCH:
        q = re.sub(r"(?i)\b(?:par\s+research\s+papers?\s+find\s+karo|research\s+papers?|academic\s+papers?|arxiv|find\s+karo|dikhao)\b", " ", q)
    elif category == ResultCategory.EDUCATION:
        q = re.sub(r"(?i)\b(?:free\s+courses?\s+ke\s+resources\s+batao|ki\s+official\s+documentation\s+dikhao|documentation\s+dikhao|tutorial\s+batao|sikhna\s+hai)\b", " ", q)
    elif category == ResultCategory.GOVERNMENT:
        q = re.sub(r"(?i)\b(?:government\s+ke\s+official\s+data\s+se|official\s+data\s+se|is\s+topic\s+ko\s+samjhao|data\s+dikhao)\b", " ", q)

    q = re.sub(r"[^\w\s-]", " ", q)
    return re.sub(r"\s+", " ", q).strip() or text.strip()


def handle_connector_request(
    msg: str,
    user_message: str,
    explicit_category: Optional[ResultCategory] = None,
    db: Optional[Session] = None,
    conversation_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Handles queries requiring external website / authorized data provider integration:
    - Shopping comparison (Amazon, Flipkart)
    - Academic research papers (arXiv)
    - Education courses & official docs (FastAPI, Python, MDN, MIT OCW, freeCodeCamp)
    - Government open datasets (World Bank, Data.gov.in)
    """
    raw_text = (user_message or "").strip()
    category = explicit_category or detect_connector_category(raw_text)

    if not category:
        return None

    clean_q = clean_search_query(raw_text, category)
    results = orchestrator.search(category=category, query=clean_q, limit=4)

    if not results:
        cat_name = category.value.capitalize()
        return {
            "type": "text",
            "content": f"⚠️ '{clean_q}' ke liye {cat_name} data source par koi verified results nahi mile. Kripya query thoda adjust karke dubara try karein.",
        }

    # Generate grounded AI summary
    summary_text = orchestrator.summarize_results(results, user_query=raw_text, category=category)

    # Determine frontend payload type
    type_map = {
        ResultCategory.SHOPPING: "shopping",
        ResultCategory.RESEARCH: "research",
        ResultCategory.EDUCATION: "education",
        ResultCategory.GOVERNMENT: "gov_data",
        ResultCategory.WEB_SEARCH: "web_search",
        ResultCategory.NEWS: "news",
    }
    frontend_type = type_map.get(category, "universal_data")

    return {
        "type": frontend_type,
        "category": category.value,
        "query": clean_q,
        "count": len(results),
        "content": [r.to_dict() for r in results],
        "text_summary": summary_text,
    }
