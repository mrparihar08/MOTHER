from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set

from backend.presentation.schemas import ImageResult, VisualType

logger = logging.getLogger(__name__)

STOPWORDS: Set[str] = {
    "a", "an", "the", "in", "on", "at", "by", "for", "with", "about", "against", "between",
    "into", "through", "during", "before", "after", "above", "below", "to", "from", "up",
    "down", "in", "out", "on", "off", "over", "under", "again", "further", "then", "once",
    "here", "there", "when", "where", "why", "how", "all", "any", "both", "each", "few",
    "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same",
    "so", "than", "too", "very", "s", "t", "can", "will", "just", "don", "should", "now",
    "overview", "introduction", "summary", "conclusion", "key", "details", "takeaways",
    "slide", "presentation", "part", "section", "chapter", "unit", "module"
}


def clean_query_text(text: str) -> str:
    """Removes slide stop words, punctuation, and AI prompt boilerplate."""
    if not text:
        return ""
    cleaned = re.sub(
        r"(?i)\b(introduction\s+to|overview\s+of|executive\s+summary\s*&?|key\s+takeaways|next\s+steps|case\s+study\s+on)\b",
        "",
        text
    )
    tokens = [w for w in re.split(r"[^\w]+", cleaned.lower()) if len(w) >= 3 and w not in STOPWORDS]
    return " ".join(tokens)


def determine_visual_type(slide_title: str, slide_content: str = "", slide_plugins: List[Any] = None) -> str:
    """
    Determines optimal visual type based on slide title, content text, and slide plugins.
    Values: PHOTO | DIAGRAM | ILLUSTRATION | ICON | PROCESS | FLOWCHART | CHART | CONCEPTUAL_IMAGE | BACKGROUND
    """
    t_lower = (slide_title or "").lower()
    c_lower = (slide_content or "").lower()
    combined = f"{t_lower} {c_lower}"

    # Check plugins first: if slide already has chart/diagram plugin, keep native visual type
    if slide_plugins:
        for plugin in slide_plugins:
            p_type = getattr(plugin, "type", "") if not isinstance(plugin, dict) else plugin.get("type", "")
            if p_type == "chart":
                return VisualType.CHART
            elif p_type == "diagram":
                return VisualType.DIAGRAM

    if re.search(r"\b(flowchart|pipeline|workflow|step-by-step|lifecycle|sequence)\b", combined):
        return VisualType.FLOWCHART
    if re.search(r"\b(architecture|structure|system\s+design|stack|framework|hierarchy|network\s+topology)\b", combined):
        return VisualType.DIAGRAM
    if re.search(r"\b(process|stage|phase|roadmap|timeline|methodology)\b", combined):
        return VisualType.PROCESS
    if re.search(r"\b(growth|revenue|metrics|analytics|chart|graph|statistic|data|percent)\b", combined):
        return VisualType.CHART
    if re.search(r"\b(versus|vs\.?|comparison|pros\s+and\s+cons|advantages|disadvantages|tradeoffs)\b", combined):
        return VisualType.CONCEPTUAL_IMAGE
    if re.search(r"\b(icon|symbol|logo|badge)\b", combined):
        return VisualType.ICON
    if re.search(r"\b(illustration|vector|drawing|sketch|diagram)\b", combined):
        return VisualType.ILLUSTRATION

    return VisualType.PHOTO


def build_slide_image_query(
    presentation_topic: str,
    slide_title: str,
    slide_content: str = "",
    visual_type: str = VisualType.PHOTO,
) -> str:
    """
    Generates a slide-specific image search query based on actual slide content and presentation topic.
    """
    clean_topic = clean_query_text(presentation_topic)
    clean_title = clean_query_text(slide_title)
    clean_content = clean_query_text(slide_content)[:80]

    # Combine title keywords with topic context
    if clean_title:
        base_query = f"{clean_title} {clean_topic}".strip()
    elif clean_content:
        base_query = f"{clean_content} {clean_topic}".strip()
    else:
        base_query = clean_topic or "presentation visual"

    # Add visual type domain modifiers if appropriate
    v_type = (visual_type or VisualType.PHOTO).lower()
    if v_type == VisualType.DIAGRAM:
        base_query += " diagram"
    elif v_type == VisualType.PROCESS:
        base_query += " process"
    elif v_type == VisualType.ILLUSTRATION:
        base_query += " illustration"
    elif v_type == VisualType.FLOWCHART:
        base_query += " flowchart"
    elif v_type == VisualType.CONCEPTUAL_IMAGE:
        base_query += " concept"

    # Limit query length to 6 tokens for optimal API search results
    words = base_query.split()
    seen = []
    for w in words:
        if w not in seen:
            seen.append(w)
    return " ".join(seen[:6])


