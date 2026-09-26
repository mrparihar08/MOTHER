from __future__ import annotations

import logging
import math
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
    StructuredPresentationPlan,
    TwoStageSlide,
    ContentPlan,
    DesignPlan,
    GlobalDesignSystem,
    PresentationMetadata,
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
    "title",
    "agenda",
    "section",
    "introduction",
    "definition",
    "concept",
    "two_column",
    "three_cards",
    "four_cards",
    "comparison",
    "process",
    "workflow",
    "timeline",
    "architecture",
    "hierarchy",
    "cycle",
    "statistics",
    "chart",
    "table",
    "case_study",
    "applications",
    "advantages_disadvantages",
    "problem_solution",
    "risks",
    "roadmap",
    "conclusion",
    "key_takeaways",
    "thank_you",
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


PRESET_SLIDE_COUNTS: List[int] = [6, 8, 10, 15, 20, 25, 30]


def analyze_prompt_complexity(prompt: str, user_requested_count: Any = None) -> int:
    """
    Analyzes presentation prompt text, length, subtopics, domain, and explicit keywords
    to automatically select an optimal slide count from preset buckets: [6, 8, 10, 15, 20, 25, 30].
    """
    prompt_str = (prompt or "").strip()

    if isinstance(user_requested_count, str):
        if user_requested_count.lower() == "auto":
            user_requested_count = None
        elif user_requested_count.isdigit():
            user_requested_count = int(user_requested_count)
        else:
            user_requested_count = None

    # 1. Search for explicit slide count in prompt text (e.g. "12 slides", "15-slide presentation")
    if prompt_str:
        m_count = re.search(r"(\d+)\s*[-_]?\s*slides?\b", prompt_str, re.IGNORECASE)
        if m_count:
            val = int(m_count.group(1))
            return min(PRESET_SLIDE_COUNTS, key=lambda x: abs(x - val))

    # 2. If user_requested_count is explicitly provided, snap to nearest preset
    if user_requested_count is not None and isinstance(user_requested_count, int):
        return min(PRESET_SLIDE_COUNTS, key=lambda x: abs(x - user_requested_count))

    if not prompt_str:
        return 8

    # 3. Analyze complexity score
    words = prompt_str.split()
    word_count = len(words)
    prompt_l = prompt_str.lower()

    score = 0

    # Word count contribution
    if word_count < 8:
        score += 0
    elif word_count <= 20:
        score += 1
    elif word_count <= 50:
        score += 2
    else:
        score += 3

    # Subtopics contribution (if list markers, newlines, semicolons, or multiple comma-separated items exist)
    subtopic_count = 0
    if "\n" in prompt_str or ";" in prompt_str or re.search(r"(?:^|\n)\s*(?:\d+\.|\*|-)\s+", prompt_str):
        subtopics = re.findall(r"(?:^|\n|;|\b(?:\d+\.|\*|-))\s*([^\n;]+)", prompt_str)
        valid_subtopics = [s.strip() for s in subtopics if len(s.strip()) > 5]
        subtopic_count = len(valid_subtopics)

    comma_items = len([c for c in re.split(r"[,;]", prompt_str) if len(c.strip()) > 3])
    if subtopic_count >= 8:
        score += 3
    elif subtopic_count >= 4:
        score += 2
    elif subtopic_count >= 1 or comma_items >= 4:
        score += 2 if comma_items >= 4 else 1

    # Scope & depth keywords
    if re.search(r"\b(quick|short|brief|summary|basic|simple|light|101)\b", prompt_l):
        score -= 2

    if re.search(r"\b(detailed|comprehensive|deep dive|architecture|system design|microservices|infrastructure|database|security|pipeline|framework|analysis|metrics|comparison|benchmark|strategy)\b", prompt_l):
        score += 2

    if re.search(r"\b(exhaustive|complete guide|masterclass|end-to-end|curriculum|roadmap|full course|enterprise|multi-module|blueprint|all-inclusive|full stack)\b", prompt_l):
        score += 4

    domain = classify_prompt_domain(prompt_str)
    if domain in {"tech", "finance", "medical", "academic"}:
        score += 1

    # Bucket mapping to [6, 8, 10, 15, 20, 25, 30]
    if score <= 0:
        return 6
    elif score == 1 or score == 2:
        return 8
    elif score == 3 or score == 4:
        return 10
    elif score == 5 or score == 6:
        return 15
    elif score in (7, 8, 9, 10):
        return 20
    elif score in (11, 12, 13):
        return 25
    else:
        return 30


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
    from backend.chats.presentation.scripts.templates import TEMPLATE_PRESETS, build_template_pptx
    from backend.chats.presentation.scripts.generate_master_template import create_master_template

    tmpl_dir = Path("./templates").resolve()
    tmpl_dir.mkdir(parents=True, exist_ok=True)

    if template_name:
        candidate = Path(template_name).expanduser()
        if candidate.is_file():
            return str(candidate)

        stem = Path(template_name).stem.lower()
        file_name = template_name if template_name.endswith(".pptx") else f"{template_name}.pptx"
        named_candidate = tmpl_dir / file_name

        if named_candidate.is_file():
            return str(named_candidate)

        # Check if requested template is in preset suite
        if stem in TEMPLATE_PRESETS:
            try:
                created = build_template_pptx(stem, TEMPLATE_PRESETS[stem], output_dir=str(tmpl_dir))
                return created
            except Exception as exc:
                logger.warning("Failed to build preset template '%s': %s", stem, exc)

    # Fallback to default base template
    default_tpl = tmpl_dir / "base_template.pptx"
    if not default_tpl.is_file():
        try:
            create_master_template(str(default_tpl))
        except Exception as exc:
            logger.warning("Failed to auto-generate default master template: %s", exc)

    return str(default_tpl)



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


