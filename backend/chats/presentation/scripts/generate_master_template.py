"""MOTHER AI PowerPoint Master Template Engine.

Provides a modular, content-aware presentation builder and layout resolver
for generating professional 16:9 widescreen PowerPoint templates (.pptx).
"""

from __future__ import annotations

import collections
import collections.abc
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Compatibility shim for python-pptx on modern Python versions
for name in ("Container", "Mapping", "MutableMapping", "Sequence", "MutableSequence", "Iterable", "Callable"):
    if not hasattr(collections, name) and hasattr(collections.abc, name):
        setattr(collections, name, getattr(collections.abc, name))

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

logger = logging.getLogger("mother.presentation.master_template")


# -----------------------------------------------------------------------------
# 1. Centralized Geometry Configuration (16:9 Widescreen)
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class GeometryConfig:
    """Master presentation dimensions and safe bounding coordinates in inches."""

    SLIDE_WIDTH: float = 13.333
    SLIDE_HEIGHT: float = 7.5

    MARGIN_X: float = 0.7
    MARGIN_Y: float = 0.5
    HEADER_HEIGHT: float = 0.85
    FOOTER_HEIGHT: float = 0.35

    CONTENT_TOP: float = 1.35
    CONTENT_BOTTOM: float = 6.65

    @property
    def content_width(self) -> float:
        return self.SLIDE_WIDTH - (2 * self.MARGIN_X)

    @property
    def content_height(self) -> float:
        return self.CONTENT_BOTTOM - self.CONTENT_TOP

    def get_column_rects(
        self, count: int, top: Optional[float] = None, height: Optional[float] = None, gap: float = 0.4
    ) -> List[Tuple[float, float, float, float]]:
        """Calculates horizontally distributed column rectangles within safe margins."""
        y = self.CONTENT_TOP if top is None else top
        h = self.content_height if height is None else height
        total_width = self.content_width
        col_width = (total_width - (count - 1) * gap) / max(1, count)

        rects = []
        for i in range(count):
            x = self.MARGIN_X + i * (col_width + gap)
            rects.append((x, y, col_width, h))
        return rects


GEOMETRY = GeometryConfig()


# -----------------------------------------------------------------------------
# 2. Validation & Contrast Systems
# -----------------------------------------------------------------------------
def calculate_luminance(color: RGBColor) -> float:
    """Computes ITU-R BT.601 perceptual luminance (0 to 255)."""
    return 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]


def calculate_contrast_ratio(c1: RGBColor, c2: RGBColor) -> float:
    """Calculates standard WCAG relative luminance contrast ratio (1.0 to 21.0)."""
    l1 = (calculate_luminance(c1) / 255.0) + 0.05
    l2 = (calculate_luminance(c2) / 255.0) + 0.05
    return max(l1, l2) / min(l1, l2)


def validate_text_contrast(text_color: RGBColor, bg_color: RGBColor, min_ratio: float = 3.0) -> bool:
    """Validates that text is sufficiently legible against its container background."""
    ratio = calculate_contrast_ratio(text_color, bg_color)
    is_valid = ratio >= min_ratio
    if not is_valid:
        logger.warning(
            f"Low text contrast detected: ratio {ratio:.2f} < {min_ratio:.2f} "
            f"(text={text_color}, bg={bg_color})"
        )
    return is_valid


def validate_shape_bounds(
    x: float, y: float, width: float, height: float, context: str = ""
) -> bool:
    """Detects invalid geometry, negative dimensions, or slide boundary overflow."""
    if width <= 0 or height <= 0:
        logger.error(f"Invalid shape dimensions in {context}: w={width}, h={height}")
        return False
    if x < 0 or y < 0:
        logger.error(f"Shape positioned out of bounds (negative origin) in {context}: x={x}, y={y}")
        return False
    if (x + width) > (GEOMETRY.SLIDE_WIDTH + 0.08) or (y + height) > (GEOMETRY.SLIDE_HEIGHT + 0.08):
        logger.warning(
            f"Shape overflows 16:9 canvas in {context}: right={x+width:.2f}, bottom={y+height:.2f} "
            f"(max {GEOMETRY.SLIDE_WIDTH}x{GEOMETRY.SLIDE_HEIGHT})"
        )
        return False
    return True


# -----------------------------------------------------------------------------
# 3. Theme Configuration Model
# -----------------------------------------------------------------------------
@dataclass
class ThemeConfig:
    """Single source of truth for presentation branding, colors, and typography."""

    name: str = "MOTHER AI Slate Teal"
    background: RGBColor = field(default_factory=lambda: RGBColor(15, 23, 42))     # Slate 900
    surface: RGBColor = field(default_factory=lambda: RGBColor(248, 250, 252))      # Slate 50
    card: RGBColor = field(default_factory=lambda: RGBColor(255, 255, 255))         # Pure White
    border: RGBColor = field(default_factory=lambda: RGBColor(226, 232, 240))       # Slate 200
    primary: RGBColor = field(default_factory=lambda: RGBColor(13, 148, 136))       # Teal 600
    secondary: RGBColor = field(default_factory=lambda: RGBColor(99, 102, 241))     # Indigo 500
    heading: RGBColor = field(default_factory=lambda: RGBColor(15, 23, 42))         # Dark Slate
    body: RGBColor = field(default_factory=lambda: RGBColor(51, 65, 85))            # Slate 700
    muted: RGBColor = field(default_factory=lambda: RGBColor(100, 116, 139))        # Slate 500
    inverse: RGBColor = field(default_factory=lambda: RGBColor(241, 245, 249))      # Slate 100
    accent_bar: RGBColor = field(default_factory=lambda: RGBColor(13, 148, 136))

    font_family: str = "Arial"
    title_size: int = 28
    subtitle_size: int = 14
    cover_title_size: int = 44
    section_title_size: int = 38
    body_size: int = 16
    bullet_size: int = 15
    stat_size: int = 48
    footer_size: int = 9

    def is_dark_bg(self) -> bool:
        return calculate_luminance(self.background) < 130

    def get_contrast_text(self, bg_color: RGBColor) -> RGBColor:
        """Returns heading (dark) or inverse (light) text color based on background luminance."""
        return self.heading if calculate_luminance(bg_color) > 140 else self.inverse


