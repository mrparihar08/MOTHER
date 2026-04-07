from __future__ import annotations

import logging
import os
import re
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Union, Annotated

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------

logger = logging.getLogger(__name__)
APP_NAME = "Vitya Presentation API"
OUTPUT_DIR = Path(os.getenv("PPT_OUTPUT_DIR", "./outputs")).resolve()
DEFAULT_TEMPLATE_FILE = os.getenv("PPT_TEMPLATE_FILE", "./templates/base_template.pptx")
ASSET_DIR = Path(os.getenv("PPT_ASSET_DIR", "./assets")).resolve()
MAX_SLIDES = int(os.getenv("PPT_MAX_SLIDES", "30"))
MAX_BULLETS_PER_SLIDE = int(os.getenv("PPT_MAX_BULLETS_PER_SLIDE", "10"))
MAX_PARAGRAPH_CHARS = int(os.getenv("PPT_MAX_PARAGRAPH_CHARS", "900"))
ALLOW_ABSOLUTE_IMAGE_PATHS = os.getenv("PPT_ALLOW_ABSOLUTE_IMAGE_PATHS", "false").lower() == "true"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
ASSET_DIR.mkdir(parents=True, exist_ok=True)

_raw_cors = os.getenv("PPT_CORS_ORIGINS", "*")
CORS_ORIGINS = [x.strip() for x in _raw_cors.split(",") if x.strip()] or ["*"]

router = APIRouter()

THEME_COLORS = {
    "light": {"background": "F8FAFC", "accent": "2563EB", "text": "0F172A", "panel": "FFFFFF"},
    "dark": {"background": "0F172A", "accent": "38BDF8", "text": "F8FAFC", "panel": "1E293B"},
    "blue": {"background": "DBEAFE", "accent": "1D4ED8", "text": "0F172A", "panel": "FFFFFF"},
    "green": {"background": "DCFCE7", "accent": "166534", "text": "052E16", "panel": "FFFFFF"},
    "purple": {"background": "F3E8FF", "accent": "7E22CE", "text": "2E1065", "panel": "FFFFFF"},
}

ALLOWED_SLIDE_TYPES = {
    "title_slide",
    "content_slide",
    "chart_slide",
    "image_slide",
    "section_slide",
    "table_slide",
}

# -----------------------------------------------------------------------------
# Schemas
# -----------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    template_name: Optional[str] = None

    include_title_slide: bool = True
    allow_bullets: bool = True
    allow_paragraph: bool = True
    allow_chart: bool = True
    allow_image: bool = True
    allow_section_slide: bool = True
    allow_table: bool = True

    background_theme: Optional[str] = Field(default="light")
    smart_mode: bool = True
    slide_types: Optional[List[str]] = None


class GenerateResponse(BaseModel):
    job_id: str
    status: Literal["completed"]
    file_name: str
    download_url: str


class SlidePluginText(BaseModel):
    type: Literal["text"]
    data: Dict[str, Any]


class SlidePluginContent(BaseModel):
    type: Literal["content"]
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
        SlidePluginContent,
        SlidePluginChart,
        SlidePluginImage,
        SlidePluginTable,
        SlidePluginNotes,
    ],
    Field(discriminator="type"),
]


class SlideSpec(BaseModel):
    layout: Optional[Literal["title_slide", "content_slide", "chart_slide", "image_slide", "section_slide", "table_slide"]] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    plugins: List[SlidePlugin] = Field(default_factory=list)


class PresentationPlan(BaseModel):
    title: str
    slides: List[SlideSpec]


# -----------------------------------------------------------------------------
# General helpers
# -----------------------------------------------------------------------------

def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", normalize_whitespace(name))[:80].strip("_")
    return cleaned or "presentation"


def hex_to_rgb(hex_color: str) -> RGBColor:
    return RGBColor.from_string(hex_color.replace("#", "").strip())


