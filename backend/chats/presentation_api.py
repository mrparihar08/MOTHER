from __future__ import annotations

import collections
import collections.abc

for name in ("Container", "Mapping", "MutableMapping", "Sequence", "MutableSequence", "Iterable", "Callable"):
    if not hasattr(collections, name) and hasattr(collections.abc, name):
        setattr(collections, name, getattr(collections.abc, name))

import logging
import os
import re
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Annotated, Dict, List, Literal, Optional, Union

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.shapes import PP_PLACEHOLDER
from pptx.enum.text import MSO_AUTO_SIZE, PP_ALIGN
from pptx.util import Inches, Pt

from backend.chats.gemini_service import generate_response
from backend.chats.unsplash_service import fetch_unsplash_image

logger = logging.getLogger(__name__)

APP_NAME = "Vitya Presentation API"
OUTPUT_DIR = Path(os.getenv("PPT_OUTPUT_DIR", "./outputs"))
DEFAULT_TEMPLATE_FILE = os.getenv("PPT_TEMPLATE_FILE", "./templates/base_template.pptx")
ASSET_DIR = Path(os.getenv("PPT_ASSET_DIR", "./assets")).resolve()
MAX_SLIDES = int(os.getenv("PPT_MAX_SLIDES", "30"))
MAX_BULLETS_PER_SLIDE = int(os.getenv("PPT_MAX_BULLETS_PER_SLIDE", "8"))
MAX_PARAGRAPH_CHARS = int(os.getenv("PPT_MAX_PARAGRAPH_CHARS", "900"))
ALLOW_ABSOLUTE_IMAGE_PATHS = os.getenv("PPT_ALLOW_ABSOLUTE_IMAGE_PATHS", "false").lower() == "true"

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

router = APIRouter()

_raw_cors = os.getenv("PPT_CORS_ORIGINS", "*")
CORS_ORIGINS = [x.strip() for x in _raw_cors.split(",") if x.strip()] or ["*"]

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
ASSET_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------

class SlidePluginText(BaseModel):
    type: Literal["text"]
    data: Dict[str, Any]


class SlidePluginBullets(BaseModel):
    type: Literal["bullets"]
    data: Dict[str, Any]


class SlidePluginParagraph(BaseModel):
    type: Literal["paragraph"]
    data: Dict[str, Any]


class SlidePluginChart(BaseModel):
    type: Literal["chart"]
    data: Dict[str, Any]


class SlidePluginImage(BaseModel):
    type: Literal["image"]
    data: Dict[str, Any]


class SlidePluginTable(BaseModel):
    type: Literal["table"]
    data: Dict[str, Any]


class SlidePluginNotes(BaseModel):
    type: Literal["notes"]
    data: Dict[str, Any]


SlidePlugin = Annotated[
    Union[
        SlidePluginText,
        SlidePluginBullets,
        SlidePluginParagraph,
        SlidePluginChart,
        SlidePluginImage,
        SlidePluginTable,
        SlidePluginNotes,
    ],
    Field(discriminator="type"),
]


class SlideSpec(BaseModel):
    layout: Optional[
        Literal[
            "title_slide",
            "title_content",
            "mixed_content_slide",
            "chart_slide",
            "image_slide",
            "bullets_slide",
            "section_slide",
            "table_slide",
        ]
    ] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    plugins: List[SlidePlugin] = Field(default_factory=list)


class PresentationPlan(BaseModel):
    title: str
    theme: Optional[Dict[str, str]] = None
    slides: List[SlideSpec]


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    template_name: Optional[str] = None
    slide_count: int = Field(default=8, ge=3, le=MAX_SLIDES)
    audience: Optional[str] = Field(default=None, max_length=120)
    tone: Optional[str] = Field(default=None, max_length=120)
    language: str = Field(default="English", max_length=80)
    include_citations: bool = False
    include_speaker_notes: bool = False
    use_gemini: bool = True

    include_title_slide: bool = True
    allow_bullets: bool = True
    allow_paragraph: bool = True
    allow_chart: bool = True
    allow_image: bool = True
    allow_section_slide: bool = True
    allow_table: bool = True

    background_theme: Optional[str] = None
    content_theme: Optional[str] = None
    visual_style: Optional[str] = None

    smart_mode: bool = True
    slide_types: Optional[List[str]] = None
    plan: Optional[PresentationPlan] = None


class GenerateResponse(BaseModel):
    job_id: str
    status: Literal["completed"]
    file_name: str
    download_url: str



# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


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
    if template_name:
        candidate = Path(template_name).expanduser()
        if candidate.is_file():
            return str(candidate)
    return DEFAULT_TEMPLATE_FILE


def ensure_template_prs(template_file: str) -> Presentation:
    path = Path(template_file)
    if path.exists():
        try:
            return Presentation(str(path))
        except Exception as exc:
            logger.warning("Failed to load template %s: %s", path, exc)
    return Presentation()


def ph(*names: str) -> tuple:
    values = []
    for name in names:
        value = getattr(PP_PLACEHOLDER, name, None)
        if value is not None:
            values.append(value)
    return tuple(values)


TITLE_PLACEHOLDER_TYPES = ph("TITLE", "CENTER_TITLE")
SUBTITLE_PLACEHOLDER_TYPES = ph("SUBTITLE")
BODY_PLACEHOLDER_TYPES = ph("BODY", "OBJECT", "VERTICAL_BODY", "VERTICAL_OBJECT", "TABLE")
IMAGE_PLACEHOLDER_TYPES = ph("PICTURE")
CHART_PLACEHOLDER_TYPES = ph("CHART")


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


def chunk_list(items: List[Any], size: int) -> List[List[Any]]:
    size = max(1, size)
    return [items[i:i + size] for i in range(0, len(items), size)]


def parse_number(value: str) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


def hex_to_rgb(hex_color: str) -> RGBColor:
    hex_color = hex_color.replace("#", "").strip()
    return RGBColor.from_string(hex_color)


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


@dataclass(frozen=True)
class Box:
    left: float
    top: float
    width: float
    height: float


def as_box(plan: Dict[str, Any], default: Box) -> Box:
    raw = plan.get("box") if isinstance(plan.get("box"), dict) else {}
    left = plan.get("left", raw.get("left", default.left))
    top = plan.get("top", raw.get("top", default.top))
    width = plan.get("width", raw.get("width", default.width))
    height = plan.get("height", raw.get("height", default.height))
    return Box(
        left=float(left),
        top=float(top),
        width=float(width),
        height=float(height),
    )


# ---------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------