# -----------------------------------------------------------------------------
# 4. Reusable Rendering Primitives
# -----------------------------------------------------------------------------
def add_blank_slide(prs: Presentation) -> Any:
    """Adds a pristine blank slide (layout 6) with all default placeholders stripped."""
    blank_layout = None
    for layout in prs.slide_layouts:
        if len(layout.placeholders) == 0:
            blank_layout = layout
            break
    if blank_layout is None:
        blank_layout = prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[-1]

    slide = prs.slides.add_slide(blank_layout)

    # Purge any inherited placeholder shapes for full manual layout control
    for ph in list(slide.placeholders):
        try:
            sp = ph._element
            sp.getparent().remove(sp)
        except Exception:
            pass
    return slide


def add_solid_background(slide: Any, color: RGBColor) -> Any:
    """Fills the slide background with a solid color."""
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0),
        Inches(0),
        Inches(GEOMETRY.SLIDE_WIDTH),
        Inches(GEOMETRY.SLIDE_HEIGHT),
    )
    bg.fill.solid()
    bg.fill.fore_color.rgb = color
    bg.line.fill.background()
    return bg


def add_card(
    slide: Any,
    x: float,
    y: float,
    w: float,
    h: float,
    theme: ThemeConfig,
    fill_color: Optional[RGBColor] = None,
    border_color: Optional[RGBColor] = None,
    border_width: float = 1.0,
    rounded: bool = True,
) -> Any:
    """Creates a stylized semantic card container with safe-area validation."""
    validate_shape_bounds(x, y, w, h, context="Card Primitive")
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE
    card = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
    card.fill.solid()
    card.fill.fore_color.rgb = fill_color or theme.card
    if border_color or border_width > 0:
        card.line.color.rgb = border_color or theme.border
        card.line.width = Pt(border_width)
    else:
        card.line.fill.background()
    return card


def add_text_box(
    slide: Any,
    x: float,
    y: float,
    w: float,
    h: float,
    word_wrap: bool = True,
    margin_lr: float = 0.08,
    margin_tb: float = 0.05,
) -> Any:
    """Creates an absolute positioned text box with zero excess padding."""
    validate_shape_bounds(x, y, w, h, context="TextBox Primitive")
    tbox = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tbox.text_frame
    tf.word_wrap = word_wrap
    tf.margin_left = Inches(margin_lr)
    tf.margin_right = Inches(margin_lr)
    tf.margin_top = Inches(margin_tb)
    tf.margin_bottom = Inches(margin_tb)
    return tbox


def add_badge(
    slide: Any,
    x: float,
    y: float,
    w: float,
    h: float,
    text: str,
    theme: Optional[Union[ThemeConfig, RGBColor]] = None,
    bg_color: Optional[RGBColor] = None,
    text_color: Optional[RGBColor] = None,
) -> Any:
    """Creates a branded badge tag with flexible theme/color input."""
    validate_shape_bounds(x, y, w, h, context="Badge Primitive")
    badge = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h)
    )

    t_cfg = theme if isinstance(theme, ThemeConfig) else ThemeConfig()
    if isinstance(theme, RGBColor):
        fill = theme
    else:
        fill = bg_color or t_cfg.primary

    badge.fill.solid()
    badge.fill.fore_color.rgb = fill
    badge.line.fill.background()

    tf = badge.text_frame
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.word_wrap = False
    p = tf.paragraphs[0]
    p.text = text
    p.alignment = PP_ALIGN.CENTER
    p.font.name = t_cfg.font_family
    p.font.size = Pt(10)
    p.font.bold = True
    p.font.color.rgb = text_color or t_cfg.get_contrast_text(fill)
    return badge


def add_header(
    slide: Any,
    title: str,
    subtitle: Optional[str],
    theme: ThemeConfig,
    show_accent_bar: bool = True,
    brand_label: str = "MOTHER AI",
) -> None:
    """Renders standardized slide header with title, category/subtitle, accent line, and logo."""
    if show_accent_bar:
        bar = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(0),
            Inches(0),
            Inches(GEOMETRY.SLIDE_WIDTH),
            Inches(0.08),
        )
        bar.fill.solid()
        bar.fill.fore_color.rgb = theme.accent_bar
        bar.line.fill.background()

    # Brand badge right top
    brand_box = add_text_box(
        slide, GEOMETRY.SLIDE_WIDTH - GEOMETRY.MARGIN_X - 2.5, 0.35, 2.5, 0.4
    )
    p_b = brand_box.text_frame.paragraphs[0]
    p_b.text = brand_label
    p_b.alignment = PP_ALIGN.RIGHT
    p_b.font.name = theme.font_family
    p_b.font.size = Pt(11)
    p_b.font.bold = True
    p_b.font.color.rgb = theme.primary

    # Title & Subtitle left top
    title_w = GEOMETRY.SLIDE_WIDTH - (2 * GEOMETRY.MARGIN_X) - 2.8
    tbox = add_text_box(slide, GEOMETRY.MARGIN_X, 0.32, title_w, GEOMETRY.HEADER_HEIGHT)
    tf = tbox.text_frame
    p_t = tf.paragraphs[0]
    p_t.text = title
    p_t.font.name = theme.font_family
    p_t.font.size = Pt(theme.title_size)
    p_t.font.bold = True
    p_t.font.color.rgb = theme.heading

    if subtitle:
        p_s = tf.add_paragraph()
        p_s.space_before = Pt(3)
        p_s.text = subtitle
        p_s.font.name = theme.font_family
        p_s.font.size = Pt(theme.subtitle_size)
        p_s.font.color.rgb = theme.muted


def add_footer(
    slide: Any,
    theme: ThemeConfig,
    left_text: str = "MOTHER AI Presentation Engine • Confidential",
    right_text: str = "",
) -> None:
    """Renders standardized slide footer."""
    y = 6.9
    w = GEOMETRY.content_width
    tbox = add_text_box(slide, GEOMETRY.MARGIN_X, y, w, GEOMETRY.FOOTER_HEIGHT)
    tf = tbox.text_frame
    p = tf.paragraphs[0]
    p.text = left_text
    p.font.name = theme.font_family
    p.font.size = Pt(theme.footer_size)
    p.font.color.rgb = theme.muted

    if right_text:
        p_r = tf.add_paragraph()
        p_r.text = right_text
        p_r.alignment = PP_ALIGN.RIGHT
        p_r.font.name = theme.font_family
        p_r.font.size = Pt(theme.footer_size)
        p_r.font.color.rgb = theme.muted


