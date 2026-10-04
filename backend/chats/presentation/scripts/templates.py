from __future__ import annotations

import collections
import collections.abc
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Forward compatibility fix for python-pptx / collections on Python 3.10+
for name in ("Container", "Mapping", "MutableMapping", "Sequence", "MutableSequence", "Iterable", "Callable"):
    if not hasattr(collections, name) and hasattr(collections.abc, name):
        setattr(collections, name, getattr(collections.abc, name))

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE


# -----------------------------------------------------------------------------
# 1. Color Utilities & Contrast Helper
# -----------------------------------------------------------------------------
def to_rgb(color_val: Any, default: RGBColor = RGBColor(15, 23, 42)) -> RGBColor:
    """Converts hex, tuple, or RGBColor to a valid pptx RGBColor instance."""
    if isinstance(color_val, RGBColor):
        return color_val
    if isinstance(color_val, (tuple, list)) and len(color_val) >= 3:
        return RGBColor(int(color_val[0]), int(color_val[1]), int(color_val[2]))
    if isinstance(color_val, str) and color_val.startswith("#") and len(color_val) in (7, 4):
        hex_s = color_val.lstrip("#")
        if len(hex_s) == 3:
            hex_s = "".join([c * 2 for c in hex_s])
        return RGBColor(int(hex_s[0:2], 16), int(hex_s[2:4], 16), int(hex_s[4:6], 16))
    return default


def to_hex_str(color_val: Any, default: str = "#0f172a") -> str:
    """Converts RGBColor, tuple, or hex string to normalized #rrggbb string."""
    if isinstance(color_val, RGBColor):
        return f"#{color_val[0]:02x}{color_val[1]:02x}{color_val[2]:02x}"
    if isinstance(color_val, (tuple, list)) and len(color_val) >= 3:
        return f"#{color_val[0]:02x}{color_val[1]:02x}{color_val[2]:02x}"
    if isinstance(color_val, str) and color_val.startswith("#"):
        return color_val
    return default


def is_light_rgb(color_val: Any) -> bool:
    """Computes perceptual luminance (ITU-R BT.601) to check if a color is light."""
    rgb = to_rgb(color_val)
    lum = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    return lum > 145


# -----------------------------------------------------------------------------
# 2. Theme Configuration Model
# -----------------------------------------------------------------------------
@dataclass
class ThemeConfig:
    id: str = "base_template"
    name: str = "Default Slate Teal"
    style_type: str = "modern"
    bg: RGBColor = field(default_factory=lambda: RGBColor(15, 23, 42))
    main_bg: RGBColor = field(default_factory=lambda: RGBColor(15, 23, 42))
    accent: RGBColor = field(default_factory=lambda: RGBColor(13, 148, 136))
    accent_sec: RGBColor = field(default_factory=lambda: RGBColor(99, 102, 241))
    card_bg: RGBColor = field(default_factory=lambda: RGBColor(248, 250, 252))
    card_border: RGBColor = field(default_factory=lambda: RGBColor(226, 232, 240))
    text_dark: RGBColor = field(default_factory=lambda: RGBColor(15, 23, 42))
    text_light: RGBColor = field(default_factory=lambda: RGBColor(255, 255, 255))
    text_muted: RGBColor = field(default_factory=lambda: RGBColor(148, 163, 184))
    sidebar_w: float = 2.5
    font_title: str = "Arial"
    font_body: str = "Calibri"

    def is_bg_light(self) -> bool:
        return is_light_rgb(self.bg)

    def is_main_bg_light(self) -> bool:
        return is_light_rgb(self.main_bg)

    def is_card_bg_light(self) -> bool:
        return is_light_rgb(self.card_bg)

    def get_text_for_bg(self, bg_color: RGBColor) -> RGBColor:
        return self.text_dark if is_light_rgb(bg_color) else self.text_light

    def get_card_text_primary(self) -> RGBColor:
        return self.text_dark if self.is_card_bg_light() else self.text_light

    def get_main_text_primary(self) -> RGBColor:
        return self.text_dark if self.is_main_bg_light() else self.text_light

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "style_type": self.style_type,
            "bg": self.bg,
            "main_bg": self.main_bg,
            "accent": self.accent,
            "accent_sec": self.accent_sec,
            "card_bg": self.card_bg,
            "card_border": self.card_border,
            "text_dark": self.text_dark,
            "text_light": self.text_light,
            "text_muted": self.text_muted,
            "sidebar_w": self.sidebar_w,
            "font_title": self.font_title,
            "font_body": self.font_body,
        }

    @classmethod
    def from_dict(cls, key: str, data: dict[str, Any]) -> ThemeConfig:
        bg = to_rgb(data.get("bg", RGBColor(15, 23, 42)))
        main_bg = to_rgb(data.get("main_bg", bg))
        accent = to_rgb(data.get("accent", RGBColor(13, 148, 136)))
        accent_sec = to_rgb(data.get("accent_sec", RGBColor(99, 102, 241)))
        card_bg = to_rgb(data.get("card_bg", RGBColor(248, 250, 252)))
        card_border = to_rgb(data.get("card_border", accent))
        text_dark = to_rgb(data.get("text_dark", RGBColor(15, 23, 42)))
        text_light = to_rgb(data.get("text_light", RGBColor(255, 255, 255)))
        text_muted = to_rgb(data.get("text_muted", RGBColor(148, 163, 184)))

        return cls(
            id=key,
            name=data.get("name", key.replace("_", " ").title()),
            style_type=data.get("style_type", "modern"),
            bg=bg,
            main_bg=main_bg,
            accent=accent,
            accent_sec=accent_sec,
            card_bg=card_bg,
            card_border=card_border,
            text_dark=text_dark,
            text_light=text_light,
            text_muted=text_muted,
            sidebar_w=float(data.get("sidebar_w", 2.5)),
            font_title=str(data.get("font_title", "Arial")),
            font_body=str(data.get("font_body", "Calibri")),
        )


# -----------------------------------------------------------------------------
# 3. Geometry & Layout System (16:9 Widescreen)
# -----------------------------------------------------------------------------
class GeometrySystem:
    SLIDE_WIDTH_INCHES: float = 13.333
    SLIDE_HEIGHT_INCHES: float = 7.5

    MARGIN_LEFT: float = 0.8
    MARGIN_RIGHT: float = 0.8
    MARGIN_TOP: float = 0.6
    MARGIN_BOTTOM: float = 0.6

    @classmethod
    def get_content_rect(cls, style_type: str = "modern", sidebar_w: float = 2.5) -> Tuple[float, float, float, float]:
        """Returns (left, top, width, height) in inches for the main slide content area."""
        if style_type == "sidebar":
            left = sidebar_w + 0.4
            top = 1.3
            width = cls.SLIDE_WIDTH_INCHES - left - cls.MARGIN_RIGHT
            height = 5.6
        else:
            left = cls.MARGIN_LEFT
            top = 1.3
            width = cls.SLIDE_WIDTH_INCHES - cls.MARGIN_LEFT - cls.MARGIN_RIGHT
            height = 5.6
        return (left, top, width, height)

    @classmethod
    def get_column_rects(
        cls,
        count: int,
        y: float = 1.4,
        h: float = 5.3,
        gap: float = 0.4,
        style_type: str = "modern",
        sidebar_w: float = 2.5,
    ) -> List[Tuple[float, float, float, float]]:
        """Calculates perfectly distributed column bounding boxes within safe margins."""
        start_x = (sidebar_w + 0.4) if style_type == "sidebar" else cls.MARGIN_LEFT
        avail_w = (cls.SLIDE_WIDTH_INCHES - start_x - cls.MARGIN_RIGHT)
        col_w = (avail_w - (count - 1) * gap) / max(1, count)

        cols = []
        for i in range(count):
            col_x = start_x + i * (col_w + gap)
            cols.append((col_x, y, col_w, h))
        return cols

    @classmethod
    def validate_bounds(cls, left: float, top: float, width: float, height: float) -> bool:
        """Validates that a bounding box remains safely inside the slide canvas."""
        if left < 0 or top < 0:
            return False
        if (left + width) > (cls.SLIDE_WIDTH_INCHES + 0.05):
            return False
        if (top + height) > (cls.SLIDE_HEIGHT_INCHES + 0.05):
            return False
        return True


