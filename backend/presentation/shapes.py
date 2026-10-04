from __future__ import annotations

import collections
import collections.abc
if not hasattr(collections, "Container"):
    collections.Container = collections.abc.Container
if not hasattr(collections, "Mapping"):
    collections.Mapping = collections.abc.Mapping
if not hasattr(collections, "MutableMapping"):
    collections.MutableMapping = collections.abc.MutableMapping
if not hasattr(collections, "Sequence"):
    collections.Sequence = collections.abc.Sequence
if not hasattr(collections, "MutableSequence"):
    collections.MutableSequence = collections.abc.MutableSequence
if not hasattr(collections, "Iterable"):
    collections.Iterable = collections.abc.Iterable

import hashlib
import logging
import math
import random
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

from backend.presentation.geometry import (
    Box,
    LEFT_MARGIN,
    RIGHT_MARGIN,
    TOP_MARGIN,
    BOTTOM_MARGIN,
    TITLE_TOP,
    SLIDE_WIDTH,
    SLIDE_HEIGHT,
    SAFE_CONTENT_BOTTOM,
    CONTENT_TOP_DEFAULT,
    as_box,
    calculate_available_content_height,
    calculate_available_content_width,
)
from backend.presentation.schemas import (
    ShapeSpec,
    SlideSpec,
    PresentationPlan,
    DecorationQualityReport,
    VisualIntent,
    ContentIntent,
)
from backend.presentation.themes import (
    THEME_COLORS,
    get_theme_palette,
    hex_to_rgb,
    is_light_color,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Constants & Enums
# ---------------------------------------------------------------------

class ShapeType:
    # Basic & Geometric
    CIRCLE = "CIRCLE"
    RING = "RING"
    DOT = "DOT"
    ROUNDED_RECT = "ROUNDED_RECT"
    RECTANGLE = "RECTANGLE"
    LINE = "LINE"
    ARC = "ARC"
    WAVE = "WAVE"
    BLOB = "BLOB"
    POLYGON = "POLYGON"
    DIAGONAL_BLOCK = "DIAGONAL_BLOCK"
    CORNER_BRACKET = "CORNER_BRACKET"
    ACCENT_BAR = "ACCENT_BAR"
    PILL = "PILL"
    GRID_PATTERN = "GRID_PATTERN"
    SOFT_CIRCLE = "SOFT_CIRCLE"
    ABSTRACT_ORB = "ABSTRACT_ORB"
    CONNECTOR_ARROW = "CONNECTOR_ARROW"
    DIAMOND = "DIAMOND"
    HEXAGON = "HEXAGON"
    TRIANGLE = "TRIANGLE"


class ShapePurpose:
    SEMANTIC = "semantic"
    DECORATIVE = "decorative"
    BACKGROUND = "background"
    CONNECTOR = "connector"
    CONTAINER = "container"


class SemanticRole:
    CARD = "CARD"
    PROCESS_NODE = "PROCESS_NODE"
    TIMELINE_NODE = "TIMELINE_NODE"
    COMPARISON_PANEL = "COMPARISON_PANEL"
    KPI_CONTAINER = "KPI_CONTAINER"
    CALLOUT = "CALLOUT"
    BENTO_CARD = "BENTO_CARD"
    DIAGRAM_NODE = "DIAGRAM_NODE"
    SECTION_BLOCK = "SECTION_BLOCK"
    PROBLEM_BLOCK = "PROBLEM_BLOCK"
    SOLUTION_BLOCK = "SOLUTION_BLOCK"
    RESULT_BLOCK = "RESULT_BLOCK"


# Explicit Layering Z-Indices
Z_BACKGROUND = 0
Z_DECORATIVE_BACKGROUND = 10
Z_DECORATIVE_ACCENT = 15
Z_SEMANTIC_CONTAINER = 20
Z_MEDIA = 30
Z_TEXT = 40
Z_FOREGROUND = 50

# Safe Area Constants
SAFE_MARGIN = 0.25
TITLE_SAFE_TOP = 0.50
TITLE_SAFE_HEIGHT = 1.0


# ---------------------------------------------------------------------
# Shape Factory
# ---------------------------------------------------------------------

def create_shape(
    shape_type: str,
    x: float,
    y: float,
    width: float,
    height: float,
    fill: Optional[str] = None,
    line_color: Optional[str] = None,
    line_width: Optional[float] = None,
    line_style: Optional[str] = "solid",
    opacity: float = 1.0,
    z_index: int = Z_DECORATIVE_BACKGROUND,
    purpose: str = ShapePurpose.DECORATIVE,
    decorative: bool = True,
    semantic_role: Optional[str] = None,
    visual_role: Optional[str] = None,
    rotation: float = 0.0,
    corner_radius: Optional[float] = None,
    shape_id: Optional[str] = None,
) -> ShapeSpec:
    """Factory helper creating validated ShapeSpec instances."""
    if not shape_id:
        clean_name = re.sub(r"[^a-zA-Z0-9_]+", "", str(shape_type).lower())
        shape_id = f"shape_{clean_name}_{int(x*100)}_{int(y*100)}"

    return ShapeSpec(
        id=shape_id,
        shape_type=shape_type.upper(),
        x=round(float(x), 3),
        y=round(float(y), 3),
        width=round(float(width), 3),
        height=round(float(height), 3),
        fill=fill,
        line_color=line_color,
        line_width=line_width,
        line_style=line_style,
        opacity=max(0.0, min(1.0, float(opacity))),
        z_index=z_index,
        purpose=purpose,
        decorative=decorative,
        semantic_role=semantic_role,
        visual_role=visual_role,
        rotation=round(float(rotation), 1),
        corner_radius=corner_radius,
    )


# ---------------------------------------------------------------------
# Theme Color Extraction
# ---------------------------------------------------------------------

def derive_shape_palette(theme_input: Any) -> Dict[str, str]:
    """Derives standard hex palette roles for shapes from active presentation theme."""
    raw_theme = "default"
    if isinstance(theme_input, str):
        raw_theme = theme_input.strip().lower()
    elif isinstance(theme_input, dict):
        raw_theme = str(theme_input.get("name", "default")).strip().lower()

    base_dict = THEME_COLORS.get(raw_theme, THEME_COLORS["default"])

    bg_hex = base_dict["background"] if base_dict["background"].startswith("#") else f"#{base_dict['background']}"
    acc_hex = base_dict["accent"] if base_dict["accent"].startswith("#") else f"#{base_dict['accent']}"
    txt_hex = base_dict["text"] if base_dict["text"].startswith("#") else f"#{base_dict['text']}"
    g_end_hex = base_dict.get("gradient_end", base_dict["background"])
    g_end_hex = g_end_hex if g_end_hex.startswith("#") else f"#{g_end_hex}"

    is_light = is_light_color(hex_to_rgb(bg_hex))
    surface_hex = "#FFFFFF" if is_light else "#1E293B"
    muted_hex = "#64748B" if is_light else "#94A3B8"
    border_hex = acc_hex

    # If user provided custom theme dict, override
    if isinstance(theme_input, dict):
        if "primary" in theme_input:
            acc_hex = theme_input["primary"]
        if "accent" in theme_input:
            acc_hex = theme_input["accent"]
        if "background" in theme_input:
            bg_hex = theme_input["background"]
        if "text" in theme_input:
            txt_hex = theme_input["text"]

    return {
        "primary": acc_hex,
        "secondary": g_end_hex,
        "accent": acc_hex,
        "background": bg_hex,
        "surface": surface_hex,
        "muted": muted_hex,
        "border": border_hex,
    }


# ---------------------------------------------------------------------
# Content Region Extraction & Collision Detection
# ---------------------------------------------------------------------

def extract_content_regions(
    slide_spec: SlideSpec,
    title_y: float = TITLE_TOP,
    content_y: float = CONTENT_TOP_DEFAULT,
) -> List[Box]:
    """Extracts bounding boxes for all meaningful content regions on a slide."""
    regions: List[Box] = []

    # 1. Title & Subtitle Bounding Region
    has_title = bool(slide_spec.title and slide_spec.title.strip())
    has_subtitle = bool(slide_spec.subtitle and slide_spec.subtitle.strip())

    if slide_spec.layout in {"title_slide", "title_subtitle"} or (not slide_spec.plugins and has_title):
        # Cover slide title box is centered and taller
        regions.append(Box(left=1.0, top=2.0, width=11.3, height=3.2))
    elif has_title:
        title_h = 0.9 if has_subtitle else 0.6
        regions.append(Box(left=LEFT_MARGIN, top=title_y, width=11.7, height=title_h))

    # 2. Content Plugins Bounding Regions
    for p in slide_spec.plugins:
        if p.type in ("notes", "speaker_notes"):
            continue
        p_data = p.data if isinstance(p.data, dict) else {}
        if "box" in p_data and isinstance(p_data["box"], dict):
            b_dict = p_data["box"]
            regions.append(Box(
                left=float(b_dict.get("left", LEFT_MARGIN)),
                top=float(b_dict.get("top", content_y)),
                width=float(b_dict.get("width", 11.7)),
                height=float(b_dict.get("height", 4.5)),
            ))
        elif p.type == "image":
            regions.append(Box(left=7.2, top=content_y, width=5.2, height=4.5))
        elif p.type in {"chart", "table", "diagram", "process_flow", "bento_grid", "kpi_grid", "split_layout"}:
            regions.append(Box(left=LEFT_MARGIN, top=content_y, width=11.7, height=4.8))
        elif p.type in {"bullets", "paragraph"}:
            regions.append(Box(left=LEFT_MARGIN, top=content_y, width=11.7, height=3.5))

    # 3. Footer Exclusion Zone
    regions.append(Box(left=0.0, top=SAFE_CONTENT_BOTTOM, width=SLIDE_WIDTH, height=SLIDE_HEIGHT - SAFE_CONTENT_BOTTOM))

    return regions


class CollisionDetector:
    """Detects and resolves geometric collisions between decorative shapes and slide content."""

    @classmethod
    def check_collision(
        cls,
        shape: ShapeSpec,
        content_boxes: List[Box],
        tolerance: float = 0.05,
    ) -> bool:
        """
        Returns True if decorative shape collides with any protected content box.
        Very faint large background shapes (opacity <= 0.12, z_index <= 10) are permitted
        behind content as soft ambient glow, but higher-opacity accents must NOT collide.
        """
        shape_box = Box(shape.x, shape.y, shape.width, shape.height)

        # Ambient background shapes with very low opacity are non-blocking
        if shape.opacity <= 0.12 and shape.z_index <= Z_DECORATIVE_BACKGROUND:
            return False

        for box in content_boxes:
            if shape_box.intersects(box, tolerance=tolerance):
                return True
        return False

    @classmethod
    def resolve_collision(
        cls,
        shape: ShapeSpec,
        content_boxes: List[Box],
    ) -> Optional[ShapeSpec]:
        """
        Attempts to resolve collision:
        1. Reposition to empty whitespace quadrant
        2. Resize / scale down
        3. Reduce opacity to ambient background level
        4. Drop shape if unresolvable
        """
        if not cls.check_collision(shape, content_boxes):
            return shape

        # Strategy 1: Test alternative whitespace anchor positions
        quadrants = [
            (SLIDE_WIDTH - shape.width - 0.4, 0.4),            # Top-Right
            (0.4, SLIDE_HEIGHT - shape.height - 0.9),          # Bottom-Left
            (SLIDE_WIDTH - shape.width - 0.4, SLIDE_HEIGHT - shape.height - 0.9),  # Bottom-Right
            (0.4, 0.4),                                        # Top-Left
        ]

        for qx, qy in quadrants:
            test_shape = create_shape(
                shape_type=shape.shape_type,
                x=qx,
                y=qy,
                width=shape.width,
                height=shape.height,
                fill=shape.fill,
                line_color=shape.line_color,
                line_width=shape.line_width,
                line_style=shape.line_style,
                opacity=shape.opacity,
                z_index=shape.z_index,
                purpose=shape.purpose,
                decorative=shape.decorative,
                semantic_role=shape.semantic_role,
                visual_role=shape.visual_role,
                rotation=shape.rotation,
                corner_radius=shape.corner_radius,
                shape_id=shape.id,
            )
            if not cls.check_collision(test_shape, content_boxes):
                return test_shape

        # Strategy 2: Resize / Scale down
        scaled_w = round(shape.width * 0.65, 2)
        scaled_h = round(shape.height * 0.65, 2)
        scaled_shape = create_shape(
            shape_type=shape.shape_type,
            x=shape.x,
            y=shape.y,
            width=scaled_w,
            height=scaled_h,
            fill=shape.fill,
            line_color=shape.line_color,
            line_width=shape.line_width,
            line_style=shape.line_style,
            opacity=shape.opacity,
            z_index=shape.z_index,
            purpose=shape.purpose,
            decorative=shape.decorative,
            semantic_role=shape.semantic_role,
            visual_role=shape.visual_role,
            rotation=shape.rotation,
            corner_radius=shape.corner_radius,
            shape_id=shape.id,
        )
        if not cls.check_collision(scaled_shape, content_boxes):
            return scaled_shape

        # Strategy 3: Push to ambient background layer with low opacity
        ambient_shape = create_shape(
            shape_type=shape.shape_type,
            x=shape.x,
            y=shape.y,
            width=shape.width,
            height=shape.height,
            fill=shape.fill,
            line_color=None,
            line_width=None,
            opacity=0.08,
            z_index=Z_DECORATIVE_BACKGROUND,
            purpose=ShapePurpose.BACKGROUND,
            decorative=True,
            visual_role=f"{shape.visual_role or 'ambient'}_demoted",
            rotation=shape.rotation,
            shape_id=shape.id,
        )
        return ambient_shape


# ---------------------------------------------------------------------
# Semantic Shape Engine
# ---------------------------------------------------------------------

class SemanticShapeEngine:
    """Generates structural information shapes (containers, process nodes, comparison panels, bento cards)."""

    @classmethod
    def generate_semantic_shapes(
        cls,
        slide_spec: SlideSpec,
        theme_palette: Dict[str, str],
    ) -> List[ShapeSpec]:
        shapes: List[ShapeSpec] = []
        intent = getattr(slide_spec, "visual_intent", None)

        card_fill = theme_palette.get("surface", "#1E293B")
        border_color = theme_palette.get("border", theme_palette["primary"])

        # Check visual plugins and generate corresponding semantic containers
        for idx, plugin in enumerate(slide_spec.plugins):
            p_data = plugin.data if isinstance(plugin.data, dict) else {}
            box_data = p_data.get("box", {})
            bx = float(box_data.get("left", LEFT_MARGIN))
            by = float(box_data.get("top", CONTENT_TOP_DEFAULT))
            bw = float(box_data.get("width", 11.7))
            bh = float(box_data.get("height", 4.5))

            if plugin.type in {"kpi_grid", "stat"}:
                shapes.append(create_shape(
                    shape_type=ShapeType.ROUNDED_RECT,
                    x=bx,
                    y=by,
                    width=bw,
                    height=bh,
                    fill=card_fill,
                    line_color=border_color,
                    line_width=1.0,
                    opacity=1.0,
                    z_index=Z_SEMANTIC_CONTAINER,
                    purpose=ShapePurpose.CONTAINER,
                    decorative=False,
                    semantic_role=SemanticRole.KPI_CONTAINER,
                    visual_role="kpi_panel_container",
                    corner_radius=0.15,
                    shape_id=f"sem_kpi_{idx}",
                ))
            elif plugin.type == "process_flow":
                steps = p_data.get("steps") or []
                num_s = max(1, len(steps))
                gap = 0.25
                node_w = (bw - (gap * (num_s - 1))) / num_s
                for s_idx in range(num_s):
                    nx = bx + s_idx * (node_w + gap)
                    shapes.append(create_shape(
                        shape_type=ShapeType.ROUNDED_RECT,
                        x=nx,
                        y=by,
                        width=node_w,
                        height=bh,
                        fill=card_fill,
                        line_color=border_color,
                        line_width=1.0,
                        opacity=1.0,
                        z_index=Z_SEMANTIC_CONTAINER,
                        purpose=ShapePurpose.SEMANTIC,
                        decorative=False,
                        semantic_role=SemanticRole.PROCESS_NODE,
                        visual_role=f"process_step_{s_idx+1}_node",
                        corner_radius=0.12,
                        shape_id=f"sem_proc_node_{idx}_{s_idx}",
                    ))
            elif plugin.type == "bento_grid":
                hero_w = round(bw * 0.56, 2)
                right_w = round(bw - hero_w - 0.25, 2)
                right_left = bx + hero_w + 0.25
                # Hero card
                shapes.append(create_shape(
                    shape_type=ShapeType.ROUNDED_RECT,
                    x=bx,
                    y=by,
                    width=hero_w,
                    height=bh,
                    fill=card_fill,
                    line_color=border_color,
                    line_width=1.2,
                    opacity=1.0,
                    z_index=Z_SEMANTIC_CONTAINER,
                    purpose=ShapePurpose.CONTAINER,
                    decorative=False,
                    semantic_role=SemanticRole.BENTO_CARD,
                    visual_role="bento_hero_container",
                    corner_radius=0.15,
                    shape_id=f"sem_bento_hero_{idx}",
                ))
                # Right upper/lower cards
                sub_h = round((bh - 0.25) / 2.0, 2)
                shapes.append(create_shape(
                    shape_type=ShapeType.ROUNDED_RECT,
                    x=right_left,
                    y=by,
                    width=right_w,
                    height=sub_h,
                    fill=card_fill,
                    line_color=border_color,
                    line_width=1.0,
                    opacity=1.0,
                    z_index=Z_SEMANTIC_CONTAINER,
                    purpose=ShapePurpose.CONTAINER,
                    decorative=False,
                    semantic_role=SemanticRole.BENTO_CARD,
                    visual_role="bento_feature_container",
                    corner_radius=0.12,
                    shape_id=f"sem_bento_feat_{idx}",
                ))
                shapes.append(create_shape(
                    shape_type=ShapeType.ROUNDED_RECT,
                    x=right_left,
                    y=by + sub_h + 0.25,
                    width=right_w,
                    height=sub_h,
                    fill=card_fill,
                    line_color=border_color,
                    line_width=1.0,
                    opacity=1.0,
                    z_index=Z_SEMANTIC_CONTAINER,
                    purpose=ShapePurpose.CONTAINER,
                    decorative=False,
                    semantic_role=SemanticRole.BENTO_CARD,
                    visual_role="bento_stat_container",
                    corner_radius=0.12,
                    shape_id=f"sem_bento_stat_{idx}",
                ))
            elif plugin.type in {"split_layout", "pros_cons"}:
                panel_w = round((bw - 0.3) / 2.0, 2)
                shapes.append(create_shape(
                    shape_type=ShapeType.ROUNDED_RECT,
                    x=bx,
                    y=by,
                    width=panel_w,
                    height=bh,
                    fill=card_fill,
                    line_color="#10B981" if plugin.type == "pros_cons" else border_color,
                    line_width=1.0,
                    opacity=1.0,
                    z_index=Z_SEMANTIC_CONTAINER,
                    purpose=ShapePurpose.CONTAINER,
                    decorative=False,
                    semantic_role=SemanticRole.COMPARISON_PANEL,
                    visual_role="comparison_left_panel",
                    corner_radius=0.12,
                    shape_id=f"sem_comp_left_{idx}",
                ))
                shapes.append(create_shape(
                    shape_type=ShapeType.ROUNDED_RECT,
                    x=bx + panel_w + 0.3,
                    y=by,
                    width=panel_w,
                    height=bh,
                    fill=card_fill,
                    line_color="#EF4444" if plugin.type == "pros_cons" else border_color,
                    line_width=1.0,
                    opacity=1.0,
                    z_index=Z_SEMANTIC_CONTAINER,
                    purpose=ShapePurpose.CONTAINER,
                    decorative=False,
                    semantic_role=SemanticRole.COMPARISON_PANEL,
                    visual_role="comparison_right_panel",
                    corner_radius=0.12,
                    shape_id=f"sem_comp_right_{idx}",
                ))

        return shapes


# ---------------------------------------------------------------------
# Decorative Shape Engine
# ---------------------------------------------------------------------

class DecorativeShapeEngine:
    """
    Intelligent Decorative Shape Engine:
    Selects, places, and validates theme-aware, composition-enhancing decorative shapes
    with strict collision avoidance and slide-rhythm sensitivity.
    """

    @classmethod
    def generate_decorations(
        cls,
        slide: SlideSpec,
        slide_type: str,
        theme: Any,
        content_regions: Optional[List[Box]] = None,
        semantic_shapes: Optional[List[ShapeSpec]] = None,
        seed: int = 42,
    ) -> List[ShapeSpec]:
        palette = derive_shape_palette(theme)
        regions = content_regions if content_regions is not None else extract_content_regions(slide)

        candidates: List[ShapeSpec] = []
        primary_c = palette["primary"]
        secondary_c = palette["secondary"]
        muted_c = palette["muted"]
        border_c = palette["border"]

        s_type = (slide_type or slide.layout or "standard").lower()
        t_lower = (slide.title or "").lower()

        # -------------------------------------------------------------
        # 1. THANK YOU / CLOSING SLIDE PRESET (1–3 elements)
        # -------------------------------------------------------------
        if slide.is_closing_slide or any(kw in t_lower for kw in ["thank you", "thanks", "q&a", "questions"]):
            candidates.append(create_shape(
                shape_type=ShapeType.ABSTRACT_ORB,
                x=9.2,
                y=0.6,
                width=3.6,
                height=3.6,
                fill=primary_c,
                opacity=0.10,
                z_index=Z_DECORATIVE_BACKGROUND,
                visual_role="thankyou_ambient_glow",
                shape_id="ty_bg_orb",
            ))
            candidates.append(create_shape(
                shape_type=ShapeType.RING,
                x=0.8,
                y=5.2,
                width=1.1,
                height=1.1,
                fill="transparent",
                line_color=primary_c,
                line_width=1.5,
                opacity=0.35,
                z_index=Z_DECORATIVE_ACCENT,
                visual_role="thankyou_corner_ring",
                shape_id="ty_corner_ring",
            ))
            candidates.append(create_shape(
                shape_type=ShapeType.ACCENT_BAR,
                x=4.6,
                y=4.2,
                width=4.1,
                height=0.04,
                fill=primary_c,
                opacity=0.80,
                z_index=Z_DECORATIVE_ACCENT,
                visual_role="thankyou_center_accent_line",
                shape_id="ty_accent_line",
            ))

        # -------------------------------------------------------------
        # 2. TITLE SLIDE DECORATION PRESET (2–4 elements)
        # -------------------------------------------------------------
        elif s_type in {"title_slide", "title_subtitle"} or (not slide.plugins and t_lower not in {"conclusion"}):
            # Large elegant background orb in top-right
            candidates.append(create_shape(
                shape_type=ShapeType.ABSTRACT_ORB,
                x=9.8,
                y=0.4,
                width=3.2,
                height=3.2,
                fill=primary_c,
                opacity=0.09,
                z_index=Z_DECORATIVE_BACKGROUND,
                visual_role="title_ambient_glow_orb",
                shape_id="title_bg_orb",
            ))
            # Subtle diagonal corner block in bottom-right
            candidates.append(create_shape(
                shape_type=ShapeType.DIAGONAL_BLOCK,
                x=10.5,
                y=4.8,
                width=2.5,
                height=2.2,
                fill=secondary_c,
                opacity=0.12,
                z_index=Z_DECORATIVE_BACKGROUND,
                rotation=45.0,
                visual_role="title_diagonal_geometric_block",
                shape_id="title_diag_block",
            ))
            # Thin crisp accent bar below title badge
            candidates.append(create_shape(
                shape_type=ShapeType.ACCENT_BAR,
                x=LEFT_MARGIN,
                y=1.65,
                width=1.8,
                height=0.04,
                fill=primary_c,
                opacity=0.85,
                z_index=Z_DECORATIVE_ACCENT,
                visual_role="title_hero_accent_bar",
                shape_id="title_accent_bar",
            ))
            # Small minimalist decorative ring in top-left
            candidates.append(create_shape(
                shape_type=ShapeType.RING,
                x=0.6,
                y=0.6,
                width=0.65,
                height=0.65,
                fill="transparent",
                line_color=primary_c,
                line_width=1.2,
                opacity=0.40,
                z_index=Z_DECORATIVE_ACCENT,
                visual_role="title_top_left_ring",
                shape_id="title_tl_ring",
            ))

        # -------------------------------------------------------------
        # 3. SECTION SLIDE DECORATION PRESET (2–3 elements)
        # -------------------------------------------------------------
        elif s_type in {"section_slide", "section_header"}:
            candidates.append(create_shape(
                shape_type=ShapeType.ABSTRACT_ORB,
                x=8.5,
                y=1.0,
                width=4.5,
                height=4.5,
                fill=primary_c,
                opacity=0.10,
                z_index=Z_DECORATIVE_BACKGROUND,
                visual_role="section_background_orb",
                shape_id="sec_bg_orb",
            ))
            candidates.append(create_shape(
                shape_type=ShapeType.ACCENT_BAR,
                x=LEFT_MARGIN,
                y=3.8,
                width=2.4,
                height=0.06,
                fill=primary_c,
                opacity=0.90,
                z_index=Z_DECORATIVE_ACCENT,
                visual_role="section_divider_bar",
                shape_id="sec_bar",
            ))

        # -------------------------------------------------------------
        # 4. PROCESS / WORKFLOW SLIDE PRESET (Process-specific accents)
        # -------------------------------------------------------------
        elif s_type in {"process_flow", "process"} or slide.visual_intent in {VisualIntent.PROCESS_FLOW, VisualIntent.PROCESS}:
            candidates.append(create_shape(
                shape_type=ShapeType.ACCENT_BAR,
                x=LEFT_MARGIN,
                y=1.35,
                width=11.7,
                height=0.02,
                fill=border_c,
                opacity=0.40,
                z_index=Z_DECORATIVE_BACKGROUND,
                visual_role="process_guideline_track",
                shape_id="proc_track_bar",
            ))
            candidates.append(create_shape(
                shape_type=ShapeType.DOT,
                x=12.2,
                y=0.65,
                width=0.16,
                height=0.16,
                fill=primary_c,
                opacity=0.80,
                z_index=Z_DECORATIVE_ACCENT,
                visual_role="process_status_dot",
                shape_id="proc_status_dot",
            ))

        # -------------------------------------------------------------
        # 5. COMPARISON / SPLIT SLIDE PRESET (Divider & Header Accents)
        # -------------------------------------------------------------
        elif s_type in {"table_slide", "comparison", "split_layout", "pros_cons"} or slide.visual_intent in {VisualIntent.COMPARISON, VisualIntent.SPLIT_PROBLEM_SOLUTION}:
            candidates.append(create_shape(
                shape_type=ShapeType.ACCENT_BAR,
                x=LEFT_MARGIN,
                y=1.38,
                width=11.7,
                height=0.02,
                fill=border_c,
                opacity=0.35,
                z_index=Z_DECORATIVE_BACKGROUND,
                visual_role="comparison_header_divider",
                shape_id="comp_divider_bar",
            ))
            candidates.append(create_shape(
                shape_type=ShapeType.CORNER_BRACKET,
                x=12.1,
                y=0.55,
                width=0.4,
                height=0.4,
                fill="transparent",
                line_color=primary_c,
                line_width=1.0,
                opacity=0.50,
                z_index=Z_DECORATIVE_ACCENT,
                visual_role="comparison_corner_bracket",
                shape_id="comp_corner_bracket",
            ))

        # -------------------------------------------------------------
        # 6. KPI SLIDE PRESET (Subtle ring & ambient halo)
        # -------------------------------------------------------------
        elif s_type in {"kpi_grid", "chart_slide"} or slide.visual_intent in {VisualIntent.KPI_GRID, VisualIntent.KPI}:
            candidates.append(create_shape(
                shape_type=ShapeType.ABSTRACT_ORB,
                x=9.5,
                y=1.5,
                width=3.5,
                height=3.5,
                fill=primary_c,
                opacity=0.07,
                z_index=Z_DECORATIVE_BACKGROUND,
                visual_role="kpi_ambient_halo",
                shape_id="kpi_bg_halo",
            ))
            candidates.append(create_shape(
                shape_type=ShapeType.RING,
                x=12.0,
                y=0.55,
                width=0.45,
                height=0.45,
                fill="transparent",
                line_color=primary_c,
                line_width=1.2,
                opacity=0.60,
                z_index=Z_DECORATIVE_ACCENT,
                visual_role="kpi_telemetry_ring",
                shape_id="kpi_ring",
            ))

        # -------------------------------------------------------------
        # 7. TIMELINE SLIDE PRESET (Milestone accents)
        # -------------------------------------------------------------
        elif slide.visual_intent == VisualIntent.TIMELINE or any(kw in t_lower for kw in ["timeline", "roadmap", "milestones", "evolution"]):
            candidates.append(create_shape(
                shape_type=ShapeType.LINE,
                x=LEFT_MARGIN,
                y=1.35,
                width=11.7,
                height=0.02,
                fill=primary_c,
                line_color=primary_c,
                line_width=1.0,
                opacity=0.60,
                z_index=Z_DECORATIVE_BACKGROUND,
                visual_role="timeline_axis_accent",
                shape_id="timeline_axis",
            ))

        # -------------------------------------------------------------
        # 8. BENTO / STRATEGIC SUMMARY PRESET (Subtle framing & corner accents)
        # -------------------------------------------------------------
        elif s_type == "bento_grid" or slide.visual_intent in {VisualIntent.BENTO_OVERVIEW, VisualIntent.STRATEGIC_SUMMARY}:
            candidates.append(create_shape(
                shape_type=ShapeType.ABSTRACT_ORB,
                x=0.2,
                y=1.2,
                width=3.0,
                height=3.0,
                fill=primary_c,
                opacity=0.06,
                z_index=Z_DECORATIVE_BACKGROUND,
                visual_role="bento_ambient_hero_glow",
                shape_id="bento_hero_glow",
            ))
            candidates.append(create_shape(
                shape_type=ShapeType.DOT,
                x=12.2,
                y=0.65,
                width=0.15,
                height=0.15,
                fill=primary_c,
                opacity=0.75,
                z_index=Z_DECORATIVE_ACCENT,
                visual_role="bento_status_dot",
                shape_id="bento_dot",
            ))

        # -------------------------------------------------------------
        # 9. IMAGE SLIDE PRESET (Framing accents strictly avoiding image)
        # -------------------------------------------------------------
        elif s_type == "image_slide" or any(p.type == "image" for p in slide.plugins):
            candidates.append(create_shape(
                shape_type=ShapeType.CORNER_BRACKET,
                x=0.6,
                y=0.55,
                width=0.45,
                height=0.45,
                fill="transparent",
                line_color=primary_c,
                line_width=1.2,
                opacity=0.60,
                z_index=Z_DECORATIVE_ACCENT,
                visual_role="image_frame_bracket",
                shape_id="img_bracket",
            ))

        # -------------------------------------------------------------
        # 10. STANDARD CONTENT SLIDE PRESET (1–2 subtle accents)
        # -------------------------------------------------------------
        else:
            candidates.append(create_shape(
                shape_type=ShapeType.ACCENT_BAR,
                x=LEFT_MARGIN,
                y=1.35,
                width=1.2,
                height=0.03,
                fill=primary_c,
                opacity=0.75,
                z_index=Z_DECORATIVE_ACCENT,
                visual_role="standard_title_sub_bar",
                shape_id="std_sub_bar",
            ))
            candidates.append(create_shape(
                shape_type=ShapeType.DOT,
                x=12.3,
                y=0.65,
                width=0.14,
                height=0.14,
                fill=primary_c,
                opacity=0.70,
                z_index=Z_DECORATIVE_ACCENT,
                visual_role="standard_top_dot",
                shape_id="std_dot",
            ))

        # -------------------------------------------------------------
        # Collision Resolution & Quality Gating
        # -------------------------------------------------------------
        validated_decorations: List[ShapeSpec] = []
        for cand in candidates:
            resolved = CollisionDetector.resolve_collision(cand, regions)
            if resolved is not None:
                validated_decorations.append(resolved)

        return validated_decorations

    @classmethod
    def decorate_slide(
        cls,
        slide_spec: SlideSpec,
        slide_idx: int = 0,
        total_slides: int = 8,
        theme: Any = "default",
        presentation_title: str = "",
    ) -> SlideSpec:
        """Decorates a single slide with both semantic and decorative shapes."""
        theme_palette = derive_shape_palette(theme)
        content_boxes = extract_content_regions(slide_spec)

        # 1. Generate semantic shapes
        sem_shapes = SemanticShapeEngine.generate_semantic_shapes(slide_spec, theme_palette)

        # 2. Derive deterministic seed for visual rhythm
        seed_str = f"{presentation_title}_{slide_spec.title}_{slide_idx}"
        seed_val = int(hashlib.md5(seed_str.encode("utf-8")).hexdigest()[:8], 16)

        # 3. Generate decorative shapes
        dec_shapes = cls.generate_decorations(
            slide=slide_spec,
            slide_type=slide_spec.layout or "standard",
            theme=theme,
            content_regions=content_boxes,
            semantic_shapes=sem_shapes,
            seed=seed_val,
        )

        all_shapes = sem_shapes + dec_shapes

        # 4. Attach decoration quality report
        dec_report = DecorationQualityValidator.validate_slide_decorations(slide_spec, dec_shapes, content_boxes)
        
        copy_obj = getattr(slide_spec, "model_copy", slide_spec.copy)
        updated_slide = copy_obj(update={"shapes": all_shapes})
        if updated_slide.quality_report:
            updated_slide.quality_report.decoration_quality = dec_report
        return updated_slide

    @classmethod
    def decorate_presentation_plan(cls, plan: PresentationPlan) -> PresentationPlan:
        """Applies consistent, rhythm-aware shape decoration across all slides in a presentation plan."""
        if not plan or not plan.slides:
            return plan

        decorated_slides: List[SlideSpec] = []
        total = len(plan.slides)
        theme = plan.theme or "default"

        for idx, s in enumerate(plan.slides):
            dec_slide = cls.decorate_slide(
                slide_spec=s,
                slide_idx=idx,
                total_slides=total,
                theme=theme,
                presentation_title=plan.title or "Presentation",
            )
            decorated_slides.append(dec_slide)

        copy_plan = getattr(plan, "model_copy", plan.copy)
        return copy_plan(update={"slides": decorated_slides})


# ---------------------------------------------------------------------
# Decoration Quality Validator
# ---------------------------------------------------------------------

class DecorationQualityValidator:
    """Evaluates decoration count, collisions against content boxes, opacity safety, readability, and density."""

    @classmethod
    def validate_slide(cls, slide: SlideSpec) -> DecorationQualityReport:
        """Convenience method to validate a slide directly."""
        decorations = [s for s in getattr(slide, "shapes", []) if s.decorative]
        content_boxes = extract_content_regions(slide)
        return cls.validate_slide_decorations(slide, decorations, content_boxes)

    @classmethod
    def validate_slide_decorations(
        cls,
        slide: SlideSpec,
        decorations: List[ShapeSpec],
        content_boxes: List[Box],
    ) -> DecorationQualityReport:
        count = len(decorations)
        collisions = 0

        for d in decorations:
            if CollisionDetector.check_collision(d, content_boxes, tolerance=0.02):
                collisions += 1

        density = "minimal" if count <= 1 else ("appropriate" if count <= 4 else "high")
        readability = "safe" if collisions == 0 else "impaired"
        rec = None if collisions == 0 else "REDUCE_OR_RELOCATE_COLLIDING_DECORATIONS"

        return DecorationQualityReport(
            count=count,
            collisions=collisions,
            density=density,
            readability=readability,
            recommendation=rec,
        )