# -----------------------------------------------------------------------------
# 5. Content-Aware Layout Resolver
# -----------------------------------------------------------------------------
class LayoutResolver:
    """Inspects structured content data and intelligently determines the optimal slide layout."""

    @staticmethod
    def resolve_layout(content: Dict[str, Any]) -> str:
        """Determines the appropriate slide layout type based on content structure."""
        if not isinstance(content, dict):
            return "title_content"

        # Explicit override
        explicit_type = content.get("type") or content.get("layout")
        if explicit_type:
            return str(explicit_type).lower().replace("-", "_")

        if content.get("is_cover") or "cover" in str(content.get("role", "")).lower():
            return "cover"
        if content.get("is_section") or "section" in str(content.get("role", "")).lower():
            return "section"

        # Structural detection
        if "timeline" in content or "milestones" in content:
            return "timeline"
        if "steps" in content or "process_steps" in content:
            return "process"
        if "quote" in content or "quotation" in content:
            return "quote"
        if "stats" in content or "kpis" in content or "metrics" in content:
            return "statistics"
        if "table" in content or ("headers" in content and "rows" in content):
            return "table"
        if "chart" in content or "chart_data" in content:
            return "chart"

        has_left = "left_column" in content or "left_card" in content
        has_right = "right_column" in content or "right_card" in content
        if has_left and has_right:
            return "two_column"

        cards = content.get("cards") or content.get("features")
        if isinstance(cards, list) and len(cards) >= 3:
            return "three_column"

        has_image = bool(content.get("image") or content.get("image_url"))
        has_paragraph = bool(content.get("paragraph") or content.get("body"))
        has_bullets = bool(content.get("bullets") or content.get("items"))

        if has_image and has_paragraph and has_bullets:
            return "mixed_content"
        if has_image and (has_paragraph or has_bullets):
            return "image_text"
        if has_paragraph and has_bullets:
            return "mixed_content"

        return "title_content"