def validate_layout(left: float, top: float, width: float, height: float) -> bool:
    """Public helper to validate coordinate boundaries."""
    return GeometrySystem.validate_bounds(left, top, width, height)


# -----------------------------------------------------------------------------
# 4. Typography System
# -----------------------------------------------------------------------------
class TypographySystem:
    COVER_TITLE_SIZE = Pt(44)
    COVER_SUBTITLE_SIZE = Pt(20)
    SECTION_TITLE_SIZE = Pt(38)
    SLIDE_TITLE_SIZE = Pt(28)
    SLIDE_SUBTITLE_SIZE = Pt(13)
    BODY_SIZE = Pt(16)
    CARD_TITLE_SIZE = Pt(18)
    CARD_BODY_SIZE = Pt(14)
    STAT_VALUE_SIZE = Pt(48)
    STAT_LABEL_SIZE = Pt(15)
    BADGE_SIZE = Pt(11)
    FOOTER_SIZE = Pt(10)

    @classmethod
    def apply_title(
        cls,
        p: Any,
        text: str,
        theme: ThemeConfig,
        color: Optional[RGBColor] = None,
        size: Pt = SLIDE_TITLE_SIZE,
        bold: bool = True,
        align: PP_ALIGN = PP_ALIGN.LEFT,
    ) -> None:
        p.text = text
        p.alignment = align
        p.font.name = theme.font_title
        p.font.size = size
        p.font.bold = bold
        p.font.color.rgb = color or theme.get_main_text_primary()

    @classmethod
    def apply_subtitle(
        cls,
        p: Any,
        text: str,
        theme: ThemeConfig,
        color: Optional[RGBColor] = None,
        size: Pt = SLIDE_SUBTITLE_SIZE,
        align: PP_ALIGN = PP_ALIGN.LEFT,
    ) -> None:
        p.text = text
        p.alignment = align
        p.font.name = theme.font_body
        p.font.size = size
        p.font.bold = False
        p.font.color.rgb = color or theme.text_muted

    @classmethod
    def apply_body(
        cls,
        p: Any,
        text: str,
        theme: ThemeConfig,
        color: Optional[RGBColor] = None,
        size: Pt = BODY_SIZE,
        bold: bool = False,
    ) -> None:
        p.text = text
        p.font.name = theme.font_body
        p.font.size = size
        p.font.bold = bold
        p.font.color.rgb = color or theme.get_card_text_primary()

    @classmethod
    def apply_bullet(
        cls,
        p: Any,
        text: str,
        theme: ThemeConfig,
        color: Optional[RGBColor] = None,
        size: Pt = CARD_BODY_SIZE,
        level: int = 0,
    ) -> None:
        p.text = text
        p.level = level
        p.font.name = theme.font_body
        p.font.size = size
        p.font.color.rgb = color or theme.get_card_text_primary()


