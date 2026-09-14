from __future__ import annotations

import logging
import os
import re
from collections import OrderedDict
from typing import Any, Dict, List, Optional
from backend.chats.services.gemini_service import generate_response
from backend.chats.services.web_search_service import perform_web_search, format_web_search_context
from backend.chats.presentation.schemas import (
    GenerateRequest,
    PresentationPlan,
    SlideSpec,
    SlidePlugin,
    SlidePluginParagraph,
    SlidePluginBullets,
    SlidePluginChart,
    SlidePluginImage,
    SlidePluginTable,
    SlidePluginNotes,
    SlidePluginDiagram,
)
from backend.chats.presentation.geometry import MixedLayoutResolver

logger = logging.getLogger(__name__)

MAX_SLIDES = int(os.getenv("PPT_MAX_SLIDES", "30"))
MAX_BULLETS_PER_SLIDE = int(os.getenv("PPT_MAX_BULLETS_PER_SLIDE", "8"))
MAX_PARAGRAPH_CHARS = int(os.getenv("PPT_MAX_PARAGRAPH_CHARS", "2500"))
DEFAULT_TEMPLATE_FILE = os.getenv("PPT_TEMPLATE_FILE", "./templates/base_template.pptx")
ALLOWED_SLIDE_TYPES = {
    "title_slide",
    "title_content",
    "mixed_content_slide",
    "chart_slide",
    "image_slide",
    "bullets_slide",
    "section_slide",
    "table_slide",
}


# ---------------------------------------------------------------------
# Helper Utilities
# ---------------------------------------------------------------------

def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def clean_ai_instructions(text: Optional[str]) -> str:
    if not text:
        return ""
    cleaned = normalize_whitespace(text)
    cleaned = re.sub(
        r"^(?i:\s*(?:break\s+down|explain\s+how|explain\s+the|explain|detail\s+the|detail|focus\s+on|highlight\s+the|highlight|describe\s+the|describe|conclude\s+with|discuss\s+the|discuss|provide\s+an|provide\s+a|provide|summarize\s+the|summarize)\s+)",
        "",
        cleaned,
    ).strip()
    return cleaned if cleaned else (text or "").strip()


def classify_prompt_domain(prompt: str) -> str:
    p = (prompt or "").lower()
    if re.search(r"\b(api|architecture|microservices|monolith|database|sql|nosql|cloud|aws|azure|gcp|devops|kubernetes|docker|python|java|react|node|backend|frontend|framework|git|security|encryption|cyber|network|server|system)\b", p):
        return "tech"
    if re.search(r"\b(revenue|profit|growth|quarterly|roi|market|business|strategy|sales|marketing|customer|b2b|b2c|valuation|investor|equity|ebitda|forecast|financial|finance|budget|cost|stock|asset)\b", p):
        if re.search(r"\b(revenue|profit|quarterly|roi|valuation|equity|ebitda|financial|finance|budget|cost|stock|asset)\b", p):
            return "finance"
        return "business"
    if re.search(r"\b(patient|clinical|health|medical|disease|pharma|hospital|fda|diagnosis|therapy|treatment|symptom|vaccine|healthcare)\b", p):
        return "medical"
    if re.search(r"\b(paper|thesis|research|literature|methodology|hypothesis|empirical|study|experiment|academic|university|journal)\b", p):
        return "academic"
    return "general"


def summarize_agenda_bullet(title: str) -> str:
    cleaned = normalize_whitespace(title)
    cleaned = re.sub(r"(?i)^(?:introduction\ to|overview\ of|deep\ dive\ into|executive\ analysis\ of|understanding\ the|concept\ of|presentation\ on|case\ study\ on)\s+", "", cleaned).strip()
    words = cleaned.split()
    if len(words) > 5:
        return " ".join(words[:5])
    return cleaned or title


LOCALIZED_BLUEPRINTS: Dict[str, Dict[str, str]] = {
    "hi": {
        "agenda": "प्रस्तुति अवलोकन और कार्यसूची",
        "intro": "{} का परिचय",
        "conclusion": "कार्यकारी सारांश और निष्कर्ष",
        "thanks": "धन्यवाद और प्रश्नोत्तरी",
    },
    "hinglish": {
        "agenda": "Presentation Overview aur Main Topics",
        "intro": "{} ka Introduction",
        "conclusion": "Executive Summary aur Nishkarsh",
        "thanks": "Dhanyawaad aur Q&A",
    },
    "es": {
        "agenda": "Resumen General y Agenda",
        "intro": "Introducción a {}",
        "conclusion": "Resumen Ejecutivo y Conclusión",
        "thanks": "Gracias y Preguntas",
    },
    "fr": {
        "agenda": "Aperçu et Ordre du Jour",
        "intro": "Introduction à {}",
        "conclusion": "Résumé Exécutif et Conclusion",
        "thanks": "Merci et Questions",
    },
    "de": {
        "agenda": "Überblick und Agenda",
        "intro": "Einführung in {}",
        "conclusion": "Zusammenfassung und Fazit",
        "thanks": "Vielen Dank & Fragen",
    },
}


def get_localized_labels(language: Optional[str]) -> Dict[str, str]:
    lang_lower = str(language or "en").lower().strip()
    if "hi" in lang_lower or "hindi" in lang_lower:
        if "hinglish" in lang_lower:
            return LOCALIZED_BLUEPRINTS["hinglish"]
        return LOCALIZED_BLUEPRINTS["hi"]
    if "hinglish" in lang_lower:
        return LOCALIZED_BLUEPRINTS["hinglish"]
    if "es" in lang_lower or "spanish" in lang_lower:
        return LOCALIZED_BLUEPRINTS["es"]
    if "fr" in lang_lower or "french" in lang_lower:
        return LOCALIZED_BLUEPRINTS["fr"]
    if "de" in lang_lower or "german" in lang_lower:
        return LOCALIZED_BLUEPRINTS["de"]
    return {
        "agenda": "Presentation Overview & Agenda",
        "intro": "Introduction to {}",
        "conclusion": "Executive Summary & Conclusion",
        "thanks": "Thank You & Q&A",
    }



def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", normalize_whitespace(name))[:80].strip("_")
    return cleaned or "presentation"


def normalize_slide_types(slide_types: Optional[List[str]]) -> Optional[List[str]]:
    if not slide_types:
        return None
    cleaned: List[str] = []
    for item in slide_types:
        value = normalize_whitespace(str(item)).lower()
        if value in ALLOWED_SLIDE_TYPES:
            cleaned.append(value)
    return cleaned or None


def resolve_template_path(template_name: Optional[str]) -> str:
    from pathlib import Path
    if template_name:
        candidate = Path(template_name).expanduser()
        if candidate.is_file():
            return str(candidate)
    return DEFAULT_TEMPLATE_FILE


def title_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", normalize_whitespace(text).lower()).strip()


def unique_title(title: str, suffix: str, seen: set[str]) -> str:
    base = normalize_whitespace(title) or "Slide"
    k = title_key(base)
    if k not in seen:
        seen.add(k)
        return base
    candidate = f"{base} - {suffix}"
    seen.add(title_key(candidate))
    return candidate