# -----------------------------------------------------------------------------
# 6. Master PPTBuilder & Specialized Slide Renderers
# -----------------------------------------------------------------------------
class PPTBuilder:
    """Production-grade PowerPoint Builder implementing 14+ responsive layouts."""

    def __init__(self, theme: Optional[ThemeConfig] = None):
        self.theme = theme or ThemeConfig()
        logger.info(f"Initialized PPTBuilder with theme '{self.theme.name}'")

    def create_presentation(self) -> Presentation:
        """Initializes a new 16:9 widescreen presentation object."""
        prs = Presentation()
        prs.slide_width = Inches(GEOMETRY.SLIDE_WIDTH)
        prs.slide_height = Inches(GEOMETRY.SLIDE_HEIGHT)
        return prs

    # 1. Cover Slide
    def add_cover(
        self,
        prs: Presentation,
        title: str = "Presentation Title Master",
        subtitle: Optional[str] = "Subtitle or Key Takeaway Text",
        badge_text: str = "MOTHER AI",
        footer_text: str = "Generated by MOTHER AI Presentation System • Confidential",
    ) -> Any:
        slide = add_blank_slide(prs)
        add_solid_background(slide, self.theme.background)

        # Brand Badge top left
        add_badge(slide, GEOMETRY.MARGIN_X, 0.8, 1.8, 0.42, badge_text, self.theme.primary)

        # Vertical Decorative Accent Bar
        accent_bar = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(GEOMETRY.MARGIN_X),
            Inches(1.8),
            Inches(0.12),
            Inches(4.2),
        )
        accent_bar.fill.solid()
        accent_bar.fill.fore_color.rgb = self.theme.primary
        accent_bar.line.fill.background()

        # Title & Subtitle Card / Box
        tbox = add_text_box(slide, GEOMETRY.MARGIN_X + 0.4, 2.0, 11.2, 3.8)
        tf = tbox.text_frame
        p_t = tf.paragraphs[0]
        p_t.text = title
        p_t.font.name = self.theme.font_family
        p_t.font.size = Pt(self.theme.cover_title_size)
        p_t.font.bold = True
        p_t.font.color.rgb = self.theme.inverse

        if subtitle:
            p_s = tf.add_paragraph()
            p_s.space_before = Pt(16)
            p_s.text = subtitle
            p_s.font.name = self.theme.font_family
            p_s.font.size = Pt(22)
            p_s.font.color.rgb = self.theme.primary

        # Discrete Footer
        foot_box = add_text_box(
            slide, GEOMETRY.MARGIN_X, 6.7, GEOMETRY.content_width, GEOMETRY.FOOTER_HEIGHT
        )
        p_f = foot_box.text_frame.paragraphs[0]
        p_f.text = footer_text
        p_f.font.name = self.theme.font_family
        p_f.font.size = Pt(self.theme.footer_size)
        p_f.font.color.rgb = self.theme.muted

        return slide

    # 2. Title + Content Slide
    def add_title_content(
        self,
        prs: Presentation,
        title: str = "Slide Header Title",
        subtitle: Optional[str] = "Categorical Context & Overview",
        paragraph: Optional[str] = "Primary overview text articulating the central thesis of this topic.",
        bullets: Optional[List[str]] = None,
    ) -> Any:
        slide = add_blank_slide(prs)
        add_solid_background(slide, self.theme.surface)
        add_header(slide, title, subtitle, self.theme)

        # Content Card
        add_card(
            slide,
            GEOMETRY.MARGIN_X,
            GEOMETRY.CONTENT_TOP,
            GEOMETRY.content_width,
            GEOMETRY.content_height,
            self.theme,
        )

        tbox = add_text_box(
            slide,
            GEOMETRY.MARGIN_X + 0.5,
            GEOMETRY.CONTENT_TOP + 0.5,
            GEOMETRY.content_width - 1.0,
            GEOMETRY.content_height - 1.0,
        )
        tf = tbox.text_frame

        if paragraph:
            p_body = tf.paragraphs[0]
            p_body.text = paragraph
            p_body.font.name = self.theme.font_family
            p_body.font.size = Pt(self.theme.body_size)
            p_body.font.color.rgb = self.theme.body

        bullet_items = bullets or [
            "Structured insight articulating core operational requirements",
            "Deterministic layout calculations eliminating placeholder drift",
            "Automatic luminance-based typography contrast validation",
        ]
        for idx, item in enumerate(bullet_items):
            p = tf.add_paragraph() if (paragraph or idx > 0) else tf.paragraphs[0]
            p.space_before = Pt(10)
            p.text = f"•   {item}"
            p.font.name = self.theme.font_family
            p.font.size = Pt(self.theme.bullet_size)
            p.font.color.rgb = self.theme.body

        add_footer(slide, self.theme)
        return slide

    # 3. Two Column Slide
    def add_two_column(
        self,
        prs: Presentation,
        title: str = "Two-Column Architecture Comparison",
        subtitle: Optional[str] = "Dual Stream Content Analysis",
        left_card: Optional[Dict[str, Any]] = None,
        right_card: Optional[Dict[str, Any]] = None,
    ) -> Any:
        slide = add_blank_slide(prs)
        add_solid_background(slide, self.theme.surface)
        add_header(slide, title, subtitle, self.theme)

        cols = GEOMETRY.get_column_rects(2, gap=0.5)

        l_data = left_card or {
            "title": "Primary Stream A",
            "body": "Detailed assessment of input factors and structural baselines.",
            "bullets": ["High baseline throughput", "Standard memory allocation", "Synchronous execution"],
        }
        r_data = right_card or {
            "title": "Optimized Stream B",
            "body": "Refactored processing pipeline utilizing parallel execution queues.",
            "bullets": ["Zero placeholder artifacts", "Strict boundary validation", "Automated contrast enforcement"],
        }

        for (cx, cy, cw, ch), data, is_accent in zip(cols, [l_data, r_data], [False, True]):
            border_c = self.theme.primary if is_accent else self.theme.border
            add_card(slide, cx, cy, cw, ch, self.theme, border_color=border_c, border_width=1.5)

            tbox = add_text_box(slide, cx + 0.4, cy + 0.4, cw - 0.8, ch - 0.8)
            tf = tbox.text_frame
            p_h = tf.paragraphs[0]
            p_h.text = data.get("title", "Column Heading")
            p_h.font.name = self.theme.font_family
            p_h.font.size = Pt(20)
            p_h.font.bold = True
            p_h.font.color.rgb = self.theme.primary if is_accent else self.theme.heading

            if "body" in data:
                p_b = tf.add_paragraph()
                p_b.space_before = Pt(8)
                p_b.text = data["body"]
                p_b.font.name = self.theme.font_family
                p_b.font.size = Pt(self.theme.body_size)
                p_b.font.color.rgb = self.theme.body

            for bullet in data.get("bullets", []):
                p_it = tf.add_paragraph()
                p_it.space_before = Pt(8)
                p_it.text = f"•  {bullet}"
                p_it.font.name = self.theme.font_family
                p_it.font.size = Pt(self.theme.bullet_size)
                p_it.font.color.rgb = self.theme.body

        add_footer(slide, self.theme)
        return slide

    # 4. Three Column Slide (3-Card Grid)
    def add_three_column(
        self,
        prs: Presentation,
        title: str = "Core Platform Capabilities",
        subtitle: Optional[str] = "Three-Pillar Modular Framework",
        cards: Optional[List[Dict[str, Any]]] = None,
    ) -> Any:
        slide = add_blank_slide(prs)
        add_solid_background(slide, self.theme.surface)
        add_header(slide, title, subtitle, self.theme)

        cards_data = cards or [
            {"title": "Geometry Engine", "badge": "PILLAR 1", "body": "Absolute bounding box calculations with 16:9 safe margins."},
            {"title": "Typography Hierarchy", "badge": "PILLAR 2", "body": "Enforces professional point scales from 44pt titles to 9pt footers."},
            {"title": "Validation Pipeline", "badge": "PILLAR 3", "body": "Continuous checking for contrast legibility and shape containment."},
        ]

        cols = GEOMETRY.get_column_rects(3, gap=0.4)
        for (cx, cy, cw, ch), card_info in zip(cols, cards_data):
            add_card(slide, cx, cy, cw, ch, self.theme, border_color=self.theme.border, border_width=1.2)

            # Top accent stripe on card
            stripe = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE, Inches(cx), Inches(cy), Inches(cw), Inches(0.08)
            )
            stripe.fill.solid()
            stripe.fill.fore_color.rgb = self.theme.primary
            stripe.line.fill.background()

            if "badge" in card_info:
                add_badge(slide, cx + 0.3, cy + 0.3, 1.2, 0.32, card_info["badge"], self.theme)

            top_offset = 0.8 if "badge" in card_info else 0.4
            tbox = add_text_box(slide, cx + 0.3, cy + top_offset, cw - 0.6, ch - top_offset - 0.4)
            tf = tbox.text_frame
            p_t = tf.paragraphs[0]
            p_t.text = card_info.get("title", "Feature Card")
            p_t.font.name = self.theme.font_family
            p_t.font.size = Pt(18)
            p_t.font.bold = True
            p_t.font.color.rgb = self.theme.heading

            p_b = tf.add_paragraph()
            p_b.space_before = Pt(10)
            p_b.text = card_info.get("body", "Description details illustrating architectural purpose.")
            p_b.font.name = self.theme.font_family
            p_b.font.size = Pt(14)
            p_b.font.color.rgb = self.theme.body

        add_footer(slide, self.theme)
        return slide

    # 5. Section Divider Slide
    def add_section(
        self,
        prs: Presentation,
        section_title: str = "Section 02: Analytical Systems",
        section_subtitle: Optional[str] = "Data Processing & Visual Representation Pipelines",
        section_number: str = "02",
    ) -> Any:
        slide = add_blank_slide(prs)
        add_solid_background(slide, self.theme.background)

        # Center Section Card
        left, top, w, h = 1.8, 2.0, 9.733, 3.5
        add_card(slide, left, top, w, h, self.theme, fill_color=self.theme.card, border_color=self.theme.primary, border_width=2.0)

        # Section Tag
        add_badge(slide, left + 0.6, top + 0.5, 1.6, 0.38, f"SECTION {section_number}", self.theme)

        tbox = add_text_box(slide, left + 0.6, top + 1.1, w - 1.2, 2.0)
        tf = tbox.text_frame
        p_t = tf.paragraphs[0]
        p_t.text = section_title
        p_t.font.name = self.theme.font_family
        p_t.font.size = Pt(self.theme.section_title_size)
        p_t.font.bold = True
        p_t.font.color.rgb = self.theme.heading

        if section_subtitle:
            p_s = tf.add_paragraph()
            p_s.space_before = Pt(10)
            p_s.text = section_subtitle
            p_s.font.name = self.theme.font_family
            p_s.font.size = Pt(18)
            p_s.font.color.rgb = self.theme.muted

        return slide

    # 6. Quote Slide
    def add_quote(
        self,
        prs: Presentation,
        quote_text: str = "Simplicity is the prerequisite for reliability.",
        author: str = "Edsger W. Dijkstra",
        source: str = "Turing Award Lecture",
    ) -> Any:
        slide = add_blank_slide(prs)
        add_solid_background(slide, self.theme.surface)
        add_header(slide, "Guiding Philosophy", "Core Design Principle", self.theme)

        # Quote Card
        add_card(
            slide,
            GEOMETRY.MARGIN_X,
            GEOMETRY.CONTENT_TOP,
            GEOMETRY.content_width,
            GEOMETRY.content_height,
            self.theme,
            border_color=self.theme.primary,
            border_width=1.5,
        )

        # Big quotation marks badge
        add_badge(
            slide,
            GEOMETRY.MARGIN_X + 0.8,
            GEOMETRY.CONTENT_TOP + 0.8,
            1.0,
            0.5,
            "QUOTE",
            self.theme,
        )

        tbox = add_text_box(
            slide,
            GEOMETRY.MARGIN_X + 0.8,
            GEOMETRY.CONTENT_TOP + 1.6,
            GEOMETRY.content_width - 1.6,
            2.5,
        )
        tf = tbox.text_frame
        p_q = tf.paragraphs[0]
        p_q.text = f'"{quote_text}"'
        p_q.font.name = self.theme.font_family
        p_q.font.size = Pt(28)
        p_q.font.bold = True
        p_q.font.color.rgb = self.theme.heading

        p_a = tf.add_paragraph()
        p_a.space_before = Pt(20)
        p_a.text = f"— {author}, {source}"
        p_a.font.name = self.theme.font_family
        p_a.font.size = Pt(18)
        p_a.font.color.rgb = self.theme.primary

        add_footer(slide, self.theme)
        return slide

    # 7. Statistics / KPI Slide
    def add_statistics(
        self,
        prs: Presentation,
        title: str = "Key Operational Benchmarks",
        subtitle: Optional[str] = "Quantitative Verification Metrics",
        metrics: Optional[List[Dict[str, str]]] = None,
    ) -> Any:
        slide = add_blank_slide(prs)
        add_solid_background(slide, self.theme.surface)
        add_header(slide, title, subtitle, self.theme)

        metric_list = metrics or [
            {"value": "99.9%", "label": "Layout Accuracy", "desc": "Zero placeholder collisions across templates"},
            {"value": "<45ms", "label": "Generation Speed", "desc": "Sub-50ms deck compile time per request"},
            {"value": "100%", "label": "16:9 Compliance", "desc": "Deterministic widescreen bounding geometry"},
        ]

        cols = GEOMETRY.get_column_rects(len(metric_list), gap=0.45)
        for (cx, cy, cw, ch), m in zip(cols, metric_list):
            add_card(slide, cx, cy, cw, ch, self.theme, border_color=self.theme.primary, border_width=1.5)

            tbox = add_text_box(slide, cx + 0.3, cy + 0.4, cw - 0.6, ch - 0.8)
            tf = tbox.text_frame

            # Value
            p_v = tf.paragraphs[0]
            p_v.text = m.get("value", "00")
            p_v.font.name = self.theme.font_family
            p_v.font.size = Pt(self.theme.stat_size)
            p_v.font.bold = True
            p_v.font.color.rgb = self.theme.primary

            # Label
            p_l = tf.add_paragraph()
            p_l.space_before = Pt(12)
            p_l.text = m.get("label", "Metric Label")
            p_l.font.name = self.theme.font_family
            p_l.font.size = Pt(18)
            p_l.font.bold = True
            p_l.font.color.rgb = self.theme.heading

            # Description
            if "desc" in m:
                p_d = tf.add_paragraph()
                p_d.space_before = Pt(8)
                p_d.text = m["desc"]
                p_d.font.name = self.theme.font_family
                p_d.font.size = Pt(14)
                p_d.font.color.rgb = self.theme.muted

        add_footer(slide, self.theme)
        return slide

    # 8. Comparison Slide
    def add_comparison(
        self,
        prs: Presentation,
        title: str = "System Paradigm Comparison",
        subtitle: Optional[str] = "Baseline Architecture vs Modular Engine",
        options: Optional[List[Dict[str, Any]]] = None,
    ) -> Any:
        return self.add_two_column(
            prs,
            title=title,
            subtitle=subtitle,
            left_card=options[0] if options and len(options) > 0 else None,
            right_card=options[1] if options and len(options) > 1 else None,
        )

    # 9. Timeline Slide
    def add_timeline(
        self,
        prs: Presentation,
        title: str = "Project Roadmap & Milestones",
        subtitle: Optional[str] = "Sequential Phase Progression",
        milestones: Optional[List[Dict[str, str]]] = None,
    ) -> Any:
        slide = add_blank_slide(prs)
        add_solid_background(slide, self.theme.surface)
        add_header(slide, title, subtitle, self.theme)

        steps = milestones or [
            {"phase": "Q1", "title": "Architecture Setup", "desc": "Modularization of ThemeConfig and Geometry systems."},
            {"phase": "Q2", "title": "Layout Resolver", "desc": "Intelligent content parsing and automated slide selection."},
            {"phase": "Q3", "title": "Validation Engine", "desc": "Safe-area bounds and WCAG contrast ratio verification."},
            {"phase": "Q4", "title": "Production Release", "desc": "Master template generation for full full-stack deployment."},
        ]

        # Connecting Horizontal Timeline Line
        y_line = GEOMETRY.CONTENT_TOP + 1.2
        line = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(GEOMETRY.MARGIN_X + 0.5),
            Inches(y_line),
            Inches(GEOMETRY.content_width - 1.0),
            Inches(0.06),
        )
        line.fill.solid()
        line.fill.fore_color.rgb = self.theme.border
        line.line.fill.background()

        cols = GEOMETRY.get_column_rects(len(steps), top=GEOMETRY.CONTENT_TOP, height=GEOMETRY.content_height, gap=0.3)
        for (cx, cy, cw, ch), step in zip(cols, steps):
            # Milestone Circle Badge
            circle = slide.shapes.add_shape(
                MSO_SHAPE.OVAL, Inches(cx + cw / 2 - 0.4), Inches(y_line - 0.37), Inches(0.8), Inches(0.8)
            )
            circle.fill.solid()
            circle.fill.fore_color.rgb = self.theme.primary
            circle.line.fill.background()
            tf_c = circle.text_frame
            tf_c.vertical_anchor = MSO_ANCHOR.MIDDLE
            p_c = tf_c.paragraphs[0]
            p_c.text = step.get("phase", "•")
            p_c.alignment = PP_ALIGN.CENTER
            p_c.font.name = self.theme.font_family
            p_c.font.size = Pt(11)
            p_c.font.bold = True
            p_c.font.color.rgb = self.theme.inverse

            # Text Card below circle
            card_top = y_line + 0.7
            card_h = ch - (card_top - cy)
            add_card(slide, cx, card_top, cw, card_h, self.theme, border_color=self.theme.border)

            tbox = add_text_box(slide, cx + 0.2, card_top + 0.2, cw - 0.4, card_h - 0.4)
            tf = tbox.text_frame
            p_t = tf.paragraphs[0]
            p_t.text = step.get("title", "Milestone")
            p_t.font.name = self.theme.font_family
            p_t.font.size = Pt(16)
            p_t.font.bold = True
            p_t.font.color.rgb = self.theme.heading

            p_d = tf.add_paragraph()
            p_d.space_before = Pt(8)
            p_d.text = step.get("desc", "Milestone description.")
            p_d.font.name = self.theme.font_family
            p_d.font.size = Pt(13)
            p_d.font.color.rgb = self.theme.body

        add_footer(slide, self.theme)
        return slide

    # 10. Process Slide
    def add_process(
        self,
        prs: Presentation,
        title: str = "Linear Execution Pipeline",
        subtitle: Optional[str] = "Step-by-Step Orchestration",
        steps: Optional[List[Dict[str, str]]] = None,
    ) -> Any:
        slide = add_blank_slide(prs)
        add_solid_background(slide, self.theme.surface)
        add_header(slide, title, subtitle, self.theme)

        step_list = steps or [
            {"step": "01", "title": "Content Ingestion", "desc": "Raw text parsing and semantic entity extraction."},
            {"step": "02", "title": "Layout Resolution", "desc": "Selecting the optimal slide architecture based on structure."},
            {"step": "03", "title": "Shape Synthesis", "desc": "Deterministic container rendering on blank slide canvas."},
            {"step": "04", "title": "Quality Verification", "desc": "Checking bounds containment and contrast readability."},
        ]

        cols = GEOMETRY.get_column_rects(len(step_list), gap=0.4)
        for idx, ((cx, cy, cw, ch), s) in enumerate(zip(cols, step_list)):
            add_card(slide, cx, cy, cw, ch, self.theme, border_color=self.theme.border, border_width=1.2)

            # Step Number Badge
            add_badge(slide, cx + 0.3, cy + 0.3, 0.8, 0.32, f"STEP {s.get('step', str(idx+1))}", self.theme)

            tbox = add_text_box(slide, cx + 0.3, cy + 0.8, cw - 0.6, ch - 1.0)
            tf = tbox.text_frame
            p_t = tf.paragraphs[0]
            p_t.text = s.get("title", "Process Step")
            p_t.font.name = self.theme.font_family
            p_t.font.size = Pt(17)
            p_t.font.bold = True
            p_t.font.color.rgb = self.theme.heading

            p_d = tf.add_paragraph()
            p_d.space_before = Pt(8)
            p_d.text = s.get("desc", "Step execution details.")
            p_d.font.name = self.theme.font_family
            p_d.font.size = Pt(13)
            p_d.font.color.rgb = self.theme.body

            # Connector Chevron (between cards)
            if idx < len(step_list) - 1:
                chev_box = add_text_box(slide, cx + cw + 0.05, cy + ch / 2 - 0.25, 0.3, 0.5)
                p_arr = chev_box.text_frame.paragraphs[0]
                p_arr.text = "➔"
                p_arr.alignment = PP_ALIGN.CENTER
                p_arr.font.size = Pt(16)
                p_arr.font.color.rgb = self.theme.primary

        add_footer(slide, self.theme)
        return slide

    # 11. Image + Text Slide
    def add_image_text(
        self,
        prs: Presentation,
        title: str = "Visual Media & Contextual Narrative",
        subtitle: Optional[str] = "Dual-Pane Image Integration",
        paragraph: Optional[str] = "Integrated visual asset framing with contextual editorial annotation.",
        bullets: Optional[List[str]] = None,
        caption: str = "Figure 1.1: Contextual system architecture diagram.",
    ) -> Any:
        slide = add_blank_slide(prs)
        add_solid_background(slide, self.theme.surface)
        add_header(slide, title, subtitle, self.theme)

        cols = GEOMETRY.get_column_rects(2, gap=0.5)

        # Left: Image Placeholder Container
        lx, ly, lw, lh = cols[0]
        add_card(slide, lx, ly, lw, lh, self.theme, fill_color=self.theme.background, border_color=self.theme.primary, border_width=1.5)
        tbox_img = add_text_box(slide, lx + 0.4, ly + lh / 2 - 0.4, lw - 0.8, 0.8)
        p_img = tbox_img.text_frame.paragraphs[0]
        p_img.alignment = PP_ALIGN.CENTER
        p_img.text = "[ IMAGE ASSET CONTAINER ]"
        p_img.font.name = self.theme.font_family
        p_img.font.size = Pt(14)
        p_img.font.bold = True
        p_img.font.color.rgb = self.theme.inverse

        # Right: Narrative Content Card
        rx, ry, rw, rh = cols[1]
        add_card(slide, rx, ry, rw, rh, self.theme)
        tbox = add_text_box(slide, rx + 0.4, ry + 0.4, rw - 0.8, rh - 0.8)
        tf = tbox.text_frame
        p_head = tf.paragraphs[0]
        p_head.text = "Key Observations"
        p_head.font.name = self.theme.font_family
        p_head.font.size = Pt(20)
        p_head.font.bold = True
        p_head.font.color.rgb = self.theme.heading

        if paragraph:
            p_p = tf.add_paragraph()
            p_p.space_before = Pt(8)
            p_p.text = paragraph
            p_p.font.name = self.theme.font_family
            p_p.font.size = Pt(self.theme.body_size)
            p_p.font.color.rgb = self.theme.body

        for b in (bullets or ["Structured descriptive takeaway point 1", "Structured descriptive takeaway point 2"]):
            p_b = tf.add_paragraph()
            p_b.space_before = Pt(8)
            p_b.text = f"•  {b}"
            p_b.font.name = self.theme.font_family
            p_b.font.size = Pt(self.theme.bullet_size)
            p_b.font.color.rgb = self.theme.body

        add_footer(slide, self.theme, left_text=caption)
        return slide

    # 12. Chart Slide
    def add_chart(
        self,
        prs: Presentation,
        title: str = "Performance Analytics Distribution",
        subtitle: Optional[str] = "Statistical Trend Visualization",
        takeaways: Optional[List[str]] = None,
    ) -> Any:
        slide = add_blank_slide(prs)
        add_solid_background(slide, self.theme.surface)
        add_header(slide, title, subtitle, self.theme)

        cols = GEOMETRY.get_column_rects(2, gap=0.5)

        # Left: Chart visual container with mock bar shapes
        cx, cy, cw, ch = cols[0]
        add_card(slide, cx, cy, cw, ch, self.theme, border_color=self.theme.primary, border_width=1.5)

        bar_w = (cw - 1.2) / 4
        bar_heights = [1.8, 3.4, 2.5, 4.2]
        for i, bh in enumerate(bar_heights):
            bx = cx + 0.6 + i * (bar_w + 0.15)
            by = cy + ch - 0.6 - bh
            bar = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE, Inches(bx), Inches(by), Inches(bar_w), Inches(bh)
            )
            bar.fill.solid()
            bar.fill.fore_color.rgb = self.theme.primary if i % 2 == 0 else self.theme.secondary
            bar.line.fill.background()

        # Right: Analytical Takeaways
        rx, ry, rw, rh = cols[1]
        add_card(slide, rx, ry, rw, rh, self.theme)
        tbox = add_text_box(slide, rx + 0.4, ry + 0.4, rw - 0.8, rh - 0.8)
        tf = tbox.text_frame
        p_t = tf.paragraphs[0]
        p_t.text = "Analytical Highlights"
        p_t.font.name = self.theme.font_family
        p_t.font.size = Pt(20)
        p_t.font.bold = True
        p_t.font.color.rgb = self.theme.heading

        items = takeaways or [
            "Consistent 45% reduction in compilation overhead",
            "Linear throughput scaling across concurrent requests",
            "Optimal cache utilization with zero memory leaks",
        ]
        for item in items:
            p_it = tf.add_paragraph()
            p_it.space_before = Pt(12)
            p_it.text = f"•  {item}"
            p_it.font.name = self.theme.font_family
            p_it.font.size = Pt(self.theme.bullet_size)
            p_it.font.color.rgb = self.theme.body

        add_footer(slide, self.theme)
        return slide

    # 13. Table Slide
    def add_table(
        self,
        prs: Presentation,
        title: str = "Component Specification & Metrics",
        subtitle: Optional[str] = "Tabular Data Inventory",
        headers: Optional[List[str]] = None,
        rows: Optional[List[List[str]]] = None,
    ) -> Any:
        slide = add_blank_slide(prs)
        add_solid_background(slide, self.theme.surface)
        add_header(slide, title, subtitle, self.theme)

        table_headers = headers or ["Module", "Responsibility", "Status"]
        table_rows = rows or [
            ["GeometryConfig", "16:9 safe margin & coordinate calculation", "Verified"],
            ["ThemeConfig", "Single source of truth for styling & contrast", "Active"],
            ["LayoutResolver", "Automated content-to-slide mapping", "Production"],
            ["PPTBuilder", "Deterministic blank-slide shape renderer", "Deployed"],
        ]

        add_card(
            slide,
            GEOMETRY.MARGIN_X,
            GEOMETRY.CONTENT_TOP,
            GEOMETRY.content_width,
            GEOMETRY.content_height,
            self.theme,
        )

        num_rows = len(table_rows) + 1
        num_cols = len(table_headers)
        table_shape = slide.shapes.add_table(
            num_rows,
            num_cols,
            Inches(GEOMETRY.MARGIN_X + 0.4),
            Inches(GEOMETRY.CONTENT_TOP + 0.4),
            Inches(GEOMETRY.content_width - 0.8),
            Inches(GEOMETRY.content_height - 0.8),
        )
        table = table_shape.table

        # Format Header Cells
        for c_idx, head in enumerate(table_headers):
            cell = table.cell(0, c_idx)
            cell.fill.solid()
            cell.fill.fore_color.rgb = self.theme.primary
            p = cell.text_frame.paragraphs[0]
            p.text = head
            p.font.name = self.theme.font_family
            p.font.bold = True
            p.font.size = Pt(14)
            p.font.color.rgb = self.theme.inverse

        # Format Data Rows
        for r_idx, row_data in enumerate(table_rows):
            for c_idx, val in enumerate(row_data):
                cell = table.cell(r_idx + 1, c_idx)
                cell.fill.solid()
                cell.fill.fore_color.rgb = self.theme.card if r_idx % 2 == 0 else self.theme.surface
                p = cell.text_frame.paragraphs[0]
                p.text = str(val)
                p.font.name = self.theme.font_family
                p.font.size = Pt(13)
                p.font.color.rgb = self.theme.body

        add_footer(slide, self.theme)
        return slide

    # 14. Mixed Content Slide
    def add_mixed_content(
        self,
        prs: Presentation,
        title: str = "Mixed Content Integration",
        subtitle: Optional[str] = "Multi-Modal Overview & Key Highlights",
        overview: Optional[str] = "This multi-modal layout seamlessly integrates conceptual prose with high-impact categorical bullet points and structured takeaways.",
        bullets: Optional[List[str]] = None,
    ) -> Any:
        slide = add_blank_slide(prs)
        add_solid_background(slide, self.theme.surface)
        add_header(slide, title, subtitle, self.theme)

        cols = GEOMETRY.get_column_rects(2, gap=0.5)

        # Left Overview Card
        lx, ly, lw, lh = cols[0]
        add_card(slide, lx, ly, lw, lh, self.theme, border_color=self.theme.primary, border_width=1.5)
        tbox_l = add_text_box(slide, lx + 0.4, ly + 0.4, lw - 0.8, lh - 0.8)
        tf_l = tbox_l.text_frame
        p_lh = tf_l.paragraphs[0]
        p_lh.text = "Strategic Synthesis"
        p_lh.font.name = self.theme.font_family
        p_lh.font.size = Pt(20)
        p_lh.font.bold = True
        p_lh.font.color.rgb = self.theme.primary

        p_lp = tf_l.add_paragraph()
        p_lp.space_before = Pt(12)
        p_lp.text = overview or "Detailed conceptual synthesis articulating architectural advantages."
        p_lp.font.name = self.theme.font_family
        p_lp.font.size = Pt(self.theme.body_size)
        p_lp.font.color.rgb = self.theme.body

        # Right Action Items Card
        rx, ry, rw, rh = cols[1]
        add_card(slide, rx, ry, rw, rh, self.theme)
        tbox_r = add_text_box(slide, rx + 0.4, ry + 0.4, rw - 0.8, rh - 0.8)
        tf_r = tbox_r.text_frame
        p_rh = tf_r.paragraphs[0]
        p_rh.text = "Actionable Deliverables"
        p_rh.font.name = self.theme.font_family
        p_rh.font.size = Pt(20)
        p_rh.font.bold = True
        p_rh.font.color.rgb = self.theme.heading

        items = bullets or [
            "Deterministic coordinate bounding checks on all rendered elements",
            "Universal compatibility with Microsoft PowerPoint and LibreOffice",
            "Flexible data-driven layout resolution for AI generation pipelines",
        ]
        for it in items:
            p_b = tf_r.add_paragraph()
            p_b.space_before = Pt(10)
            p_b.text = f"•  {it}"
            p_b.font.name = self.theme.font_family
            p_b.font.size = Pt(self.theme.bullet_size)
            p_b.font.color.rgb = self.theme.body

        add_footer(slide, self.theme)
        return slide

    def render_slide_from_data(self, prs: Presentation, slide_data: Dict[str, Any]) -> Any:
        """Dynamically renders a slide from arbitrary structured input data."""
        layout_type = LayoutResolver.resolve_layout(slide_data)
        title = slide_data.get("title", "Slide Title")
        subtitle = slide_data.get("subtitle")

        logger.info(f"Rendering slide '{title}' with resolved layout '{layout_type}'")

        if layout_type == "cover":
            return self.add_cover(
                prs,
                title=title,
                subtitle=subtitle,
                badge_text=slide_data.get("badge", "MOTHER AI"),
                footer_text=slide_data.get("footer", "MOTHER AI Presentation Engine"),
            )
        elif layout_type == "two_column":
            return self.add_two_column(
                prs,
                title=title,
                subtitle=subtitle,
                left_card=slide_data.get("left_column") or slide_data.get("left_card"),
                right_card=slide_data.get("right_column") or slide_data.get("right_card"),
            )
        elif layout_type == "three_column":
            return self.add_three_column(
                prs, title=title, subtitle=subtitle, cards=slide_data.get("cards") or slide_data.get("features")
            )
        elif layout_type == "section":
            return self.add_section(
                prs,
                section_title=title,
                section_subtitle=subtitle,
                section_number=slide_data.get("section_number", "01"),
            )
        elif layout_type == "quote":
            return self.add_quote(
                prs,
                quote_text=slide_data.get("quote") or title,
                author=slide_data.get("author", "Author"),
                source=slide_data.get("source", "Source"),
            )
        elif layout_type == "statistics":
            return self.add_statistics(
                prs,
                title=title,
                subtitle=subtitle,
                metrics=slide_data.get("metrics") or slide_data.get("stats") or slide_data.get("kpis"),
            )
        elif layout_type == "timeline":
            return self.add_timeline(
                prs,
                title=title,
                subtitle=subtitle,
                milestones=slide_data.get("milestones") or slide_data.get("timeline"),
            )
        elif layout_type == "process":
            return self.add_process(
                prs,
                title=title,
                subtitle=subtitle,
                steps=slide_data.get("steps") or slide_data.get("process_steps"),
            )
        elif layout_type == "image_text":
            return self.add_image_text(
                prs,
                title=title,
                subtitle=subtitle,
                paragraph=slide_data.get("paragraph") or slide_data.get("body"),
                bullets=slide_data.get("bullets") or slide_data.get("items"),
                caption=slide_data.get("caption", "Contextual Visual Asset"),
            )
        elif layout_type == "chart":
            return self.add_chart(
                prs, title=title, subtitle=subtitle, takeaways=slide_data.get("takeaways") or slide_data.get("bullets")
            )
        elif layout_type == "table":
            return self.add_table(
                prs,
                title=title,
                subtitle=subtitle,
                headers=slide_data.get("headers"),
                rows=slide_data.get("rows"),
            )
        elif layout_type == "mixed_content":
            return self.add_mixed_content(
                prs,
                title=title,
                subtitle=subtitle,
                overview=slide_data.get("paragraph") or slide_data.get("overview"),
                bullets=slide_data.get("bullets") or slide_data.get("items"),
            )
        else:
            return self.add_title_content(
                prs,
                title=title,
                subtitle=subtitle,
                paragraph=slide_data.get("paragraph") or slide_data.get("body"),
                bullets=slide_data.get("bullets") or slide_data.get("items"),
            )

    def build_master_template(self, output_path: Union[str, Path]) -> str:
        """Generates a complete, verified master template presentation containing all 14 layouts."""
        out_file = Path(output_path).resolve()
        out_file.parent.mkdir(parents=True, exist_ok=True)

        prs = self.create_presentation()

        # Build all 14 clean master slide layouts
        self.add_cover(prs)
        self.add_title_content(prs)
        self.add_two_column(prs)
        self.add_three_column(prs)
        self.add_section(prs)
        self.add_quote(prs)
        self.add_statistics(prs)
        self.add_comparison(prs)
        self.add_timeline(prs)
        self.add_process(prs)
        self.add_image_text(prs)
        self.add_chart(prs)
        self.add_table(prs)
        self.add_mixed_content(prs)

        prs.save(str(out_file))
        logger.info(f"Successfully generated master template at '{out_file}' ({len(prs.slides)} layouts)")
        return str(out_file)


# -----------------------------------------------------------------------------
# 7. Public API Function
# -----------------------------------------------------------------------------
def create_master_template(output_path: str = "./templates/base_template.pptx") -> str:
    """Generates a professional 16:9 widescreen Master PowerPoint Template (.pptx).

    Preserves public API compatibility and produces clean blank-layout slides.
    """
    builder = PPTBuilder()
    return builder.build_master_template(output_path)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    out_path = sys.argv[1] if len(sys.argv) > 1 else "./templates/base_template.pptx"
    created_path = create_master_template(out_path)
    print(f"[SUCCESS] Created Master PPT Template at: {created_path}")