# -----------------------------------------------------------------------------
# 5. 16 Distinct Template Archetypes & Presets Registry
# -----------------------------------------------------------------------------
TEMPLATE_ARCHETYPES: dict[str, dict[str, Any]] = {
    # 1. Ion Boardroom - Deep Purple/Magenta Gradient with Accent Tag
    "ion_boardroom": {
        "name": "Ion Boardroom",
        "style_type": "ion",
        "bg": RGBColor(30, 27, 75),           # Deep Midnight Indigo
        "main_bg": RGBColor(15, 23, 42),       # Dark Slate Canvas
        "accent": RGBColor(236, 72, 153),      # Vibrant Magenta Pill
        "accent_sec": RGBColor(168, 85, 247),  # Purple Neon
        "card_bg": RGBColor(30, 27, 75),
        "card_border": RGBColor(236, 72, 153),
        "text_dark": RGBColor(255, 255, 255),
        "text_light": RGBColor(255, 255, 255),
    },

    # 2. Berlin Executive - Burnt Orange & Charcoal Slate
    "berlin_executive": {
        "name": "Berlin Executive",
        "style_type": "berlin",
        "bg": RGBColor(234, 88, 12),          # Burnt Orange Header
        "main_bg": RGBColor(248, 250, 252),   # Off-White Body
        "accent": RGBColor(30, 41, 59),        # Charcoal Slate Center Bar
        "accent_sec": RGBColor(234, 88, 12),
        "card_bg": RGBColor(255, 255, 255),
        "card_border": RGBColor(226, 232, 240),
        "text_dark": RGBColor(15, 23, 42),
        "text_light": RGBColor(255, 255, 255),
    },

    # 3. Quotable - Cyan & Charcoal Dual Block
    "quotable_teal": {
        "name": "Quotable Teal & Black",
        "style_type": "quotable",
        "bg": RGBColor(13, 148, 136),         # Cyan Teal Top Block
        "main_bg": RGBColor(15, 23, 42),      # Dark Slate Bottom Canvas
        "accent": RGBColor(20, 184, 166),     # Teal Accent
        "accent_sec": RGBColor(255, 255, 255),
        "card_bg": RGBColor(30, 41, 59),
        "card_border": RGBColor(20, 184, 166),
        "text_dark": RGBColor(15, 23, 42),
        "text_light": RGBColor(255, 255, 255),
    },

    # 4. Geometric Color Block - Arch Curves & Pastel Block
    "geometric_block": {
        "name": "Geometric Color Block",
        "style_type": "geometric",
        "bg": RGBColor(243, 232, 255),        # Soft Pastel Lavender
        "main_bg": RGBColor(243, 232, 255),
        "accent": RGBColor(29, 78, 216),       # Royal Blue Arch Block
        "accent_sec": RGBColor(126, 34, 206),  # Deep Purple Arch Block
        "card_bg": RGBColor(255, 255, 255),
        "card_border": RGBColor(221, 214, 254),
        "text_dark": RGBColor(15, 23, 42),
        "text_light": RGBColor(255, 255, 255),
    },

    # 5. Urban Monochrome - Charcoal & Slate Architectural Grid
    "urban_monochrome": {
        "name": "Urban Monochrome",
        "style_type": "urban",
        "bg": RGBColor(15, 23, 42),           # Slate Dark
        "main_bg": RGBColor(15, 23, 42),
        "accent": RGBColor(56, 189, 248),      # Cyan Sky Line Accent
        "accent_sec": RGBColor(148, 163, 184), # Cool Gray
        "card_bg": RGBColor(30, 41, 59),
        "card_border": RGBColor(56, 189, 248),
        "text_dark": RGBColor(255, 255, 255),
        "text_light": RGBColor(255, 255, 255),
    },

    # 6. Crop Frame - Corner Brackets & Beige Sand
    "crop_frame": {
        "name": "Crop Bracket Minimal",
        "style_type": "crop",
        "bg": RGBColor(254, 243, 199),        # Cream / Warm Sand
        "main_bg": RGBColor(254, 243, 199),
        "accent": RGBColor(24, 24, 27),        # Deep Charcoal Corner Brackets
        "accent_sec": RGBColor(120, 53, 15),
        "card_bg": RGBColor(255, 255, 255),
        "card_border": RGBColor(24, 24, 27),
        "text_dark": RGBColor(24, 24, 27),
        "text_light": RGBColor(255, 255, 255),
    },

    # 7. Circuit Tech - Electric Cyan & Blue Mesh
    "circuit_tech": {
        "name": "Circuit Tech Cyber",
        "style_type": "circuit",
        "bg": RGBColor(3, 105, 161),          # Ocean Electric Blue
        "main_bg": RGBColor(15, 23, 42),      # Dark Blue Canvas
        "accent": RGBColor(6, 182, 212),      # Cyan Tech Circuit Line
        "accent_sec": RGBColor(56, 189, 248),
        "card_bg": RGBColor(15, 23, 42),
        "card_border": RGBColor(6, 182, 212),
        "text_dark": RGBColor(255, 255, 255),
        "text_light": RGBColor(255, 255, 255),
    },

    # 8. Celestial Night - Deep Space Indigo & Ring Radar
    "celestial_night": {
        "name": "Celestial Night",
        "style_type": "celestial",
        "bg": RGBColor(15, 23, 42),           # Deep Space Navy
        "main_bg": RGBColor(15, 23, 42),
        "accent": RGBColor(129, 140, 248),     # Indigo Glowing Ring
        "accent_sec": RGBColor(192, 132, 252), # Purple Glow
        "card_bg": RGBColor(30, 27, 75),
        "card_border": RGBColor(129, 140, 248),
        "text_dark": RGBColor(255, 255, 255),
        "text_light": RGBColor(255, 255, 255),
    },

    # 9. Artistic Neon - Orange & Dark Canvas Asymmetric Split
    "artistic_neon": {
        "name": "Artistic Neon",
        "style_type": "artistic",
        "bg": RGBColor(249, 115, 22),         # Neon Orange Left Block
        "main_bg": RGBColor(24, 24, 27),      # Dark Charcoal Right Canvas
        "accent": RGBColor(249, 115, 22),
        "accent_sec": RGBColor(244, 63, 94),
        "card_bg": RGBColor(39, 39, 42),
        "card_border": RGBColor(249, 115, 22),
        "text_dark": RGBColor(255, 255, 255),
        "text_light": RGBColor(255, 255, 255),
    },

    # 10. Atlas Crimson - Solid Red Callout Banner on White
    "atlas_bold": {
        "name": "Atlas Crimson Banner",
        "style_type": "atlas",
        "bg": RGBColor(220, 38, 38),          # Crimson Red Floating Banner
        "main_bg": RGBColor(250, 250, 250),   # Off-White Subtle Grid
        "accent": RGBColor(220, 38, 38),
        "accent_sec": RGBColor(185, 28, 28),
        "card_bg": RGBColor(255, 255, 255),
        "card_border": RGBColor(220, 38, 38),
        "text_dark": RGBColor(15, 23, 42),
        "text_light": RGBColor(255, 255, 255),
    },

    # 11. Organic Pastel - Earthy Taupe with Fluid Blobs
    "organic_pastel": {
        "name": "Organic Earthy Pastel",
        "style_type": "organic",
        "bg": RGBColor(245, 245, 244),        # Warm Stone Beige
        "main_bg": RGBColor(245, 245, 244),
        "accent": RGBColor(168, 162, 158),    # Taupe Organic Blob
        "accent_sec": RGBColor(194, 65, 12),   # Muted Clay Accent
        "card_bg": RGBColor(255, 255, 255),
        "card_border": RGBColor(214, 211, 209),
        "text_dark": RGBColor(41, 37, 36),
        "text_light": RGBColor(255, 255, 255),
    },

    # 12. Dividend Burgundy - White Header with Burgundy Footer Block
    "dividend_burgundy": {
        "name": "Dividend Burgundy Block",
        "style_type": "dividend",
        "bg": RGBColor(76, 5, 25),            # Deep Burgundy Footer Block
        "main_bg": RGBColor(248, 250, 252),   # Clean Slate Canvas
        "accent": RGBColor(76, 5, 25),
        "accent_sec": RGBColor(159, 18, 57),
        "card_bg": RGBColor(255, 255, 255),
        "card_border": RGBColor(226, 232, 240),
        "text_dark": RGBColor(15, 23, 42),
        "text_light": RGBColor(255, 255, 255),
    },

    # 13. Savon Classic - Mint Patterned Card with Paperclip Tab
    "savon_classic": {
        "name": "Savon Classic Card",
        "style_type": "savon",
        "bg": RGBColor(204, 251, 241),        # Light Mint Soft Background
        "main_bg": RGBColor(204, 251, 241),
        "accent": RGBColor(13, 148, 136),      # Mint Teal Tab Accent
        "accent_sec": RGBColor(45, 212, 191),
        "card_bg": RGBColor(255, 255, 255),
        "card_border": RGBColor(153, 246, 228),
        "text_dark": RGBColor(19, 78, 74),
        "text_light": RGBColor(255, 255, 255),
    },

    # 14. Wood Type Vintage - Timber & Stamp Badge
    "wood_type": {
        "name": "Wood Type Vintage",
        "style_type": "wood",
        "bg": RGBColor(69, 26, 3),            # Deep Timber Brown
        "main_bg": RGBColor(255, 251, 235),   # Muted Parchment Canvas
        "accent": RGBColor(180, 83, 9),        # Warm Amber Seal Stamp
        "accent_sec": RGBColor(120, 53, 15),
        "card_bg": RGBColor(255, 255, 255),
        "card_border": RGBColor(252, 211, 77),
        "text_dark": RGBColor(69, 26, 3),
        "text_light": RGBColor(255, 255, 255),
    },

    # 15. Sidebar Executive - Royal Navy Rail & Off-White Card
    "sidebar_executive": {
        "name": "Executive Sidebar Rail",
        "style_type": "sidebar",
        "bg": RGBColor(15, 23, 42),           # Dark Navy Sidebar
        "main_bg": RGBColor(248, 250, 252),   # Off-White Main Canvas
        "accent": RGBColor(37, 99, 235),       # Royal Blue
        "accent_sec": RGBColor(13, 148, 136),  # Teal
        "sidebar_w": 2.5,
        "card_bg": RGBColor(255, 255, 255),
        "card_border": RGBColor(226, 232, 240),
        "text_dark": RGBColor(15, 23, 42),
        "text_light": RGBColor(255, 255, 255),
    },

    # 16. Modern Glassmorphism - Glowing Purple & Cyan Neon on Dark Zinc
    "modern_glassmorphism": {
        "name": "Modern Dark Glassmorphism",
        "style_type": "glassmorphism",
        "bg": RGBColor(9, 9, 11),             # Zinc 950
        "main_bg": RGBColor(9, 9, 11),
        "accent": RGBColor(168, 85, 247),      # Purple Neon
        "accent_sec": RGBColor(6, 182, 212),   # Cyan Neon
        "card_bg": RGBColor(24, 24, 27),
        "card_border": RGBColor(168, 85, 247), # Glowing Purple Border
        "text_dark": RGBColor(255, 255, 255),
        "text_light": RGBColor(255, 255, 255),
    },
}

TEMPLATE_PRESETS: dict[str, dict[str, Any]] = {
    "base_template": {
        "name": "Default Slate Teal",
        "style_type": "modern",
        "bg": RGBColor(15, 23, 42),          # Dark Slate
        "accent": RGBColor(13, 148, 136),      # Teal
        "accent_sec": RGBColor(99, 102, 241),  # Indigo
        "card_bg": RGBColor(248, 250, 252),
        "card_border": RGBColor(226, 232, 240),
        "text_dark": RGBColor(15, 23, 42),
        "text_muted": RGBColor(100, 116, 139),
        "text_light": RGBColor(241, 245, 249),
    },
    "corporate_light": {
        "name": "Corporate Light Blue",
        "style_type": "modern",
        "bg": RGBColor(255, 255, 255),       # White
        "accent": RGBColor(37, 99, 235),       # Blue 600
        "accent_sec": RGBColor(2, 132, 199),   # Sky 600
        "card_bg": RGBColor(241, 245, 249),    # Slate 100
        "card_border": RGBColor(203, 213, 225),
        "text_dark": RGBColor(15, 23, 42),
        "text_muted": RGBColor(71, 85, 105),
        "text_light": RGBColor(255, 255, 255),
    },
    "modern_dark": {
        "name": "Modern Minimalist Dark",
        "style_type": "modern",
        "bg": RGBColor(24, 24, 27),          # Zinc 900
        "accent": RGBColor(168, 85, 247),      # Purple 500
        "accent_sec": RGBColor(236, 72, 153),  # Pink 500
        "card_bg": RGBColor(39, 39, 42),      # Zinc 800
        "card_border": RGBColor(63, 63, 70),
        "text_dark": RGBColor(255, 255, 255),
        "text_muted": RGBColor(161, 161, 170),
        "text_light": RGBColor(255, 255, 255),
    },
    "emerald_nature": {
        "name": "Emerald Eco & Sustainability",
        "style_type": "modern",
        "bg": RGBColor(2, 44, 34),           # Emerald 950
        "accent": RGBColor(16, 185, 129),     # Emerald 500
        "accent_sec": RGBColor(52, 211, 153),  # Emerald 400
        "card_bg": RGBColor(6, 78, 59),       # Emerald 900
        "card_border": RGBColor(4, 120, 87),
        "text_dark": RGBColor(255, 255, 255),
        "text_muted": RGBColor(167, 243, 208),
        "text_light": RGBColor(240, 253, 244),
    },
    "executive_gold": {
        "name": "Executive Gold Luxury",
        "style_type": "modern",
        "bg": RGBColor(28, 25, 23),          # Stone 900
        "accent": RGBColor(245, 158, 11),      # Amber 500 Gold
        "accent_sec": RGBColor(217, 119, 6),   # Amber 600
        "card_bg": RGBColor(44, 36, 32),
        "card_border": RGBColor(120, 53, 15),
        "text_dark": RGBColor(255, 255, 255),
        "text_muted": RGBColor(217, 119, 6),
        "text_light": RGBColor(254, 243, 199),
    },
    "cyber_neon": {
        "name": "Cyberpunk Neon Tech",
        "style_type": "modern",
        "bg": RGBColor(9, 9, 11),            # Zinc 950
        "accent": RGBColor(244, 63, 94),       # Rose 500 Neon
        "accent_sec": RGBColor(6, 182, 212),   # Cyan 500
        "card_bg": RGBColor(24, 24, 27),
        "card_border": RGBColor(244, 63, 94),
        "text_dark": RGBColor(255, 255, 255),
        "text_muted": RGBColor(161, 161, 170),
        "text_light": RGBColor(255, 255, 255),
    },
    **TEMPLATE_ARCHETYPES,
}