def best_font_size_for_bullets(points: List[Any], base: int = 18, box_width: float = 11.7, box_height: float = 5.0) -> int:
    pts = [normalize_whitespace(str(p)) for p in points if str(p).strip()]
    if not pts:
        return base

    w_eff = max(1.0, box_width - 0.6)
    for font_size in range(base, 9, -1):
        c_width = font_size * 0.0072
        cpl = max(10, int(w_eff / c_width))
        total_lines = sum(max(1, math.ceil(len(p) / cpl)) for p in pts)
        line_height_in = (font_size * 1.35) / 72.0
        est_height = total_lines * line_height_in + (len(pts) * 0.04) + 0.20
        if est_height <= box_height or font_size <= 10:
            return max(10, font_size)

    return 10


def best_font_size_for_paragraph(text: str, base: int = 15, box_width: float = 11.7, box_height: float = 5.0) -> int:
    text = normalize_whitespace(text)
    if not text:
        return base

    w_eff = max(1.0, box_width - 0.5)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for font_size in range(base, 9, -1):
        c_width = font_size * 0.0072
        cpl = max(10, int(w_eff / c_width))
        total_lines = sum(max(1, math.ceil(len(l) / cpl)) for l in lines) if lines else max(1, math.ceil(len(text) / cpl))
        line_height_in = (font_size * 1.30) / 72.0
        est_height = total_lines * line_height_in + (len(lines) * 0.04) + 0.20
        if est_height <= box_height or font_size <= 10:
            return max(10, font_size)

    return 10


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
        return "♦ "
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

    # Automatically analyze complexity & set slide count to preset bucket (6, 8, 10, 15, 20, 25, 30)
    req.slide_count = analyze_prompt_complexity(req.prompt, req.slide_count)

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
    if not getattr(req, "include_agenda_slide", True):
        options.append("Do NOT include an Agenda / Table of Contents slide; go directly from Title Cover to Introduction.")

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

    gemini_prompt = f"""You are an advanced AI-powered Presentation Generation Engine.
Your goal is to generate a professional, coherent, topic-specific presentation. Do NOT behave like a template filler. Every presentation must be dynamically planned according to the user's topic, audience, purpose, and requested slide count.

<topic>
{req.prompt}
</topic>

<instructions>
{instructions}
</instructions>

CORE ENGINE RULES & SPECIFICATIONS:

1. TOPIC ANALYSIS & BESPOKE ACTION-ORIENTED TITLE INTELLIGENCE:
- Target around {req.slide_count} slides.
- Analyze topic domain, target audience, complexity level, important subtopics, and logical dependencies before structuring slides.
- Every slide MUST have a clear purpose, topic-specific content, bespoke title, and informative subtitle.
- Slide 1 MUST be a main title cover with a bespoke title and subtitle.
- Slide 2 MUST be "Presentation Overview & Agenda". It MUST NOT contain any Image. The bullet points MUST dynamically list the exact bespoke slide titles of subsequent slides (Slide 3 to Slide N-1).
- Slide N-1 MUST be an executive summary with a bespoke title (e.g. "Strategic Takeaways & Future Horizon").
- Slide N MUST be "Thank You & Next Steps".

2. DYNAMIC SUBTOPIC GENERATION & NARRATIVE FLOW:
- Generate subtopics specifically for this topic domain. DO NOT reuse a fixed universal list (e.g. Intro -> History -> Architecture -> Benefits -> Security -> Case Study -> Future) unless those sections genuinely fit the topic.
- Follow a logical narrative flow tailored to the subject from context to core concepts, architecture/mechanism, applications, evidence, tradeoffs, challenges, case study, and conclusion.

3. ASSIGN A CLEAR PURPOSE TO EVERY SLIDE:
- Every slide must answer one clear question (e.g. "What is this topic?", "How does it work?", "What are the components?", "How do these compare?", "What are the real-world results?"). Never create a slide whose purpose is simply to add empty text.

4. CONTENT DRIVES DESIGN & SLIDE TYPE SELECTION:
- Definition -> Explanation + core concepts
- Timeline -> Chronological visual/phases
- Process / Workflow -> Step-by-step diagram (`Diagram: [Step 1] ➔ [Step 2] ➔ [Step 3]`)
- Architecture -> System/component diagram matching actual subject
- Comparison -> Clearly labeled comparison table with meaningful column headers
- Benefits / Features -> Highlighted cards / bullet breakdown
- Statistics -> KPI stat cards (`Stat: [Value] | [Metric Description]`) or Charts (`Chart: [type]`)
- Case Study -> Problem -> Solution -> Implementation -> Outcome -> Lesson (label hypothetical examples as "Illustrative Example")
- Best Practices / Recommendations -> Actionable items
- Conclusion -> Derived strictly from actual presentation findings across the deck

5. ELIMINATE GENERIC FILLER:
- NEVER output meaningless filler phrases like "Key aspect of...", "Critical operational considerations...", "Strategic takeaway...", "Comprehensive domain analysis...", "Foundational workflows...", "Industry benchmarks...", "Implementation protocols...", "Key architectural drivers...", "Performance optimizations designed to achieve scalable outcomes...".
- Replace generic language with actual concrete facts, real terminology, domain metrics, and actionable details.

6. MEANINGFUL COMPARISON TABLES:
- NEVER create tables with undefined "Option A" or "Option B". Always use topic-specific labeled concepts (e.g., "Supervised Learning vs Unsupervised Learning", "Monolithic vs Microservices").
- Every column and row must have a meaningful label.

7. TOPIC-SPECIFIC ARCHITECTURE:
- Architecture diagrams must represent actual subject components (e.g. `[Data Sources] ➔ [Ingestion Pipeline] ➔ [Preprocessing] ➔ [Model Training] ➔ [Inference Engine] ➔ [Prediction API]`), never generic "Layer 1 ➔ Layer 2 ➔ Layer 3".

8. VISUAL INTELLIGENCE & RELEVANCE:
- Images must match the actual meaning of the slide (`TITLE + KEY MESSAGE + CONTENT + VISUAL PURPOSE`).
- Use photos, diagrams, flowcharts, timelines, tables, KPI stat cards, or charts appropriately. Do not put random images on slides where diagrams or charts communicate better.

9. PREVENT REPETITION:
- Do not repeat paragraphs, bullet points, examples, explanations, or diagrams across slides. Each slide must add a genuinely new perspective.

10. CONTENT QUALITY & DENSITY:
- PARAGRAPH RICHNESS & LENGTH: Paragraph text MUST be rich, detailed, and comprehensive (60 to 100 words per paragraph, consisting of 2 to 4 complete sentences). Never output single-sentence fragments.
- BULLET QUALITY: Bullet points must be high-impact, insightful, and audience-ready (3-5 bullet points per slide, 18-30 words per bullet point with concrete metrics and domain terminology).

11. INTELLIGENT CHART SELECTION & DATA GROUNDING:
- Select chart type best suited for numerical metrics (`Chart: line`, `Chart: column`, `Chart: bar`, `Chart: pie`, `Chart: donut`, `Chart: area`). Ground all values in domain reality.

OUTPUT FORMAT:
Return ONLY the plain-text slide script for Slide 1 to Slide N (where N = {req.slide_count} target slides). Do not use Markdown code fences, introductory prose, or JSON.
Use these format structures across slides (Slide 1 to Slide N):

Slide 1:
Title: [Bespoke Topic Title]
Subtitle: [Informative Executive Subtitle]

Slide 2:
Title: Presentation Overview & Agenda
Bullets:
- [Dynamic Action Slide 3 Title]
- [Dynamic Action Slide 4 Title]
- [Dynamic Action Slide 5 Title]
- [Dynamic Action Slide 6 Title]

Slide 3:
Title: [Action-Oriented Domain Headline]
Subtitle: [Key Domain Context]
Paragraph: [Detailed narrative paragraph providing deep domain context, core definition, and background scope (60-100 words).]

Slide 4:
Title: [Specific Architecture / Process Title]
Diagram: [Data Source Ingestion] ➔ [Core Processing Engine] ➔ [Analytics Pipeline] ➔ [Output API]
Bullets:
- Primary data ingestion and entry point
- Core processing engine and analytics pipeline
- Output dispatch and service integration

Slide 5:
Title: [Domain Performance & Reliability Metrics]
Stat: 99.9% SLA | Industry Benchmark Reliability
Stat: 4.2x Speedup | Processing Throughput Rate
Stat: 35% Reduction | Annual Infrastructure Savings

Slide 6:
Title: [Architectural Tradeoffs & Technology Comparison]
Pros: High Scalability, Fault Isolation, Independent Deployments
Cons: Increased Network Latency, Distributed Logging Complexity

Slide 7:
Title: [Topic-Specific Feature Comparison]
Table:
Criterion | [Concept X] | [Concept Y]
Performance | High (99.9% uptime) | Medium (98.5%)
Cost Tier | Enterprise Tier | Open Source
Scalability | Multi-region | Single-region

Slide 8:
Title: [Real-World Deployment Scenario]
Image: [Specific topic keyword query]
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
# JSON Presentation Plan Parser & 2-Stage Plan Builder
# ---------------------------------------------------------------------

import json


def parse_json_presentation_plan(raw_text: str) -> Optional[StructuredPresentationPlan]:
    if not raw_text or not isinstance(raw_text, str):
        return None
    raw = raw_text.strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    json_str = match.group(0)
    try:
        data = json.loads(json_str)
        if isinstance(data, dict) and "presentation" in data and "slides" in data:
            return StructuredPresentationPlan.model_validate(data)
    except Exception as exc:
        logger.debug("Failed to parse JSON presentation plan: %s", exc)
    return None


def build_structured_plan(plan: PresentationPlan, prompt: str = "") -> StructuredPresentationPlan:
    domain = classify_prompt_domain(prompt or plan.title)

    gds = GlobalDesignSystem(
        theme_name=plan.theme.get("name", "modern_corporate") if plan.theme else "modern_corporate",
        background=plan.theme.get("background", "#FFFFFF") if plan.theme else "#FFFFFF",
        primary_color=plan.theme.get("primary", "#0F172A") if plan.theme else "#0F172A",
        secondary_color=plan.theme.get("secondary", "#3B82F6") if plan.theme else "#3B82F6",
        accent_colors=[plan.theme.get("accent", "#10B981")] if plan.theme else ["#10B981", "#F59E0B", "#6366F1"],
        text_color=plan.theme.get("text", "#1E293B") if plan.theme else "#1E293B",
        muted_text_color="#64748B",
        font_family="Inter, Arial, sans-serif",
        title_font_size="28pt",
        subtitle_font_size="18pt",
        body_font_size="14pt",
        border_radius="8px",
        spacing_system="relaxed",
        visual_style="modern",
    )

    two_stage_slides: List[TwoStageSlide] = []

    for idx, slide in enumerate(plan.slides):
        s_num = idx + 1
        title = slide.title or f"Slide {s_num}"
        subtitle = slide.subtitle or ""
        t_lower = title.lower()

        stype = "concept"
        if idx == 0 or slide.layout == "title_slide":
            stype = "title" if idx == 0 else "thank_you"
        elif "agenda" in t_lower or "overview" in t_lower:
            stype = "agenda"
        elif "introduction" in t_lower or "context" in t_lower:
            stype = "introduction"
        elif "definition" in t_lower:
            stype = "definition"
        elif "conclusion" in t_lower or "summary" in t_lower:
            stype = "conclusion"
        elif "thank" in t_lower or "q&a" in t_lower:
            stype = "thank_you"
        elif any(p.type == "chart" for p in slide.plugins):
            stype = "chart"
        elif any(p.type == "table" for p in slide.plugins):
            stype = "table"
        elif any(p.type == "diagram" for p in slide.plugins):
            if "roadmap" in t_lower or "timeline" in t_lower:
                stype = "timeline"
            elif "architecture" in t_lower or "stack" in t_lower:
                stype = "architecture"
            else:
                stype = "process"
        elif "comparison" in t_lower or "versus" in t_lower or "vs" in t_lower:
            stype = "comparison"
        elif "application" in t_lower or "use case" in t_lower:
            stype = "applications"
        elif "risk" in t_lower or "mitigation" in t_lower:
            stype = "risks"
        elif "roadmap" in t_lower:
            stype = "roadmap"

        content_items: List[Any] = []
        speaker_notes = ""
        visual_info: Dict[str, Any] = {"type": "none", "description": "Standard content presentation"}

        for p in slide.plugins:
            if p.type == "bullets":
                pts = p.data.get("points") or []
                content_items.extend(pts)
            elif p.type == "paragraph":
                txt = p.data.get("text") or ""
                if txt:
                    content_items.append(txt)
            elif p.type == "notes":
                speaker_notes = p.data.get("notes") or ""
            elif p.type == "chart":
                visual_info = {
                    "type": "chart",
                    "chart_type": p.data.get("chart_type", "column"),
                    "data": p.data,
                }
            elif p.type == "table":
                visual_info = {
                    "type": "table",
                    "data": p.data,
                }
            elif p.type == "diagram":
                visual_info = {
                    "type": p.data.get("diagram_type", "flowchart"),
                    "steps": p.data.get("diagram", "").split(" ➔ "),
                    "header": p.data.get("header") or title,
                }

        purpose = f"Communicate {stype} details for {title}"

        cp = ContentPlan(
            type=stype,
            purpose=purpose,
            title=title,
            subtitle=subtitle,
            key_message=subtitle if subtitle and subtitle.strip().lower() != title.strip().lower() else "",
            content=content_items,
            speaker_notes=speaker_notes,
        )

        density = "low" if stype in {"title", "thank_you", "section"} else ("high" if stype in {"comparison", "table", "chart"} else "medium")

        dp = DesignPlan(
            layout=slide.layout or "mixed_content_slide",
            background="default",
            title_position="center" if stype in {"title", "thank_you"} else "top_left",
            content_alignment="center" if stype in {"title", "thank_you"} else "left",
            density=density,
            visual=visual_info,
            elements=[],
            spacing="balanced",
            emphasis=[title],
        )

        two_stage_slides.append(TwoStageSlide(
            slide_number=s_num,
            content_plan=cp,
            design_plan=dp,
        ))

    meta = PresentationMetadata(
        title=plan.title,
        subtitle=plan.slides[0].subtitle if plan.slides else "",
        audience="General Audience",
        purpose="Executive Presentation",
        slide_count=len(plan.slides),
    )

    return StructuredPresentationPlan(
        presentation=meta,
        design_system=gds,
        slides=two_stage_slides,
    )


# ---------------------------------------------------------------------
# Local Fallback Prompt Planner
# ---------------------------------------------------------------------

class PromptPlanner:
    def extract_user_subtopics(self, prompt: str) -> List[str]:
        prompt = (prompt or "").strip()
        if not prompt:
            return []

        match = re.search(
            r"(?:subtopics?|sub-topics?|topics?|sections?|including|covering|cover|with|key topics?|points?)\s*[:\-]?\s*(.+?)(?=\n\n|\.\s*(?:Use|Keep|Make|Ending|Add|$)|$)",
            prompt,
            re.IGNORECASE | re.DOTALL,
        )
        raw_subtopics = ""
        if match:
            raw_subtopics = match.group(1).strip()
        elif "\n" in prompt:
            lines = [l.strip() for l in prompt.splitlines() if l.strip()]
            if len(lines) >= 2:
                raw_subtopics = "\n".join(lines[1:])

        if raw_subtopics:
            raw_subtopics = re.sub(r"(?i)^(?:presentation\s+on|create\s+a\s+\d+[-_]?slide[s]?\s+.*?\s+on|covering|topics?)\s*", "", raw_subtopics)
            parts = re.split(r"[,;|\n•*]|\band\b", raw_subtopics)
            cleaned = []
            for p in parts:
                c = normalize_whitespace(p)
                c = re.sub(r"^\s*(?:\d+[\.\)]|[a-zA-Z][\.\)]|[\-*•–])\s*", "", c)
                c = c.strip(".*-“\" ”:;,")
                c = re.sub(r"(?i)^(?:presentation\s+on|covering|topics?)\s*", "", c).strip()
                if (
                    c
                    and len(c) >= 2
                    and not re.match(r"^(and|or|with|etc|following|slides?|ppt|presentation|ending|strong|conclusion|covering|on)$", c, re.IGNORECASE)
                    and not re.search(r"(?i)\b\d+\s*[-_]?\s*slides?\b", c)
                ):
                    if c.islower():
                        c = c.title()
                    cleaned.append(c)
            if cleaned:
                seen = set()
                dedup = []
                for item in cleaned:
                    if item.lower() not in seen:
                        seen.add(item.lower())
                        dedup.append(item)
                return dedup[:30]

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
        user_subtopics: Optional[List[str]] = None,
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
            desired_count = analyze_prompt_complexity(prompt, target_slide_count)

            if domain == "tech":
                fallback_topics = [
                    ("Main Title", "title"),
                    (labels["agenda"], "bullets"),
                    ("Introduction & Executive Context", "paragraph"),
                    ("Problem Statement & Technical Challenges", "bullets"),
                    ("Strategic System Objectives", "bullets"),
                    ("System Architecture & Core Infrastructure", "diagram"),
                    ("Data Pipeline & Event Streaming Protocol", "diagram"),
                    ("API Gateway & Microservices Protocol", "table"),
                    ("Database Schema & Persistence Layer", "table"),
                    ("Caching Strategy & In-Memory Optimization", "paragraph"),
                    ("Authentication & Security Infrastructure", "bullets"),
                    ("Zero-Trust Encryption & Access Control", "bullets"),
                    ("Concurrency & Async Worker Threadpools", "paragraph"),
                    ("Machine Learning & Intelligence Cascade", "chart"),
                    ("Performance Benchmarks & Latency SLA", "chart"),
                    ("Scalability, Auto-Scaling & Load Balancing", "chart"),
                    ("Fault Tolerance & High Availability", "bullets"),
                    ("Observability & Distributed Tracing", "table"),
                    ("DevOps Pipeline & CI/CD Automation", "diagram"),
                    ("Container Orchestration & Kubernetes", "bullets"),
                    ("Infrastructure as Code & Cloud Deployments", "paragraph"),
                    ("Third-Party Integrations & Webhooks", "table"),
                    ("Disaster Recovery & Data Replication", "bullets"),
                    ("Compliance, Audit Logs & Governance", "bullets"),
                    ("Cloud Resource Optimization & TCO", "chart"),
                    ("Real-World Use Cases & Case Studies", "mixed"),
                    ("Lessons Learned & Refinements", "paragraph"),
                    ("Future Scope & Tech Roadmap", "bullets"),
                    (labels["conclusion"], "paragraph"),
                    (labels["thanks"], "section"),
                ]
            elif domain == "finance":
                fallback_topics = [
                    ("Main Title", "title"),
                    (labels["agenda"], "bullets"),
                    ("Executive Summary & Financial Scope", "paragraph"),
                    ("Macroeconomic Context & Market Drivers", "bullets"),
                    ("Strategic Financial Objectives", "bullets"),
                    ("Monetization Model & Revenue Streams", "diagram"),
                    ("Quarterly Revenue Growth Trajectory", "chart"),
                    ("Expense Structure & Cost Allocations", "chart"),
                    ("EBITDA & Net Profit Margins", "chart"),
                    ("Cash Flow Statement & Liquidity Metrics", "table"),
                    ("Balance Sheet Asset & Liability Structure", "table"),
                    ("Valuation Metrics & Peer Benchmarking", "table"),
                    ("Unit Economics & LTV Metric Analysis", "chart"),
                    ("Customer Acquisition Cost & Payback Period", "chart"),
                    ("Capital Structure & Debt Management", "paragraph"),
                    ("Investor Relations & Equity Value", "bullets"),
                    ("Strategic Mergers, Acquisitions & Deals", "bullets"),
                    ("Financial Risk Management & Mitigation", "bullets"),
                    ("Regulatory Governance & Audit Trail", "table"),
                    ("Tax Strategy & Global Compliance", "paragraph"),
                    ("Departmental Budget Distribution", "chart"),
                    ("Cost Optimization & Savings Opportunities", "bullets"),
                    ("5-Year Financial Forecast & Projections", "chart"),
                    ("Scenario Analysis & Stress Testing", "mixed"),
                    ("Capital Expenditure (CapEx) Roadmap", "bullets"),
                    ("Portfolio Diversification Strategy", "bullets"),
                    ("ESG & Sustainable Finance Standards", "paragraph"),
                    ("Strategic Growth Roadmap", "bullets"),
                    (labels["conclusion"], "paragraph"),
                    (labels["thanks"], "section"),
                ]
            elif domain == "business":
                fallback_topics = [
                    ("Main Title", "title"),
                    (labels["agenda"], "bullets"),
                    ("Executive Context & Business Scope", "paragraph"),
                    ("Market Opportunity & Demographics", "bullets"),
                    ("Core Vision, Mission & Values", "paragraph"),
                    ("Business Model & Value Proposition", "diagram"),
                    ("Product Portfolio & Service Lines", "table"),
                    ("Competitive Landscape & Market Positioning", "table"),
                    ("SWOT Matrix & Strategic Quadrants", "table"),
                    ("Go-to-Market (GTM) Strategy", "diagram"),
                    ("Sales Pipeline & Distribution Channels", "bullets"),
                    ("Marketing Execution & Lead Generation", "chart"),
                    ("Customer Retention & Cohort Analytics", "chart"),
                    ("Operational Workflow & Logistics", "diagram"),
                    ("Strategic Alliances & Ecosystem Partners", "bullets"),
                    ("Governance & Leadership Structure", "diagram"),
                    ("Key Performance Indicators (KPIs)", "chart"),
                    ("Risk Mitigation & Business Continuity", "bullets"),
                    ("Legal Framework & Quality Standards", "table"),
                    ("Product Innovation & R&D Pipeline", "diagram"),
                    ("Brand Positioning & Brand Equity", "paragraph"),
                    ("Digital Transformation & Automation", "bullets"),
                    ("Financial Trajectory & Revenue Goals", "chart"),
                    ("Resource Optimization & Cost Management", "chart"),
                    ("Global Expansion & Regional Scaling", "bullets"),
                    ("Client Case Studies & Testimonials", "mixed"),
                    ("Corporate Responsibility & Ethics", "paragraph"),
                    ("Strategic Milestones & Roadmap", "bullets"),
                    (labels["conclusion"], "paragraph"),
                    (labels["thanks"], "section"),
                ]
            elif domain == "medical":
                fallback_topics = [
                    ("Main Title", "title"),
                    (labels["agenda"], "bullets"),
                    ("Clinical Overview & Scope", "paragraph"),
                    ("Epidemiological Insights & Disease Profile", "bullets"),
                    ("Pathophysiology & Disease Mechanism", "diagram"),
                    ("Clinical Manifestations & Symptoms", "bullets"),
                    ("Diagnostic Imaging & Lab Protocols", "table"),
                    ("Therapeutic Guidelines & Standard of Care", "table"),
                    ("Pharmacology & Mechanism of Action", "diagram"),
                    ("Clinical Trial Methodology", "diagram"),
                    ("Phase Metrics & Trial Efficacy Data", "chart"),
                    ("Safety Profile & Adverse Events", "chart"),
                    ("Patient Survival & Recovery Rates", "chart"),
                    ("Comparative Drug & Treatment Matrix", "table"),
                    ("FDA & Global Regulatory Alignment", "bullets"),
                    ("Precision Medicine & Patient Stratification", "paragraph"),
                    ("Clinical Workflow & Hospital Integration", "diagram"),
                    ("Healthcare Economics & Treatment Cost", "chart"),
                    ("Quality of Life Metrics & Patient Care", "bullets"),
                    ("Medical Technology Integration", "table"),
                    ("Biomarker Profiles & Genomic Data", "paragraph"),
                    ("Clinical Risk Management & Safety", "bullets"),
                    ("Multidisciplinary Care Coordination", "diagram"),
                    ("Real-World Evidence & Post-Market Data", "mixed"),
                    ("Global Public Health Impact", "bullets"),
                    ("Ethical Standards & Informed Consent", "paragraph"),
                    ("Emerging Clinical Therapies", "bullets"),
                    ("Clinical Research & Future Horizon", "bullets"),
                    (labels["conclusion"], "paragraph"),
                    (labels["thanks"], "section"),
                ]
            elif domain == "academic":
                fallback_topics = [
                    ("Main Title", "title"),
                    (labels["agenda"], "bullets"),
                    ("Abstract & Core Research Scope", "paragraph"),
                    ("Problem Statement & Research Questions", "bullets"),
                    ("Theoretical Model & Core Hypotheses", "paragraph"),
                    ("Literature Review & Historical Context", "table"),
                    ("Research Methodology & Framework", "diagram"),
                    ("Data Sampling & Gathering Methods", "bullets"),
                    ("Experimental Setup & Key Controls", "table"),
                    ("Qualitative & Quantitative Protocols", "table"),
                    ("Empirical Results & Statistical Analysis", "chart"),
                    ("Model Significance & Validation Data", "chart"),
                    ("Comparative Findings vs Literature", "table"),
                    ("Analytical Proofs & Theoretical Notes", "paragraph"),
                    ("Empirical Case Study Analysis A", "mixed"),
                    ("Empirical Case Study Analysis B", "mixed"),
                    ("Mathematical & Algorithmic Breakdown", "diagram"),
                    ("Sensitivity Analysis & Variable Impact", "chart"),
                    ("Discussion of Core Findings", "paragraph"),
                    ("Theoretical & Practical Implications", "bullets"),
                    ("Research Limitations & Constraints", "bullets"),
                    ("Validity & Bias Control Measures", "table"),
                    ("Cross-Disciplinary Applications", "bullets"),
                    ("Policy & Educational Recommendations", "paragraph"),
                    ("Academic Dissemination & Publications", "bullets"),
                    ("Peer Review & Methodological Revisions", "paragraph"),
                    ("Grant Funding & Resource Usage", "chart"),
                    ("Future Directions & Research Horizons", "bullets"),
                    (labels["conclusion"], "paragraph"),
                    (labels["thanks"], "section"),
                ]
            else:
                fallback_topics = [
                    ("Main Title", "title"),
                    (labels["agenda"], "bullets"),
                    ("Introduction & Executive Context", "paragraph"),
                    ("Core Principles & Foundational Scope", "paragraph"),
                    ("Problem Statement & Industry Challenges", "bullets"),
                    ("Objectives & Strategic Deliverables", "bullets"),
                    ("Historical Background & Evolution", "bullets"),
                    ("Current Status & Industry Landscape", "mixed"),
                    ("System Architecture & Infrastructure", "diagram"),
                    ("Process Workflow & Execution Lifecycle", "diagram"),
                    ("Comprehensive Solution Comparison", "table"),
                    ("Key Features & Capabilities Matrix", "table"),
                    ("Performance Metrics & Benchmark Data", "chart"),
                    ("Growth Analytics & Impact Metrics", "chart"),
                    ("Strategic Advantages & Key Benefits", "bullets"),
                    ("Operational Constraints & Risk Factors", "bullets"),
                    ("Security Protocols & Governance", "bullets"),
                    ("Quality Standards & Compliance Matrix", "table"),
                    ("Resource Allocation & Utilization", "chart"),
                    ("Integration Protocol & System APIs", "diagram"),
                    ("User Experience & Engagement Model", "paragraph"),
                    ("Real-World Use Cases & Applications", "mixed"),
                    ("Enterprise Implementation Case Study", "mixed"),
                    ("Scaled Optimization Case Study", "mixed"),
                    ("Lessons Learned & Best Practices", "paragraph"),
                    ("Cost-Benefit Analysis & ROI", "chart"),
                    ("Long-Term Viability & Sustainability", "paragraph"),
                    ("Future Scope & Innovation Roadmap", "bullets"),
                    (labels["conclusion"], "paragraph"),
                    (labels["thanks"], "section"),
                ]

            custom_user_subtopics = user_subtopics or self.extract_user_subtopics(prompt)
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

                # Pad custom_topics with domain fallback topics if needed
                existing_titles = {t[0].lower() for t in custom_topics}
                for item in fallback_topics:
                    if item[0].lower() not in existing_titles and item[0] not in ("Main Title", labels["agenda"]):
                        custom_topics.append(item)
                        existing_titles.add(item[0].lower())
                    if len(custom_topics) >= 30:
                        break

                custom_topics.append((labels["conclusion"], "paragraph"))
                custom_topics.append((labels["thanks"], "section"))
                fallback_topics = custom_topics

            total_available = len(fallback_topics)
            if desired_count >= total_available:
                selected_indices = list(range(total_available))
            else:
                front_indices = [0, 1, 2] if total_available > 3 else [0, 1]
                back_indices = [total_available - 2, total_available - 1]
                mid_needed = desired_count - len(front_indices) - len(back_indices)

                if mid_needed > 0:
                    start_mid = len(front_indices)
                    end_mid = total_available - 3
                    step = (end_mid - start_mid) / max(1, mid_needed - 1) if mid_needed > 1 else 0
                    middle_indices = [int(round(start_mid + i * step)) for i in range(mid_needed)]
                else:
                    middle_indices = []

                selected_indices = front_indices + middle_indices + back_indices

            seen_i = set()
            unique_indices = []
            for i in selected_indices:
                if i not in seen_i and 0 <= i < total_available:
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
                    para_text = (
                        f"In-depth analysis of {topic} within the context of {presentation_title}. "
                        f"This slide examines core mechanisms, operational principles, key functional components, "
                        f"and real-world application strategies relevant to {presentation_title}."
                    )
                    slides.append(self._make_paragraph_slide(topic, para_text))
                elif layout_type == "table" and allow_table:
                    comp_match = re.search(r"(.+?)\s+(?:vs\.?|versus|compared\s+to)\s+(.+)", presentation_title, re.IGNORECASE)
                    if comp_match:
                        opt_a = re.sub(r"(?i)^(?:presentation\ |overview\ |comparison\ |systems?\ )*", "", comp_match.group(1)).strip()
                        opt_b = re.sub(r"(?i)\s*(?:systems?|technologies|architecture|comparison)$", "", comp_match.group(2)).strip()
                        table_headers = ["Criterion / Metric", (opt_a[:22] or "Baseline Approach"), (opt_b[:22] or "Advanced Approach")]
                        table_rows = [
                            ["Data Architecture", f"Strict {opt_a[:12]} Schema", f"Dynamic {opt_b[:12]} Format"],
                            ["Consistency Model", "Strong Immediate Consistency", "Eventual / Flexible Consistency"],
                            ["Scalability Model", "Vertical Scale-Up", "Horizontal Auto-Sharding"],
                            ["Query Interface", "Standardized Query Engine", "Flexible API / Document Query"],
                        ]
                    else:
                        table_headers = ["Criterion / Metric", f"{presentation_title[:15]} Standard", f"{presentation_title[:15]} Advanced"]
                        table_rows = [
                            ["Performance", "Standard Baseline", "High Throughput Execution"],
                            ["Scalability", "Single-Region Deployment", "Global Multi-Cluster Infrastructure"],
                            ["Security & Governance", "Standard Encryption Protocols", "Zero-Trust Enterprise Compliance"],
                            ["Operational Efficiency", "Baseline Resource Allocation", "Automated Resource Optimization"],
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
                                "slide_title": topic,
                                "title": f"{topic} Process Flow",
                                "header": f"{topic} Process Flow",
                                "diagram_title": f"{topic} Process Flow",
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

            return ensure_conclusion_and_thankyou_slides(
                PresentationPlan(title=presentation_title, slides=slides[:desired_count]),
                presentation_title,
            )

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
                plugins.append(SlidePluginDiagram(type="diagram", data={
                    "diagram": diagram,
                    "diagram_type": diag_type,
                    "slide_title": raw_title,
                    "title": f"{raw_title} Process Flow",
                    "header": f"{raw_title} Process Flow",
                    "diagram_title": f"{raw_title} Process Flow",
                }))

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
                expanded = (
                    f"Detailed domain overview and strategic analysis for {raw_title}. "
                    f"This section examines core technology standards, operational workflows, and domain benchmarks within {presentation_title}, "
                    f"delivering actionable insights to drive enterprise value and system maturity."
                )
                slides.append(self._make_paragraph_slide(t("Overview"), expanded, notes))

        return ensure_conclusion_and_thankyou_slides(
            PresentationPlan(title=presentation_title, slides=slides[:MAX_SLIDES]),
            presentation_title,
        )

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
        clean_text = normalize_whitespace(text or "")
        words = clean_text.split()
        if len(words) < 25 and clean_text:
            topic_ctx = title if title and title.lower() not in {"overview", "key points", "slide", "details"} else "this domain"
            enrichment = (
                f" This comprehensive domain analysis details core operational mechanisms, strategic rationale, "
                f"and industry benchmarks for {topic_ctx}. It highlights key architectural drivers, risk mitigations, "
                f"and implementation protocols designed to ensure scalable performance and measurable long-term value."
            )
            clean_text = (clean_text.rstrip(".") + "." + enrichment).strip()
            clean_text = re.sub(r"\.\s*\.", ".", clean_text)
            clean_text = normalize_whitespace(clean_text)

        plugins: List[SlidePlugin] = [
            SlidePluginParagraph(
                type="paragraph",
                data={"title": title or "Overview", "text": clean_text, "top": 1.45, "height": 3.8, "font_size": 18},
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
                return normalize_whitespace(re.sub(r"[*“\"”]", "", first_title))

        first_line = normalize_whitespace(prompt.split("\n", 1)[0])
        clean_title = re.sub(r"(?i)\s*(?:with|including|key)?\s*sub-?topics?\s*[:\-].*$", "", first_line).strip()
        clean_title = re.sub(r"(?i)\s*(?:covering|includes|with|focusing\s+on)\s+.*$", "", clean_title).strip()

        clean_title = re.sub(
            r"(?i)^(?:create|make|generate|build|draft|prepare|design)?\s*(?:a|an)?\s*(?:\d+[-_\s]*slides?|\d+[-_\s]*page)?\s*(?:presentation|ppt|deck|slide deck)\s+(?:on|about|for)\s+",
            "",
            clean_title,
        ).strip()
        clean_title = re.sub(r"(?i)^(?:topic|title)\s*[:\-]\s*", "", clean_title).strip()
        clean_title = re.sub(r"(?i)^presentation\s+on\s+", "", clean_title).strip()
        clean_title = re.sub(r"[*“\"”]", "", clean_title).strip()

        if not clean_title or len(clean_title) < 3:
            clean_title = first_line

        if clean_title.islower():
            clean_title = clean_title.title()

        return clean_title if len(clean_title) <= 70 else clean_title[:70].rstrip() + "..."

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
            c_type = str(chart_type).lower()
            if c_type == "radar":
                categories = ["Security & Trust", "Scalability", "Speed & Latency", "Usability", "Cost Efficiency"]
                clean_values = [88.0, 94.0, 76.0, 90.0, 82.0]
                if series_name == "Metrics Data" or series_name == "Usage":
                    series_name = "Capability Score (0-100)"
            elif c_type == "gauge":
                categories = ["System SLA Uptime Target"]
                clean_values = [99.8]
                if series_name == "Metrics Data" or series_name == "Usage":
                    series_name = "Target Attainment (%)"
            elif c_type == "waterfall":
                categories = ["Q1 Baseline", "New Revenue", "OpEx Costs", "Tax & Subtraction", "Net Q2 Total"]
                clean_values = [120.0, 45.0, -22.0, -14.0, 129.0]
                if series_name == "Metrics Data" or series_name == "Usage":
                    series_name = "Net Financial Change ($M)"
            elif c_type in {"pie", "donut"}:
                categories = ["Enterprise Tier", "Mid-Market", "SMB & Startup", "Individual"]
                clean_values = [42.0, 28.0, 18.0, 12.0]
                if series_name == "Metrics Data" or series_name == "Usage":
                    series_name = "Share Distribution (%)"
            elif c_type in {"line", "area", "trend"}:
                categories = ["2021", "2022", "2023", "2024", "2025"]
                clean_values = [18.5, 34.2, 58.7, 82.4, 94.0]
                if series_name == "Metrics Data" or series_name == "Usage":
                    series_name = "Adoption Rate (%)"
            elif c_type in {"bar", "bar_horizontal"}:
                categories = ["Primary Vector", "Secondary Factor", "Operational Impact", "Policy Gap"]
                clean_values = [68.4, 48.2, 32.8, 19.5]
                if series_name == "Metrics Data" or series_name == "Usage":
                    series_name = "Severity & Impact Index"
            else:
                clean_values = [28.5, 54.0, 82.5, 120.0][:len(categories)]
                while len(clean_values) < len(categories):
                    clean_values.append(round(28.5 * (len(clean_values) + 1) * 1.15, 1))
                if series_name == "Metrics Data" or series_name == "Usage":
                    series_name = "Performance Index"

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
        if "radar" in t or "spider" in t:
            return "radar"
        if "gauge" in t or "dial" in t:
            return "gauge"
        if "waterfall" in t or "bridge" in t:
            return "waterfall"
        if "donut" in t or "doughnut" in t or "ring" in t:
            return "donut"
        if "pie" in t:
            return "pie"
        if "bar" in t or "horizontal" in t:
            return "bar_horizontal"
        if "line" in t or "trend" in t or "area" in t:
            return "line"
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


def ensure_conclusion_and_thankyou_slides(plan: PresentationPlan, presentation_title: Optional[str] = None) -> PresentationPlan:
    """Ensures that every presentation plan always ends with a Conclusion slide as the second-to-last slide and a Thank You slide as the final slide."""
    if not plan or not plan.slides:
        return plan

    p_title = presentation_title or plan.title or "Presentation"

    def is_conclusion_slide(s: SlideSpec) -> bool:
        t_lower = (s.title or "").lower()
        if any(kw in t_lower for kw in ["conclusion", "executive summary", "key takeaways", "summary & conclusion", "final thoughts"]):
            return True
        for p in s.plugins:
            if isinstance(p.data, dict) and "title" in p.data:
                pt_lower = str(p.data.get("title", "")).lower()
                if any(kw in pt_lower for kw in ["conclusion", "executive summary", "key takeaways"]):
                    return True
        return False

    def is_thankyou_slide(s: SlideSpec) -> bool:
        t_lower = (s.title or "").lower()
        sub_lower = (s.subtitle or "").lower()
        return any(kw in t_lower or kw in sub_lower for kw in ["thank you", "thanks", "q&a", "questions", "dhanyawad", "merci", "danke", "gracias"])

    slides = list(plan.slides)

    # 1. Ensure Thank You slide is at the very end
    if not is_thankyou_slide(slides[-1]):
        ty_idx = next((i for i, s in enumerate(slides) if is_thankyou_slide(s)), None)
        if ty_idx is not None:
            ty_slide = slides.pop(ty_idx)
            slides.append(ty_slide)
        else:
            slides.append(
                SlideSpec(
                    layout="title_slide",
                    title="Thank You",
                    subtitle="Questions & Discussion | Thank You for Your Attention",
                    plugins=[],
                )
            )

    # 2. Ensure Conclusion slide is at second-to-last position (index len(slides)-2)
    if len(slides) >= 2:
        second_last = slides[-2]
        if not is_conclusion_slide(second_last):
            c_idx = next((i for i, s in enumerate(slides[:-1]) if is_conclusion_slide(s)), None)
            if c_idx is not None:
                c_slide = slides.pop(c_idx)
                slides.insert(len(slides) - 1, c_slide)
            else:
                conc_bullets = [
                    f"Strategic synthesis and key takeaways of {p_title}.",
                    "Core operational milestones, performance metrics, and deliverable targets.",
                    "Next steps for deployment, team integration, and continuous improvement.",
                ]
                conc_slide = SlideSpec(
                    layout="bullets_slide",
                    title="Conclusion",
                    subtitle="Executive Summary & Key Takeaways",
                    plugins=[
                        SlidePluginBullets(
                            type="bullets",
                            data={
                                "title": "Conclusion",
                                "points": conc_bullets,
                                "bullet_style": "check",
                            }
                        )
                    ],
                )
                slides.insert(len(slides) - 1, conc_slide)

    res_plan = PresentationPlan(
        title=plan.title,
        theme=plan.theme,
        slides=slides,
        brand_logo=plan.brand_logo,
        brand_color=plan.brand_color,
        brand_secondary_color=plan.brand_secondary_color,
        brand_font=plan.brand_font,
        brand_footer=plan.brand_footer,
        use_custom_brand=plan.use_custom_brand,
        use_ai_image_generation=plan.use_ai_image_generation,
    )
    res_plan.structured_plan = build_structured_plan(res_plan, plan.title)
    return res_plan

