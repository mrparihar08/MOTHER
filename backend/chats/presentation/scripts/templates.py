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
# Preset Template Theme Configurations
# -----------------------------------------------------------------------------
TEMPLATE_PRESETS = {
    "base_template": {
        "name": "Default Slate Teal",
        "theme": "default",
        "description": "Clean dark slate background with teal accent highlight",
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
        "theme": "light",
        "description": "Crisp corporate light aesthetic with royal blue accents",
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
        "theme": "dark",
        "description": "Sleek dark zinc layout with vibrant neon purple accents",
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
        "theme": "emerald",
        "description": "Deep emerald theme for sustainability, eco, and energy topics",
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
        "theme": "executive_gold",
        "description": "Luxury stone and amber gold palette for high-level executive decks",
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
        "theme": "cyberpunk_neon",
        "description": "High-contrast dark tech theme with neon rose and cyan highlights",
        "bg": RGBColor(9, 9, 11),            # Zinc 950
        "accent": RGBColor(244, 63, 94),       # Rose 500 Neon
        "accent_sec": RGBColor(6, 182, 212),   # Cyan 500
        "card_bg": RGBColor(24, 24, 27),
        "card_border": RGBColor(244, 63, 94),
        "text_dark": RGBColor(255, 255, 255),
        "text_muted": RGBColor(161, 161, 170),
        "text_light": RGBColor(255, 255, 255),
    },
    "sidebar_executive": {
        "name": "Sidebar Executive Slate",
        "theme": "executive_slate",
        "description": "Executive sidebar rail archetype layout with indigo accents",
        "bg": RGBColor(15, 23, 42),          # Slate 900
        "accent": RGBColor(99, 102, 241),      # Indigo 500
        "accent_sec": RGBColor(13, 148, 136),  # Teal 600
        "card_bg": RGBColor(30, 41, 59),      # Slate 800
        "card_border": RGBColor(51, 65, 85),
        "text_dark": RGBColor(255, 255, 255),
        "text_muted": RGBColor(148, 163, 184),
        "text_light": RGBColor(241, 245, 249),
    },
    "corporate_banner": {
        "name": "Corporate Hero Banner Blue",
        "theme": "ocean_blue",
        "description": "Top hero banner archetype layout with sky blue header accents",
        "bg": RGBColor(6, 16, 30),           # Deep Navy
        "accent": RGBColor(56, 189, 248),      # Sky 400
        "accent_sec": RGBColor(3, 105, 161),   # Sky 700
        "card_bg": RGBColor(11, 37, 69),
        "card_border": RGBColor(30, 58, 138),
        "text_dark": RGBColor(255, 255, 255),
        "text_muted": RGBColor(147, 197, 253),
        "text_light": RGBColor(240, 249, 255),
    },
}


def get_template_preset(preset_key: str) -> dict:
    key = (preset_key or "").strip().lower()
    if key in TEMPLATE_PRESETS:
        return TEMPLATE_PRESETS[key]
    # Check normalized matching
    for k, v in TEMPLATE_PRESETS.items():
        if k in key or key in k:
            return v
    return TEMPLATE_PRESETS["base_template"]


def list_available_templates() -> list[dict]:
    templates_list = []
    for key, cfg in TEMPLATE_PRESETS.items():
        templates_list.append({
            "key": key,
            "name": cfg["name"],
            "theme": cfg.get("theme", "default"),
            "description": cfg.get("description", ""),
        })
    return templates_list


def build_template_pptx(preset_key: str, cfg: dict, output_dir: str = "./templates") -> str:
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{preset_key}.pptx"

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    bg_color = cfg["bg"]
    accent_color = cfg["accent"]
    accent_sec = cfg["accent_sec"]
    card_bg = cfg["card_bg"]
    card_border = cfg["card_border"]
    text_dark = cfg["text_dark"]
    text_muted = cfg["text_muted"]
    text_light = cfg["text_light"]

    # -------------------------------------------------------------------------
    # Layout 0: Cover Slide
    # -------------------------------------------------------------------------
    slide_0 = prs.slides.add_slide(prs.slide_layouts[0])
    bg0 = slide_0.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(7.5))
    bg0.fill.solid()
    bg0.fill.fore_color.rgb = bg_color
    bg0.line.fill.background()

    # Vertical Accent Line
    bar0 = slide_0.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.8), Inches(0.12), Inches(4.0))
    bar0.fill.solid()
    bar0.fill.fore_color.rgb = accent_color
    bar0.line.fill.background()

    # Brand Logo
    lbox0 = slide_0.shapes.add_textbox(Inches(0.8), Inches(0.8), Inches(4.0), Inches(0.6))
    p_l0 = lbox0.text_frame.paragraphs[0]
    p_l0.text = "MOTHER AI"
    p_l0.font.size = Pt(14)
    p_l0.font.bold = True
    p_l0.font.color.rgb = accent_color

    # Title & Subtitle
    tbox0 = slide_0.shapes.add_textbox(Inches(1.2), Inches(2.0), Inches(11.0), Inches(1.8))
    p_t0 = tbox0.text_frame.paragraphs[0]
    p_t0.text = f"{cfg['name']} Cover"
    p_t0.font.size = Pt(44)
    p_t0.font.bold = True
    p_t0.font.color.rgb = text_light

    sbox0 = slide_0.shapes.add_textbox(Inches(1.2), Inches(4.0), Inches(11.0), Inches(1.2))
    p_s0 = sbox0.text_frame.paragraphs[0]
    p_s0.text = "Predefined Slide Master Template"
    p_s0.font.size = Pt(22)
    p_s0.font.color.rgb = accent_sec

    # -------------------------------------------------------------------------
    # Layout 1: Title & Content Slide
    # -------------------------------------------------------------------------
    slide_1 = prs.slides.add_slide(prs.slide_layouts[1])
    top1 = slide_1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(0.08))
    top1.fill.solid()
    top1.fill.fore_color.rgb = accent_color
    top1.line.fill.background()

    tbox1 = slide_1.shapes.add_textbox(Inches(0.8), Inches(0.35), Inches(9.5), Inches(0.8))
    p_t1 = tbox1.text_frame.paragraphs[0]
    p_t1.text = "Slide Header Title"
    p_t1.font.size = Pt(28)
    p_t1.font.bold = True
    p_t1.font.color.rgb = text_dark

    card1 = slide_1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.3), Inches(11.733), Inches(5.3))
    card1.fill.solid()
    card1.fill.fore_color.rgb = card_bg
    card1.line.color.rgb = card_border
    card1.line.width = Pt(1)

    # -------------------------------------------------------------------------
    # Save Presentation
    # -------------------------------------------------------------------------
    prs.save(str(out_file))
    print(f"[SUCCESS] Built template '{preset_key}' ({cfg['name']}) -> {out_file.name}")
    return str(out_file)


def generate_all_templates(output_dir: str = "./templates") -> list[str]:
    created_files = []
    print("[INFO] Generating suite of Predefined PPT Templates...")
    for key, cfg in TEMPLATE_PRESETS.items():
        path = build_template_pptx(key, cfg, output_dir=output_dir)
        created_files.append(path)
    print(f"[DONE] Total {len(created_files)} templates created successfully!")
    return created_files


if __name__ == "__main__":
    generate_all_templates()