def get_theme_palette(theme_name: Optional[str]) -> Dict[str, RGBColor]:
    theme = normalize_whitespace(theme_name or "light").lower()
    raw = THEME_COLORS.get(theme, THEME_COLORS["light"])
    return {k: hex_to_rgb(v) for k, v in raw.items()}


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


def normalize_slide_types(slide_types: Optional[List[str]]) -> Optional[List[str]]:
    if not slide_types:
        return None
    cleaned = [normalize_whitespace(x).lower() for x in slide_types]
    cleaned = [x for x in cleaned if x in ALLOWED_SLIDE_TYPES]
    return cleaned or None


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
    return [items[i : i + max(1, size)] for i in range(0, len(items), max(1, size))]


def parse_number(value: str) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


# -----------------------------------------------------------------------------
# Low-level slide drawing helpers
# -----------------------------------------------------------------------------

def add_accent_bar(slide, palette: Dict[str, RGBColor]) -> None:
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(0.28))
    bar.fill.solid()
    bar.fill.fore_color.rgb = palette["accent"]
    bar.line.fill.background()


def set_slide_background(slide, theme_name: Optional[str]) -> Dict[str, RGBColor]:
    palette = get_theme_palette(theme_name)
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = palette["background"]
    add_accent_bar(slide, palette)
    return palette


def add_textbox(
    slide,
    left: float,
    top: float,
    width: float,
    height: float,
    text: str,
    *,
    font_size: int = 20,
    bold: bool = False,
    color: Optional[RGBColor] = None,
    align: Optional[str] = None,
    italic: bool = False,
) -> Any:
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = box.text_frame
    tf.clear()
    tf.word_wrap = True
    p = tf.paragraphs[0]
    if align == "center":
        p.alignment = 1
    elif align == "right":
        p.alignment = 2
    run = p.add_run()
    run.text = text
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.italic = italic
    if color is not None:
        run.font.color.rgb = color
    return box


def set_paragraph_style(paragraph, *, font_size: int, bold: bool = False, color: Optional[RGBColor] = None) -> None:
    for run in paragraph.runs:
        run.font.size = Pt(font_size)
        run.font.bold = bold
        if color is not None:
            run.font.color.rgb = color


def add_round_panel(slide, left: float, top: float, width: float, height: float, fill: RGBColor, line: Optional[RGBColor] = None) -> Any:
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height))
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
    return shape


