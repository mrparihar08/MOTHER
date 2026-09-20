from __future__ import annotations

import collections
import collections.abc
import sys
from pathlib import Path

# Forward compatibility fix for python-pptx / collections on Python 3.10+
for name in ("Container", "Mapping", "MutableMapping", "Sequence", "MutableSequence", "Iterable", "Callable"):
    if not hasattr(collections, name) and hasattr(collections.abc, name):
        setattr(collections, name, getattr(collections.abc, name))

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE


# -----------------------------------------------------------------------------
# 16 Distinct Template Design Architectures (PowerPoint Professional Themes)
# -----------------------------------------------------------------------------
TEMPLATE_ARCHETYPES = {
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

# -----------------------------------------------------------------------------
# Preset Template Theme Configurations (Compatible with tests & presentation engine)
# -----------------------------------------------------------------------------
TEMPLATE_PRESETS = {
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


def get_template_preset(preset_key: str) -> dict:
    return TEMPLATE_PRESETS.get(preset_key, {})


def list_available_templates() -> list[dict]:
    return [
        {
            "key": k,
            "name": v.get("name", k),
            "style_type": v.get("style_type", "modern"),
            "theme": v.get("theme", "auto"),
        }
        for k, v in TEMPLATE_PRESETS.items()
    ]


def build_template_pptx(preset_key: str, cfg: dict, output_dir: str = "./templates") -> str:
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{preset_key}.pptx"

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    style_type = cfg.get("style_type", "modern")
    bg_color = cfg.get("bg", RGBColor(15, 23, 42))
    main_bg = cfg.get("main_bg", bg_color)
    accent_color = cfg.get("accent", RGBColor(13, 148, 136))
    accent_sec = cfg.get("accent_sec", RGBColor(99, 102, 241))
    card_bg = cfg.get("card_bg", RGBColor(248, 250, 252))
    card_border = cfg.get("card_border", accent_color)
    text_dark = cfg.get("text_dark", RGBColor(15, 23, 42))
    text_light = cfg.get("text_light", RGBColor(255, 255, 255))

    # -------------------------------------------------------------------------
    # Layout 0: Cover Slide (Master Cover Layout)
    # -------------------------------------------------------------------------
    slide_0 = prs.slides.add_slide(prs.slide_layouts[0])
    
    # Base background fill
    bg0 = slide_0.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(7.5))
    bg0.fill.solid()
    bg0.fill.fore_color.rgb = bg_color
    bg0.line.fill.background()

    if style_type == "ion":
        # Ion Boardroom: Magenta pill tag top right + floating dark card
        tag = slide_0.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(10.5), Inches(0.4), Inches(2.2), Inches(0.4))
        tag.fill.solid()
        tag.fill.fore_color.rgb = accent_color
        tag.line.fill.background()

        card0 = slide_0.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.0), Inches(1.8), Inches(11.333), Inches(4.5))
        card0.fill.solid()
        card0.fill.fore_color.rgb = card_bg
        card0.line.color.rgb = accent_color
        card0.line.width = Pt(2.0)

        tbox = slide_0.shapes.add_textbox(Inches(1.5), Inches(2.5), Inches(10.3), Inches(2.0))
        p_t = tbox.text_frame.paragraphs[0]
        p_t.text = cfg["name"]
        p_t.font.size = Pt(46)
        p_t.font.bold = True
        p_t.font.color.rgb = text_light

    elif style_type == "berlin":
        # Berlin: Burnt orange top bar + thick dark slate center banner
        bar0 = slide_0.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(2.5), Inches(13.333), Inches(2.5))
        bar0.fill.solid()
        bar0.fill.fore_color.rgb = accent_color
        bar0.line.fill.background()

        tbox = slide_0.shapes.add_textbox(Inches(1.0), Inches(3.0), Inches(11.333), Inches(1.5))
        p_t = tbox.text_frame.paragraphs[0]
        p_t.text = cfg["name"]
        p_t.font.size = Pt(48)
        p_t.font.bold = True
        p_t.font.color.rgb = text_light

    elif style_type == "quotable":
        # Quotable: Top 50% teal, bottom 50% dark charcoal
        b_bottom = slide_0.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(3.75), Inches(13.333), Inches(3.75))
        b_bottom.fill.solid()
        b_bottom.fill.fore_color.rgb = main_bg
        b_bottom.line.fill.background()

        # White speech box
        box0 = slide_0.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.5), Inches(2.2), Inches(10.333), Inches(3.0))
        box0.fill.solid()
        box0.fill.fore_color.rgb = RGBColor(255, 255, 255)
        box0.line.color.rgb = accent_color

        tbox = slide_0.shapes.add_textbox(Inches(1.8), Inches(2.8), Inches(9.7), Inches(1.8))
        p_t = tbox.text_frame.paragraphs[0]
        p_t.text = cfg["name"]
        p_t.font.size = Pt(44)
        p_t.font.bold = True
        p_t.font.color.rgb = text_dark

    elif style_type == "geometric":
        # Geometric Color Block: Arch semi-circle block
        arch = slide_0.shapes.add_shape(MSO_SHAPE.OVAL, Inches(2.0), Inches(1.0), Inches(9.333), Inches(9.333))
        arch.fill.solid()
        arch.fill.fore_color.rgb = accent_color
        arch.line.fill.background()

        tbox = slide_0.shapes.add_textbox(Inches(2.5), Inches(2.8), Inches(8.333), Inches(2.0))
        p_t = tbox.text_frame.paragraphs[0]
        p_t.text = cfg["name"]
        p_t.alignment = PP_ALIGN.CENTER
        p_t.font.size = Pt(44)
        p_t.font.bold = True
        p_t.font.color.rgb = text_light

    elif style_type == "crop":
        # Crop brackets on 4 corners
        # Top-left corner
        c1 = slide_0.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.0), Inches(1.0), Inches(1.5), Inches(0.12))
        c1.fill.solid(); c1.fill.fore_color.rgb = accent_color; c1.line.fill.background()
        c2 = slide_0.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.0), Inches(1.0), Inches(0.12), Inches(1.5))
        c2.fill.solid(); c2.fill.fore_color.rgb = accent_color; c2.line.fill.background()
        # Bottom-right corner
        c3 = slide_0.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(10.833), Inches(6.38), Inches(1.5), Inches(0.12))
        c3.fill.solid(); c3.fill.fore_color.rgb = accent_color; c3.line.fill.background()
        c4 = slide_0.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(12.213), Inches(5.0), Inches(0.12), Inches(1.5))
        c4.fill.solid(); c4.fill.fore_color.rgb = accent_color; c4.line.fill.background()

        tbox = slide_0.shapes.add_textbox(Inches(2.0), Inches(2.8), Inches(9.333), Inches(2.0))
        p_t = tbox.text_frame.paragraphs[0]
        p_t.alignment = PP_ALIGN.CENTER
        p_t.text = cfg["name"]
        p_t.font.size = Pt(46)
        p_t.font.bold = True
        p_t.font.color.rgb = text_dark

    elif style_type == "atlas":
        # Atlas: Concentric circle rings + crimson central callout box
        ring = slide_0.shapes.add_shape(MSO_SHAPE.OVAL, Inches(4.166), Inches(1.25), Inches(5.0), Inches(5.0))
        ring.fill.background()
        ring.line.color.rgb = RGBColor(226, 232, 240)
        ring.line.width = Pt(2.0)

        banner0 = slide_0.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.5), Inches(2.8), Inches(10.333), Inches(1.8))
        banner0.fill.solid()
        banner0.fill.fore_color.rgb = accent_color
        banner0.line.fill.background()

        tbox = slide_0.shapes.add_textbox(Inches(1.8), Inches(3.0), Inches(9.7), Inches(1.4))
        p_t = tbox.text_frame.paragraphs[0]
        p_t.alignment = PP_ALIGN.CENTER
        p_t.text = cfg["name"]
        p_t.font.size = Pt(44)
        p_t.font.bold = True
        p_t.font.color.rgb = text_light

    elif style_type == "dividend":
        # Dividend: White top body + Burgundy bottom footer block
        bot0 = slide_0.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(4.5), Inches(13.333), Inches(3.0))
        bot0.fill.solid()
        bot0.fill.fore_color.rgb = bg_color
        bot0.line.fill.background()

        # Top 3 colored accent lines
        l1 = slide_0.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.0), Inches(0.8), Inches(3.5), Inches(0.08))
        l1.fill.solid(); l1.fill.fore_color.rgb = accent_sec; l1.line.fill.background()
        l2 = slide_0.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(4.8), Inches(0.8), Inches(3.5), Inches(0.08))
        l2.fill.solid(); l2.fill.fore_color.rgb = accent_color; l2.line.fill.background()

        tbox = slide_0.shapes.add_textbox(Inches(1.0), Inches(1.8), Inches(11.333), Inches(2.0))
        p_t = tbox.text_frame.paragraphs[0]
        p_t.text = cfg["name"]
        p_t.font.size = Pt(46)
        p_t.font.bold = True
        p_t.font.color.rgb = text_dark

    elif style_type == "savon":
        # Savon: Patterned Mint background + Framed card with paperclip tab
        tab = slide_0.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(5.8), Inches(1.4), Inches(1.7), Inches(0.4))
        tab.fill.solid(); tab.fill.fore_color.rgb = accent_color; tab.line.fill.background()

        card0 = slide_0.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.5), Inches(1.8), Inches(10.333), Inches(4.2))
        card0.fill.solid(); card0.fill.fore_color.rgb = card_bg; card0.line.color.rgb = card_border; card0.line.width = Pt(2.0)

        tbox = slide_0.shapes.add_textbox(Inches(1.8), Inches(2.8), Inches(9.7), Inches(2.0))
        p_t = tbox.text_frame.paragraphs[0]
        p_t.alignment = PP_ALIGN.CENTER
        p_t.text = cfg["name"]
        p_t.font.size = Pt(44)
        p_t.font.bold = True
        p_t.font.color.rgb = text_dark

    elif style_type == "wood":
        # Wood Type Vintage: Brown timber background + Parchment card + Amber Seal Stamp
        card0 = slide_0.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.5), Inches(1.8), Inches(10.333), Inches(4.2))
        card0.fill.solid(); card0.fill.fore_color.rgb = main_bg; card0.line.color.rgb = accent_color; card0.line.width = Pt(3.0)

        seal = slide_0.shapes.add_shape(MSO_SHAPE.OVAL, Inches(10.2), Inches(4.8), Inches(1.2), Inches(1.2))
        seal.fill.solid(); seal.fill.fore_color.rgb = accent_color; seal.line.fill.background()

        tbox = slide_0.shapes.add_textbox(Inches(1.8), Inches(2.8), Inches(9.7), Inches(2.0))
        p_t = tbox.text_frame.paragraphs[0]
        p_t.alignment = PP_ALIGN.CENTER
        p_t.text = cfg["name"].upper()
        p_t.font.size = Pt(44)
        p_t.font.bold = True
        p_t.font.color.rgb = text_dark

    elif style_type == "sidebar":
        rail = slide_0.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(cfg["sidebar_w"]), Inches(7.5))
        rail.fill.solid(); rail.fill.fore_color.rgb = accent_color; rail.line.fill.background()

        tbox = slide_0.shapes.add_textbox(Inches(3.0), Inches(2.2), Inches(9.5), Inches(2.0))
        p_t = tbox.text_frame.paragraphs[0]
        p_t.text = cfg["name"]
        p_t.font.size = Pt(44)
        p_t.font.bold = True
        p_t.font.color.rgb = text_dark

    elif style_type == "artistic":
        split = slide_0.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(4.5), Inches(7.5))
        split.fill.solid(); split.fill.fore_color.rgb = accent_color; split.line.fill.background()

        tbox = slide_0.shapes.add_textbox(Inches(5.0), Inches(2.2), Inches(7.5), Inches(2.0))
        p_t = tbox.text_frame.paragraphs[0]
        p_t.text = cfg["name"]
        p_t.font.size = Pt(44)
        p_t.font.bold = True
        p_t.font.color.rgb = text_light

    else:
        # Urban / Circuit / Celestial / Glassmorphism
        bar = slide_0.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.8), Inches(0.12), Inches(4.0))
        bar.fill.solid(); bar.fill.fore_color.rgb = accent_color; bar.line.fill.background()

        tbox = slide_0.shapes.add_textbox(Inches(1.2), Inches(2.0), Inches(11.0), Inches(1.8))
        p_t = tbox.text_frame.paragraphs[0]
        p_t.text = cfg["name"]
        p_t.font.size = Pt(44)
        p_t.font.bold = True
        p_t.font.color.rgb = text_light if style_type in {"urban", "circuit", "celestial", "glassmorphism"} else text_dark

    # -------------------------------------------------------------------------
    # Layout 1: Master Content Slide Layout (Applied across all content slides)
    # -------------------------------------------------------------------------
    slide_1 = prs.slides.add_slide(prs.slide_layouts[1])
    bg1 = slide_1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(7.5))
    bg1.fill.solid()
    bg1.fill.fore_color.rgb = main_bg
    bg1.line.fill.background()

    if style_type == "ion":
        # Header strip & content card
        header = slide_1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(1.0))
        header.fill.solid(); header.fill.fore_color.rgb = bg_color; header.line.fill.background()

        card1 = slide_1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.3), Inches(11.733), Inches(5.5))
        card1.fill.solid(); card1.fill.fore_color.rgb = card_bg; card1.line.color.rgb = card_border

    elif style_type == "berlin":
        # Burnt Orange Header Strip
        header = slide_1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(1.2))
        header.fill.solid(); header.fill.fore_color.rgb = bg_color; header.line.fill.background()

        card1 = slide_1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.5), Inches(11.733), Inches(5.4))
        card1.fill.solid(); card1.fill.fore_color.rgb = card_bg; card1.line.color.rgb = card_border

    elif style_type == "quotable":
        # Teal header strip
        header = slide_1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(1.1))
        header.fill.solid(); header.fill.fore_color.rgb = bg_color; header.line.fill.background()

        card1 = slide_1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.4), Inches(11.733), Inches(5.5))
        card1.fill.solid(); card1.fill.fore_color.rgb = card_bg; card1.line.color.rgb = card_border

    elif style_type == "dividend":
        # Burgundy Footer Block on content slides
        footer = slide_1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(6.5), Inches(13.333), Inches(1.0))
        footer.fill.solid(); footer.fill.fore_color.rgb = bg_color; footer.line.fill.background()

        card1 = slide_1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.0), Inches(11.733), Inches(5.2))
        card1.fill.solid(); card1.fill.fore_color.rgb = card_bg; card1.line.color.rgb = card_border

    elif style_type == "sidebar":
        rail1 = slide_1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(cfg["sidebar_w"]), Inches(7.5))
        rail1.fill.solid(); rail1.fill.fore_color.rgb = bg_color; rail1.line.fill.background()

        logo_box = slide_1.shapes.add_textbox(Inches(0.4), Inches(0.4), Inches(1.8), Inches(0.5))
        p_l = logo_box.text_frame.paragraphs[0]
        p_l.text = "MOTHER AI"
        p_l.font.size = Pt(12); p_l.font.bold = True; p_l.font.color.rgb = accent_color

        card1 = slide_1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(2.8), Inches(1.3), Inches(9.8), Inches(5.5))
        card1.fill.solid(); card1.fill.fore_color.rgb = card_bg; card1.line.color.rgb = card_border

    elif style_type == "crop":
        c1 = slide_1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.5), Inches(0.5), Inches(1.0), Inches(0.08))
        c1.fill.solid(); c1.fill.fore_color.rgb = accent_color; c1.line.fill.background()
        c2 = slide_1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.5), Inches(0.5), Inches(0.08), Inches(1.0))
        c2.fill.solid(); c2.fill.fore_color.rgb = accent_color; c2.line.fill.background()

        card1 = slide_1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.3), Inches(11.733), Inches(5.5))
        card1.fill.solid(); card1.fill.fore_color.rgb = card_bg; card1.line.color.rgb = card_border

    else:
        # Default top bar header accent for content slides
        top_bar = slide_1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(0.1))
        top_bar.fill.solid(); top_bar.fill.fore_color.rgb = accent_color; top_bar.line.fill.background()

        card1 = slide_1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.3), Inches(11.733), Inches(5.5))
        card1.fill.solid(); card1.fill.fore_color.rgb = card_bg; card1.line.color.rgb = card_border
        card1.line.width = Pt(1.5)

    # -------------------------------------------------------------------------
    # Save Presentation Template Archetype
    # -------------------------------------------------------------------------
    prs.save(str(out_file))
    print(f"[SUCCESS] Built Distinct Archetype Template '{preset_key}' ({cfg['name']}) -> {out_file.name}")
    return str(out_file)