THEME_COLORS = {
    "light": {"background": "F8FAFC", "gradient_start": "F8FAFC", "gradient_end": "E2E8F0", "accent": "2563EB", "text": "0F172A"},
    "dark": {"background": "0F172A", "gradient_start": "0F172A", "gradient_end": "31104B", "accent": "C084FC", "text": "FFFFFF"},
    "midnight": {"background": "0F172A", "gradient_start": "0F172A", "gradient_end": "31104B", "accent": "C084FC", "text": "FFFFFF"},
    "purple": {"background": "1E1B4B", "gradient_start": "1E1B4B", "gradient_end": "4C0519", "accent": "C084FC", "text": "FFFFFF"},
    "blue": {"background": "06101E", "gradient_start": "06101E", "gradient_end": "134074", "accent": "60A5FA", "text": "FFFFFF"},
    "emerald": {"background": "022C22", "gradient_start": "022C22", "gradient_end": "047857", "accent": "34D399", "text": "FFFFFF"},
    "slate": {"background": "18181B", "gradient_start": "18181B", "gradient_end": "3F3F46", "accent": "A1A1AA", "text": "FFFFFF"},
    "ai": {"background": "0F172A", "gradient_start": "0F172A", "gradient_end": "31104B", "accent": "C084FC", "text": "F8FAFC"},
    "data": {"background": "1E1B4B", "gradient_start": "1E1B4B", "gradient_end": "31104B", "accent": "C084FC", "text": "FFFFFF"},
    "startup": {"background": "1E1B4B", "gradient_start": "1E1B4B", "gradient_end": "7C2D12", "accent": "F97316", "text": "FFFFFF"},
    "education": {"background": "FFFBEB", "gradient_start": "FFFBEB", "gradient_end": "FEF3C7", "accent": "D97706", "text": "451F00"},
    "finance": {"background": "0F172A", "gradient_start": "0F172A", "gradient_end": "14532D", "accent": "34D399", "text": "FFFFFF"},
    "medical": {"background": "FFF1F2", "gradient_start": "FFF1F2", "gradient_end": "FFE4E6", "accent": "E11D48", "text": "4C0519"},
    "default": {"background": "0F172A", "gradient_start": "0F172A", "gradient_end": "31104B", "accent": "C084FC", "text": "FFFFFF"},
}

THEME_KEYWORDS = {
    "ai": ["artificial intelligence", "machine learning", "deep learning", "neural", "llm", "genai", "generative ai", "model"],
    "data": ["data", "analytics", "dashboard", "sql", "etl", "visualization", "insight"],
    "startup": ["startup", "mvp", "founder", "pitch", "product launch", "scale"],
    "education": ["education", "school", "college", "student", "teacher", "course", "study"],
    "finance": ["finance", "money", "budget", "bank", "investment", "trading", "portfolio"],
    "medical": ["medical", "health", "doctor", "clinic", "hospital", "patient", "diagnosis"],
}

VISUAL_STYLES = {
    "minimal": {"show_top_bar": False, "shadow": False},
    "corporate": {"show_top_bar": True, "shadow": False},
    "academic": {"show_top_bar": False, "shadow": False},
    "modern_gradient": {"show_top_bar": True, "shadow": True},
}


def detect_theme(text: str) -> str:
    raw = normalize_whitespace(text or "").lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", raw)
    padded = f" {normalized} "
    scores: Dict[str, int] = {}
    for theme, keywords in THEME_KEYWORDS.items():
        score = 0
        for kw in keywords:
            kw_norm = kw.lower().strip()
            if " " in kw_norm:
                if f" {kw_norm} " in padded:
                    score += 3
            else:
                if re.search(rf"\b{re.escape(kw_norm)}\b", normalized):
                    score += 1
        scores[theme] = score
    best_theme = max(scores, key=scores.get)
    return best_theme if scores[best_theme] > 0 else "default"


def detect_visual_style(text: str) -> str:
    raw = normalize_whitespace(text or "").lower()
    if any(word in raw for word in ("research", "study", "paper", "thesis", "seminar", "academic", "university")):
        return "academic"
    if any(word in raw for word in ("business", "company", "client", "report", "meeting", "corporate", "management")):
        return "corporate"
    if any(word in raw for word in ("modern", "ui", "design", "startup", "product", "demo", "landing", "brand")):
        return "modern_gradient"
    return "minimal"


def get_theme_palette(theme_input: Any) -> Dict[str, Any]:
    if isinstance(theme_input, dict):
        bg = theme_input.get("bg_color") or theme_input.get("background") or "#0F172A"
        g_start = theme_input.get("bg_gradient_start") or theme_input.get("bg_start") or bg
        g_end = theme_input.get("bg_gradient_end") or theme_input.get("bg_end") or bg
        txt = theme_input.get("text_color") or theme_input.get("text") or "#FFFFFF"
        acc = theme_input.get("accent_color") or theme_input.get("accent") or "#C084FC"
        return {
            "background": hex_to_rgb(bg),
            "gradient_start": hex_to_rgb(g_start),
            "gradient_end": hex_to_rgb(g_end),
            "text": hex_to_rgb(txt),
            "accent": hex_to_rgb(acc),
        }

    theme = normalize_whitespace(str(theme_input or "default")).lower()
    raw = THEME_COLORS.get(theme, THEME_COLORS["default"])
    bg_hex = raw["background"]
    g_start_hex = raw.get("gradient_start", bg_hex)
    g_end_hex = raw.get("gradient_end", bg_hex)
    return {
        "background": hex_to_rgb(bg_hex),
        "gradient_start": hex_to_rgb(g_start_hex),
        "gradient_end": hex_to_rgb(g_end_hex),
        "accent": hex_to_rgb(raw["accent"]),
        "text": hex_to_rgb(raw["text"]),
    }


def get_visual_style(style_name: Optional[str]) -> Dict[str, Any]:
    style = normalize_whitespace(style_name or "minimal").lower()
    return VISUAL_STYLES.get(style, VISUAL_STYLES["minimal"])


def apply_background_theme(slide, theme_input: Any, visual_style: Optional[str] = None) -> None:
    palette = get_theme_palette(theme_input)
    fill = slide.background.fill

    try:
        if palette.get("gradient_start") and palette.get("gradient_end") and palette["gradient_start"] != palette["gradient_end"]:
            fill.gradient()
            fill.gradient_angle = 135.0
            stops = fill.gradient_stops
            stops[0].position = 0.0
            stops[0].color.rgb = palette["gradient_start"]
            stops[1].position = 1.0
            stops[1].color.rgb = palette["gradient_end"]
            return
    except Exception:
        pass

    fill.solid()
    fill.fore_color.rgb = palette["background"]


def set_run_style(run, font_size: int, bold: bool = False, color: Optional[RGBColor] = None) -> None:
    run.font.size = Pt(font_size)
    run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color


def configure_text_frame(tf, *, font_size: int, color: Optional[RGBColor] = None, bold: bool = False) -> None:
    try:
        tf.word_wrap = True
    except Exception:
        pass
    try:
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    except Exception:
        pass
    try:
        tf.margin_left = Inches(0.04)
        tf.margin_right = Inches(0.04)
        tf.margin_top = Inches(0.02)
        tf.margin_bottom = Inches(0.02)
    except Exception:
        pass

    for p in tf.paragraphs:
        for run in p.runs:
            set_run_style(run, font_size=font_size, bold=bold, color=color)


def best_font_size_for_bullets(points: List[Any], base: int = 14) -> int:
    count = max(1, len(points))
    longest = max((len(normalize_whitespace(str(p))) for p in points), default=0)
    size = base
    if count >= 6:
        size -= 2
    if count >= 8:
        size -= 2
    if longest >= 90:
        size -= 2
    elif longest >= 70:
        size -= 1
    return max(11, size)