def get_template_preset(preset_key: Optional[str]) -> dict[str, Any]:
    """Retrieves the theme dictionary by key with fallback to empty dict."""
    if not preset_key:
        return {}
    return TEMPLATE_PRESETS.get(preset_key) or TEMPLATE_ARCHETYPES.get(preset_key) or {}


# -----------------------------------------------------------------------------
# 6. Slide Creation & Element Construction Helpers
# -----------------------------------------------------------------------------
def create_presentation() -> Presentation:
    """Initializes a new 16:9 widescreen presentation."""
    prs = Presentation()
    prs.slide_width = Inches(GeometrySystem.SLIDE_WIDTH_INCHES)
    prs.slide_height = Inches(GeometrySystem.SLIDE_HEIGHT_INCHES)
    return prs


def create_blank_slide(prs: Presentation) -> Any:
    """Creates a blank slide layout and removes any default template placeholders."""
    # Find blank layout (usually layout index 6 or layout with least placeholders)
    blank_layout = None
    for layout in prs.slide_layouts:
        if len(layout.placeholders) == 0:
            blank_layout = layout
            break
    if blank_layout is None:
        blank_layout = prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[-1]

    slide = prs.slides.add_slide(blank_layout)

    # Purge any inherited placeholder shapes to ensure 100% full custom control
    for ph in list(slide.placeholders):
        try:
            sp = ph._element
            sp.getparent().remove(sp)
        except Exception:
            pass
    return slide


def add_solid_background(slide: Any, color: RGBColor) -> Any:
    """Creates a full-canvas background rectangle."""
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0),
        Inches(0),
        Inches(GeometrySystem.SLIDE_WIDTH_INCHES),
        Inches(GeometrySystem.SLIDE_HEIGHT_INCHES),
    )
    bg.fill.solid()
    bg.fill.fore_color.rgb = color
    bg.line.fill.background()
    return bg


def add_card(
    slide: Any,
    left: float,
    top: float,
    width: float,
    height: float,
    fill_color: RGBColor,
    border_color: Optional[RGBColor] = None,
    border_width: float = 1.0,
    rounded: bool = True,
) -> Any:
    """Creates a stylized semantic card container."""
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE
    card = slide.shapes.add_shape(
        shape_type, Inches(left), Inches(top), Inches(width), Inches(height)
    )
    card.fill.solid()
    card.fill.fore_color.rgb = fill_color
    if border_color and border_width > 0:
        card.line.color.rgb = border_color
        card.line.width = Pt(border_width)
    else:
        card.line.fill.background()
    return card


def add_text_box(
    slide: Any,
    left: float,
    top: float,
    width: float,
    height: float,
    word_wrap: bool = True,
) -> Any:
    """Creates an absolute positioned text box with zero padding."""
    tbox = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = tbox.text_frame
    tf.word_wrap = word_wrap
    tf.margin_left = Inches(0.08)
    tf.margin_right = Inches(0.08)
    tf.margin_top = Inches(0.05)
    tf.margin_bottom = Inches(0.05)
    return tbox


def add_badge(
    slide: Any,
    left: float,
    top: float,
    width: float,
    height: float,
    text: str,
    bg_color: RGBColor,
    text_color: RGBColor,
) -> Any:
    """Creates a pill badge tag."""
    badge = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height)
    )
    badge.fill.solid()
    badge.fill.fore_color.rgb = bg_color
    badge.line.fill.background()
    tf = badge.text_frame
    tf.word_wrap = False
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.text = text
    p.alignment = PP_ALIGN.CENTER
    p.font.size = TypographySystem.BADGE_SIZE
    p.font.bold = True
    p.font.color.rgb = text_color
    return badge


def add_footer(
    slide: Any,
    theme: ThemeConfig,
    left_text: str = "MOTHER AI Presentation Engine",
    right_text: str = "",
) -> None:
    """Adds a standard discrete footer line and labels."""
    y = 6.9
    h = 0.35
    w = GeometrySystem.SLIDE_WIDTH_INCHES - GeometrySystem.MARGIN_LEFT - GeometrySystem.MARGIN_RIGHT
    tbox = add_text_box(slide, GeometrySystem.MARGIN_LEFT, y, w, h)
    p = tbox.text_frame.paragraphs[0]
    p.text = left_text
    p.font.size = TypographySystem.FOOTER_SIZE
    p.font.color.rgb = theme.text_muted