def set_slide_notes(slide, notes: str) -> None:
    notes = normalize_whitespace(notes)
    if not notes:
        return
    try:
        ns = slide.notes_slide
        ns.notes_text_frame.text = notes
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Parsing structured prompt blocks
# -----------------------------------------------------------------------------

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
    ) -> PresentationPlan:
        prompt = (prompt or "").strip()
        blocks = self.extract_structured_slides(prompt)
        if not blocks:
            blocks = [prompt]

        presentation_title = self.extract_overall_title(prompt, blocks)
        allowed_set = set(slide_types) if slide_types else None

        def allowed(layout_name: str) -> bool:
            if allowed_set is not None and layout_name not in allowed_set:
                return False
            if layout_name == "title_slide":
                return include_title_slide
            if layout_name == "content_slide":
                return allow_bullets or allow_paragraph
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

        for idx, block in enumerate(blocks):
            parsed = self.parse_slide_block(block)
            title = parsed.get("title") or (presentation_title if idx == 0 else f"Slide {idx + 1}")
            subtitle = parsed.get("subtitle") or ""
            notes = parsed.get("notes") or ""

            # First block becomes a proper title slide.
            if idx == 0 and include_title_slide and allowed("title_slide"):
                slides.append(
                    SlideSpec(
                        layout="title_slide",
                        title=title,
                        subtitle=subtitle,
                        plugins=[
                            SlidePluginText(
                                type="text",
                                data={"title": title, "subtitle": subtitle},
                            )
                        ],
                    )
                )

                # Preserve any extra content from the first block if the user added it.
                has_extra_content = any([
                    parsed.get("paragraph"),
                    parsed.get("bullets"),
                    parsed.get("table_rows"),
                    parsed.get("image_path"),
                    parsed.get("chart_series"),
                    parsed.get("chart_points"),
                ])
                if not has_extra_content:
                    continue

            # Section block
            if parsed.get("section_title") and allow_section_slide and allowed("section_slide"):
                section_title = parsed.get("section_title") or title
                slides.append(
                    SlideSpec(
                        layout="section_slide",
                        title=section_title,
                        subtitle=subtitle,
                        plugins=[
                            SlidePluginText(
                                type="text",
                                data={"title": section_title, "subtitle": subtitle},
                            )
                        ],
                    )
                )
                continue

            # Dedicated slide types
            if parsed.get("table_rows") and allow_table and allowed("table_slide"):
                table_payload = self.build_table_payload(parsed, title=title)
                slides.append(
                    SlideSpec(
                        layout="table_slide",
                        title=title,
                        subtitle=subtitle,
                        plugins=[
                            SlidePluginTable(type="table", data=table_payload),
                            *( [SlidePluginNotes(type="notes", data={"notes": notes})] if notes else [] ),
                        ],
                    )
                )
                continue

            if (parsed.get("chart_series") or parsed.get("chart_points")) and allow_chart and allowed("chart_slide"):
                chart_payload = self.build_chart_payload(parsed, title=title)
                slides.append(
                    SlideSpec(
                        layout="chart_slide",
                        title=title,
                        subtitle=subtitle,
                        plugins=[
                            SlidePluginChart(type="chart", data=chart_payload),
                            *( [SlidePluginNotes(type="notes", data={"notes": notes})] if notes else [] ),
                        ],
                    )
                )
                continue

            if parsed.get("image_path") and allow_image and allowed("image_slide"):
                slides.append(
                    SlideSpec(
                        layout="image_slide",
                        title=title,
                        subtitle=subtitle,
                        plugins=[
                            SlidePluginImage(
                                type="image",
                                data={
                                    "path": parsed["image_path"],
                                    "caption": title,
                                    "title": title,
                                    "subtitle": subtitle,
                                },
                            ),
                            *( [SlidePluginNotes(type="notes", data={"notes": notes})] if notes else [] ),
                        ],
                    )
                )
                continue

            # Normal content slide: keep paragraph + bullets together on the same slide.
            paragraph = parsed.get("paragraph", "")
            bullets = parsed.get("bullets") or []

            if paragraph and smart_mode and len(paragraph) > MAX_PARAGRAPH_CHARS:
                paragraph = split_text_into_chunks(paragraph, MAX_PARAGRAPH_CHARS)[0]

            if bullets and smart_mode and len(bullets) > MAX_BULLETS_PER_SLIDE:
                bullets = chunk_list(bullets, MAX_BULLETS_PER_SLIDE)[0]

            if (paragraph or bullets) and allowed("content_slide"):
                slides.append(
                    SlideSpec(
                        layout="content_slide",
                        title=title,
                        subtitle=subtitle,
                        plugins=[
                            SlidePluginContent(
                                type="content",
                                data={
                                    "title": title,
                                    "subtitle": subtitle,
                                    "paragraph": paragraph,
                                    "bullets": bullets,
                                    "notes": notes,
                                },
                            ),
                            *( [SlidePluginNotes(type="notes", data={"notes": notes})] if notes else [] ),
                        ],
                    )
                )
                continue

            # Fallback slide to avoid dropping content.
            slides.append(
                SlideSpec(
                    layout="content_slide",
                    title=title,
                    subtitle=subtitle,
                    plugins=[
                        SlidePluginContent(
                            type="content",
                            data={
                                "title": title,
                                "subtitle": subtitle,
                                "paragraph": paragraph or "Overview",
                                "bullets": bullets,
                                "notes": notes,
                            },
                        )
                    ],
                )
            )

        return PresentationPlan(title=presentation_title, slides=slides[:MAX_SLIDES])

    def extract_structured_slides(self, prompt: str) -> List[str]:
        pattern = re.compile(
            r"(?:^|\n)\s*slide\s*\d+\s*[:\-]?\s*(.*?)(?=(?:\n\s*slide\s*\d+\s*[:\-]?)|$)",
            re.IGNORECASE | re.DOTALL,
        )
        blocks = [block.strip() for block in pattern.findall(prompt) if block.strip()]
        return blocks

    def extract_overall_title(self, prompt: str, blocks: List[str]) -> str:
        if blocks:
            title = self.extract_section_value(blocks[0], "title")
            if title:
                return title

        m = re.search(r'presentation on\s*["“](.*?)["”]', prompt, re.IGNORECASE | re.DOTALL)
        if m:
            return normalize_whitespace(m.group(1))

        first_line = normalize_whitespace(prompt.split("\n", 1)[0])
        if len(first_line) <= 60:
            return first_line
        return first_line[:60].rstrip() + "..."

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
            if re.match(r"^(title|subtitle|paragraph|bullets?|chart|chart type|categories|values|image|path|series name|table|notes|speaker notes|section)\b", line, re.IGNORECASE):
                continue
            if len(line) <= 60:
                return line
        return None

    def parse_slide_block(self, block: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "title": None,
            "subtitle": None,
            "section_title": None,
            "paragraph": "",
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
            "notes": "",
            "is_chart": False,
        }

        mode: Optional[str] = None
        paragraph_lines: List[str] = []
        note_lines: List[str] = []
        current_series = "Usage"

        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            if m := re.match(r"^\s*title\b\s*[:\-]\s*(.+?)\s*$", line, re.IGNORECASE):
                result["title"] = normalize_whitespace(m.group(1))
                mode = None
                continue

            if m := re.match(r"^\s*subtitle\b\s*[:\-]\s*(.+?)\s*$", line, re.IGNORECASE):
                result["subtitle"] = normalize_whitespace(m.group(1))
                mode = None
                continue

            if m := re.match(r"^\s*section\b\s*[:\-]\s*(.+?)\s*$", line, re.IGNORECASE):
                result["section_title"] = normalize_whitespace(m.group(1))
                mode = None
                continue

            if m := re.match(r"^\s*paragraph\b\s*[:\-]?\s*(.*)$", line, re.IGNORECASE):
                mode = "paragraph"
                tail = normalize_whitespace(m.group(1))
                if tail:
                    paragraph_lines.append(tail)
                continue

            if m := re.match(r"^\s*bullets?\b\s*[:\-]?\s*(.*)$", line, re.IGNORECASE):
                mode = "bullets"
                tail = normalize_whitespace(m.group(1))
                if tail:
                    result["bullets"].append(tail)
                continue

            if m := re.match(r"^\s*table\b\s*[:\-]?\s*(.*)$", line, re.IGNORECASE):
                mode = "table"
                tail = normalize_whitespace(m.group(1))
                if tail and "|" in tail:
                    row = self.parse_table_row(tail)
                    if row:
                        result["table_rows"].append(row)
                continue

            if m := re.match(r"^\s*chart\s*type\b\s*[:\-]\s*(.+?)\s*$", line, re.IGNORECASE):
                result["chart_type"] = self.normalize_chart_type(m.group(1))
                result["is_chart"] = True
                mode = "chart"
                continue

            if m := re.match(r"^\s*chart\b\s*[:\-]?\s*(.+?)\s*$", line, re.IGNORECASE):
                value = normalize_whitespace(m.group(1))
                if value and value.lower() in {"line", "bar", "column", "pie"}:
                    result["chart_type"] = self.normalize_chart_type(value)
                result["is_chart"] = True
                mode = "chart"
                continue

            if m := re.match(r"^\s*series\s*name\b\s*[:\-]\s*(.+?)\s*$", line, re.IGNORECASE):
                current_series = normalize_whitespace(m.group(1)) or f"Series {len(result['chart_series']) + 1}"
                result["series_name"] = current_series
                result["chart_series"].setdefault(current_series, OrderedDict())
                result["is_chart"] = True
                mode = "chart"
                continue

            if m := re.match(r"^\s*series\b\s*[:\-]\s*(.+?)\s*$", line, re.IGNORECASE):
                current_series = normalize_whitespace(m.group(1)) or f"Series {len(result['chart_series']) + 1}"
                result["series_name"] = current_series
                result["chart_series"].setdefault(current_series, OrderedDict())
                result["is_chart"] = True
                mode = "chart"
                continue

            if m := re.match(r"^\s*(?:image|path)\b\s*[:\-]\s*(.+?)\s*$", line, re.IGNORECASE):
                result["image_path"] = normalize_whitespace(m.group(1))
                mode = None
                continue

            if m := re.match(r"^\s*(?:notes|speaker\s*notes)\b\s*[:\-]?\s*(.*)$", line, re.IGNORECASE):
                mode = "notes"
                tail = normalize_whitespace(m.group(1))
                if tail:
                    note_lines.append(tail)
                continue

            if m := re.match(r"^\s*categories\b\s*[:\-]\s*(.+?)\s*$", line, re.IGNORECASE):
                cats = self.split_inline_list(normalize_whitespace(m.group(1)))
                if cats:
                    result["chart_categories"] = cats
                continue

            if mode == "paragraph":
                if re.match(r"^(title|subtitle|bullets?|chart|chart type|categories|values|image|path|series name|table|notes|speaker notes|section)\b", line, re.IGNORECASE):
                    mode = None
                else:
                    paragraph_lines.append(line)
                    continue

            elif mode == "bullets":
                bullet_match = re.match(r"^(?:[-*•]|\d+[.)])\s*(.*\S)$", line)
                if bullet_match:
                    result["bullets"].append(normalize_whitespace(bullet_match.group(1)))
                elif not re.match(r"^(title|subtitle|paragraph|chart|chart type|categories|values|image|path|series name|table|notes|speaker notes|section)\b", line, re.IGNORECASE):
                    result["bullets"].append(normalize_whitespace(line))
                continue

            elif mode == "table":
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

            elif mode == "chart":
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

            elif mode == "notes":
                if re.match(r"^(title|subtitle|paragraph|bullets?|chart|chart type|categories|values|image|path|series name|table|section)\b", line, re.IGNORECASE):
                    mode = None
                else:
                    note_lines.append(line)
                    continue

            # Generic table capture if user pasted a markdown table without a table: marker.
            if "|" in line:
                row = self.parse_table_row(line)
                if row and len(row) >= 2:
                    result["table_rows"].append(row)
                    continue

        if not result["title"]:
            result["title"] = self.extract_heading_title(block)

        result["paragraph"] = normalize_whitespace(" ".join(paragraph_lines))
        result["notes"] = normalize_whitespace(" ".join(note_lines))

        if result["chart_series"] and not result["chart_categories"]:
            seen: List[str] = []
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
        parts = [p for p in parts if p]
        # Skip markdown separator rows like --- | ---
        if parts and all(re.fullmatch(r"[:\-\s]+", p) for p in parts):
            return []
        return parts

    def normalize_chart_type(self, text: str) -> str:
        t = normalize_whitespace(text).lower()
        if "line" in t:
            return "line"
        if "bar" in t:
            return "bar"
        if "pie" in t:
            return "pie"
        return "column"

    def is_chart_block(self, text_l: str) -> bool:
        return bool(re.search(r"\b(chart|graph)\b", text_l) or re.search(r"\b[A-Za-z]{3,9}\s*[:=]\s*\d+(?:\.\d+)?\b", text_l))

    def build_chart_payload(self, parsed: Dict[str, Any], title: str) -> Dict[str, Any]:
        chart_series = parsed.get("chart_series") or OrderedDict()
        chart_type = parsed.get("chart_type") or "line"
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