def best_font_size_for_paragraph(text: str, base: int = 14) -> int:
    text = normalize_whitespace(text)
    size = base
    if len(text) > 400:
        size -= 3
    elif len(text) > 250:
        size -= 2
    elif len(text) > 150:
        size -= 1
    return max(11, size)


def find_placeholder_by_types(slide, placeholder_types: tuple) -> Optional[Any]:
    for shape in slide.placeholders:
        try:
            if shape.placeholder_format.type in placeholder_types:
                return shape
        except Exception:
            continue
    return None


def set_shape_text(shape, text: str, font_size: int = 20, bold: bool = False, color: Optional[RGBColor] = None) -> None:
    if not hasattr(shape, "text_frame"):
        return
    tf = shape.text_frame
    tf.clear()
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = text
    set_run_style(run, font_size=font_size, bold=bold, color=color)
    try:
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    except Exception:
        pass


def add_textbox(slide, left, top, width, height, text: str, font_size: int = 20, bold: bool = False, color: Optional[RGBColor] = None) -> None:
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.clear()
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = text
    set_run_style(run, font_size=font_size, bold=bold, color=color)
    try:
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    except Exception:
        pass


def write_text_or_fallback(
    slide,
    placeholder_types: tuple,
    text: str,
    *,
    fallback_left: float,
    fallback_top: float,
    fallback_width: float,
    fallback_height: float,
    font_size: int,
    bold: bool = False,
    color: Optional[RGBColor] = None,
) -> None:
    shape = find_placeholder_by_types(slide, placeholder_types)
    if shape is not None:
        try:
            set_shape_text(shape, text, font_size=font_size, bold=bold, color=color)
            return
        except Exception:
            pass

    add_textbox(
        slide,
        Inches(fallback_left),
        Inches(fallback_top),
        Inches(fallback_width),
        Inches(fallback_height),
        text,
        font_size=font_size,
        bold=bold,
        color=color,
    )


def set_slide_notes(slide, notes: str) -> None:
    notes = normalize_whitespace(notes)
    if not notes:
        return
    try:
        ns = slide.notes_slide
        tf = ns.notes_text_frame
        tf.clear()
        tf.text = notes
    except Exception:
        pass


def sanitize_image_path(path_text: str) -> Optional[str]:
    path_text = normalize_whitespace(path_text)
    if not path_text:
        return None

    candidate = Path(path_text)
    if candidate.is_absolute():
        if ALLOW_ABSOLUTE_IMAGE_PATHS and candidate.exists():
            return str(candidate)
        return None

    resolved = (ASSET_DIR / candidate).resolve()
    try:
        if not str(resolved).startswith(str(ASSET_DIR)):
            return None
    except Exception:
        return None
    return str(resolved) if resolved.exists() else None


def fetch_unsplash_image_for_topic(topic_query: str) -> Optional[str]:
    """Fetch an image from Unsplash service for a given slide topic or title."""
    return fetch_unsplash_image(topic_query)


def render_slide_title(slide, title: str, theme_name: Optional[str] = None) -> None:
    title = normalize_whitespace(title)
    if not title:
        return
    palette = get_theme_palette(theme_name)
    write_text_or_fallback(
        slide,
        TITLE_PLACEHOLDER_TYPES,
        title,
        fallback_left=0.7,
        fallback_top=0.35,
        fallback_width=12.0,
        fallback_height=0.6,
        font_size=24,
        bold=True,
        color=palette["accent"],
    )


# ---------------------------------------------------------------------
# Layout detection
# ---------------------------------------------------------------------

@dataclass
class LayoutSpec:
    layout_index: int


@dataclass
class LayoutInfo:
    index: int
    name: str
    placeholder_count: int
    has_title: bool
    has_body: bool
    has_picture: bool
    has_chart: bool
    has_table: bool


class TemplateDetector:
    def __init__(self, template_file: str):
        self.template_file = template_file
        self.prs = ensure_template_prs(template_file)
        self.layouts = self._inspect_layouts()

    def _inspect_layouts(self) -> List[LayoutInfo]:
        layouts: List[LayoutInfo] = []
        for idx, layout in enumerate(self.prs.slide_layouts):
            name = (layout.name or f"layout_{idx}").strip().lower()
            has_title = False
            has_body = False
            has_picture = False
            has_chart = False
            has_table = False

            for ph_shape in layout.placeholders:
                try:
                    ph_type = ph_shape.placeholder_format.type
                    if ph_type in TITLE_PLACEHOLDER_TYPES:
                        has_title = True
                    elif ph_type in SUBTITLE_PLACEHOLDER_TYPES or ph_type in BODY_PLACEHOLDER_TYPES:
                        has_body = True
                    elif ph_type in IMAGE_PLACEHOLDER_TYPES:
                        has_picture = True
                    elif ph_type in CHART_PLACEHOLDER_TYPES:
                        has_chart = True
                    elif ph_type == getattr(PP_PLACEHOLDER, "TABLE", None):
                        has_table = True
                except Exception:
                    continue

            layouts.append(
                LayoutInfo(
                    index=idx,
                    name=name,
                    placeholder_count=len(layout.placeholders),
                    has_title=has_title,
                    has_body=has_body,
                    has_picture=has_picture,
                    has_chart=has_chart,
                    has_table=has_table,
                )
            )
        return layouts

    def _score(self, layout: LayoutInfo, target: str) -> int:
        name = layout.name
        score = 0

        if target == "title_slide":
            if any(k in name for k in ("title", "cover", "front")):
                score += 100
            if layout.has_title:
                score += 30
            if not layout.has_body:
                score += 10

        elif target in {"title_content", "bullets_slide"}:
            if any(k in name for k in ("content", "body", "text", "bullet", "list")):
                score += 100
            if layout.has_title and layout.has_body:
                score += 40
            if layout.placeholder_count >= 2:
                score += 10

        elif target == "section_slide":
            if any(k in name for k in ("section", "divider", "break")):
                score += 100
            if layout.has_title and not layout.has_body:
                score += 20

        elif target == "chart_slide":
            if any(k in name for k in ("chart", "graph", "data", "analytics")):
                score += 100
            if layout.has_chart:
                score += 40
            if layout.has_title and layout.has_body:
                score += 15

        elif target == "image_slide":
            if any(k in name for k in ("image", "picture", "photo", "visual")):
                score += 100
            if layout.has_picture:
                score += 40
            if layout.has_title and layout.has_body:
                score += 15

        elif target == "table_slide":
            if any(k in name for k in ("table", "data", "content", "body")):
                score += 100
            if layout.has_table or layout.has_body:
                score += 25
            if layout.has_title:
                score += 10

        if layout.placeholder_count == 0:
            score -= 20

        return score

    def pick_best_layout_index(self, target: str) -> int:
        if not self.layouts:
            return 0
        ranked = sorted(
            ((self._score(layout, target), layout.index) for layout in self.layouts),
            key=lambda x: x[0],
            reverse=True,
        )
        best_score, best_index = ranked[0]
        return best_index if best_score > 0 else 0

    def build_registry(self) -> Dict[str, LayoutSpec]:
        return {
            "title_slide": LayoutSpec(self.pick_best_layout_index("title_slide")),
            "title_content": LayoutSpec(self.pick_best_layout_index("title_content")),
            "section_slide": LayoutSpec(self.pick_best_layout_index("section_slide")),
            "bullets_slide": LayoutSpec(self.pick_best_layout_index("bullets_slide")),
            "chart_slide": LayoutSpec(self.pick_best_layout_index("chart_slide")),
            "image_slide": LayoutSpec(self.pick_best_layout_index("image_slide")),
            "table_slide": LayoutSpec(self.pick_best_layout_index("table_slide")),
            "mixed_content_slide": LayoutSpec(self.pick_best_layout_index("title_content")),
        }