def split_text_into_chunks(text: str, max_chars: int = MAX_PARAGRAPH_CHARS) -> List[str]:
    text = normalize_whitespace(text)
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: List[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= max_chars:
            current += " " + sentence
        else:
            chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks or [text[:max_chars]]


def best_font_size_for_bullets(points: List[Any], base: int = 18) -> int:
    count = max(1, len(points))
    longest = max((len(normalize_whitespace(str(p))) for p in points), default=0)
    size = base
    if count >= 10:
        size -= 2
    if count >= 7:
        size -= 1
    if longest >= 100:
        size -= 2
    elif longest >= 70:
        size -= 1
    return max(16, size)


def best_font_size_for_paragraph(text: str, base: int = 15) -> int:
    text = normalize_whitespace(text)
    size = base
    if len(text) > 800:
        size -= 4
    elif len(text) > 500:
        size -= 3
    elif len(text) > 300:
        size -= 2
    elif len(text) > 150:
        size -= 1
    return max(10, size)


def detect_bullet_style(points: Any = None, selected_style: Optional[str] = "auto") -> str:
    st = str(selected_style or "auto").lower().strip()
    if st not in {"auto", "none", ""}:
        return st
    joined = " ".join(safe_list(points)).lower()
    if re.search(r"(step|phase|stage|rank|order|first|second|third|1\.|2\.|3\.)", joined):
        return "number"
    if re.search(r"(task|todo|check|verify|complete|done|feature|status)", joined):
        return "check"
    if re.search(r"(key|important|highlight|top|benefit|advantage|star)", joined):
        return "star"
    if re.search(r"(process|flow|next|then|direction|target|goal)", joined):
        return "arrow"
    if re.search(r"(option|category|tier|type)", joined):
        return "alpha"
    return "bullet"


def format_bullet_prefix(style: str = "auto", index: int = 0, points: Any = None) -> str:
    resolved_style = detect_bullet_style(points, style)
    st = str(resolved_style or "bullet").lower().strip()
    if st in {"number", "numbered", "123"}:
        return f"{index + 1}. "
    if st in {"alpha", "abc"}:
        return f"{chr(65 + (index % 26))}. "
    if st == "roman":
        romans = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
        return f"{romans[index % 10]}. "
    if st in {"check", "checklist"}:
        return "✔ "
    if st == "star":
        return "✦ "
    if st == "arrow":
        return "➜ "
    if st == "diamond":
        return "🔹 "
    return "• "


def detect_diagram_type(text: str = "", selected_type: Optional[str] = "auto", context_text: str = "") -> str:
    stype = str(selected_type or "auto").lower().strip()
    if stype not in {"auto", "none", ""}:
        return stype
    raw = f"{text} {context_text}".lower()
    if re.search(r"(tree|hierarchy|decision|branch|node|tree_structure)", raw):
        return "tree"
    if re.search(r"(cycle|loop|repeat|iterat|pdca|agile|sprint|circular|feedback)", raw):
        return "cycle"
    if re.search(r"(funnel|conversion|lead|pipeline|sales|stage)", raw):
        return "funnel"
    if re.search(r"(pyramid|hierarchy|maslow|foundation|level|tier)", raw):
        return "pyramid"
    if re.search(r"(swot|matrix|quadrant|2x2|grid)", raw):
        return "quadrant"
    if re.search(r"(vs|versus|compare|comparison|difference|pros|cons)", raw):
        return "comparison"
    if re.search(r"(timeline|roadmap|milestone|phase|quarter|q1|q2|q3|q4|era|history|evolution|year|19\d\d|20\d\d)", raw):
        return "timeline"
    if re.search(r"(stack|architecture|layer|tier|database|backend|frontend|api|system|component|engine|framework)", raw):
        return "architecture"
    if re.search(r"(input|output|processing|io\b|ingestion|extraction|pipeline|data flow)", raw):
        return "io_cards"
    if re.search(r"(mindmap|brainstorm|category|concept|topic|branch)", raw):
        return "mindmap"
    return "flowchart"


def build_dynamic_diagram_badge(diag_type: str, context_text: str = "", slide_title: str = "") -> Optional[str]:
    raw_topic = context_text or slide_title or ""
    clean = re.sub(r"(?i)^(?:presentation\ |overview\ |introduction\ to\ |concept\ of\ |system\ |architecture\ |process\ |workflow\ |lifecycle\ )+", "", raw_topic).strip()
    clean = re.sub(r"(?i)\s*(?:architecture|stack|diagram|process|workflow|lifecycle|ppt|presentation)$", "", clean).strip()

    if not clean or len(clean) < 3 or clean.lower() in {"system", "overview", "introduction", "architecture", "stack"}:
        return None

    words = clean.upper().split()
    topic_upper = " ".join(words[:4]) if len(words) > 4 else clean.upper()

    icons = {
        "tree": "🌳",
        "flowchart": "🔄",
        "architecture": "🏛️",
        "timeline": "📅",
        "mindmap": "🧠",
        "funnel": "🔻",
        "cycle": "🔁",
        "pyramid": "🔺",
        "quadrant": "🧭",
        "comparison": "⚔️",
    }
    icon = icons.get(diag_type, "⚙️")
    suffix_map = {
        "tree": "HIERARCHY",
        "flowchart": "WORKFLOW",
        "architecture": "ARCHITECTURE",
        "timeline": "ROADMAP",
        "mindmap": "CONCEPT MAP",
        "funnel": "FUNNEL",
        "cycle": "PROCESS LOOP",
        "pyramid": "HIERARCHY",
        "quadrant": "MATRIX",
        "comparison": "COMPARISON",
    }
    suffix = suffix_map.get(diag_type, "STACK")
    if suffix in topic_upper:
        badge = f"{icon} {topic_upper}"
    else:
        badge = f"{icon} {topic_upper} {suffix}"

    return badge


def chunk_list(items: List[Any], size: int) -> List[List[Any]]:
    size = max(1, size)
    return [items[i:i + size] for i in range(0, len(items), size)]


def parse_number(value: str) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


# ---------------------------------------------------------------------
# Gemini Presentation Planning Script Builder
# ---------------------------------------------------------------------

def build_gemini_slide_script(req: GenerateRequest) -> Optional[str]:
    if not req.use_gemini or not os.getenv("GEMINI_API_KEY"):
        return None

    options = []
    if req.audience:
        aud_lower = req.audience.lower()
        if any(kw in aud_lower for kw in ["exec", "ceo", "board", "c-suite", "management", "investor", "leadership"]):
            options.append(f"Target Audience: {req.audience} (Focus on strategic ROI, financial impact, risk management, and executive decisions. Avoid granular code/jargon).")
        elif any(kw in aud_lower for kw in ["dev", "eng", "tech", "architect", "coder", "software"]):
            options.append(f"Target Audience: {req.audience} (Focus on technical specs, architecture, APIs, data schemas, performance benchmarks, and implementation protocols).")
        elif any(kw in aud_lower for kw in ["student", "academic", "school", "university", "beginner", "general"]):
            options.append(f"Target Audience: {req.audience} (Focus on accessible concepts, intuitive analogies, real-world examples, and clear foundational definitions).")
        else:
            options.append(f"Target Audience: {req.audience} (Tailor vocabulary and depth specifically for this audience).")
    if req.tone:
        options.append(f"Tone: {req.tone}.")
    options.append(f"Language: {req.language}.")
    if req.include_citations:
        options.append("Add a final Sources slide containing short, credible source names/URLs. Do not invent fake citations.")
    if req.include_speaker_notes:
        options.append("Add one concise `Notes:` line to every non-title slide.")

    search_context = ""
    if req.use_web_search:
        try:
            results = perform_web_search(req.prompt, max_results=5)
            if results:
                search_context = format_web_search_context(req.prompt, results)
        except Exception as exc:
            logger.warning("Web search for presentation generation failed: %s", exc)

    instructions = " ".join(options)
    if search_context:
        instructions += f"\n\n{search_context}\nIncorporate these latest real-time web facts, current statistics, and domain developments into the presentation slides."

    gemini_prompt = f"""You are a world-class presentation designer and domain content strategist.
Create a professional, visually rich, logically structured PowerPoint script about this topic:

<topic>
{req.prompt}
</topic>

<instructions>
{instructions}
</instructions>

Follow these strict design and content rules:

1. TOPIC & EXECUTIVE STRUCTURE INTELLIGENCE:
- Target around {req.slide_count} slides.
- Slide 1 MUST be a clean Main Title Cover (Title: [Topic Name], Subtitle: [Executive Subtitle]).
- Slide 2 MUST be "Presentation Overview & Agenda". It MUST NOT contain any Image.
- The bullet points on Slide 2 (Agenda) MUST DYNAMICALLY list the EXACT slide titles of all subsequent slides (Slide 3 to Slide N) included in this presentation script.
- Slide 3 MUST ALWAYS be the explicit "Introduction to [Topic Name]" slide (e.g. "Introduction to Artificial Intelligence"), providing deep domain definition, background, and strategic scope.
- Subsequent slides MUST use clear, professional structural titles (e.g. "Core Principles", "System Architecture", "Process Workflow", "Feature & Solution Comparison", "Performance Data & Metrics", "Real-World Applications", "Strategic Advantages", "Executive Summary & Conclusion").
- EVERY slide title must be clean, executive, and free of repetitive prefixes like "Topic Name: Slide Title" or internal instructions.

2. CONTENT QUALITY & DENSITY:
- Bullet points must be high-impact, insightful, and audience-ready (3-5 bullet points per slide, max 15-20 words per bullet).
- Keep text concise and avoid slide clutter. Use punchy, action-oriented phrasing.
- Provide concrete domain details, real terminology, and practical insights.

3. INTELLIGENT CHART SELECTION & ACCURATE DATA GROUNDING:
- DYNAMIC CHART TYPE SELECTION: Whenever a slide presents numerical metrics, Gemini MUST select the chart type best suited for the data:
  * `Chart: line` -> Best for time-series growth, historical trends, or trajectories over time (e.g., 2020 to 2026).
  * `Chart: column` -> Best for phase-wise adoption, discrete category metrics, or multi-year milestones.
  * `Chart: bar` -> Best for ranking threat vectors, category distribution, survey breakdown, or horizontal comparison.
  * `Chart: pie` or `Chart: donut` -> Best for market share %, budget allocation, or component proportions.
  * `Chart: area` -> Best for cumulative volume or capacity over time.
- ACCURATE DOMAIN DATA: Gemini MUST use real-world domain knowledge to generate realistic, domain-grounded numerical data points (percentages %, rates, index scores, response times, market values). NEVER output generic 0 values.
- Format chart lines strictly as:
  Chart: [type: column | line | bar | pie | area | donut]
  Series Name: [Specific Metric Name, e.g. Threat Vector Share (%)]
  [Category or Year 1]: [Real Number Value]
  [Category or Year 2]: [Real Number Value]
  [Category or Year 3]: [Real Number Value]
  [Category or Year 4]: [Real Number Value]

4. VISUAL LAYOUT VARIETY & DYNAMIC SELECTION:
- Vary slide layouts across the deck to maintain visual engagement:
  * Diagram / Process: Use `Diagram: [Step 1] ➔ [Step 2] ➔ [Step 3]` for architecture, lifecycles, and workflows.
  * Solution Comparison: Use structured `Table:` for side-by-side feature comparisons.
  * Metrics Callout: Pair `Chart:` with 2-3 key takeaway bullet points.
  * Visual Showcase: Pair `Image: [search query]` with concise narrative paragraphs.

OUTPUT FORMAT:
Return ONLY the plain-text slide script. Do not use Markdown code fences, introductory prose, or JSON.
Use these exact slide format structures:

Slide 1:
Title: [Specific Professional Title]
Subtitle: [Informative Executive Subtitle]

Slide 2:
Title: Presentation Overview & Agenda
Bullets:
- [Dynamic Slide 3 Title]
- [Dynamic Slide 4 Title]
- [Dynamic Slide 5 Title]
- [Dynamic Slide 6 Title]

Slide 3:
Title: Introduction to [Topic Name]
Paragraph: [Detailed, comprehensive narrative paragraph providing deep domain context, core definition, and background scope.]

Slide 4:
Title: System Architecture & Components
Diagram: [Input Layer] ➔ [Core Engine] ➔ [Analytics Service] ➔ [Output API]
Bullets:
- Primary data ingestion and entry point
- Core processing engine and analytics pipeline
- Output dispatch and service integration

Slide 5:
Title: Comprehensive Solution Comparison
Table:
Criterion | Option A | Option B | Option C
Performance | High (99.9% uptime) | Medium (98.5%) | High (99.5%)
Cost Tier | Enterprise Tier | Pay-as-you-go | Open Source
Scalability | Multi-region | Single-region | Hybrid Cloud

Slide 6:
Title: Performance Data & Metrics
Chart: line
Series Name: Enterprise Adoption Rate (%)
2021: 18.5
2022: 34.2
2023: 58.7
2024: 82.4
2025: 94.0

Slide 7:
Title: Real-World Applications & Use Cases
Image: [Specific topic keyword image query]
Paragraph: [Practical deployment scenario and real-world impact...]

Notes: [Concise speaker note for the presenter.]"""

    try:
        response = generate_response(gemini_prompt)
    except Exception as exc:
        logger.error("Gemini presentation planning exception: %s", exc)
        return None

    if not response or response.startswith("Gemini API key is not configured") or response.startswith("Gemini error"):
        logger.warning("Gemini presentation planning failed; using local planner")
        return None

    response = response.strip()
    response = re.sub(r"^```[a-zA-Z]*\s*", "", response, flags=re.IGNORECASE)
    response = re.sub(r"\s*```$", "", response)

    m_slide = re.search(r"(?im)^\s*slide\s*0?1\s*[:\-]", response)
    if m_slide:
        response = response[m_slide.start():]

    returned_slides = len(re.findall(r"(?im)^\s*slide\s*\d+\s*[:\-]", response))
    if returned_slides < 2:
        logger.warning("Gemini returned an invalid presentation script; using local planner")
        return None
    if returned_slides != req.slide_count:
        logger.warning(
            "Gemini returned %s slides when %s were requested; using the valid response",
            returned_slides,
            req.slide_count,
        )
    return response


# ---------------------------------------------------------------------
# Local Fallback Prompt Planner
# ---------------------------------------------------------------------

class PromptPlanner:
    def extract_user_subtopics(self, prompt: str) -> List[str]:
        prompt = (prompt or "").strip()
        if not prompt:
            return []

        match = re.search(
            r"(?:subtopics?|sub-topics?|topics?|sections?|including|with|key topics?|points?)\s*[:\-]\s*(.+?)(?=\n\n|\.\s*$|$)",
            prompt,
            re.IGNORECASE | re.DOTALL,
        )
        raw_subtopics = ""
        if match:
            raw_subtopics = match.group(1).strip()
        elif "\n" in prompt:
            lines = [l.strip() for l in prompt.splitlines() if l.strip()]
            if len(lines) >= 2:
                raw_subtopics = ", ".join(lines[1:])

        if raw_subtopics:
            parts = re.split(r"[,;|\n•*\-]|\band\b", raw_subtopics)
            cleaned = []
            for p in parts:
                c = normalize_whitespace(p).strip(".- ")
                if c and len(c) >= 3 and not re.match(r"^(and|or|with|etc|following|slides?|ppt|presentation)$", c, re.IGNORECASE):
                    cleaned.append(c)
            if cleaned:
                return cleaned[:15]

        return []

    def plan(
        self,
        prompt: str,
        *,
        include_title_slide: bool = True,
        allow_bullets: bool = True,
        allow_paragraph: bool = True,
        allow_chart: bool = True,
        allow_image: bool = True,
        allow_section_slide: bool = True,
        allow_table: bool = True,
        smart_mode: bool = True,
        slide_types: Optional[List[str]] = None,
        target_slide_count: Optional[int] = None,
        language: Optional[str] = "english",
    ) -> PresentationPlan:
        prompt = (prompt or "").strip()
        prompt_l = prompt.lower()
        domain = classify_prompt_domain(prompt)
        labels = get_localized_labels(language)
        blocks = self.extract_structured_slides(prompt)
        presentation_title = self.extract_overall_title(prompt, blocks)
        allowed_set = set(slide_types) if slide_types else None

        def allowed(layout_name: str) -> bool:
            if allowed_set is not None and layout_name not in allowed_set:
                return False
            if layout_name == "title_slide":
                return include_title_slide
            if layout_name == "bullets_slide":
                return allow_bullets
            if layout_name == "title_content":
                return allow_paragraph or allow_bullets or allow_image or allow_chart or allow_table
            if layout_name == "mixed_content_slide":
                return allow_paragraph or allow_bullets or allow_image or allow_chart or allow_table
            if layout_name == "chart_slide":
                return allow_chart
            if layout_name == "image_slide":
                return allow_image
            if layout_name == "section_slide":
                return allow_section_slide
            if layout_name == "table_slide":
                return allow_table
            return True

        slides: List[SlideSpec] = []

        if not blocks:
            slides = []
            desired_count = min(max(target_slide_count or 8, 3), MAX_SLIDES)

            if domain == "tech":
                fallback_topics = [
                    ("Main Title", "title"),
                    (labels["agenda"], "bullets"),
                    ("Introduction & Executive Context", "paragraph"),
                    ("System Architecture & Core Components", "diagram"),
                    ("API Specifications & Data Protocols", "table"),
                    ("Performance Benchmarks & Scalability", "chart"),
                    ("Security, Compliance & Resilience", "bullets"),
                    ("Deployment & Operational Strategy", "mixed"),
                    ("Future Scope & Tech Roadmap", "bullets"),
                    (labels["conclusion"], "paragraph"),
                    (labels["thanks"], "section"),
                ]
            elif domain == "finance":
                fallback_topics = [
                    ("Main Title", "title"),
                    (labels["agenda"], "bullets"),
                    ("Executive Summary & Market Position", "paragraph"),
                    ("Key Financial Metrics & Revenue Growth", "chart"),
                    ("Competitive Landscape & Market Share", "table"),
                    ("Cost Optimization & EBITDA Margin", "chart"),
                    ("Strategic Investment & Capital Allocation", "bullets"),
                    ("Risk Management & Financial Resilience", "mixed"),
                    ("Future Forecast & Valuation Growth", "bullets"),
                    (labels["conclusion"], "paragraph"),
                    (labels["thanks"], "section"),
                ]
            elif domain == "business":
                fallback_topics = [
                    ("Main Title", "title"),
                    (labels["agenda"], "bullets"),
                    ("Executive Context & Business Scope", "paragraph"),
                    ("Strategic Objectives & Key Deliverables", "bullets"),
                    ("Market Opportunity & Competitor Matrix", "table"),
                    ("Operational Workflow & Execution Roadmap", "diagram"),
                    ("Growth Metrics & Market Penetration", "chart"),
                    ("Key Risks & Mitigation Framework", "bullets"),
                    ("Real-World Use Cases & Case Studies", "mixed"),
                    (labels["conclusion"], "paragraph"),
                    (labels["thanks"], "section"),
                ]
            elif domain == "medical":
                fallback_topics = [
                    ("Main Title", "title"),
                    (labels["agenda"], "bullets"),
                    ("Clinical Overview & Disease Etiology", "paragraph"),
                    ("Diagnostic Protocols & Patient Workflow", "diagram"),
                    ("Clinical Trial Metrics & Efficacy Data", "chart"),
                    ("Therapeutic Comparison & Safety Profile", "table"),
                    ("Regulatory Landscape & FDA Alignment", "bullets"),
                    ("Patient Outcomes & Real-World Evidence", "mixed"),
                    ("Future Horizon & Research Directions", "bullets"),
                    (labels["conclusion"], "paragraph"),
                    (labels["thanks"], "section"),
                ]
            elif domain == "academic":
                fallback_topics = [
                    ("Main Title", "title"),
                    (labels["agenda"], "bullets"),
                    ("Theoretical Background & Research Scope", "paragraph"),
                    ("Methodology & Experimental Framework", "diagram"),
                    ("Empirical Results & Statistical Analysis", "chart"),
                    ("Comparative Literature Analysis", "table"),
                    ("Key Findings & Academic Insights", "bullets"),
                    ("Limitations & Research Constraints", "mixed"),
                    ("Future Research Directions", "bullets"),
                    (labels["conclusion"], "paragraph"),
                    (labels["thanks"], "section"),
                ]
            else:
                fallback_topics = [
                    ("Main Title", "title"),
                    (labels["agenda"], "bullets"),
                    ("Introduction & Executive Context", "paragraph"),
                    ("Core Concepts & Key Principles", "paragraph"),
                    ("Key Problem Statement & Challenges", "bullets"),
                    ("Objectives & Strategic Scope", "bullets"),
                    ("Current Status & Industry Landscape", "mixed"),
                    ("System Architecture & Core Components", "diagram"),
                    ("Process Workflow & Execution Lifecycle", "diagram"),
                    ("Comprehensive Solution Comparison", "table"),
                    ("Performance Metrics & Data Analysis", "chart"),
                    ("Strategic Advantages & Key Benefits", "bullets"),
                    ("Operational Constraints & Risk Factors", "bullets"),
                    ("Real-World Applications & Use Cases", "mixed"),
                    ("Future Scope & Innovation Roadmap", "bullets"),
                    (labels["conclusion"], "paragraph"),
                    ("References & Credible Sources", "bullets"),
                    (labels["thanks"], "section"),
                ]

            custom_user_subtopics = self.extract_user_subtopics(prompt)
            if custom_user_subtopics:
                custom_topics = [
                    ("Main Title", "title"),
                    (labels["agenda"], "bullets"),
                    (labels["intro"].format(presentation_title), "paragraph"),
                ]
                layout_cycle = ["mixed", "diagram", "table", "chart", "bullets", "paragraph"]
                for i, sub in enumerate(custom_user_subtopics):
                    l_type = layout_cycle[i % len(layout_cycle)]
                    custom_topics.append((sub, l_type))
                custom_topics.append((labels["conclusion"], "paragraph"))
                custom_topics.append((labels["thanks"], "section"))
                fallback_topics = custom_topics

            total_available = len(fallback_topics)
            last_middle = max(1, total_available - 2)
            if desired_count >= total_available:
                selected_indices = list(range(total_available))
            else:
                mandatory_front = [0, 1, 2] if total_available > 2 else [0, 1]
                last_idx = total_available - 1
                remaining_count = max(0, desired_count - len(mandatory_front) - 1)

                if remaining_count > 0:
                    start_mid = len(mandatory_front)
                    end_mid = max(start_mid, total_available - 2)
                    middle_indices = [
                        int(round(start_mid + i * (end_mid - start_mid) / max(1, remaining_count - 1)))
                        for i in range(remaining_count)
                    ]
                else:
                    middle_indices = []

                selected_indices = mandatory_front + middle_indices + [last_idx]

            seen_i = set()
            unique_indices = []
            for i in selected_indices:
                if i not in seen_i:
                    seen_i.add(i)
                    unique_indices.append(i)

            for idx in unique_indices:
                raw_topic, layout_type = fallback_topics[idx]
                if raw_topic == "Main Title":
                    topic = presentation_title
                elif raw_topic == labels["agenda"] or raw_topic == "Presentation Overview & Agenda":
                    topic = labels["agenda"]
                elif raw_topic.startswith("Introduction"):
                    topic = labels["intro"].format(presentation_title)
                else:
                    topic = raw_topic

                if layout_type == "title" and include_title_slide:
                    slides.append(self._make_title_slide(presentation_title, f"Executive Analysis & Strategic Overview of {presentation_title}"))
                elif layout_type == "section" and allow_section_slide:
                    slides.append(self._make_section_slide(labels["thanks"]))
                elif layout_type == "paragraph" and allow_paragraph:
                    slides.append(self._make_paragraph_slide(
                        topic,
                        f"Executive domain analysis and strategic context introducing key principles of {presentation_title}."
                    ))
                elif layout_type == "table" and allow_table:
                    comp_match = re.search(r"(.+?)\s+(?:vs\.?|versus|compared\s+to)\s+(.+)", presentation_title, re.IGNORECASE)
                    if comp_match:
                        opt_a = re.sub(r"(?i)^(?:presentation\ |overview\ |comparison\ |systems?\ )*", "", comp_match.group(1)).strip()
                        opt_b = re.sub(r"(?i)\s*(?:systems?|technologies|architecture|comparison)$", "", comp_match.group(2)).strip()
                        table_headers = ["Criterion / Feature", (opt_a[:22] or "Option A"), (opt_b[:22] or "Option B")]
                        table_rows = [
                            ["Data Architecture", f"Strict {opt_a[:12]} Schema", f"Dynamic {opt_b[:12]} Format"],
                            ["Consistency & ACID", "Strong Immediate Consistency", "Eventual / Flexible Consistency"],
                            ["Scalability Model", "Vertical Scale-Up", "Horizontal Auto-Sharding"],
                            ["Query Interface", "Standardized SQL Engine", "Flexible API / Document Query"],
                        ]
                    else:
                        table_headers = ["Criterion / Feature", "Option A (Baseline)", "Option B (Advanced)"]
                        table_rows = [
                            ["Performance", "Standard Baseline", "High Throughput"],
                            ["Scalability", "Single-Region", "Global Multi-Cluster"],
                            ["Security & Compliance", "Basic Protocol", "Zero-Trust Enterprise"],
                            ["Cost Efficiency", "Moderate Overhead", "Optimized TCO"],
                        ]

                    slides.append(self._make_table_slide(
                        topic,
                        {
                            "title": topic,
                            "headers": table_headers,
                            "rows": table_rows,
                        }
                    ))
                elif layout_type == "chart" and allow_chart:
                    t_lower = (presentation_title + " " + raw_topic).lower()
                    if any(k in t_lower for k in ["growth", "trend", "year", "time", "rate", "adoption", "trajectory"]):
                        c_type = "line"
                        cats = ["2021", "2022", "2023", "2024", "2025"]
                        vals = [18.5, 34.2, 58.7, 82.4, 94.0]
                        s_name = f"{presentation_title[:24]} Adoption Rate (%)"
                    elif any(k in t_lower for k in ["share", "market", "distribution", "allocation", "composition"]):
                        c_type = "pie"
                        cats = ["Enterprise Tier", "Mid-Market", "SMB / Startup", "Individual"]
                        vals = [42, 28, 18, 12]
                        s_name = f"{presentation_title[:24]} Share Distribution (%)"
                    elif any(k in t_lower for k in ["threat", "risk", "vector", "ranking", "challenge"]):
                        c_type = "bar"
                        cats = ["Primary Vector", "Secondary Risk", "Operational Impact", "Policy Gap"]
                        vals = [65.4, 48.2, 32.8, 19.5]
                        s_name = f"{presentation_title[:24]} Severity Index"
                    elif any(k in t_lower for k in ["revenue", "financial", "margin", "cost", "ebitda"]):
                        c_type = "column"
                        cats = ["Q1 Baseline", "Q2 Growth", "Q3 Scaling", "Q4 Forecast"]
                        vals = [1.8, 4.2, 9.5, 18.2]
                        s_name = f"{presentation_title[:24]} Revenue ($M)"
                    else:
                        c_type = "column"
                        cats = ["Phase 1 (Baseline)", "Phase 2 (Adoption)", "Phase 3 (Scaling)", "Phase 4 (Maturity)"]
                        vals = [28.5, 54.0, 82.5, 120.0]
                        s_name = f"{presentation_title[:24]} Performance Index"

                    slides.append(self._make_chart_slide(
                        topic,
                        {
                            "chart_type": c_type,
                            "title": topic,
                            "categories": cats,
                            "values": vals,
                            "series_name": s_name,
                        }
                    ))
                elif layout_type == "diagram":
                    t_low = (presentation_title + " " + raw_topic).lower()
                    if any(k in t_low for k in ["architecture", "stack", "tier", "component", "layer", "system"]):
                        d_type = "architecture"
                        diag_text = f"[{presentation_title} Ingestion] ➔ [Core Processing Engine] ➔ [Security & Storage] ➔ [{raw_topic[:15]} API]"
                    elif any(k in t_low for k in ["timeline", "roadmap", "milestone", "phase", "future"]):
                        d_type = "timeline"
                        diag_text = "Phase 1: Architecture ➔ Phase 2: Core Build ➔ Phase 3: Validation ➔ Phase 4: Scale"
                    elif any(k in t_low for k in ["input", "output", "processing", "io"]):
                        d_type = "io_cards"
                        diag_text = f"Raw Ingestion Data ➔ {presentation_title[:15]} Processing ➔ Strategic Output"
                    elif any(k in t_low for k in ["swot", "quadrant", "matrix"]):
                        d_type = "quadrant"
                        diag_text = "Core Strengths ➔ Key Vulnerabilities ➔ Market Opportunities ➔ External Threats"
                    elif any(k in t_low for k in ["cycle", "loop", "repeat", "iteration"]):
                        d_type = "cycle"
                        diag_text = "Requirement Phase ➔ Design & Build ➔ Validation Test ➔ Production Deployment"
                    else:
                        d_type = "flowchart"
                        diag_text = f"[{presentation_title[:15]} Ingestion] ➔ [Processing Engine] ➔ [Optimization] ➔ [{raw_topic[:15]} Dispatch]"

                    slides.append(self._make_mixed_slide(
                        topic,
                        [
                            SlidePluginDiagram(type="diagram", data={
                                "diagram": diag_text,
                                "diagram_type": d_type,
                                "slide_title": topic
                            }),
                            SlidePluginBullets(type="bullets", data={
                                "points": [
                                    f"Primary operational phase in {raw_topic.lower()}",
                                    "Modular component integration and data flow",
                                    "Validation, monitoring, and quality assurance",
                                ]
                            }),
                        ]
                    ))
                elif layout_type == "mixed" and allow_paragraph and allow_bullets:
                    slides.append(self._make_mixed_slide(
                        topic,
                        [
                            SlidePluginParagraph(type="paragraph", data={"text": f"Strategic analysis and key operational highlights of {raw_topic.lower()}."}),
                            SlidePluginBullets(type="bullets", data={"points": [
                                f"Core capability and function within {presentation_title}",
                                "Practical integration baseline and operational impact",
                                "Target metric alignment and performance benchmark",
                            ]}),
                        ]
                    ))
                elif allow_bullets:
                    if "Overview" in raw_topic or "Agenda" in raw_topic or raw_topic == labels["agenda"]:
                        bullet_points = []
                        for next_i in range(idx + 1, len(unique_indices)):
                            next_idx = unique_indices[next_i]
                            next_raw_topic, _ = fallback_topics[next_idx]
                            if next_raw_topic in {labels["thanks"], "Thank You & Q&A", "Main Title", labels["agenda"], "Presentation Overview & Agenda"}:
                                continue
                            if next_raw_topic.startswith("Introduction"):
                                next_topic = labels["intro"].format(presentation_title)
                            else:
                                next_topic = next_raw_topic
                            bullet_points.append(summarize_agenda_bullet(next_topic))

                        if not bullet_points:
                            bullet_points = [
                                summarize_agenda_bullet(labels["intro"].format(presentation_title)),
                                "Core Concepts & Principles",
                                "Performance Analysis & Comparison",
                                summarize_agenda_bullet(labels["conclusion"]),
                            ]
                    else:
                        bullet_points = [
                            f"Key aspect of {raw_topic.lower()} in relation to {presentation_title}",
                            "Critical operational considerations and guidelines",
                            "Strategic takeaway and audience outcome",
                        ]
                    slides.append(self._make_bullets_slide(topic, bullet_points))
                elif allow_paragraph:
                    slides.append(self._make_paragraph_slide(topic, f"Key context about {raw_topic.lower()}."))

            return PresentationPlan(title=presentation_title, slides=slides[:desired_count])

        seen_titles: set[str] = set()

        for idx, block in enumerate(blocks):
            parsed = self.parse_slide_block(block)

            raw_title = (
                parsed["title"]
                or self.extract_heading_title(block)
                or (presentation_title if idx == 0 else f"Slide {idx + 1}")
            )
            raw_title = normalize_whitespace(raw_title)

            notes = normalize_whitespace(parsed.get("notes", ""))
            paragraph = normalize_whitespace(parsed.get("paragraph", ""))
            bullets = parsed.get("bullets") or []
            image_path = normalize_whitespace(parsed.get("image_path") or "")
            chart_series = parsed.get("chart_series") or {}
            chart_points = parsed.get("chart_points") or []
            table_rows = parsed.get("table_rows") or []

            if idx == 0 and allowed("title_slide"):
                slides.append(self._make_title_slide(raw_title, parsed.get("subtitle", "")))

            if allow_section_slide and self.is_section_block(block, parsed):
                slides.append(self._make_section_slide(parsed.get("section_title") or raw_title))
                continue

            def t(suffix: str) -> str:
                return unique_title(raw_title, suffix, seen_titles)

            plugins: List[SlidePlugin] = []

            diagram = normalize_whitespace(parsed.get("diagram", ""))
            if diagram:
                diag_type = parsed.get("diagram_type", "auto")
                plugins.append(SlidePluginDiagram(type="diagram", data={"diagram": diagram, "diagram_type": diag_type, "slide_title": raw_title}))

            if paragraph and allow_paragraph:
                plugins.append(SlidePluginParagraph(type="paragraph", data={"text": paragraph, "font_size": 18}))

            if bullets and allow_bullets:
                plugins.append(SlidePluginBullets(type="bullets", data={"points": bullets[:MAX_BULLETS_PER_SLIDE]}))

            if image_path and allow_image:
                plugins.append(SlidePluginImage(type="image", data={"path": image_path, "caption": raw_title}))

            if (chart_series or chart_points) and allow_chart:
                plugins.append(SlidePluginChart(type="chart", data=self.build_chart_payload(parsed)))

            if table_rows and allow_table:
                plugins.append(SlidePluginTable(type="table", data=self.build_table_payload(parsed, title=raw_title)))

            if len(plugins) >= 2:
                box_list = MixedLayoutResolver.resolve_list([p.type for p in plugins])
                adjusted: List[SlidePlugin] = []

                for plugin, box in zip(plugins, box_list):
                    data = dict(plugin.data)
                    if box:
                        data["box"] = {"left": box.left, "top": box.top, "width": box.width, "height": box.height}
                    data.pop("title", None)
                    adjusted.append(type(plugin)(type=plugin.type, data=data))

                if notes:
                    adjusted.append(SlidePluginNotes(type="notes", data={"notes": notes}))

                slides.append(
                    SlideSpec(
                        layout="mixed_content_slide",
                        title=t("Overview"),
                        plugins=adjusted,
                    )
                )
                continue

            if len(plugins) == 1:
                plugin = plugins[0]
                if plugin.type == "paragraph":
                    slides.append(self._make_paragraph_slide(t("Overview"), paragraph, notes))
                elif plugin.type == "bullets":
                    slides.append(self._make_bullets_slide(t("Key Points"), bullets, notes))
                elif plugin.type == "image":
                    slides.append(self._make_image_slide(t("Visual"), image_path))
                elif plugin.type == "chart":
                    slides.append(self._make_chart_slide(t("Chart"), self.build_chart_payload(parsed)))
                elif plugin.type == "table":
                    slides.append(self._make_table_slide(t("Table"), self.build_table_payload(parsed, title=raw_title)))
                continue

            if allow_paragraph and raw_title and idx != 0:
                slides.append(self._make_paragraph_slide(t("Overview"), raw_title, notes))

        return PresentationPlan(title=presentation_title, slides=slides[:MAX_SLIDES])

    def _make_section_slide(self, title: str) -> SlideSpec:
        return SlideSpec(
            layout="section_slide",
            title=title,
            plugins=[],
        )

    def _make_title_slide(self, title: str, subtitle: str = "") -> SlideSpec:
        return SlideSpec(
            layout="title_slide",
            title=title,
            subtitle=subtitle or "Generated from prompt",
            plugins=[],
        )

    def _make_paragraph_slide(self, title: str, text: str, notes: str = "") -> SlideSpec:
        plugins: List[SlidePlugin] = [
            SlidePluginParagraph(
                type="paragraph",
                data={"title": title or "Overview", "text": text, "top": 1.45, "height": 3.8, "font_size": 18},
            )
        ]
        if notes:
            plugins.append(SlidePluginNotes(type="notes", data={"notes": notes}))
        return SlideSpec(layout="title_content", title=title or "Overview", plugins=plugins)

    def _make_bullets_slide(self, title: str, points: List[str], notes: str = "") -> SlideSpec:
        plugins: List[SlidePlugin] = [
            SlidePluginBullets(
                type="bullets",
                data={"title": title or "Key Points", "points": points, "top": 1.55, "height": 4.85},
            )
        ]
        if notes:
            plugins.append(SlidePluginNotes(type="notes", data={"notes": notes}))
        return SlideSpec(layout="bullets_slide", title=title or "Key Points", plugins=plugins)

    def _make_chart_slide(self, title: str, chart_payload: Dict[str, Any]) -> SlideSpec:
        return SlideSpec(layout="chart_slide", title=title or "Chart", plugins=[SlidePluginChart(type="chart", data=chart_payload)])

    def _make_image_slide(self, title: str, image_path: str) -> SlideSpec:
        return SlideSpec(
            layout="image_slide",
            title=title or "Visual",
            plugins=[SlidePluginImage(type="image", data={"path": image_path, "caption": title or "Visual", "title": title or "Visual"})],
        )

    def _make_table_slide(self, title: str, table_payload: Dict[str, Any]) -> SlideSpec:
        return SlideSpec(layout="table_slide", title=title or "Table", plugins=[SlidePluginTable(type="table", data=table_payload)])

    def _make_mixed_slide(self, title: str, plugins: List[SlidePlugin], notes: str = "") -> SlideSpec:
        if notes:
            plugins = plugins + [SlidePluginNotes(type="notes", data={"notes": notes})]
        return SlideSpec(layout="mixed_content_slide", title=title, plugins=plugins)

    def extract_structured_slides(self, prompt: str) -> List[str]:
        pattern = re.compile(
            r"(?:^|\n)\s*slide\s*\d+\s*[:\-]?\s*(.*?)(?=(?:\n\s*slide\s*\d+\s*[:\-]?)|$)",
            re.IGNORECASE | re.DOTALL,
        )
        return [block.strip() for block in pattern.findall(prompt) if block.strip()]

    def extract_overall_title(self, prompt: str, blocks: List[str]) -> str:
        if blocks:
            first_title = self.extract_section_value(blocks[0], "title")
            if first_title:
                return first_title
        m = re.search(r'presentation on\s*["“](.*?)["”]', prompt, re.IGNORECASE | re.DOTALL)
        if m:
            return normalize_whitespace(m.group(1))
        first_line = normalize_whitespace(prompt.split("\n", 1)[0])
        clean_title = re.sub(r"(?i)\s*(?:with|including|key)?\s*sub-?topics?\s*[:\-].*$", "", first_line).strip()
        clean_title = re.sub(r"(?i)^presentation\s+on\s+", "", clean_title).strip()
        if not clean_title:
            clean_title = first_line
        return clean_title if len(clean_title) <= 60 else clean_title[:60].rstrip() + "..."

    def extract_section_value(self, text: str, key: str) -> Optional[str]:
        pattern = rf"(?im)^\s*{re.escape(key)}\b\s*[:\-]\s*(.+?)\s*$"
        m = re.search(pattern, text)
        if m:
            value = normalize_whitespace(m.group(1))
            return value or None
        return None

    def extract_heading_title(self, text: str) -> Optional[str]:
        for raw_line in text.splitlines():
            line = normalize_whitespace(raw_line)
            if not line:
                continue
            if re.match(r"^(title|subtitle|paragraph|bullets?|chart|chart type|values|categories|image|path|series name|table|notes|speaker notes|section)\b", line, re.IGNORECASE):
                continue
            if len(line) <= 50:
                return line
        return None

    def is_section_block(self, block: str, parsed: Dict[str, Any]) -> bool:
        if parsed.get("section_title"):
            return True

        lines = [normalize_whitespace(x) for x in block.splitlines() if normalize_whitespace(x)]
        if len(lines) != 1:
            return False

        line = lines[0]
        if len(line) <= 60 and line.upper() == line and any(ch.isalpha() for ch in line):
            if not parsed.get("title") and not parsed.get("subtitle"):
                return True
        return False

    def parse_slide_block(self, block: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "title": None,
            "subtitle": None,
            "section_title": None,
            "paragraph": "",
            "paragraph_lines": [],
            "bullets": [],
            "diagram": None,
            "chart_points": [],
            "chart_values": [],
            "chart_type": None,
            "chart_series": OrderedDict(),
            "chart_categories": [],
            "series_name": "Usage",
            "image_path": None,
            "table_headers": [],
            "table_rows": [],
            "notes_lines": [],
            "notes": "",
            "is_chart": False,
        }

        mode: Optional[str] = None
        current_series = "Usage"

        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            m = re.match(r"^\s*title\b\s*[:\-]\s*(.+?)\s*$", line, re.IGNORECASE)
            if m:
                result["title"] = clean_ai_instructions(m.group(1))
                mode = None
                continue

            m = re.match(r"^\s*subtitle\b\s*[:\-]\s*(.+?)\s*$", line, re.IGNORECASE)
            if m:
                result["subtitle"] = clean_ai_instructions(m.group(1))
                mode = None
                continue

            m = re.match(r"^\s*section\b\s*[:\-]\s*(.+?)\s*$", line, re.IGNORECASE)
            if m:
                result["section_title"] = clean_ai_instructions(m.group(1))
                mode = None
                continue

            m = re.match(r"^\s*(?:diagram|flowchart)\b\s*[:\-]\s*(.+?)\s*$", line, re.IGNORECASE)
            if m:
                result["diagram"] = clean_ai_instructions(m.group(1))
                mode = None
                continue

            m = re.match(r"^\s*paragraph\b\s*[:\-]?\s*(.*)$", line, re.IGNORECASE)
            if m:
                mode = "paragraph"
                tail = normalize_whitespace(m.group(1))
                if tail:
                    result["paragraph_lines"].append(tail)
                continue

            m = re.match(r"^\s*bullets?\b\s*[:\-]?\s*(.*)$", line, re.IGNORECASE)
            if m:
                mode = "bullets"
                tail = normalize_whitespace(m.group(1))
                if tail:
                    result["bullets"].append(tail)
                continue

            m = re.match(r"^\s*table\b\s*[:\-]?\s*(.*)$", line, re.IGNORECASE)
            if m:
                mode = "table"
                tail = normalize_whitespace(m.group(1))
                if tail and "|" in tail:
                    row = self.parse_table_row(tail)
                    if row:
                        result["table_rows"].append(row)
                continue

            m = re.match(r"^\s*chart\s*type\b\s*[:\-]\s*(.+?)\s*$", line, re.IGNORECASE)
            if m:
                result["chart_type"] = self.normalize_chart_type(m.group(1))
                result["is_chart"] = True
                mode = "chart"
                continue

            m = re.match(r"^\s*chart\b\s*[:\-]?\s*(.+?)\s*$", line, re.IGNORECASE)
            if m:
                value = normalize_whitespace(m.group(1))
                if value and value.lower() in {"line", "bar", "column", "pie"}:
                    result["chart_type"] = self.normalize_chart_type(value)
                result["is_chart"] = True
                mode = "chart"
                continue

            m = re.match(r"^\s*series\s*name\b\s*[:\-]\s*(.+?)\s*$", line, re.IGNORECASE)
            if m:
                current_series = normalize_whitespace(m.group(1)) or f"Series {len(result['chart_series']) + 1}"
                result["series_name"] = current_series
                result["chart_series"].setdefault(current_series, OrderedDict())
                result["is_chart"] = True
                continue

            m = re.match(r"^\s*series\b\s*[:\-]\s*(.+?)\s*$", line, re.IGNORECASE)
            if m:
                current_series = normalize_whitespace(m.group(1)) or f"Series {len(result['chart_series']) + 1}"
                result["series_name"] = current_series
                result["chart_series"].setdefault(current_series, OrderedDict())
                result["is_chart"] = True
                continue

            m = re.match(r"^\s*(?:image|path)\b\s*[:\-]\s*(.+?)\s*$", line, re.IGNORECASE)
            if m:
                result["image_path"] = normalize_whitespace(m.group(1))
                mode = None
                continue

            m = re.match(r"^\s*(?:notes|speaker\s*notes)\b\s*[:\-]?\s*(.*)$", line, re.IGNORECASE)
            if m:
                mode = "notes"
                tail = normalize_whitespace(m.group(1))
                if tail:
                    result["notes_lines"].append(tail)
                continue

            m = re.match(r"^\s*categories\b\s*[:\-]\s*(.+?)\s*$", line, re.IGNORECASE)
            if m:
                raw = normalize_whitespace(m.group(1))
                cats = self.split_inline_list(raw)
                if cats:
                    result["chart_categories"] = cats
                continue

            if mode == "paragraph":
                if re.match(r"^(title|subtitle|bullets?|chart|chart type|categories|values|image|path|series name|table|notes|speaker notes|section|diagram|flowchart)\b", line, re.IGNORECASE):
                    mode = None
                else:
                    result["paragraph_lines"].append(line)
                    continue

            if mode == "bullets":
                bullet_match = re.match(r"^(?:[-*•]|\d+[.)])\s*(.*\S)$", line)
                if bullet_match:
                    point = clean_ai_instructions(bullet_match.group(1))
                    if point:
                        result["bullets"].append(point)
                    continue
                if not re.match(r"^(title|subtitle|paragraph|chart|chart type|categories|values|image|path|series name|table|notes|speaker notes|section|diagram|flowchart)\b", line, re.IGNORECASE):
                    cleaned_pt = clean_ai_instructions(line)
                    if cleaned_pt:
                        result["bullets"].append(cleaned_pt)
                continue

            if mode == "table":
                if "|" in line:
                    row = self.parse_table_row(line)
                    if row:
                        result["table_rows"].append(row)
                    continue
                if re.match(r"^(title|subtitle|paragraph|bullets?|chart|chart type|image|path|notes|speaker notes|section|diagram|flowchart)\b", line, re.IGNORECASE):
                    mode = None
                else:
                    if result["table_rows"]:
                        result["table_rows"][-1].append(normalize_whitespace(line))
                continue

            if mode == "chart":
                if m := re.match(r"^\s*type\b\s*[:\-]\s*(.+?)\s*$", line, re.IGNORECASE):
                    result["chart_type"] = self.normalize_chart_type(m.group(1))
                    result["is_chart"] = True
                    continue
                if m := re.match(r"^\s*series\s*name\b\s*[:\-]\s*(.+?)\s*$", line, re.IGNORECASE):
                    current_series = normalize_whitespace(m.group(1)) or f"Series {len(result['chart_series']) + 1}"
                    result["series_name"] = current_series
                    result["chart_series"].setdefault(current_series, OrderedDict())
                    result["is_chart"] = True
                    continue
                if m := re.match(r"^\s*categories\b\s*[:\-]\s*(.+?)\s*$", line, re.IGNORECASE):
                    cats = self.split_inline_list(normalize_whitespace(m.group(1)))
                    if cats:
                        result["chart_categories"] = cats
                    continue
                if m := re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9 _%/\(\)-]{0,40})\s*[:=]\s*(\d+(?:\.\d+)?)\s*$", line):
                    category = normalize_whitespace(m.group(1))
                    value = parse_number(m.group(2))
                    if category and value is not None:
                        result["chart_points"].append(category)
                        result["chart_values"].append(value)
                        result["chart_series"].setdefault(current_series, OrderedDict())
                        result["chart_series"][current_series][category] = value
                        result["is_chart"] = True
                    continue

            if mode == "notes":
                if re.match(r"^(title|subtitle|paragraph|bullets?|chart|chart type|categories|values|image|path|series name|table|section|diagram|flowchart)\b", line, re.IGNORECASE):
                    mode = None
                else:
                    result["notes_lines"].append(line)
                    continue

            if "|" in line:
                row = self.parse_table_row(line)
                if row and len(row) >= 2:
                    result["table_rows"].append(row)
                    continue

        if not result["title"]:
            raw_h = self.extract_heading_title(block)
            result["title"] = clean_ai_instructions(raw_h) if raw_h else None
        else:
            result["title"] = clean_ai_instructions(result["title"])

        if result["subtitle"]:
            result["subtitle"] = clean_ai_instructions(result["subtitle"])

        if result["paragraph_lines"]:
            result["paragraph"] = clean_ai_instructions(" ".join(result["paragraph_lines"]))

        if result["bullets"]:
            result["bullets"] = [clean_ai_instructions(b) for b in result["bullets"] if clean_ai_instructions(b)]

        if result["notes_lines"]:
            result["notes"] = clean_ai_instructions(" ".join(result["notes_lines"]))

        if result["chart_series"] and not result["chart_categories"]:
            seen = []
            for mapping in result["chart_series"].values():
                for cat in mapping.keys():
                    if cat not in seen:
                        seen.append(cat)
            result["chart_categories"] = seen
        if not result["chart_series"] and result["chart_points"]:
            series_name = result.get("series_name") or "Usage"
            result["chart_series"] = OrderedDict({series_name: OrderedDict(zip(result["chart_points"], result["chart_values"]))})
        if self.is_chart_block(block.lower()):
            result["is_chart"] = True
        return result

    def split_inline_list(self, raw: str) -> List[str]:
        parts = re.split(r"\s*[|,;/]\s*", normalize_whitespace(raw))
        return [p for p in (normalize_whitespace(x) for x in parts) if p]

    def parse_table_row(self, line: str) -> List[str]:
        parts = [normalize_whitespace(x) for x in line.strip().strip("|").split("|")]
        return [p for p in parts if p]

    def build_chart_payload(self, parsed: Dict[str, Any], prompt_domain: str = "general") -> Dict[str, Any]:
        chart_series = parsed.get("chart_series") or OrderedDict()
        chart_type = parsed.get("chart_type") or "column"
        title = parsed.get("title") or "Performance Metrics & Data Analysis"
        categories = parsed.get("chart_categories") or parsed.get("chart_points") or ["Phase 1 (Baseline)", "Phase 2 (Growth)", "Phase 3 (Scale)", "Phase 4 (Maturity)"]
        series_name = parsed.get("series_name") or "Metrics Data"

        if chart_series:
            return {
                "chart_type": chart_type,
                "title": title,
                "categories": categories,
                "series_map": chart_series,
                "series_name": series_name,
            }

        raw_values = parsed.get("chart_values") or []
        clean_values = []
        for v in raw_values:
            num = parse_number(re.sub(r"[^\d.-]", "", str(v))) if not isinstance(v, (int, float)) else float(v)
            if num is not None:
                clean_values.append(num)

        if not clean_values or all(v == 0.0 for v in clean_values):
            t_lower = (title + " " + series_name + " " + prompt_domain).lower()
            if any(k in t_lower for k in ["latency", "response", "duration", "delay", "ms", "speed"]):
                clean_values = [145.0, 98.5, 45.2, 22.0][:len(categories)]
                if series_name == "Metrics Data" or series_name == "Usage":
                    series_name = "Latency (ms)"
            elif any(k in t_lower for k in ["availability", "uptime", "accuracy", "rate", "efficiency", "%", "share", "adoption"]):
                clean_values = [98.2, 99.1, 99.7, 99.99][:len(categories)]
                if series_name == "Metrics Data" or series_name == "Usage":
                    series_name = "Availability (%)"
            elif any(k in t_lower for k in ["revenue", "sales", "arr", "ebitda", "capital", "cost", "budget", "$", "dollar", "finance"]):
                clean_values = [1.8, 4.2, 9.5, 18.2][:len(categories)]
                if series_name == "Metrics Data" or series_name == "Usage":
                    series_name = "Revenue ($M)"
            else:
                clean_values = [round(28.5 * (i + 1) * 1.15, 1) for i in range(len(categories))]

        return {
            "chart_type": chart_type,
            "title": title,
            "categories": categories,
            "values": clean_values,
            "series_name": series_name,
        }

    def build_table_payload(self, parsed: Dict[str, Any], title: str) -> Dict[str, Any]:
        rows = parsed.get("table_rows") or []
        headers = parsed.get("table_headers") or []
        data_rows = rows

        if rows:
            if not headers and len(rows) >= 2:
                headers = rows[0]
                data_rows = rows[1:]
            elif not headers:
                headers = [f"Column {i + 1}" for i in range(len(rows[0]))]
                data_rows = rows

        return {"title": title or "Table", "headers": headers, "rows": data_rows}

    def is_chart_block(self, text_l: str) -> bool:
        if re.search(r"\b(chart|graph)\b", text_l):
            return True
        if re.search(r"\b[A-Za-z]{3,9}\s*[:=]\s*\d+(?:\.\d+)?\b", text_l):
            return True
        return False

    def normalize_chart_type(self, text: str) -> str:
        t = normalize_whitespace(text).lower()
        if "line" in t:
            return "line"
        if "bar" in t:
            return "bar"
        if "pie" in t:
            return "pie"
        return "column"

    def extract_bullets(self, text: str) -> List[str]:
        bullets: List[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if re.match(r"^(title|subtitle|paragraph|chart|chart type|categories|values|image|path|series name|table|notes|speaker notes|section)\b", line, re.IGNORECASE):
                continue
            bullet_match = re.match(r"^(?:[-*•]|\d+[.)])\s+(.*\S)$", line)
            if bullet_match:
                cleaned = normalize_whitespace(bullet_match.group(1))
                if cleaned:
                    bullets.append(cleaned)
        if bullets:
            return bullets[:MAX_BULLETS_PER_SLIDE]
        chunks = re.split(r"[.;]\s+|\n+", text)
        for chunk in chunks:
            chunk = normalize_whitespace(chunk)
            if not chunk:
                continue
            if re.match(r"^(title|subtitle|paragraph|chart|image|path|table|notes)\b", chunk, re.IGNORECASE):
                continue
            if len(chunk) >= 12:
                bullets.append(chunk)
        return bullets[:MAX_BULLETS_PER_SLIDE]