def score_image_result(
    img: ImageResult,
    query: str,
    slide_title: str,
    visual_type: str = VisualType.PHOTO,
    used_urls: Set[str] = None,
) -> float:
    """
    Ranks an image candidate based on:
    1. Relevance score (title & query keyword matching)
    2. Visual type match score
    3. Resolution & aspect ratio quality score
    4. License compatibility score
    5. Duplicate penalty (for already-used presentation images)
    """
    used_urls = used_urls or set()
    score = 0.0

    title_lower = (img.title or "").lower()
    query_tokens = [w for w in query.lower().split() if len(w) >= 3]
    title_tokens = [w for w in slide_title.lower().split() if len(w) >= 3]

    # 1. Relevance Score (Max 35 pts)
    match_count = sum(1 for tok in query_tokens if tok in title_lower)
    score += min(25.0, match_count * 8.0)

    title_match_count = sum(1 for tok in title_tokens if tok in title_lower)
    score += min(10.0, title_match_count * 5.0)

    # 2. Visual Type Match Score (Max 20 pts)
    v_type = (visual_type or VisualType.PHOTO).lower()
    if v_type == VisualType.PHOTO and "photo" in (img.provider or "").lower():
        score += 15.0
    elif v_type in {VisualType.DIAGRAM, VisualType.PROCESS, VisualType.FLOWCHART} and any(k in title_lower for k in ["diagram", "chart", "flow", "process", "map", "schema"]):
        score += 20.0
    elif v_type == VisualType.ILLUSTRATION and any(k in title_lower for k in ["illustration", "vector", "art", "drawing"]):
        score += 20.0
    else:
        score += 10.0

    # 3. Resolution & Aspect Ratio Score (Max 20 pts)
    if img.width >= 1200:
        score += 12.0
    elif img.width >= 800:
        score += 8.0
    elif img.width >= 400:
        score += 4.0

    if 1.2 <= img.aspect_ratio <= 1.8:
        score += 8.0
    elif 0.9 <= img.aspect_ratio <= 2.2:
        score += 4.0

    # 4. License Score (Max 25 pts)
    lic_status = (img.license_status or "").lower()
    if lic_status == "commercial_safe":
        if "CC0" in (img.license or "").upper() or "PUBLIC DOMAIN" in (img.license or "").upper():
            score += 25.0
        else:
            score += 20.0
    elif lic_status == "non_commercial":
        score += 10.0
    else:
        score += 5.0

    # 5. Duplicate Penalty (-50 pts)
    if img.image_url in used_urls or img.source_url in used_urls or img.id in used_urls:
        score -= 50.0

    return round(score, 2)


def rank_and_select_images(
    images: List[ImageResult],
    query: str,
    slide_title: str,
    visual_type: str = VisualType.PHOTO,
    limit: int = 10,
    used_urls: Set[str] = None,
) -> List[ImageResult]:
    """Scores, ranks, and returns top selected images sorted by relevance score."""
    if not images:
        return []

    scored_images: List[ImageResult] = []
    for img in images:
        s = score_image_result(img, query=query, slide_title=slide_title, visual_type=visual_type, used_urls=used_urls)
        img_copy = img.model_copy(update={"relevance_score": s, "visual_type": visual_type})
        scored_images.append(img_copy)

    # Sort descending by relevance score
    ranked = sorted(scored_images, key=lambda x: x.relevance_score, reverse=True)
    return ranked[:limit]