# -----------------------------------------------------------------------------
# 7. Theme Rendering Strategies
# -----------------------------------------------------------------------------
class BaseThemeRenderer:
    """Base strategy for rendering slides according to theme design specs."""

    def __init__(self, theme: ThemeConfig):
        self.theme = theme

    def render_cover_slide(
        self,
        prs: Presentation,
        title: str,
        subtitle: Optional[str] = None,
        badge: Optional[str] = None,
    ) -> Any:
        slide = create_blank_slide(prs)
        add_solid_background(slide, self.theme.bg)
        self.add_cover_decorations(slide)

        # Main Cover Card / Text
        left, top, w, h = 1.2, 2.0, 10.933, 3.8
        card = add_card(slide, left, top, w, h, self.theme.card_bg, self.theme.card_border, 1.5)

        tbox = add_text_box(slide, left + 0.6, top + 0.6, w - 1.2, 1.8)
        p_title = tbox.text_frame.paragraphs[0]
        TypographySystem.apply_title(
            p_title,
            title or self.theme.name,
            self.theme,
            color=self.theme.get_card_text_primary(),
            size=TypographySystem.COVER_TITLE_SIZE,
            bold=True,
        )

        if subtitle:
            p_sub = tbox.text_frame.add_paragraph()
            p_sub.space_before = Pt(14)
            TypographySystem.apply_subtitle(
                p_sub,
                subtitle,
                self.theme,
                color=self.theme.text_muted,
                size=TypographySystem.COVER_SUBTITLE_SIZE,
            )

        if badge:
            add_badge(
                slide,
                left + 0.6,
                top + h - 0.9,
                1.8,
                0.38,
                badge,
                self.theme.accent,
                self.theme.get_text_for_bg(self.theme.accent),
            )

        return slide

    def render_content_slide(
        self,
        prs: Presentation,
        title: str,
        subtitle: Optional[str] = None,
        body_paragraphs: Optional[List[str]] = None,
        bullets: Optional[List[str]] = None,
        footer_text: Optional[str] = None,
    ) -> Any:
        slide = create_blank_slide(prs)
        add_solid_background(slide, self.theme.main_bg)
        self.add_slide_header(slide, title, subtitle)

        left, top, width, height = GeometrySystem.get_content_rect(
            self.theme.style_type, self.theme.sidebar_w
        )
        card = add_card(
            slide, left, top, width, height, self.theme.card_bg, self.theme.card_border, 1.0
        )

        tbox = add_text_box(slide, left + 0.5, top + 0.4, width - 1.0, height - 0.8)
        tf = tbox.text_frame

        if body_paragraphs:
            for i, para in enumerate(body_paragraphs):
                p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                if i > 0:
                    p.space_before = Pt(12)
                TypographySystem.apply_body(p, para, self.theme)

        if bullets:
            for bullet in bullets:
                p = tf.add_paragraph()
                p.space_before = Pt(8)
                TypographySystem.apply_bullet(p, bullet, self.theme)

        add_footer(slide, self.theme, left_text=footer_text or self.theme.name)
        return slide

    def render_feature_grid_slide(
        self,
        prs: Presentation,
        title: str,
        subtitle: Optional[str] = None,
        items: Optional[List[Dict[str, str]]] = None,
    ) -> Any:
        slide = create_blank_slide(prs)
        add_solid_background(slide, self.theme.main_bg)
        self.add_slide_header(slide, title, subtitle)

        cards_data = items or [
            {"title": "Core Architecture", "body": "High-performance modular slide generator with zero placeholder collisions."},
            {"title": "Adaptive Layouts", "body": "16:9 widescreen coordinate system automatically fitting all device ratios."},
            {"title": "Color Harmony", "body": "Luminance-aware contrast validation ensuring optimal readability across displays."},
        ]

        cols = GeometrySystem.get_column_rects(
            len(cards_data), y=1.5, h=5.1, gap=0.4, style_type=self.theme.style_type, sidebar_w=self.theme.sidebar_w
        )

        for col_rect, data in zip(cols, cards_data):
            cx, cy, cw, ch = col_rect
            add_card(slide, cx, cy, cw, ch, self.theme.card_bg, self.theme.card_border, 1.2)

            # Accent Top Stripe
            accent_bar = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE, Inches(cx), Inches(cy), Inches(cw), Inches(0.08)
            )
            accent_bar.fill.solid()
            accent_bar.fill.fore_color.rgb = self.theme.accent
            accent_bar.line.fill.background()

            tbox = add_text_box(slide, cx + 0.3, cy + 0.3, cw - 0.6, ch - 0.6)
            tf = tbox.text_frame
            p_head = tf.paragraphs[0]
            TypographySystem.apply_title(
                p_head,
                data.get("title", "Feature"),
                self.theme,
                color=self.theme.get_card_text_primary(),
                size=TypographySystem.CARD_TITLE_SIZE,
                bold=True,
            )

            p_body = tf.add_paragraph()
            p_body.space_before = Pt(12)
            TypographySystem.apply_body(
                p_body,
                data.get("body", "Description details go here with complete clarity."),
                self.theme,
                size=TypographySystem.CARD_BODY_SIZE,
            )

        add_footer(slide, self.theme, left_text=self.theme.name)
        return slide

    def render_stat_slide(
        self,
        prs: Presentation,
        title: str,
        subtitle: Optional[str] = None,
        stat_value: str = "99.8%",
        stat_label: str = "Reliability Score",
        description: str = "Comprehensive end-to-end slide rendering pipeline with zero formatting defects.",
        items: Optional[List[str]] = None,
    ) -> Any:
        slide = create_blank_slide(prs)
        add_solid_background(slide, self.theme.main_bg)
        self.add_slide_header(slide, title, subtitle)

        left, top, width, height = GeometrySystem.get_content_rect(
            self.theme.style_type, self.theme.sidebar_w
        )
        add_card(slide, left, top, width, height, self.theme.card_bg, self.theme.accent, 1.8)

        # Big Stat Circle/Badge
        stat_circle = slide.shapes.add_shape(
            MSO_SHAPE.OVAL, Inches(left + 0.8), Inches(top + 0.8), Inches(1.8), Inches(1.8)
        )
        stat_circle.fill.solid()
        stat_circle.fill.fore_color.rgb = self.theme.accent
        stat_circle.line.fill.background()

        # Big Stat Text Box
        tbox_val = add_text_box(slide, left + 2.9, top + 0.8, width - 3.4, 1.0)
        p_val = tbox_val.text_frame.paragraphs[0]
        p_val.text = stat_value
        p_val.font.name = self.theme.font_title
        p_val.font.size = TypographySystem.STAT_VALUE_SIZE
        p_val.font.bold = True
        p_val.font.color.rgb = self.theme.accent

        # Stat Label & Description
        tbox_desc = add_text_box(slide, left + 2.9, top + 1.8, width - 3.4, height - 2.2)
        tf_desc = tbox_desc.text_frame
        p_lbl = tf_desc.paragraphs[0]
        TypographySystem.apply_title(
            p_lbl,
            stat_label,
            self.theme,
            color=self.theme.get_card_text_primary(),
            size=TypographySystem.CARD_TITLE_SIZE,
            bold=True,
        )

        p_det = tf_desc.add_paragraph()
        p_det.space_before = Pt(8)
        TypographySystem.apply_body(p_det, description, self.theme, size=TypographySystem.BODY_SIZE)

        if items:
            for item in items:
                p_it = tf_desc.add_paragraph()
                p_it.space_before = Pt(6)
                TypographySystem.apply_bullet(p_it, item, self.theme)

        add_footer(slide, self.theme, left_text=self.theme.name)
        return slide

    def render_comparison_slide(
        self,
        prs: Presentation,
        title: str,
        subtitle: Optional[str] = None,
        left_card: Optional[Dict[str, Any]] = None,
        right_card: Optional[Dict[str, Any]] = None,
    ) -> Any:
        slide = create_blank_slide(prs)
        add_solid_background(slide, self.theme.main_bg)
        self.add_slide_header(slide, title, subtitle)

        l_data = left_card or {
            "title": "Baseline Option A",
            "items": ["Standard processing throughput", "Default resource utilization", "Manual layout tuning"],
        }
        r_data = right_card or {
            "title": "Optimized Option B",
            "items": ["10x faster batch compilation", "Automated collision avoidance", "Zero placeholder glitches"],
        }

        cols = GeometrySystem.get_column_rects(
            2, y=1.5, h=5.1, gap=0.5, style_type=self.theme.style_type, sidebar_w=self.theme.sidebar_w
        )

        for col_rect, data, is_accent in zip(cols, [l_data, r_data], [False, True]):
            cx, cy, cw, ch = col_rect
            border_color = self.theme.accent if is_accent else self.theme.card_border
            add_card(slide, cx, cy, cw, ch, self.theme.card_bg, border_color, 1.5)

            tbox = add_text_box(slide, cx + 0.4, cy + 0.4, cw - 0.8, ch - 0.8)
            tf = tbox.text_frame
            p_h = tf.paragraphs[0]
            TypographySystem.apply_title(
                p_h,
                data.get("title", "Comparison Column"),
                self.theme,
                color=self.theme.accent if is_accent else self.theme.get_card_text_primary(),
                size=TypographySystem.CARD_TITLE_SIZE,
                bold=True,
            )

            for bullet in data.get("items", []):
                p_b = tf.add_paragraph()
                p_b.space_before = Pt(10)
                TypographySystem.apply_bullet(p_b, bullet, self.theme)

        add_footer(slide, self.theme, left_text=self.theme.name)
        return slide

    def render_section_slide(
        self,
        prs: Presentation,
        section_title: str,
        section_subtitle: Optional[str] = None,
        section_number: str = "01",
    ) -> Any:
        slide = create_blank_slide(prs)
        add_solid_background(slide, self.theme.bg)
        self.add_cover_decorations(slide)

        left, top, w, h = 1.5, 2.2, 10.333, 3.2
        add_card(slide, left, top, w, h, self.theme.card_bg, self.theme.accent, 2.0)

        # Number badge
        add_badge(
            slide,
            left + 0.6,
            top + 0.5,
            1.2,
            0.4,
            f"SECTION {section_number}",
            self.theme.accent,
            self.theme.get_text_for_bg(self.theme.accent),
        )

        tbox = add_text_box(slide, left + 0.6, top + 1.1, w - 1.2, 1.6)
        p_t = tbox.text_frame.paragraphs[0]
        TypographySystem.apply_title(
            p_t,
            section_title,
            self.theme,
            color=self.theme.get_card_text_primary(),
            size=TypographySystem.SECTION_TITLE_SIZE,
            bold=True,
        )

        if section_subtitle:
            p_sub = tbox.text_frame.add_paragraph()
            p_sub.space_before = Pt(8)
            TypographySystem.apply_subtitle(
                p_sub,
                section_subtitle,
                self.theme,
                color=self.theme.text_muted,
                size=TypographySystem.COVER_SUBTITLE_SIZE,
            )

        return slide

    def render_table_slide(
        self,
        prs: Presentation,
        title: str,
        headers: List[str],
        rows: List[List[str]],
        subtitle: Optional[str] = None,
    ) -> Any:
        slide = create_blank_slide(prs)
        add_solid_background(slide, self.theme.main_bg)
        self.add_slide_header(slide, title, subtitle)

        left, top, width, height = GeometrySystem.get_content_rect(
            self.theme.style_type, self.theme.sidebar_w
        )
        add_card(slide, left, top, width, height, self.theme.card_bg, self.theme.card_border, 1.0)

        num_rows = len(rows) + 1
        num_cols = len(headers)
        table_shape = slide.shapes.add_table(
            num_rows, num_cols, Inches(left + 0.3), Inches(top + 0.3), Inches(width - 0.6), Inches(height - 0.6)
        )
        table = table_shape.table

        # Format Headers
        for c_idx, head in enumerate(headers):
            cell = table.cell(0, c_idx)
            cell.fill.solid()
            cell.fill.fore_color.rgb = self.theme.accent
            p = cell.text_frame.paragraphs[0]
            p.text = head
            p.font.bold = True
            p.font.size = Pt(14)
            p.font.color.rgb = self.theme.get_text_for_bg(self.theme.accent)

        # Format Data Rows
        for r_idx, row in enumerate(rows):
            for c_idx, val in enumerate(row):
                cell = table.cell(r_idx + 1, c_idx)
                cell.fill.solid()
                row_bg = self.theme.card_bg if r_idx % 2 == 0 else self.theme.main_bg
                cell.fill.fore_color.rgb = row_bg
                p = cell.text_frame.paragraphs[0]
                p.text = str(val)
                p.font.size = Pt(13)
                p.font.color.rgb = self.theme.get_card_text_primary()

        add_footer(slide, self.theme, left_text=self.theme.name)
        return slide

    def render_chart_slide(
        self,
        prs: Presentation,
        title: str,
        subtitle: Optional[str] = None,
        chart_description: Optional[str] = None,
    ) -> Any:
        slide = create_blank_slide(prs)
        add_solid_background(slide, self.theme.main_bg)
        self.add_slide_header(slide, title, subtitle)

        cols = GeometrySystem.get_column_rects(
            2, y=1.5, h=5.1, gap=0.5, style_type=self.theme.style_type, sidebar_w=self.theme.sidebar_w
        )

        # Left: Chart visual container
        cx, cy, cw, ch = cols[0]
        add_card(slide, cx, cy, cw, ch, self.theme.card_bg, self.theme.accent, 1.5)

        # Chart bar mock visual
        bar_w = (cw - 1.2) / 4
        bar_heights = [2.0, 3.2, 2.6, 4.0]
        for i, bh in enumerate(bar_heights):
            bx = cx + 0.6 + i * (bar_w + 0.15)
            by = cy + ch - 0.6 - bh
            bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(bx), Inches(by), Inches(bar_w), Inches(bh))
            bar.fill.solid()
            bar.fill.fore_color.rgb = self.theme.accent if i % 2 == 0 else self.theme.accent_sec
            bar.line.fill.background()

        # Right: Insights text container
        rx, ry, rw, rh = cols[1]
        add_card(slide, rx, ry, rw, rh, self.theme.card_bg, self.theme.card_border, 1.0)
        tbox = add_text_box(slide, rx + 0.4, ry + 0.4, rw - 0.8, rh - 0.8)
        tf = tbox.text_frame
        p_t = tf.paragraphs[0]
        TypographySystem.apply_title(
            p_t,
            "Key Performance Metrics",
            self.theme,
            color=self.theme.get_card_text_primary(),
            size=TypographySystem.CARD_TITLE_SIZE,
            bold=True,
        )

        p_desc = tf.add_paragraph()
        p_desc.space_before = Pt(12)
        TypographySystem.apply_body(
            p_desc,
            chart_description or "Observed significant performance uplift following optimization release.",
            self.theme,
        )

        add_footer(slide, self.theme, left_text=self.theme.name)
        return slide

    def render_image_slide(
        self,
        prs: Presentation,
        title: str,
        subtitle: Optional[str] = None,
        caption: str = "High-resolution contextual visual asset.",
    ) -> Any:
        slide = create_blank_slide(prs)
        add_solid_background(slide, self.theme.main_bg)
        self.add_slide_header(slide, title, subtitle)

        cols = GeometrySystem.get_column_rects(
            2, y=1.5, h=5.1, gap=0.5, style_type=self.theme.style_type, sidebar_w=self.theme.sidebar_w
        )

        # Left Image Mock Container
        lx, ly, lw, lh = cols[0]
        img_card = add_card(slide, lx, ly, lw, lh, self.theme.bg, self.theme.accent, 1.5)
        tbox_img = add_text_box(slide, lx + 0.4, ly + lh / 2 - 0.4, lw - 0.8, 0.8)
        p_img = tbox_img.text_frame.paragraphs[0]
        p_img.alignment = PP_ALIGN.CENTER
        p_img.text = "[ IMAGE ASSET CONTAINER ]"
        p_img.font.size = Pt(14)
        p_img.font.bold = True
        p_img.font.color.rgb = self.theme.get_text_for_bg(self.theme.bg)

        # Right Editorial Description
        rx, ry, rw, rh = cols[1]
        add_card(slide, rx, ry, rw, rh, self.theme.card_bg, self.theme.card_border, 1.0)
        tbox = add_text_box(slide, rx + 0.4, ry + 0.4, rw - 0.8, rh - 0.8)
        tf = tbox.text_frame
        p_t = tf.paragraphs[0]
        TypographySystem.apply_title(
            p_t,
            "Visual Overview",
            self.theme,
            color=self.theme.get_card_text_primary(),
            size=TypographySystem.CARD_TITLE_SIZE,
            bold=True,
        )

        p_c = tf.add_paragraph()
        p_c.space_before = Pt(12)
        TypographySystem.apply_body(p_c, caption, self.theme)

        add_footer(slide, self.theme, left_text=self.theme.name)
        return slide

    def render_mixed_content_slide(
        self,
        prs: Presentation,
        title: str,
        subtitle: Optional[str] = None,
        left_content: Optional[str] = None,
        right_content: Optional[List[str]] = None,
    ) -> Any:
        return self.render_comparison_slide(
            prs,
            title,
            subtitle,
            left_card={"title": "Primary Concept", "items": [left_content or "Detailed overview."]},
            right_card={"title": "Supporting Evidence", "items": right_content or ["Point 1", "Point 2"]},
        )

    # Decorative Elements (Overridden by specific theme renderers)
    def add_cover_decorations(self, slide: Any) -> None:
        pass

    def add_slide_header(self, slide: Any, title: str, subtitle: Optional[str] = None) -> None:
        """Standard top header banner/text."""
        if self.theme.style_type == "sidebar":
            # Sidebar rail
            rail = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(self.theme.sidebar_w), Inches(7.5)
            )
            rail.fill.solid()
            rail.fill.fore_color.rgb = self.theme.bg
            rail.line.fill.background()

            logo_box = add_text_box(slide, 0.4, 0.4, self.theme.sidebar_w - 0.8, 0.6)
            p_l = logo_box.text_frame.paragraphs[0]
            p_l.text = "MOTHER AI"
            p_l.font.size = Pt(14)
            p_l.font.bold = True
            p_l.font.color.rgb = self.theme.accent

            tbox = add_text_box(slide, self.theme.sidebar_w + 0.4, 0.4, 9.8, 0.8)
        else:
            # Top subtle line accent
            line = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(GeometrySystem.SLIDE_WIDTH_INCHES), Inches(0.08)
            )
            line.fill.solid()
            line.fill.fore_color.rgb = self.theme.accent
            line.line.fill.background()

            tbox = add_text_box(slide, GeometrySystem.MARGIN_LEFT, 0.4, 11.733, 0.8)

        p = tbox.text_frame.paragraphs[0]
        TypographySystem.apply_title(
            p, title, self.theme, color=self.theme.get_main_text_primary(), size=TypographySystem.SLIDE_TITLE_SIZE
        )

        if subtitle:
            p_sub = tbox.text_frame.add_paragraph()
            TypographySystem.apply_subtitle(p_sub, subtitle, self.theme)


