from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from pptx.dml.color import RGBColor


# ---------------------------------------------------------------------
# Theme Colors & Keywords Registry
# ---------------------------------------------------------------------

THEME_COLORS = {
    "light": {"background": "F8FAFC", "gradient_start": "F8FAFC", "gradient_end": "E2E8F0", "accent": "2563EB", "text": "0F172A", "badge": "2563EB", "table_header_bg": "2563EB", "table_header_text": "FFFFFF", "table_row_bg1": "FFFFFF", "table_row_bg2": "F1F5F9", "table_row_text": "0F172A"},
    "dark": {"background": "0F172A", "gradient_start": "0F172A", "gradient_end": "31104B", "accent": "C084FC", "text": "FFFFFF", "badge": "C084FC", "table_header_bg": "6366F1", "table_header_text": "FFFFFF", "table_row_bg1": "1E293B", "table_row_bg2": "0F172A", "table_row_text": "FFFFFF"},
    "midnight": {"background": "0F172A", "gradient_start": "0F172A", "gradient_end": "31104B", "accent": "C084FC", "text": "FFFFFF", "badge": "C084FC", "table_header_bg": "6366F1", "table_header_text": "FFFFFF", "table_row_bg1": "1E293B", "table_row_bg2": "0F172A", "table_row_text": "FFFFFF"},
    "purple": {"background": "1E1B4B", "gradient_start": "1E1B4B", "gradient_end": "31104B", "accent": "C084FC", "text": "FFFFFF", "badge": "C084FC", "table_header_bg": "7C3AED", "table_header_text": "FFFFFF", "table_row_bg1": "2D2766", "table_row_bg2": "1E1B4B", "table_row_text": "FFFFFF"},
    "blue": {"background": "06101E", "gradient_start": "06101E", "gradient_end": "134074", "accent": "60A5FA", "text": "FFFFFF", "badge": "60A5FA", "table_header_bg": "2563EB", "table_header_text": "FFFFFF", "table_row_bg1": "0B2545", "table_row_bg2": "06101E", "table_row_text": "FFFFFF"},
    "ocean_blue": {"background": "06101E", "gradient_start": "06101E", "gradient_end": "134074", "accent": "38BDF8", "text": "FFFFFF", "badge": "38BDF8", "table_header_bg": "0284C7", "table_header_text": "FFFFFF", "table_row_bg1": "0B2545", "table_row_bg2": "06101E", "table_row_text": "FFFFFF"},
    "emerald": {"background": "022C22", "gradient_start": "022C22", "gradient_end": "047857", "accent": "34D399", "text": "FFFFFF", "badge": "34D399", "table_header_bg": "059669", "table_header_text": "FFFFFF", "table_row_bg1": "064E3B", "table_row_bg2": "022C22", "table_row_text": "FFFFFF"},
    "emerald_dark": {"background": "022C22", "gradient_start": "022C22", "gradient_end": "047857", "accent": "34D399", "text": "FFFFFF", "badge": "34D399", "table_header_bg": "059669", "table_header_text": "FFFFFF", "table_row_bg1": "064E3B", "table_row_bg2": "022C22", "table_row_text": "FFFFFF"},
    "cyberpunk_neon": {"background": "09090B", "gradient_start": "09090B", "gradient_end": "581C87", "accent": "F43F5E", "text": "FFFFFF", "badge": "F43F5E", "table_header_bg": "E11D48", "table_header_text": "FFFFFF", "table_row_bg1": "2E1065", "table_row_bg2": "09090B", "table_row_text": "FFFFFF"},
    "wall_street": {"background": "022C22", "gradient_start": "022C22", "gradient_end": "1E293B", "accent": "10B981", "text": "FFFFFF", "badge": "10B981", "table_header_bg": "059669", "table_header_text": "FFFFFF", "table_row_bg1": "1E293B", "table_row_bg2": "022C22", "table_row_text": "FFFFFF"},
    "executive_gold": {"background": "1C1917", "gradient_start": "1C1917", "gradient_end": "78350F", "accent": "F59E0B", "text": "FFFFFF", "badge": "F59E0B", "table_header_bg": "D97706", "table_header_text": "FFFFFF", "table_row_bg1": "451A03", "table_row_bg2": "1C1917", "table_row_text": "FFFFFF"},
    "velvet_rose": {"background": "2A0813", "gradient_start": "2A0813", "gradient_end": "881337", "accent": "FB7185", "text": "FFFFFF", "badge": "FB7185", "table_header_bg": "E11D48", "table_header_text": "FFFFFF", "table_row_bg1": "4C0519", "table_row_bg2": "2A0813", "table_row_text": "FFFFFF"},
    "slate": {"background": "18181B", "gradient_start": "18181B", "gradient_end": "3F3F46", "accent": "6366F1", "text": "FFFFFF", "badge": "6366F1", "table_header_bg": "6366F1", "table_header_text": "FFFFFF", "table_row_bg1": "1E293B", "table_row_bg2": "0F172A", "table_row_text": "FFFFFF"},
    "executive_slate": {"background": "18181B", "gradient_start": "18181B", "gradient_end": "3F3F46", "accent": "6366F1", "text": "FFFFFF", "badge": "6366F1", "table_header_bg": "6366F1", "table_header_text": "FFFFFF", "table_row_bg1": "1E293B", "table_row_bg2": "0F172A", "table_row_text": "FFFFFF"},
    "titanium_white": {"background": "FFFFFF", "gradient_start": "FFFFFF", "gradient_end": "F4F4F5", "accent": "4F46E5", "text": "18181B", "badge": "4F46E5", "table_header_bg": "4F46E5", "table_header_text": "FFFFFF", "table_row_bg1": "F4F4F5", "table_row_bg2": "E4E4E7", "table_row_text": "18181B"},
    "sunset_glow": {"background": "2E1065", "gradient_start": "2E1065", "gradient_end": "9F1239", "accent": "FB7185", "text": "FFFFFF", "badge": "FB7185", "table_header_bg": "E11D48", "table_header_text": "FFFFFF", "table_row_bg1": "4C0519", "table_row_bg2": "2E1065", "table_row_text": "FFFFFF"},
    "ai": {"background": "0F172A", "gradient_start": "0F172A", "gradient_end": "31104B", "accent": "C084FC", "text": "F8FAFC", "badge": "C084FC", "table_header_bg": "6366F1", "table_header_text": "FFFFFF", "table_row_bg1": "1E293B", "table_row_bg2": "0F172A", "table_row_text": "FFFFFF"},
    "data": {"background": "1E1B4B", "gradient_start": "1E1B4B", "gradient_end": "31104B", "accent": "C084FC", "text": "FFFFFF", "badge": "C084FC", "table_header_bg": "7C3AED", "table_header_text": "FFFFFF", "table_row_bg1": "2D2766", "table_row_bg2": "1E1B4B", "table_row_text": "FFFFFF"},
    "startup": {"background": "1E1B4B", "gradient_start": "1E1B4B", "gradient_end": "7C2D12", "accent": "F97316", "text": "FFFFFF", "badge": "F97316", "table_header_bg": "EA580C", "table_header_text": "FFFFFF", "table_row_bg1": "431407", "table_row_bg2": "1E1B4B", "table_row_text": "FFFFFF"},
    "education": {"background": "FFFBEB", "gradient_start": "FFFBEB", "gradient_end": "FEF3C7", "accent": "D97706", "text": "451F00", "badge": "D97706", "table_header_bg": "D97706", "table_header_text": "FFFFFF", "table_row_bg1": "FEF3C7", "table_row_bg2": "FDE68A", "table_row_text": "451F00"},
    "finance": {"background": "0F172A", "gradient_start": "0F172A", "gradient_end": "14532D", "accent": "34D399", "text": "FFFFFF", "badge": "34D399", "table_header_bg": "10B981", "table_header_text": "FFFFFF", "table_row_bg1": "064E3B", "table_row_bg2": "0F172A", "table_row_text": "FFFFFF"},
    "medical": {"background": "FFF1F2", "gradient_start": "FFF1F2", "gradient_end": "FFE4E6", "accent": "E11D48", "text": "4C0519", "badge": "E11D48", "table_header_bg": "E11D48", "table_header_text": "FFFFFF", "table_row_bg1": "FFE4E6", "table_row_bg2": "FECDD3", "table_row_text": "4C0519"},
    "royal_violet": {"background": "2E1065", "gradient_start": "2E1065", "gradient_end": "581C87", "accent": "C084FC", "text": "FFFFFF", "badge": "C084FC", "table_header_bg": "7E22CE", "table_header_text": "FFFFFF", "table_row_bg1": "3B0764", "table_row_bg2": "2E1065", "table_row_text": "FFFFFF"},
    "nordic_frost": {"background": "082F49", "gradient_start": "082F49", "gradient_end": "0C4A6E", "accent": "38BDF8", "text": "FFFFFF", "badge": "38BDF8", "table_header_bg": "0284C7", "table_header_text": "FFFFFF", "table_row_bg1": "0F172A", "table_row_bg2": "082F49", "table_row_text": "FFFFFF"},
    "amber_bronze": {"background": "291E10", "gradient_start": "291E10", "gradient_end": "451A03", "accent": "F59E0B", "text": "FFFFFF", "badge": "F59E0B", "table_header_bg": "B45309", "table_header_text": "FFFFFF", "table_row_bg1": "451A03", "table_row_bg2": "291E10", "table_row_text": "FFFFFF"},
    "teal_cyan": {"background": "042F2E", "gradient_start": "042F2E", "gradient_end": "134E4A", "accent": "2DD4BF", "text": "FFFFFF", "badge": "2DD4BF", "table_header_bg": "0D9488", "table_header_text": "FFFFFF", "table_row_bg1": "134E4A", "table_row_bg2": "042F2E", "table_row_text": "FFFFFF"},
    "slate_dark": {"background": "0F172A", "gradient_start": "0F172A", "gradient_end": "1E293B", "accent": "94A3B8", "text": "FFFFFF", "badge": "94A3B8", "table_header_bg": "475569", "table_header_text": "FFFFFF", "table_row_bg1": "1E293B", "table_row_bg2": "0F172A", "table_row_text": "FFFFFF"},
    "monochrome_black": {"background": "000000", "gradient_start": "000000", "gradient_end": "0F172A", "accent": "E2E8F0", "text": "FFFFFF", "badge": "E2E8F0", "table_header_bg": "334155", "table_header_text": "FFFFFF", "table_row_bg1": "1E293B", "table_row_bg2": "000000", "table_row_text": "FFFFFF"},
    "default": {"background": "0F172A", "gradient_start": "0F172A", "gradient_end": "31104B", "accent": "C084FC", "text": "FFFFFF", "badge": "C084FC", "table_header_bg": "6366F1", "table_header_text": "FFFFFF", "table_row_bg1": "1E293B", "table_row_bg2": "0F172A", "table_row_text": "FFFFFF"},
}