# -----------------------------------------------------------------------------
# Plugin system
# -----------------------------------------------------------------------------

class BasePlugin:
    def apply(self, slide, plan: Dict[str, Any], theme_name: Optional[str] = None) -> None:
        raise NotImplementedError


class TextPlugin(BasePlugin):
    def apply(self, slide, plan: Dict[str, Any], theme_name: Optional[str] = None) -> None:
        palette = get_theme_palette(theme_name)
        title = normalize_whitespace(plan.get("title", ""))
        subtitle = normalize_whitespace(plan.get("subtitle", ""))

        # Centered title slide.
        add_round_panel(slide, 0.95, 1.5, 11.45, 3.2, palette["panel"], palette["accent"])
        if title:
            add_textbox(slide, 1.35, 2.0, 10.5, 0.9, title, font_size=32, bold=True, color=palette["accent"], align="center")
        if subtitle:
            add_textbox(slide, 1.35, 3.0, 10.5, 0.9, subtitle, font_size=18, color=palette["text"], align="center")


class ContentPlugin(BasePlugin):
    def apply(self, slide, plan: Dict[str, Any], theme_name: Optional[str] = None) -> None:
        palette = get_theme_palette(theme_name)
        title = normalize_whitespace(plan.get("title", ""))
        subtitle = normalize_whitespace(plan.get("subtitle", ""))
        paragraph = normalize_whitespace(plan.get("paragraph", ""))
        bullets = plan.get("bullets", []) or []

        if title:
            add_textbox(slide, 0.8, 0.45, 9.8, 0.6, title, font_size=24, bold=True, color=palette["accent"])
        if subtitle:
            add_textbox(slide, 0.82, 1.0, 10.5, 0.35, subtitle, font_size=12, italic=True, color=palette["text"])

        y = 1.45

        if paragraph:
            add_round_panel(slide, 0.85, y, 11.6, 1.6, palette["panel"], palette["accent"])
            box = slide.shapes.add_textbox(Inches(1.05), Inches(y + 0.12), Inches(11.1), Inches(1.25))
            tf = box.text_frame
            tf.clear()
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.text = paragraph
            p.space_after = Pt(6)
            set_paragraph_style(p, font_size=18, color=palette["text"])
            y += 1.85

        if bullets:
            bullet_height = max(1.4, min(4.3, 0.34 * len(bullets) + 0.55))
            add_round_panel(slide, 0.85, y, 11.6, bullet_height, palette["panel"], palette["accent"])
            box = slide.shapes.add_textbox(Inches(1.0), Inches(y + 0.12), Inches(11.0), Inches(bullet_height - 0.2))
            tf = box.text_frame
            tf.clear()
            tf.word_wrap = True
            for i, point in enumerate(bullets):
                p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                p.text = f"• {point}"
                p.level = 0
                p.space_after = Pt(6)
                set_paragraph_style(p, font_size=17, color=palette["text"])
            y += bullet_height + 0.2