# -----------------------------------------------------------------------------
# Specific Theme Strategy Implementations
# -----------------------------------------------------------------------------
class IonThemeRenderer(BaseThemeRenderer):
    """Ion Boardroom: Magenta pill tag + rounded glowing neon borders."""

    def add_cover_decorations(self, slide: Any) -> None:
        add_badge(slide, 10.5, 0.5, 2.2, 0.45, "ION EXECUTIVE", self.theme.accent, self.theme.text_light)


class BerlinThemeRenderer(BaseThemeRenderer):
    """Berlin Executive: Burnt orange top bar + charcoal slate center banner."""

    def add_cover_decorations(self, slide: Any) -> None:
        bar = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(0), Inches(2.2), Inches(GeometrySystem.SLIDE_WIDTH_INCHES), Inches(3.2)
        )
        bar.fill.solid()
        bar.fill.fore_color.rgb = self.theme.accent
        bar.line.fill.background()

    def add_slide_header(self, slide: Any, title: str, subtitle: Optional[str] = None) -> None:
        header = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(GeometrySystem.SLIDE_WIDTH_INCHES), Inches(1.1)
        )
        header.fill.solid()
        header.fill.fore_color.rgb = self.theme.bg
        header.line.fill.background()

        tbox = add_text_box(slide, GeometrySystem.MARGIN_LEFT, 0.2, 11.733, 0.7)
        p = tbox.text_frame.paragraphs[0]
        TypographySystem.apply_title(
            p, title, self.theme, color=self.theme.text_light, size=TypographySystem.SLIDE_TITLE_SIZE
        )