TEMPLATE_PRESETS = TEMPLATE_ARCHETYPES


def get_template_preset(key: str) -> Optional[dict[str, Any]]:
    return TEMPLATE_ARCHETYPES.get(key)


def list_available_templates(templates_dir: str = "./templates") -> list[dict[str, Any]]:
    result = []
    t_dir = Path(templates_dir).resolve()
    for key, cfg in TEMPLATE_ARCHETYPES.items():
        file_name = f"{key}.pptx"
        file_path = t_dir / file_name
        bg_rgb = cfg.get("bg")
        accent_rgb = cfg.get("accent")
        bg_hex = f"#{bg_rgb[0]:02x}{bg_rgb[1]:02x}{bg_rgb[2]:02x}" if isinstance(bg_rgb, RGBColor) else "#0f172a"
        accent_hex = f"#{accent_rgb[0]:02x}{accent_rgb[1]:02x}{accent_rgb[2]:02x}" if isinstance(accent_rgb, RGBColor) else "#c084fc"
        result.append({
            "id": key,
            "name": cfg.get("name", key.replace("_", " ").title()),
            "style_type": cfg.get("style_type", "default"),
            "file_name": file_name,
            "exists": file_path.is_file(),
            "bg": bg_hex,
            "accent": accent_hex,
            "badge": key[:5].upper(),
        })
    return result


if __name__ == "__main__":
    generate_all_templates()