class ChartPlugin(BasePlugin):
    def apply(self, slide, plan: Dict[str, Any], theme_name: Optional[str] = None) -> None:
        palette = get_theme_palette(theme_name)
        chart_type = str(plan.get("chart_type", "column")).lower()
        categories = list(plan.get("categories", []))
        values = list(plan.get("values", []))
        series_map = plan.get("series_map") or {}
        series_name = normalize_whitespace(plan.get("series_name", "Usage"))
        title = normalize_whitespace(plan.get("title", "Chart"))

        if title:
            add_textbox(slide, 0.8, 0.45, 10.0, 0.6, title, font_size=24, bold=True, color=palette["accent"])

        chart_data = CategoryChartData()
        if series_map:
            if not categories:
                seen: List[str] = []
                for mapping in series_map.values():
                    for cat in mapping.keys():
                        if cat not in seen:
                            seen.append(cat)
                categories = seen
            chart_data.categories = categories
            for s_name, mapping in series_map.items():
                series_values = [float(mapping.get(cat, 0)) for cat in categories]
                chart_data.add_series(str(s_name), series_values)
        else:
            if len(categories) != len(values):
                n = min(len(categories), len(values))
                categories = categories[:n]
                values = values[:n]
            if not categories:
                categories = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
            if not values:
                values = [12, 18, 24, 31, 39, 48]
            chart_data.categories = categories
            chart_data.add_series(series_name, values)

        chart_kind = XL_CHART_TYPE.COLUMN_CLUSTERED
        if chart_type == "line":
            chart_kind = XL_CHART_TYPE.LINE_MARKERS
        elif chart_type == "bar":
            chart_kind = XL_CHART_TYPE.BAR_CLUSTERED
        elif chart_type == "pie":
            chart_kind = XL_CHART_TYPE.PIE

        slide.shapes.add_chart(chart_kind, Inches(0.9), Inches(1.35), Inches(12.0), Inches(4.9), chart_data)