class QuotableThemeRenderer(BaseThemeRenderer):
    """Quotable: Cyan Teal top 50% split with dark charcoal bottom canvas."""

    def add_cover_decorations(self, slide: Any) -> None:
        bottom = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(0), Inches(3.75), Inches(GeometrySystem.SLIDE_WIDTH_INCHES), Inches(3.75)
        )
        bottom.fill.solid()
        bottom.fill.fore_color.rgb = self.theme.main_bg
        bottom.line.fill.background()


class GeometricThemeRenderer(BaseThemeRenderer):
    """Geometric Color Block: Arch semi-circle curves & pastel canvas."""

    def add_cover_decorations(self, slide: Any) -> None:
        arch = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(2.0), Inches(1.0), Inches(9.333), Inches(9.333))
        arch.fill.solid()
        arch.fill.fore_color.rgb = self.theme.accent
        arch.line.fill.background()


class CropThemeRenderer(BaseThemeRenderer):
    """Crop Bracket: Refined editorial corner brackets on warm sand."""

    def add_cover_decorations(self, slide: Any) -> None:
        # Top-left corner brackets
        c1 = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.0), Inches(1.0), Inches(1.5), Inches(0.12))
        c1.fill.solid(); c1.fill.fore_color.rgb = self.theme.accent; c1.line.fill.background()
        c2 = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.0), Inches(1.0), Inches(0.12), Inches(1.5))
        c2.fill.solid(); c2.fill.fore_color.rgb = self.theme.accent; c2.line.fill.background()
        # Bottom-right corner brackets
        c3 = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(10.833), Inches(6.38), Inches(1.5), Inches(0.12))
        c3.fill.solid(); c3.fill.fore_color.rgb = self.theme.accent; c3.line.fill.background()
        c4 = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(12.213), Inches(5.0), Inches(0.12), Inches(1.5))
        c4.fill.solid(); c4.fill.fore_color.rgb = self.theme.accent; c4.line.fill.background()


class AtlasThemeRenderer(BaseThemeRenderer):
    """Atlas Crimson: Concentric ring geometry + crimson floating banner."""

    def add_cover_decorations(self, slide: Any) -> None:
        ring = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(4.166), Inches(1.25), Inches(5.0), Inches(5.0))
        ring.fill.background()
        ring.line.color.rgb = self.theme.card_border
        ring.line.width = Pt(2.0)


class DividendThemeRenderer(BaseThemeRenderer):
    """Dividend Burgundy: White top header with burgundy footer block."""

    def add_cover_decorations(self, slide: Any) -> None:
        bot = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(0), Inches(4.5), Inches(GeometrySystem.SLIDE_WIDTH_INCHES), Inches(3.0)
        )
        bot.fill.solid()
        bot.fill.fore_color.rgb = self.theme.bg
        bot.line.fill.background()


class SavonThemeRenderer(BaseThemeRenderer):
    """Savon Mint: Soft mint background + paperclip tab header."""

    def add_cover_decorations(self, slide: Any) -> None:
        tab = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(5.8), Inches(1.4), Inches(1.7), Inches(0.4))
        tab.fill.solid()
        tab.fill.fore_color.rgb = self.theme.accent
        tab.line.fill.background()


class WoodThemeRenderer(BaseThemeRenderer):
    """Wood Type Vintage: Timber brown canvas + parchment card + amber seal stamp."""

    def add_cover_decorations(self, slide: Any) -> None:
        seal = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(10.5), Inches(4.8), Inches(1.2), Inches(1.2))
        seal.fill.solid()
        seal.fill.fore_color.rgb = self.theme.accent
        seal.line.fill.background()


class ArtisticThemeRenderer(BaseThemeRenderer):
    """Artistic Neon: Neon orange left vertical split with dark right canvas."""

    def add_cover_decorations(self, slide: Any) -> None:
        split = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(4.5), Inches(7.5))
        split.fill.solid()
        split.fill.fore_color.rgb = self.theme.accent
        split.line.fill.background()


class CircuitThemeRenderer(BaseThemeRenderer):
    """Circuit Tech: Electric cyan and blue technical cyber lines."""

    def add_cover_decorations(self, slide: Any) -> None:
        bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.8), Inches(0.12), Inches(4.0))
        bar.fill.solid()
        bar.fill.fore_color.rgb = self.theme.accent
        bar.line.fill.background()


class CelestialThemeRenderer(BaseThemeRenderer):
    """Celestial Night: Deep space navy with glowing orbital radar rings."""

    def add_cover_decorations(self, slide: Any) -> None:
        ring = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(9.5), Inches(0.5), Inches(4.5), Inches(4.5))
        ring.fill.background()
        ring.line.color.rgb = self.theme.accent
        ring.line.width = Pt(1.5)


class GlassmorphismThemeRenderer(BaseThemeRenderer):
    """Modern Glassmorphism: Dark zinc 950 with glowing purple & cyan neon borders."""

    def add_cover_decorations(self, slide: Any) -> None:
        glow_bar = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.0), Inches(1.8), Inches(11.333), Inches(4.2)
        )
        glow_bar.fill.solid()
        glow_bar.fill.fore_color.rgb = self.theme.card_bg
        glow_bar.line.color.rgb = self.theme.accent
        glow_bar.line.width = Pt(2.0)


# Strategy Factory
def get_theme_renderer(theme: ThemeConfig) -> BaseThemeRenderer:
    """Returns the specialized theme renderer matching the theme style_type."""
    st = theme.style_type.lower()
    if st == "ion":
        return IonThemeRenderer(theme)
    elif st == "berlin":
        return BerlinThemeRenderer(theme)
    elif st == "quotable":
        return QuotableThemeRenderer(theme)
    elif st == "geometric":
        return GeometricThemeRenderer(theme)
    elif st == "crop":
        return CropThemeRenderer(theme)
    elif st == "atlas":
        return AtlasThemeRenderer(theme)
    elif st == "dividend":
        return DividendThemeRenderer(theme)
    elif st == "savon":
        return SavonThemeRenderer(theme)
    elif st == "wood":
        return WoodThemeRenderer(theme)
    elif st == "artistic":
        return ArtisticThemeRenderer(theme)
    elif st == "circuit":
        return CircuitThemeRenderer(theme)
    elif st == "celestial":
        return CelestialThemeRenderer(theme)
    elif st == "glassmorphism":
        return GlassmorphismThemeRenderer(theme)
    return BaseThemeRenderer(theme)