@lru_cache(maxsize=16)
def get_layout_registry(template_file: str) -> Dict[str, LayoutSpec]:
    return TemplateDetector(template_file).build_registry()


# ---------------------------------------------------------------------
# Mixed slide geometry
# ---------------------------------------------------------------------

class MixedLayoutResolver:
    FULL = Box(0.85, 1.35, 11.75, 5.15)

    @staticmethod
    def resolve(plugin_types: set[str]) -> Dict[str, Box]:
        kinds = set(plugin_types)

        if kinds == {"paragraph", "image"}:
            return {
                "paragraph": Box(0.85, 1.45, 6.25, 4.95),
                "image": Box(7.25, 1.55, 5.15, 4.55),
            }
        if kinds == {"paragraph", "bullets"}:
            return {
                "paragraph": Box(0.85, 1.45, 11.5, 2.25),
                "bullets": Box(0.95, 3.85, 11.2, 2.35),
            }
        if kinds == {"image", "bullets"}:
            return {
                "image": Box(0.85, 1.55, 6.2, 4.8),
                "bullets": Box(7.2, 1.55, 5.3, 4.8),
            }
        if kinds == {"paragraph", "chart"}:
            return {
                "paragraph": Box(0.85, 1.45, 4.1, 4.9),
                "chart": Box(5.15, 1.45, 7.25, 4.9),
            }
        if kinds == {"bullets", "chart"}:
            return {
                "chart": Box(0.85, 1.45, 7.0, 4.9),
                "bullets": Box(8.05, 1.45, 4.35, 4.9),
            }
        if kinds == {"table", "paragraph"}:
            return {
                "paragraph": Box(0.85, 1.45, 4.2, 1.8),
                "table": Box(0.75, 3.0, 11.8, 3.1),
            }
        return {kind: MixedLayoutResolver.FULL for kind in kinds}


# ---------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------

def build_gemini_slide_script(req: GenerateRequest) -> Optional[str]:
    from dotenv import load_dotenv
    load_dotenv()
    if not req.use_gemini or not os.getenv("GEMINI_API_KEY"):
        return None

    options = []
    if req.audience:
        options.append(f"Audience: {req.audience}.")
    if req.tone:
        options.append(f"Tone: {req.tone}.")
    options.append(f"Write in {req.language}.")
    if req.include_citations:
        options.append("Add a final Sources slide containing short, credible source names/URLs. Do not invent citations.")
    if req.include_speaker_notes:
        options.append("Add one concise `Notes:` line to every non-title slide.")

    instructions = " ".join(options)
    gemini_prompt = f"""You are an expert presentation designer and content strategist.
Create exactly {req.slide_count} visually diverse slides about this request:
{req.prompt}

{instructions}

CRITICAL REQUIREMENT: AUTO BEST SLIDE SELECTION & LAYOUT DIVERSITY.
Do NOT use bullet points for every slide! Use a rich mix of slide formats across the presentation:
- Slide 1: Must be a Title slide (`Title: ...` and `Subtitle: ...`)
- Overview / Executive Summary slides: Use a clear text paragraph (`Paragraph: 2-3 sentence overview`)
- Key Features / Bullet Highlights: Use bullet points (`Bullets:\n- point 1\n- point 2\n- point 3`)
- Visual Showcase / Concept slides: Use an Image placeholder (`Image: topic keyword`, e.g. `Image: Healthcare diagnostic technology` or `Image: Business finance growth`)
- Mixed Content slides: Combine `Paragraph:` with `Bullets:`, or `Bullets:` with `Chart:`, or `Paragraph:` with `Image:` on the same slide.
- Major Topic Transitions: Use a Section Divider (`Section: Topic Name`)

Return ONLY the plain-text slide script. Do not use Markdown code fences, introductory prose, or JSON.
Every slide must start with `Slide N:` and use these exact labels where appropriate:

Slide 1:
Title: ...
Subtitle: ...

Slide 2:
Title: Executive Summary
Paragraph: ...

Slide 3:
Title: Core Features
Bullets:
- Point 1
- Point 2
- Point 3

Slide 4:
Title: Feature Comparison
Table:
Feature | Standard | Premium
Security | Basic | Advanced
Storage | 10GB | 100GB

Slide 5:
Title: Key Visual Highlight
Image: Technology innovation lab
Paragraph: Modern digital transformation requires continuous innovation...

Slide 6:
Title: Growth & Performance
Chart: column
Series Name: Performance
Q1: 25
Q2: 45
Q3: 70
Q4: 95

Notes: concise speaker note for each slide.
Never fabricate statistics, but use realistic thematic figures or data tables when describing trends."""

    response = generate_response(gemini_prompt)
    if not response or response.startswith("Gemini API key is not configured.") or response.startswith("Gemini error:"):
        logger.warning("Gemini presentation planning failed; using local planner")
        return None
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