class ImagePlugin(BasePlugin):
    def apply(self, slide, plan: Dict[str, Any], theme_name: Optional[str] = None) -> None:
        palette = get_theme_palette(theme_name)
        path = normalize_whitespace(plan.get("path", ""))
        caption = normalize_whitespace(plan.get("caption", ""))
        title = normalize_whitespace(plan.get("title", ""))
        subtitle = normalize_whitespace(plan.get("subtitle", ""))

        if title:
            add_textbox(slide, 0.8, 0.45, 10.0, 0.6, title, font_size=24, bold=True, color=palette["accent"])
        if subtitle:
            add_textbox(slide, 0.82, 1.0, 10.5, 0.3, subtitle, font_size=12, italic=True, color=palette["text"])

        safe_path = sanitize_image_path(path)
        if safe_path:
            slide.shapes.add_picture(safe_path, Inches(1.0), Inches(1.55), width=Inches(7.6))
        else:
            add_round_panel(slide, 1.0, 1.6, 7.8, 3.2, palette["panel"], palette["accent"])
            add_textbox(slide, 1.3, 2.8, 7.2, 0.6, f"Image not found: {path or 'none'}", font_size=18, color=palette["text"], align="center")

        if caption:
            add_textbox(slide, 1.0, 5.35, 7.8, 0.35, caption, font_size=12, color=palette["text"], align="center")