THEME_KEYWORDS = {
    "ai": ["artificial intelligence", "machine learning", "deep learning", "neural", "llm", "genai", "generative ai", "model", "gpt", "rag", "bot"],
    "data": ["data", "analytics", "dashboard", "sql", "etl", "visualization", "insight", "big data", "warehouse", "bi"],
    "startup": ["startup", "mvp", "founder", "pitch", "product launch", "scale", "venture", "seed", "series a", "pitch deck"],
    "education": ["education", "school", "college", "student", "teacher", "course", "study", "university", "academic", "learning", "curriculum"],
    "finance": ["finance", "money", "budget", "bank", "investment", "trading", "portfolio", "accounting", "revenue", "ebitda", "profit"],
    "medical": ["medical", "health", "doctor", "clinic", "hospital", "patient", "diagnosis", "pharma", "clinical", "healthcare", "therapy"],
    "cyberpunk_neon": ["crypto", "blockchain", "metaverse", "web3", "nft", "gaming", "esports", "cyber", "neon", "hacker"],
    "executive_gold": ["luxury", "real estate", "premium", "wealth", "vip", "gold", "estate", "mansion", "exclusive"],
    "wall_street": ["stocks", "capital", "wall street", "banking", "equity", "hedge fund", "nasdaq", "forex", "market share"],
    "emerald": ["green", "eco", "sustainability", "environment", "climate", "nature", "esg", "solar", "renewable", "clean energy"],
    "ocean_blue": ["cloud", "saas", "infrastructure", "devops", "kubernetes", "aws", "azure", "docker", "marine", "maritime"],
    "nordic_frost": ["frost", "arctic", "cold", "snow", "ice", "nordic", "winter", "scandinavia"],
    "sunset_glow": ["creative", "design", "sunset", "media", "entertainment", "brand", "agency", "art", "fashion"],
    "velvet_rose": ["rose", "velvet", "beauty", "cosmetics", "lifestyle", "boutique", "romance", "wellness"],
    "academic": ["research", "thesis", "paper", "literature", "methodology", "empirical", "hypothesis", "study", "journal"],
}