class PromptPlanner:
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
    ) -> PresentationPlan:
        prompt = (prompt or "").strip()
        prompt_l = prompt.lower()
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
            if include_title_slide:
                slides.append(self._make_title_slide(presentation_title))

            if allow_section_slide and any(k in prompt_l for k in ("overview", "introduction", "intro")):
                slides.append(self._make_section_slide("Overview"))

            if allow_bullets:
                slides.append(self._make_bullets_slide(
                    "Key Points",
                    ["Clear problem statement", "Main ideas and workflow", "Practical use cases"],
                ))

            if allow_paragraph and len(prompt) > 80:
                slides.append(self._make_paragraph_slide("Summary", prompt[:600]))

            if allow_chart and re.search(r"\b(chart|graph|trend|growth|comparison)\b", prompt_l):
                slides.append(self._make_chart_slide(
                    "Trend Chart",
                    {
                        "chart_type": "line",
                        "title": "Trend Chart",
                        "categories": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
                        "values": [12, 18, 24, 31, 39, 48],
                        "series_name": "Usage",
                    },
                ))

            # Keep non-AI fallback diverse with varied slide layouts
            fallback_topics = [
                ("Introduction", "paragraph"),
                ("Why It Matters", "bullets"),
                ("Key Features & Specifications", "table"),
                ("Growth & Impact Metrics", "chart"),
                ("Best Practices & Use Cases", "mixed"),
                ("Challenges & Solutions", "bullets"),
                ("Implementation Steps", "paragraph"),
                ("Conclusion & Next Steps", "bullets"),
            ]
            desired_count = min(max(target_slide_count or len(slides), 1), MAX_SLIDES)
            for idx, (topic, layout_type) in enumerate(fallback_topics):
                if len(slides) >= desired_count:
                    break
                if layout_type == "paragraph" and allow_paragraph:
                    slides.append(self._make_paragraph_slide(topic, f"Key context and strategic overview regarding {topic.lower()}."))
                elif layout_type == "table" and allow_table:
                    slides.append(self._make_table_slide(
                        topic,
                        {
                            "title": topic,
                            "headers": ["Metric / Phase", "Standard", "Target"],
                            "rows": [["Phase 1", "Initial Setup", "Completed"], ["Phase 2", "Optimization", "In Progress"], ["Phase 3", "Scaling", "Planned"]],
                        }
                    ))
                elif layout_type == "chart" and allow_chart:
                    slides.append(self._make_chart_slide(
                        topic,
                        {
                            "chart_type": "column",
                            "title": topic,
                            "categories": ["Phase 1", "Phase 2", "Phase 3", "Phase 4"],
                            "values": [25, 55, 80, 100],
                            "series_name": "Progress %",
                        }
                    ))
                elif layout_type == "mixed" and allow_paragraph and allow_bullets:
                    slides.append(self._make_mixed_slide(
                        topic,
                        [
                            SlidePluginParagraph(type="paragraph", data={"text": f"Overview of {topic.lower()} in modern workflow."}),
                            SlidePluginBullets(type="bullets", data={"points": ["Key advantage 1", "Key advantage 2", "Key advantage 3"]}),
                        ]
                    ))
                elif allow_bullets:
                    slides.append(self._make_bullets_slide(
                        topic,
                        [
                            f"How {topic.lower()} relates to the presentation topic",
                            "Important context and practical considerations",
                            "A concise takeaway for the audience",
                        ],
                    ))
                elif allow_paragraph:
                    slides.append(self._make_paragraph_slide(topic, f"Key context about {topic.lower()}."))

            return PresentationPlan(title=presentation_title, slides=slides[:MAX_SLIDES])

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
                boxes = MixedLayoutResolver.resolve({p.type for p in plugins})
                adjusted: List[SlidePlugin] = []

                for plugin in plugins:
                    data = dict(plugin.data)
                    box = boxes.get(plugin.type)
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
            plugins=[SlidePluginText(type="text", data={"title": title, "subtitle": ""})],
        )

    def _make_title_slide(self, title: str, subtitle: str = "") -> SlideSpec:
        return SlideSpec(
            layout="title_slide",
            title=title,
            subtitle=subtitle or "Generated from prompt",
            plugins=[SlidePluginText(type="text", data={"title": title, "subtitle": subtitle or "Generated from prompt"})],
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
        return first_line if len(first_line) <= 60 else first_line[:60].rstrip() + "..."

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
                result["title"] = normalize_whitespace(m.group(1))
                mode = None
                continue

            m = re.match(r"^\s*subtitle\b\s*[:\-]\s*(.+?)\s*$", line, re.IGNORECASE)
            if m:
                result["subtitle"] = normalize_whitespace(m.group(1))
                mode = None
                continue

            m = re.match(r"^\s*section\b\s*[:\-]\s*(.+?)\s*$", line, re.IGNORECASE)
            if m:
                result["section_title"] = normalize_whitespace(m.group(1))
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
                if re.match(r"^(title|subtitle|bullets?|chart|chart type|categories|values|image|path|series name|table|notes|speaker notes|section)\b", line, re.IGNORECASE):
                    mode = None
                else:
                    result["paragraph_lines"].append(line)
                    continue

            if mode == "bullets":
                bullet_match = re.match(r"^(?:[-*•]|\d+[.)])\s*(.*\S)$", line)
                if bullet_match:
                    point = normalize_whitespace(bullet_match.group(1))
                    if point:
                        result["bullets"].append(point)
                    continue
                if not re.match(r"^(title|subtitle|paragraph|chart|chart type|categories|values|image|path|series name|table|notes|speaker notes|section)\b", line, re.IGNORECASE):
                    result["bullets"].append(normalize_whitespace(line))
                continue

            if mode == "table":
                if "|" in line:
                    row = self.parse_table_row(line)
                    if row:
                        result["table_rows"].append(row)
                    continue
                if re.match(r"^(title|subtitle|paragraph|bullets?|chart|chart type|image|path|notes|speaker notes|section)\b", line, re.IGNORECASE):
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
                if m := re.match(r"^\s*([A-Za-z][A-Za-z0-9 _-]{0,30})\s*[:=]\s*(\d+(?:\.\d+)?)\s*$", line):
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
                if re.match(r"^(title|subtitle|paragraph|bullets?|chart|chart type|categories|values|image|path|series name|table|section)\b", line, re.IGNORECASE):
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
            result["title"] = self.extract_heading_title(block)
        if result["paragraph_lines"]:
            result["paragraph"] = normalize_whitespace(" ".join(result["paragraph_lines"]))
        if result["notes_lines"]:
            result["notes"] = normalize_whitespace(" ".join(result["notes_lines"]))
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

    def build_chart_payload(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        chart_series = parsed.get("chart_series") or OrderedDict()
        chart_type = parsed.get("chart_type") or "line"
        title = parsed.get("title") or "Growth Chart"
        categories = parsed.get("chart_categories") or []
        series_name = parsed.get("series_name") or "Usage"

        if chart_series:
            return {
                "chart_type": chart_type,
                "title": title,
                "categories": categories,
                "series_map": chart_series,
                "series_name": series_name,
            }

        categories = parsed.get("chart_points") or categories or ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
        values = parsed.get("chart_values") or [12, 18, 24, 31, 39, 48]
        return {
            "chart_type": chart_type,
            "title": title,
            "categories": categories,
            "values": values,
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


# ---------------------------------------------------------------------
# Plugins
# ---------------------------------------------------------------------

class BasePlugin:
    def apply(self, slide, plan: Dict[str, Any], theme_name: Optional[str] = None) -> None:
        pass

    def apply_with_y(
        self,
        slide,
        plan: Dict[str, Any],
        current_y: float,
        left_margin: float,
        content_width: float,
        palette: Dict[str, RGBColor],
    ) -> float:
        self.apply(slide, plan, theme_name=None)
        return current_y


class TextPlugin(BasePlugin):
    def apply(self, slide, plan: Dict[str, Any], theme_name: Optional[str] = None) -> None:
        pass

    def apply_with_y(
        self,
        slide,
        plan: Dict[str, Any],
        current_y: float,
        left_margin: float,
        content_width: float,
        palette: Dict[str, RGBColor],
    ) -> float:
        text = normalize_whitespace(plan.get("text", "") or plan.get("subtitle", "") or plan.get("title", ""))
        if not text:
            return current_y
        box = slide.shapes.add_textbox(Inches(left_margin), Inches(current_y), Inches(content_width), Inches(0.5))
        tf = box.text_frame
        tf.clear()
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = text
        p.font.size = Pt(20)
        p.font.bold = True
        p.font.color.rgb = palette["accent"]
        return current_y + 0.65


class ParagraphPlugin(BasePlugin):
    def apply(self, slide, plan: Dict[str, Any], theme_name: Optional[str] = None) -> None:
        pass

    def apply_with_y(
        self,
        slide,
        plan: Dict[str, Any],
        current_y: float,
        left_margin: float,
        content_width: float,
        palette: Dict[str, RGBColor],
    ) -> float:
        text = normalize_whitespace(plan.get("text", ""))
        if not text:
            return current_y

        user_font = plan.get("font_size")
        font_size = int(user_font) if user_font and str(user_font).isdigit() else best_font_size_for_paragraph(text, base=14)

        default_height = 0.6 if len(text) < 120 else (0.8 if len(text) < 250 else 1.1)
        box_spec = as_box(plan, Box(left_margin, current_y, content_width, default_height))

        box = slide.shapes.add_textbox(Inches(box_spec.left), Inches(box_spec.top), Inches(box_spec.width), Inches(box_spec.height))
        tf = box.text_frame
        tf.clear()
        tf.word_wrap = True
        tf.text = text
        configure_text_frame(tf, font_size=font_size, color=palette["text"])

        alignment = str(plan.get("alignment", "left")).lower()
        align_map = {"center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT, "justify": PP_ALIGN.JUSTIFY, "left": PP_ALIGN.LEFT}
        if alignment in align_map:
            for p in tf.paragraphs:
                p.alignment = align_map[alignment]

        return max(current_y, box_spec.top) + box_spec.height + 0.15


class BulletsPlugin(BasePlugin):
    def apply(self, slide, plan: Dict[str, Any], theme_name: Optional[str] = None) -> None:
        pass

    def apply_with_y(
        self,
        slide,
        plan: Dict[str, Any],
        current_y: float,
        left_margin: float,
        content_width: float,
        palette: Dict[str, RGBColor],
    ) -> float:
        points = safe_list(plan.get("points"))
        if not points:
            return current_y

        user_font = plan.get("font_size")
        bullet_font = int(user_font) if user_font and str(user_font).isdigit() else best_font_size_for_bullets(points, base=14)

        default_height = max(0.6, 0.28 * len(points))
        box_spec = as_box(plan, Box(left_margin, current_y, content_width, default_height))

        box = slide.shapes.add_textbox(Inches(box_spec.left), Inches(box_spec.top), Inches(box_spec.width), Inches(box_spec.height))
        tf = box.text_frame
        tf.clear()
        tf.word_wrap = True
        for idx, point in enumerate(points):
            p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
            p.text = f"•  {point}"
            p.level = 0
            p.space_after = Pt(2)

        configure_text_frame(tf, font_size=bullet_font, color=palette["text"])

        alignment = str(plan.get("alignment", "left")).lower()
        align_map = {"center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT, "justify": PP_ALIGN.JUSTIFY, "left": PP_ALIGN.LEFT}
        if alignment in align_map:
            for p in tf.paragraphs:
                p.alignment = align_map[alignment]

        return max(current_y, box_spec.top) + box_spec.height + 0.20


class ChartPlugin(BasePlugin):
    def apply(self, slide, plan: Dict[str, Any], theme_name: Optional[str] = None) -> None:
        palette = get_theme_palette(theme_name)
        chart_type = str(plan.get("chart_type", "column")).lower()
        categories = list(plan.get("categories", []))
        values = list(plan.get("values", []))
        series_map = plan.get("series_map") or {}
        series_name = normalize_whitespace(plan.get("series_name", "Usage"))
        top_pos = float(plan.get("top", 1.8))
        box = as_box(plan, Box(0.9, top_pos, 8.5, 3.8))

        chart_data = CategoryChartData()
        if series_map:
            if not categories:
                seen: List[str] = []
                for mapping in series_map.values():
                    if isinstance(mapping, dict):
                        for cat in mapping.keys():
                            if cat not in seen:
                                seen.append(cat)
                categories = seen
            if not categories:
                categories = ["Phase 1", "Phase 2", "Phase 3", "Phase 4"]
            chart_data.categories = categories
            for s_name, mapping in series_map.items():
                if isinstance(mapping, dict):
                    series_values = []
                    for cat in categories:
                        val = mapping.get(cat, 0)
                        try:
                            series_values.append(float(val))
                        except Exception:
                            series_values.append(0.0)
                    chart_data.add_series(str(s_name), series_values)
                elif isinstance(mapping, (list, tuple)):
                    series_values = [float(v) for v in mapping[:len(categories)]]
                    if len(series_values) < len(categories):
                        series_values += [0.0] * (len(categories) - len(series_values))
                    chart_data.add_series(str(s_name), series_values)
        else:
            if not categories and not values:
                categories = ["Q1", "Q2", "Q3", "Q4"]
                values = [25.0, 50.0, 75.0, 100.0]
            elif not categories:
                categories = [f"Item {i+1}" for i in range(len(values))]
            elif not values:
                values = [10.0 * (i+1) for i in range(len(categories))]

            n = min(len(categories), len(values))
            if n == 0:
                categories = ["Q1", "Q2", "Q3", "Q4"]
                values = [25.0, 50.0, 75.0, 100.0]
            else:
                categories = categories[:n]
                values = values[:n]

            chart_data.categories = categories
            chart_data.add_series(series_name, values)

        chart_kind = XL_CHART_TYPE.COLUMN_CLUSTERED
        if chart_type == "line":
            chart_kind = XL_CHART_TYPE.LINE_MARKERS
        elif chart_type == "bar":
            chart_kind = XL_CHART_TYPE.BAR_CLUSTERED
        elif chart_type == "pie":
            chart_kind = XL_CHART_TYPE.PIE

        try:
            slide.shapes.add_chart(chart_kind, Inches(box.left), Inches(box.top), Inches(box.width), Inches(box.height), chart_data)
        except Exception as exc:
            logger.warning("Failed to render PPT chart: %s", exc)
            fallback_box = slide.shapes.add_textbox(Inches(box.left), Inches(box.top), Inches(box.width), Inches(1.5))
            tf = fallback_box.text_frame
            tf.text = f"[{series_name} Chart]\nData: " + ", ".join(f"{c}: {v}" for c, v in zip(categories, values if not series_map else []))
            try:
                tf.paragraphs[0].runs[0].font.color.rgb = palette["text"]
            except Exception:
                pass

    def apply_with_y(
        self,
        slide,
        plan: Dict[str, Any],
        current_y: float,
        left_margin: float,
        content_width: float,
        palette: Dict[str, RGBColor],
    ) -> float:
        self.apply(slide, {**plan, "top": current_y, "box": {"left": left_margin, "top": current_y, "width": 8.5, "height": 3.8}}, theme_name=None)
        return current_y + 4.0


class ImagePlugin(BasePlugin):
    def apply(self, slide, plan: Dict[str, Any], theme_name: Optional[str] = None) -> None:
        palette = get_theme_palette(theme_name)
        path = normalize_whitespace(plan.get("path", ""))
        caption = normalize_whitespace(plan.get("caption", ""))
        top_pos = float(plan.get("top", 1.8))
        box = as_box(plan, Box(1.0, top_pos, 6.6, 3.8))

        safe_path = sanitize_image_path(path)
        if not safe_path:
            query = path or caption or "presentation visual"
            fetched = fetch_unsplash_image_for_topic(query)
            if fetched:
                safe_path = sanitize_image_path(fetched)

        if safe_path:
            try:
                slide.shapes.add_picture(
                    safe_path,
                    Inches(box.left),
                    Inches(box.top),
                    width=Inches(box.width),
                    height=Inches(box.height),
                )
            except Exception as exc:
                logger.warning("Failed to insert picture %s: %s", safe_path, exc)
                safe_path = None

        if not safe_path:
            box_shape = slide.shapes.add_textbox(Inches(box.left), Inches(box.top), Inches(box.width), Inches(box.height))
            tf = box_shape.text_frame
            tf.text = f"Visual: {caption or path or 'Topic'}"
            tf.paragraphs[0].font.size = Pt(18)
            try:
                tf.paragraphs[0].runs[0].font.color.rgb = palette["text"]
            except Exception:
                pass

        if caption:
            cap = slide.shapes.add_textbox(Inches(box.left), Inches(box.top + box.height + 0.08), Inches(box.width), Inches(0.35))
            cap_tf = cap.text_frame
            cap_tf.text = caption
            cap_tf.paragraphs[0].font.size = Pt(12)
            try:
                cap_tf.paragraphs[0].runs[0].font.color.rgb = palette["text"]
            except Exception:
                pass

    def apply_with_y(
        self,
        slide,
        plan: Dict[str, Any],
        current_y: float,
        left_margin: float,
        content_width: float,
        palette: Dict[str, RGBColor],
    ) -> float:
        self.apply(slide, {**plan, "top": current_y, "box": {"left": left_margin, "top": current_y, "width": 6.6, "height": 3.8}}, theme_name=None)
        return current_y + 4.0


class TablePlugin(BasePlugin):
    def apply(self, slide, plan: Dict[str, Any], theme_name: Optional[str] = None) -> None:
        palette = get_theme_palette(theme_name)
        headers = safe_list(plan.get("headers"))
        rows = safe_list(plan.get("rows"))
        top_pos = float(plan.get("top", 1.8))
        box = as_box(plan, Box(0.75, top_pos, 11.5, 3.5))

        if not headers or not rows:
            box_shape = slide.shapes.add_textbox(Inches(1.0), Inches(top_pos), Inches(8.0), Inches(1.0))
            tf = box_shape.text_frame
            tf.text = "Table data not found or incomplete."
            tf.paragraphs[0].font.size = Pt(18)
            return

        cols = len(headers)
        row_count = len(rows) + 1
        table_shape = slide.shapes.add_table(row_count, cols, Inches(box.left), Inches(box.top), Inches(box.width), Inches(box.height))
        table = table_shape.table

        for c, header in enumerate(headers):
            cell = table.cell(0, c)
            cell.text = str(header)
            try:
                cell.fill.solid()
                cell.fill.fore_color.rgb = palette["accent"]
            except Exception:
                pass
            for p in cell.text_frame.paragraphs:
                for run in p.runs:
                    set_run_style(run, font_size=12, bold=True, color=palette["background"])

        for r, row in enumerate(rows, start=1):
            values = list(row) + [""] * max(0, cols - len(row))
            values = values[:cols]
            for c, value in enumerate(values):
                cell = table.cell(r, c)
                cell.text = str(value)
                for p in cell.text_frame.paragraphs:
                    for run in p.runs:
                        set_run_style(run, font_size=10, color=palette["text"])

    def apply_with_y(
        self,
        slide,
        plan: Dict[str, Any],
        current_y: float,
        left_margin: float,
        content_width: float,
        palette: Dict[str, RGBColor],
    ) -> float:
        self.apply(slide, {**plan, "top": current_y, "box": {"left": left_margin, "top": current_y, "width": content_width, "height": 3.2}}, theme_name=None)
        return current_y + 3.5


class NotesPlugin(BasePlugin):
    def apply(self, slide, plan: Dict[str, Any], theme_name: Optional[str] = None) -> None:
        set_slide_notes(slide, plan.get("notes", ""))

    def apply_with_y(
        self,
        slide,
        plan: Dict[str, Any],
        current_y: float,
        left_margin: float,
        content_width: float,
        palette: Dict[str, RGBColor],
    ) -> float:
        set_slide_notes(slide, plan.get("notes", ""))
        return current_y


PLUGIN_REGISTRY: Dict[str, BasePlugin] = {
    "text": TextPlugin(),
    "paragraph": ParagraphPlugin(),
    "bullets": BulletsPlugin(),
    "chart": ChartPlugin(),
    "image": ImagePlugin(),
    "table": TablePlugin(),
    "notes": NotesPlugin(),
}


# ---------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------

class PptRenderer:
    def __init__(self, template_file: str = DEFAULT_TEMPLATE_FILE):
        self.template_file = template_file

    def auto_select_layout(self, slide_spec: SlideSpec, slide_index: int) -> str:
        plugin_types = {p.type for p in slide_spec.plugins}
        content_types = plugin_types - {"notes"}

        if slide_spec.layout:
            return slide_spec.layout

        if slide_index == 0 and content_types == {"text"}:
            return "title_slide"

        mixed_kinds = {"paragraph", "bullets", "image", "chart", "table"}
        if len(content_types & mixed_kinds) >= 2:
            return "mixed_content_slide"

        if "chart" in content_types:
            return "chart_slide"
        if "image" in content_types:
            return "image_slide"
        if "table" in content_types:
            return "table_slide"
        if content_types == {"bullets"}:
            return "bullets_slide"
        if "paragraph" in content_types:
            return "title_content"
        if "text" in content_types:
            return "title_content"
        return "title_content"

    def render(self, plan: PresentationPlan, content_theme: Optional[str] = None, visual_style: Optional[str] = None) -> Presentation:
        prs = ensure_template_prs(self.template_file)
        layout_registry = get_layout_registry(self.template_file)
        active_theme = plan.theme or content_theme

        for idx, slide_spec in enumerate(plan.slides):
            layout_key = self.auto_select_layout(slide_spec, idx)
            layout_spec = layout_registry.get(layout_key, LayoutSpec(layout_index=0))
            layout_index = layout_spec.layout_index
            if layout_index >= len(prs.slide_layouts):
                layout_index = 0

            slide_layout = prs.slide_layouts[layout_index]
            slide = prs.slides.add_slide(slide_layout)

            # Remove built-in template placeholders so "Click to add title" doesn't overlap!
            for sp in list(slide.placeholders):
                try:
                    sp._element.getparent().remove(sp._element)
                except Exception:
                    pass

            apply_background_theme(slide, active_theme, visual_style=visual_style)

            palette = get_theme_palette(active_theme)
            current_y = 0.35
            left_margin = 0.8
            content_width = 11.2

            # 1. Slide Badge ("SLIDE X OF Y") matching Frontend UI
            badge_box = slide.shapes.add_textbox(Inches(left_margin), Inches(current_y), Inches(content_width), Inches(0.25))
            p_b = badge_box.text_frame.paragraphs[0]
            p_b.text = f"SLIDE {idx + 1} OF {len(plan.slides)}"
            p_b.font.size = Pt(9)
            p_b.font.bold = True
            p_b.font.color.rgb = palette["accent"]
            current_y += 0.30

            # 2. Main Title Rendering
            title_text = slide_spec.title or (plan.title if idx == 0 else "")
            if title_text:
                title_font_size = Pt(26) if idx == 0 or slide_spec.layout in {"title_slide", "section_slide"} else Pt(20)
                t_box = slide.shapes.add_textbox(Inches(left_margin), Inches(current_y), Inches(content_width), Inches(0.55))
                tf_t = t_box.text_frame
                tf_t.word_wrap = True
                p_t = tf_t.paragraphs[0]
                p_t.text = title_text
                p_t.font.size = title_font_size
                p_t.font.bold = True
                p_t.font.color.rgb = palette["text"]
                current_y += 0.60

            # 3. Subtitle Rendering
            if slide_spec.subtitle:
                sub_box = slide.shapes.add_textbox(Inches(left_margin), Inches(current_y), Inches(content_width), Inches(0.40))
                tf_s = sub_box.text_frame
                tf_s.word_wrap = True
                p_s = tf_s.paragraphs[0]
                p_s.text = slide_spec.subtitle
                p_s.font.size = Pt(14)
                p_s.font.color.rgb = RGBColor(148, 163, 184)
                current_y += 0.45

            current_y += 0.05 # Padding gap

            # 4. Plugins sequentially rendered down current_y
            for plugin in slide_spec.plugins:
                handler = PLUGIN_REGISTRY.get(plugin.type)
                if handler is None:
                    continue
                next_y = handler.apply_with_y(slide, plugin.data, current_y=current_y, left_margin=left_margin, content_width=content_width, palette=palette)
                if next_y is not None and next_y > current_y:
                    current_y = next_y

        return prs


# ---------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------

def save_presentation(prs: Presentation, title: str) -> str:
    file_id = uuid.uuid4().hex
    filename = f"{safe_filename(title)}_{file_id}.pptx"
    file_path = OUTPUT_DIR / filename
    prs.save(str(file_path))
    return str(file_path)


# ---------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------

def ensure_plan_images(plan: PresentationPlan) -> PresentationPlan:
    """Auto-populate image URLs and paths for any image plugins in the plan.

    Ensures both Frontend UI preview and PPT rendering receive valid image URLs.
    """
    for slide in plan.slides:
        for plugin in slide.plugins:
            if plugin.type == "image":
                data = dict(plugin.data)
                url = data.get("url") or data.get("path") or ""
                caption = data.get("caption") or data.get("title") or slide.title or "Visual"

                if not url or (not url.startswith("http") and not Path(url).exists()):
                    fetched = fetch_unsplash_image(caption)
                    if fetched:
                        url = fetched

                data["url"] = url
                data["path"] = url
                plugin.data = data
    return plan


class PresentationService:
    def __init__(self) -> None:
        self.planner = PromptPlanner()

    def generate(self, req: GenerateRequest) -> tuple[str, PresentationPlan, str]:
        template_file = resolve_template_path(req.template_name)
        # Renderer carries the chosen template. Keep it request-local so two
        # simultaneous users cannot accidentally render with each other's
        # template.
        renderer = PptRenderer(template_file=template_file)

        if req.plan is not None:
            if isinstance(req.plan, dict):
                plan = PresentationPlan(**req.plan)
            else:
                plan = req.plan
        else:
            # Gemini produces researched, slide-by-slide content. The local prompt
            # planner is still used to validate/normalize that content into plugins.
            planning_prompt = build_gemini_slide_script(req) or req.prompt

            plan = self.planner.plan(
                planning_prompt,
                include_title_slide=req.include_title_slide,
                allow_bullets=req.allow_bullets,
                allow_paragraph=req.allow_paragraph,
                allow_chart=req.allow_chart,
                allow_image=req.allow_image,
                allow_section_slide=req.allow_section_slide,
                allow_table=req.allow_table,
                smart_mode=req.smart_mode,
                slide_types=normalize_slide_types(req.slide_types),
                target_slide_count=req.slide_count,
            )

        plan = ensure_plan_images(plan)

        content_theme = normalize_whitespace(req.content_theme or req.background_theme or "")
        if not content_theme or content_theme.lower() in {"auto", "detect"}:
            content_theme = detect_theme(req.prompt)

        visual_style = normalize_whitespace(req.visual_style or "")
        if not visual_style or visual_style.lower() in {"auto", "detect"}:
            visual_style = detect_visual_style(req.prompt)

        prs = renderer.render(plan, content_theme=content_theme, visual_style=visual_style)
        file_path = save_presentation(prs, plan.title)
        return file_path, plan, plan.title


service = PresentationService()


# ---------------------------------------------------------------------
# API
# ---------------------------------------------------------------------

@router.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@router.post("/plan", response_model=PresentationPlan)
async def preview_plan(req: GenerateRequest) -> PresentationPlan:
    try:
        planning_prompt = await run_in_threadpool(build_gemini_slide_script, req)
        plan = await run_in_threadpool(
            service.planner.plan,
            planning_prompt or req.prompt,
            include_title_slide=req.include_title_slide,
            allow_bullets=req.allow_bullets,
            allow_paragraph=req.allow_paragraph,
            allow_chart=req.allow_chart,
            allow_image=req.allow_image,
            allow_section_slide=req.allow_section_slide,
            allow_table=req.allow_table,
            smart_mode=req.smart_mode,
            slide_types=normalize_slide_types(req.slide_types),
            target_slide_count=req.slide_count,
        )
        return ensure_plan_images(plan)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/generate", response_model=GenerateResponse)
async def generate_presentation(req: GenerateRequest, request: Request) -> GenerateResponse:
    try:
        file_path, _plan, _title = await run_in_threadpool(service.generate, req)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    job_id = uuid.uuid4().hex
    filename = Path(file_path).name
    download_url = str(request.url_for("download_ppt", file_name=filename))

    return GenerateResponse(job_id=job_id, status="completed", file_name=filename, download_url=download_url)


@router.get("/download/{file_name}", name="download_ppt")
def download_ppt(file_name: str) -> FileResponse:
    # Restrict downloads to files we generated; this also prevents path
    # traversal attempts through encoded path separators.
    if Path(file_name).name != file_name or not file_name.lower().endswith(".pptx"):
        raise HTTPException(status_code=404, detail="File not found")
    file_path = OUTPUT_DIR / file_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path=str(file_path),
        filename=file_name,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


@router.get("/")
def root():
    return {
        "name": APP_NAME,
        "status": "ok",
        "endpoints": ["/plan", "/generate", "/download/{file_name}"],
        "max_slides": MAX_SLIDES,
    }