class TablePlugin(BasePlugin):
    def apply(self, slide, plan: Dict[str, Any], theme_name: Optional[str] = None) -> None:
        palette = get_theme_palette(theme_name)
        title = normalize_whitespace(plan.get("title", "Table"))
        headers = plan.get("headers", []) or []
        rows = plan.get("rows", []) or []

        if title:
            add_textbox(slide, 0.8, 0.45, 10.0, 0.6, title, font_size=24, bold=True, color=palette["accent"])

        if not headers or not rows:
            add_round_panel(slide, 1.0, 1.65, 11.2, 1.0, palette["panel"], palette["accent"])
            add_textbox(slide, 1.2, 1.9, 10.8, 0.4, "Table data not found or incomplete.", font_size=18, color=palette["text"], align="center")
            return

        cols = len(headers)
        row_count = len(rows) + 1
        table_shape = slide.shapes.add_table(row_count, cols, Inches(0.8), Inches(1.5), Inches(12.0), Inches(4.95))
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
                    run.font.size = Pt(12)
                    run.font.bold = True
                    run.font.color.rgb = palette["background"]

        for r, row in enumerate(rows, start=1):
            values = list(row) + [""] * max(0, cols - len(row))
            values = values[:cols]
            for c, value in enumerate(values):
                cell = table.cell(r, c)
                cell.text = str(value)
                for p in cell.text_frame.paragraphs:
                    for run in p.runs:
                        run.font.size = Pt(11)
                        run.font.color.rgb = palette["text"]


class NotesPlugin(BasePlugin):
    def apply(self, slide, plan: Dict[str, Any], theme_name: Optional[str] = None) -> None:
        set_slide_notes(slide, plan.get("notes", ""))