VISUAL_STYLES = {
    "minimal": {"show_top_bar": False, "shadow": False},
    "corporate": {"show_top_bar": True, "shadow": False},
    "academic": {"show_top_bar": False, "shadow": False},
    "modern_gradient": {"show_top_bar": True, "shadow": True},
}


# ---------------------------------------------------------------------
# Color & Contrast Helpers
# ---------------------------------------------------------------------

def clean_str(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def hex_to_rgb(hex_color: str, default: Optional[RGBColor] = None) -> RGBColor:
    try:
        clean = (hex_color or "").replace("#", "").strip()
        if len(clean) == 3:
            clean = "".join(c * 2 for c in clean)
        return RGBColor.from_string(clean)
    except Exception:
        return default or RGBColor(15, 23, 42)


def calculate_luminance(rgb: RGBColor) -> float:
    def adjust(val: int) -> float:
        c = val / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * adjust(rgb[0]) + 0.7152 * adjust(rgb[1]) + 0.0722 * adjust(rgb[2])


def calculate_contrast_ratio(rgb1: RGBColor, rgb2: RGBColor) -> float:
    l1 = calculate_luminance(rgb1)
    l2 = calculate_luminance(rgb2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def ensure_readable_text_color(bg_rgb: RGBColor, preferred_text_rgb: RGBColor, min_ratio: float = 4.5) -> RGBColor:
    if calculate_contrast_ratio(bg_rgb, preferred_text_rgb) >= min_ratio:
        return preferred_text_rgb
    white = RGBColor(255, 255, 255)
    dark_slate = RGBColor(15, 23, 42)
    if calculate_contrast_ratio(bg_rgb, white) >= calculate_contrast_ratio(bg_rgb, dark_slate):
        return white
    return dark_slate


def is_light_color(rgb: RGBColor) -> bool:
    try:
        return calculate_luminance(rgb) > 0.4
    except Exception:
        return False


def detect_theme(text: str) -> str:
    raw = clean_str(text or "").lower()
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
    raw = clean_str(text or "").lower()
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
        bdg = theme_input.get("badge_color") or theme_input.get("slide_numbering_color") or theme_input.get("badge") or acc
        th_bg = theme_input.get("table_header_bg") or acc
        th_txt = theme_input.get("table_header_text") or "#FFFFFF"
        tr_bg1 = theme_input.get("table_row_bg1") or "#1E293B"
        tr_bg2 = theme_input.get("table_row_bg2") or bg
        tr_txt = theme_input.get("table_row_text") or txt

        bg_rgb = hex_to_rgb(bg)
        txt_rgb = hex_to_rgb(txt)
        acc_rgb = hex_to_rgb(acc)
        is_light = is_light_color(bg_rgb)

        card_bg_rgb = hex_to_rgb("#FFFFFF" if is_light else "#1E293B")
        card_border_rgb = acc_rgb
        card_txt_rgb = ensure_readable_text_color(card_bg_rgb, txt_rgb)

        return {
            "background": bg_rgb,
            "gradient_start": hex_to_rgb(g_start),
            "gradient_end": hex_to_rgb(g_end),
            "text": ensure_readable_text_color(bg_rgb, txt_rgb),
            "accent": acc_rgb,
            "badge": hex_to_rgb(bdg),
            "table_header_bg": hex_to_rgb(th_bg),
            "table_header_text": ensure_readable_text_color(hex_to_rgb(th_bg), hex_to_rgb(th_txt)),
            "table_row_bg1": hex_to_rgb(tr_bg1),
            "table_row_bg2": hex_to_rgb(tr_bg2),
            "table_row_text": hex_to_rgb(tr_txt),
            "card_bg": card_bg_rgb,
            "card_border": card_border_rgb,
            "card_text": card_txt_rgb,
            "accent_secondary": hex_to_rgb(bdg),
        }

    theme = clean_str(str(theme_input or "default")).lower()
    raw = THEME_COLORS.get(theme, THEME_COLORS["default"])
    bg_hex = raw["background"]
    g_start_hex = raw.get("gradient_start", bg_hex)
    g_end_hex = raw.get("gradient_end", bg_hex)
    badge_hex = raw.get("badge") or raw.get("accent")

    th_bg_hex = raw.get("table_header_bg") or raw.get("accent")
    th_txt_hex = raw.get("table_header_text") or "FFFFFF"
    tr_bg1_hex = raw.get("table_row_bg1") or "1E293B"
    tr_bg2_hex = raw.get("table_row_bg2") or bg_hex
    tr_txt_hex = raw.get("table_row_text") or raw.get("text")

    bg_rgb = hex_to_rgb(bg_hex)
    txt_rgb = hex_to_rgb(raw["text"])
    acc_rgb = hex_to_rgb(raw["accent"])
    is_light = is_light_color(bg_rgb)

    card_bg_rgb = hex_to_rgb("#FFFFFF" if is_light else "#1E293B")
    card_border_rgb = acc_rgb
    card_txt_rgb = ensure_readable_text_color(card_bg_rgb, txt_rgb)

    return {
        "background": bg_rgb,
        "gradient_start": hex_to_rgb(g_start_hex),
        "gradient_end": hex_to_rgb(g_end_hex),
        "accent": acc_rgb,
        "text": ensure_readable_text_color(bg_rgb, txt_rgb),
        "badge": hex_to_rgb(badge_hex),
        "table_header_bg": hex_to_rgb(th_bg_hex),
        "table_header_text": ensure_readable_text_color(hex_to_rgb(th_bg_hex), hex_to_rgb(th_txt_hex)),
        "table_row_bg1": hex_to_rgb(tr_bg1_hex),
        "table_row_bg2": hex_to_rgb(tr_bg2_hex),
        "table_row_text": hex_to_rgb(tr_txt_hex),
        "card_bg": card_bg_rgb,
        "card_border": card_border_rgb,
        "card_text": card_txt_rgb,
        "accent_secondary": hex_to_rgb(badge_hex),
    }


def get_chart_series_colors(theme_input: Any, num_series: int = 5) -> List[RGBColor]:
    palette = get_theme_palette(theme_input)
    accent = palette["accent"]
    badge = palette["badge"]
    header = palette["table_header_bg"]

    def adjust_rgb(base: RGBColor, factor_r: float, factor_g: float, factor_b: float) -> RGBColor:
        r = max(0, min(255, int(base[0] * factor_r)))
        g = max(0, min(255, int(base[1] * factor_g)))
        b = max(0, min(255, int(base[2] * factor_b)))
        return RGBColor(r, g, b)

    series_candidates = [
        accent,
        header,
        badge,
        adjust_rgb(accent, 0.7, 1.2, 0.9),
        adjust_rgb(header, 1.3, 0.8, 1.1),
        adjust_rgb(accent, 1.2, 0.9, 0.6),
        adjust_rgb(badge, 0.6, 1.1, 1.3),
    ]
    unique: List[RGBColor] = []
    for c in series_candidates:
        if not any(c[0] == u[0] and c[1] == u[1] and c[2] == u[2] for u in unique):
            unique.append(c)
        if len(unique) >= num_series:
            break

    while len(unique) < num_series:
        unique.append(adjust_rgb(accent, 0.8 + 0.05 * len(unique), 1.1 - 0.05 * len(unique), 1.0))

    return unique[:num_series]


def get_visual_style(style_name: Optional[str]) -> Dict[str, Any]:
    style = clean_str(style_name or "minimal").lower()
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