# -----------------------------------------------------------------------------
# 8. High-Level SlideRenderer Facade
# -----------------------------------------------------------------------------
class SlideRenderer:
    """High-level facade coordinating slide generation across theme engines."""

    def __init__(self, theme_or_preset: Union[str, dict, ThemeConfig]):
        if isinstance(theme_or_preset, ThemeConfig):
            self.theme = theme_or_preset
        elif isinstance(theme_or_preset, dict):
            key = theme_or_preset.get("id", "custom")
            self.theme = ThemeConfig.from_dict(key, theme_or_preset)
        else:
            cfg = get_template_preset(theme_or_preset)
            self.theme = ThemeConfig.from_dict(theme_or_preset, cfg)

        self.theme_renderer = get_theme_renderer(self.theme)

    def render_presentation(
        self,
        output_path: Union[str, Path],
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
    ) -> str:
        """Builds a complete, professional multi-slide master deck showcasing all layouts."""
        prs = create_presentation()

        deck_title = title or self.theme.name
        deck_sub = subtitle or "AI-Powered Adaptive Widescreen Slide Architecture"

        # 1. Cover Slide
        self.theme_renderer.render_cover_slide(prs, deck_title, deck_sub, badge="MASTER TEMPLATE")

        # 2. Content Slide (Executive Summary)
        self.theme_renderer.render_content_slide(
            prs,
            title="Executive Overview",
            subtitle="Strategic Architectural Principles",
            body_paragraphs=[
                "This presentation template demonstrates high-precision 16:9 widescreen layout geometry. Every element is rendered on clean blank slides with zero default placeholder interference.",
                "Semantic information cards and decorative compositions are logically separated to prevent overlapping shapes and guarantee text contrast readability.",
            ],
            bullets=[
                "Deterministic 16:9 widescreen positioning with 0.8-inch safe margins",
                "Automatic luminance-based text contrast calculation",
                "Modular ThemeConfig and Strategy-pattern ThemeRenderer architecture",
            ],
        )

        # 3. 3-Card Feature Grid Slide
        self.theme_renderer.render_feature_grid_slide(
            prs,
            title="Core Platform Capabilities",
            subtitle="Modular Component Architecture",
            items=[
                {"title": "Geometry System", "body": "Absolute bounding box calculation avoiding layout collisions and text wrapping issues."},
                {"title": "Typography Engine", "body": "Standardized font hierarchy from 44pt titles down to 10pt discrete footers."},
                {"title": "Theme Strategies", "body": "16 bespoke design archetypes with specialized decorative visual treatments."},
            ],
        )

        # 4. Stat Callout Slide
        self.theme_renderer.render_stat_slide(
            prs,
            title="Performance Benchmarks",
            subtitle="Verified Real-World Efficiency",
            stat_value="99.9%",
            stat_label="Automated Layout Accuracy",
            description="Elimination of placeholder ghosting, duplicate title areas, and unanchored text boxes across 100% of tested slide archetypes.",
            items=[
                "Zero placeholder collisions across all PowerPoint versions",
                "Sub-50ms slide generation compile latency",
            ],
        )

        # 5. 2-Column Split Comparison Slide
        self.theme_renderer.render_comparison_slide(
            prs,
            title="Architecture Comparison",
            subtitle="Legacy Placeholders vs Blank Slide Engine",
            left_card={
                "title": "Legacy Slide Layouts (0-4)",
                "items": [
                    "Unwanted placeholder shape artifacts",
                    "Invisible placeholder bounding box collisions",
                    "Duplicate title boxes during re-renders",
                    "Hardcoded 4:3 and 16:9 layout discrepancies",
                ],
            },
            right_card={
                "title": "Modern Blank Slide Engine",
                "items": [
                    "Clean blank layouts (prs.slide_layouts[6])",
                    "Strict bounding box geometry validation",
                    "Fully theme-aware styling and contrast",
                    "Extensible ThemeRenderer strategy hierarchy",
                ],
            },
        )

        # 6. Section Divider Slide
        self.theme_renderer.render_section_slide(
            prs,
            section_title="Data & Visual Analytics",
            section_subtitle="Structured Data Rendering Components",
            section_number="02",
        )

        # 7. Table Slide
        self.theme_renderer.render_table_slide(
            prs,
            title="Component Inventory & Metrics",
            subtitle="System Architecture Specification",
            headers=["Component", "Responsibility", "Status"],
            rows=[
                ["ThemeConfig", "Encapsulates colors, typography, borders, and luminance", "Production Ready"],
                ["GeometrySystem", "Computes 16:9 safe bounds and column distributions", "Verified"],
                ["TypographySystem", "Enforces standardized type scale and contrast", "Active"],
                ["SlideRenderer", "Facade coordinating slide builds and theme strategies", "Deployed"],
            ],
        )

        # 8. Chart / Analytics Slide
        self.theme_renderer.render_chart_slide(
            prs,
            title="Generation Latency Distribution",
            subtitle="Speed and Reliability Across Themes",
            chart_description="Average deck compilation time remained under 45ms per deck across all 16 template archetypes.",
        )

        # 9. Image & Story Slide
        self.theme_renderer.render_image_slide(
            prs,
            title="Visual Media Storytelling",
            subtitle="Integrated Image & Card Composition",
            caption="Contextually aligned media placeholders with structured editorial captions and attribution metadata.",
        )

        # Save to disk
        out_path = Path(output_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        prs.save(str(out_path))
        return str(out_path)


# -----------------------------------------------------------------------------
# 9. Public API Entrypoints
# -----------------------------------------------------------------------------
def build_template_pptx(preset_key: str, cfg: dict, output_dir: str = "./templates") -> str:
    """Builds a complete PowerPoint template presentation for the specified preset."""
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{preset_key}.pptx"

    theme = ThemeConfig.from_dict(preset_key, cfg)
    renderer = SlideRenderer(theme)
    return renderer.render_presentation(out_file)


def list_available_templates(templates_dir: str = "./templates") -> list[dict[str, Any]]:
    """Lists all available templates and presets with normalized hex colors and contrast metadata."""
    result = []
    t_dir = Path(templates_dir).resolve()

    for key, raw_cfg in TEMPLATE_PRESETS.items():
        file_name = f"{key}.pptx"
        file_path = t_dir / file_name
        theme = ThemeConfig.from_dict(key, raw_cfg)

        bg_hex = to_hex_str(theme.bg, "#0f172a")
        main_bg_hex = to_hex_str(theme.main_bg, bg_hex)
        accent_hex = to_hex_str(theme.accent, "#c084fc")
        accent_sec_hex = to_hex_str(theme.accent_sec, accent_hex)
        card_bg_hex = to_hex_str(theme.card_bg, "#1e293b")
        card_border_hex = to_hex_str(theme.card_border, accent_hex)
        text_dark_hex = to_hex_str(theme.text_dark, "#0f172a")
        text_light_hex = to_hex_str(theme.text_light, "#ffffff")
        text_muted_hex = to_hex_str(theme.text_muted, "#94a3b8")

        font_color_hex = text_dark_hex if theme.is_bg_light() else text_light_hex

        result.append({
            "id": key,
            "key": key,
            "name": theme.name,
            "style_type": theme.style_type,
            "theme": raw_cfg.get("theme", "auto"),
            "file_name": file_name,
            "exists": file_path.is_file(),
            "bg": bg_hex,
            "main_bg": main_bg_hex,
            "accent": accent_hex,
            "accent_sec": accent_sec_hex,
            "card_bg": card_bg_hex,
            "card_border": card_border_hex,
            "text_dark": text_dark_hex,
            "text_light": text_light_hex,
            "text_muted": text_muted_hex,
            "font_color": font_color_hex,
            "badge": key[:5].upper(),
        })
    return result


if __name__ == "__main__":
    pass