PLUGIN_REGISTRY: Dict[str, BasePlugin] = {
    "text": TextPlugin(),
    "content": ContentPlugin(),
    "chart": ChartPlugin(),
    "image": ImagePlugin(),
    "table": TablePlugin(),
    "notes": NotesPlugin(),
}


# -----------------------------------------------------------------------------
# Renderer
# -----------------------------------------------------------------------------

class PptRenderer:
    def __init__(self, template_file: str = DEFAULT_TEMPLATE_FILE):
        self.template_file = template_file

    def render(self, plan: PresentationPlan, background_theme: Optional[str] = None) -> Presentation:
        prs = ensure_template_prs(self.template_file)
        if len(prs.slides) > 0:
            # Start from a clean deck copy only if the template already has slides.
            pass

        for slide_spec in plan.slides:
            layout_index = 6 if len(prs.slide_layouts) > 6 else 0
            slide = prs.slides.add_slide(prs.slide_layouts[layout_index])
            set_slide_background(slide, background_theme)

            for plugin in slide_spec.plugins:
                handler = PLUGIN_REGISTRY.get(plugin.type)
                if handler is None:
                    raise ValueError(f"Unsupported plugin: {plugin.type}")
                handler.apply(slide, plugin.data, theme_name=background_theme)

        return prs


# -----------------------------------------------------------------------------
# Storage and service
# -----------------------------------------------------------------------------

def save_presentation(prs: Presentation, title: str) -> str:
    file_id = uuid.uuid4().hex
    filename = f"{safe_filename(title)}_{file_id}.pptx"
    file_path = OUTPUT_DIR / filename
    prs.save(str(file_path))
    return str(file_path)


class PresentationService:
    def __init__(self) -> None:
        self.planner = PromptPlanner()
        self.renderer = PptRenderer()

    def generate(self, req: GenerateRequest) -> Tuple[str, PresentationPlan, str]:
        template_file = resolve_template_path(req.template_name)
        self.renderer = PptRenderer(template_file=template_file)

        plan = self.planner.plan(
            req.prompt,
            include_title_slide=req.include_title_slide,
            allow_bullets=req.allow_bullets,
            allow_paragraph=req.allow_paragraph,
            allow_chart=req.allow_chart,
            allow_image=req.allow_image,
            allow_section_slide=req.allow_section_slide,
            allow_table=req.allow_table,
            smart_mode=req.smart_mode,
            slide_types=normalize_slide_types(req.slide_types),
        )
        prs = self.renderer.render(plan, background_theme=req.background_theme)
        file_path = save_presentation(prs, plan.title)
        return file_path, plan, plan.title


service = PresentationService()


# -----------------------------------------------------------------------------
# API endpoints
# -----------------------------------------------------------------------------

@router.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@router.post("/plan", response_model=PresentationPlan)
def preview_plan(req: GenerateRequest) -> PresentationPlan:
    try:
        return service.planner.plan(
            req.prompt,
            include_title_slide=req.include_title_slide,
            allow_bullets=req.allow_bullets,
            allow_paragraph=req.allow_paragraph,
            allow_chart=req.allow_chart,
            allow_image=req.allow_image,
            allow_section_slide=req.allow_section_slide,
            allow_table=req.allow_table,
            smart_mode=req.smart_mode,
            slide_types=normalize_slide_types(req.slide_types),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/generate", response_model=GenerateResponse)
def generate_presentation(req: GenerateRequest, request: Request) -> GenerateResponse:
    try:
        file_path, _plan, _title = service.generate(req)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    job_id = uuid.uuid4().hex
    filename = Path(file_path).name
    download_url = str(request.url_for("download_ppt", file_name=filename))

    return GenerateResponse(
        job_id=job_id,
        status="completed",
        file_name=filename,
        download_url=download_url,
    )


@router.get("/download/{file_name}", name="download_ppt")
def download_ppt(file_name: str) -> FileResponse:
    file_path = OUTPUT_DIR / file_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path=str(file_path),
        filename=file_name,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
