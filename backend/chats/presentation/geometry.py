from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional
from pptx import Presentation
from pptx.enum.shapes import PP_PLACEHOLDER

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# ---------------------------------------------------------------------
# Centralized Slide Geometry Constants (16:9 HD Standard)
# ---------------------------------------------------------------------

SLIDE_WIDTH = 13.333
SLIDE_HEIGHT = 7.5
TOP_MARGIN = 0.6
LEFT_MARGIN = 0.8
RIGHT_MARGIN = 0.8
BOTTOM_MARGIN = 0.6
TITLE_TOP = 0.6
TITLE_MAX_HEIGHT = 1.0
CONTENT_TOP_DEFAULT = 1.40
FOOTER_TOP = 6.85
FOOTER_HEIGHT = 0.50

# HARD exclusion zone: content MUST NOT exceed 6.70 inches vertically!
SAFE_CONTENT_BOTTOM = 6.70

def calculate_available_content_height(top_y: float = CONTENT_TOP_DEFAULT) -> float:
    """Calculates available vertical content space above footer exclusion zone."""
    return max(1.0, round(SAFE_CONTENT_BOTTOM - max(TOP_MARGIN, top_y), 2))

def calculate_available_content_width(left_margin: float = LEFT_MARGIN, right_margin: float = RIGHT_MARGIN) -> float:
    """Calculates available horizontal content width respecting margins."""
    return max(2.0, round(SLIDE_WIDTH - left_margin - right_margin, 2))


# ---------------------------------------------------------------------
# Slide Geometry Presets (16:9 vs 4:3)
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class SlideGeometry:
    name: str
    slide_width: float
    slide_height: float
    content_left: float
    content_top: float
    content_width: float
    content_height: float


SLIDE_16_9 = SlideGeometry(
    name="16:9",
    slide_width=SLIDE_WIDTH,
    slide_height=SLIDE_HEIGHT,
    content_left=LEFT_MARGIN,
    content_top=CONTENT_TOP_DEFAULT,
    content_width=11.7,
    content_height=5.3,
)

SLIDE_4_3 = SlideGeometry(
    name="4:3",
    slide_width=10.0,
    slide_height=7.5,
    content_left=0.6,
    content_top=1.4,
    content_width=8.8,
    content_height=5.3,
)


# ---------------------------------------------------------------------
# Box Bounding Geometry with Clamping & Collision Protection
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class Box:
    left: float
    top: float
    width: float
    height: float

    @property
    def bottom(self) -> float:
        return round(self.top + self.height, 2)

    @property
    def right(self) -> float:
        return round(self.left + self.width, 2)

    def clamp(
        self,
        max_width: float = SLIDE_WIDTH,
        max_height: float = SLIDE_HEIGHT,
        margin_left: float = LEFT_MARGIN,
        margin_top: float = TOP_MARGIN,
        max_bottom: float = SAFE_CONTENT_BOTTOM,
    ) -> Box:
        c_left = max(margin_left, min(self.left, max_width - 1.0))
        c_top = max(margin_top, min(self.top, max_bottom - 0.5))
        max_avail_w = max(1.0, max_width - RIGHT_MARGIN - c_left)
        max_avail_h = max(0.5, max_bottom - c_top)
        c_width = max(0.5, min(self.width, max_avail_w))
        c_height = max(0.5, min(self.height, max_avail_h))
        return Box(
            round(c_left, 2),
            round(c_top, 2),
            round(c_width, 2),
            round(c_height, 2),
        )

    def intersects(self, other: Box, tolerance: float = 0.05) -> bool:
        return not (
            self.left + self.width - tolerance <= other.left
            or other.left + other.width - tolerance <= self.left
            or self.top + self.height - tolerance <= other.top
            or other.top + other.height - tolerance <= self.top
        )


def as_box(plan: Dict[str, Any], default: Box) -> Box:
    raw = plan.get("box") if isinstance(plan.get("box"), dict) else {}

    def _to_f(val: Any, def_val: float) -> float:
        if val is None or isinstance(val, (dict, list)):
            return def_val
        try:
            return float(val)
        except (ValueError, TypeError):
            return def_val

    left = _to_f(raw.get("left", plan.get("left")), default.left)
    top = _to_f(raw.get("top", plan.get("top")), default.top)
    width = _to_f(raw.get("width", plan.get("width")), default.width)
    height = _to_f(raw.get("height", plan.get("height")), default.height)
    b = Box(
        left=left,
        top=top,
        width=width,
        height=height,
    )
    return b.clamp()


def validate_and_adjust_boxes(boxes: List[Box], current_y: float = CONTENT_TOP_DEFAULT, safe_bottom: float = SAFE_CONTENT_BOTTOM) -> List[Box]:
    """
    Runs a 2D rectangle collision check (box.intersects(prev)) across layout bounding boxes.
    If overlap occurs or if top exceeds current_y/safe_bottom, automatically adjusts box positions
    or clamps heights before rendering to eliminate shape overlap.
    """
    if not boxes:
        return []

    adjusted: List[Box] = []
    for i, box in enumerate(boxes):
        c_box = box.clamp(max_bottom=safe_bottom)
        if i > 0:
            prev = adjusted[i - 1]
            if c_box.intersects(prev, tolerance=0.05):
                if c_box.left < prev.right and prev.left < c_box.right:
                    new_top = max(c_box.top, prev.bottom + 0.15)
                    avail_h = max(0.5, safe_bottom - new_top)
                    new_h = min(c_box.height, avail_h)
                    c_box = Box(c_box.left, round(new_top, 2), c_box.width, round(new_h, 2))
                elif c_box.top < prev.bottom and prev.top < c_box.bottom:
                    new_left = max(c_box.left, prev.right + 0.15)
                    avail_w = max(1.0, SLIDE_WIDTH - RIGHT_MARGIN - new_left)
                    new_w = min(c_box.width, avail_w)
                    c_box = Box(round(new_left, 2), c_box.top, round(new_w, 2), c_box.height)
        adjusted.append(c_box)

    return adjusted


# ---------------------------------------------------------------------
# Mixed Layout Resolver
# ---------------------------------------------------------------------

class MixedLayoutResolver:
    """
    Intelligent layout resolver for mixed slide content.

    Slide content types supported:
        diagram, paragraph, bullets, chart, table, image

    Coordinates are based on a 16:9 presentation (or custom SlideGeometry).
    Now fully density-aware and footer exclusion protected.
    """

    FULL = Box(LEFT_MARGIN, CONTENT_TOP_DEFAULT, 11.7, 5.3)

    LEFT = LEFT_MARGIN
    TOP = CONTENT_TOP_DEFAULT
    WIDTH = 11.7
    HEIGHT = 5.3
    GAP = 0.2

    HEIGHT_WEIGHT = {
        "diagram": 1.2,
        "paragraph": 0.8,
        "bullets": 1.0,
        "chart": 1.3,
        "table": 1.4,
        "image": 1.2,
        "stat": 0.8,
        "kpi_grid": 1.0,
        "callout": 0.7,
        "pros_cons": 1.1,
        "roadmap": 1.1,
        "code_block": 1.2,
        "speaker_card": 1.0,
        "bento_grid": 1.4,
        "process_flow": 1.2,
        "split_layout": 1.3,
    }

    @staticmethod
    def resolve_list_for_layout(
        plugin_types: List[str],
        layout: Optional[str] = None,
        top_y: float = CONTENT_TOP_DEFAULT,
        left_margin: float = LEFT_MARGIN,
        content_width: float = 11.7,
        density: str = "MEDIUM",
    ) -> List[Box]:
        if not plugin_types:
            return []
        count = len(plugin_types)
        avail_h = calculate_available_content_height(top_y)

        if count == 1:
            if layout == "blank":
                return [Box(left_margin, 0.8, content_width, max(1.0, round(SAFE_CONTENT_BOTTOM - 0.8, 2)))]
            return [Box(left_margin, top_y, content_width, avail_h)]

        # 2-column layout (Paragraph + Image, Bullets + Image, etc.)
        if count == 2:
            has_visual = any(k in {"image", "chart", "table", "code_block", "speaker_card"} for k in plugin_types)
            if has_visual or layout in {"two_content", "comparison", "content_caption", "picture_caption"}:
                gap = 0.4
                # Dynamic width ratio based on density & content priority
                if density == "HIGH":
                    ratio1 = 0.64 if plugin_types[0] in {"paragraph", "bullets"} else 0.36
                elif density == "LOW":
                    ratio1 = 0.50
                else:
                    ratio1 = 0.58 if plugin_types[0] in {"paragraph", "bullets"} else 0.42

                w1 = round((content_width - gap) * ratio1, 2)
                w2 = round(content_width - gap - w1, 2)
                h = min(avail_h, 4.8)

                return [
                    Box(left_margin, top_y, w1, h),
                    Box(round(left_margin + w1 + gap, 2), top_y, w2, h),
                ]

        return MixedLayoutResolver.resolve_list(
            plugin_types,
            top_y=top_y,
            left_margin=left_margin,
            content_width=content_width,
        )

    @staticmethod
    def resolve_list(
        plugin_types: List[str],
        top_y: float = CONTENT_TOP_DEFAULT,
        left_margin: float = LEFT_MARGIN,
        content_width: float = 11.7,
    ) -> List[Box]:
        if not plugin_types:
            return []

        count = len(plugin_types)
        avail_h = calculate_available_content_height(top_y)
        if count == 1:
            return [Box(left_margin, top_y, content_width, avail_h)]

        unique_kinds = set(plugin_types)
        if len(unique_kinds) == count:
            dict_res = MixedLayoutResolver.resolve(unique_kinds)
            if all(t in dict_res for t in plugin_types):
                boxes = []
                for t in plugin_types:
                    b = dict_res[t]
                    adj_top = max(top_y, round(b.top + (top_y - CONTENT_TOP_DEFAULT), 2))
                    adj_h = min(b.height, calculate_available_content_height(adj_top))
                    boxes.append(Box(b.left, adj_top, b.width, adj_h))
                return boxes

        # -------------------------------------------------------------
        # Flexible Dynamic Positioning for N Plugins (Duplicates & Mixed)
        # -------------------------------------------------------------
        if count == 2:
            has_visual = any(k in {"image", "chart", "table", "code_block", "speaker_card"} for k in plugin_types)
            if has_visual:
                gap = 0.4
                w = round((content_width - gap) / 2.0, 2)
                h = min(avail_h, 4.8)
                return [
                    Box(left_margin, top_y, w, h),
                    Box(round(left_margin + w + gap, 2), top_y, w, h),
                ]
            else:
                gap = 0.2
                h1 = round((avail_h - gap) * 0.45, 2)
                h2 = round((avail_h - gap) * 0.55, 2)
                return [
                    Box(left_margin, top_y, content_width, h1),
                    Box(left_margin, round(top_y + h1 + gap, 2), content_width, h2),
                ]

        if count == 3:
            has_cards_or_imgs = any(k in {"image", "chart", "stat", "speaker_card"} for k in plugin_types)
            if has_cards_or_imgs:
                gap = 0.3
                col_w = round((content_width - (gap * 2)) / 3.0, 2)
                h = min(avail_h, 4.8)
                return [
                    Box(left_margin, top_y, col_w, h),
                    Box(round(left_margin + col_w + gap, 2), top_y, col_w, h),
                    Box(round(left_margin + (col_w + gap) * 2, 2), top_y, col_w, h),
                ]
            else:
                gap = 0.2
                row_h = round((avail_h - (gap * 2)) / 3.0, 2)
                return [
                    Box(left_margin, top_y, content_width, row_h),
                    Box(left_margin, round(top_y + row_h + gap, 2), content_width, row_h),
                    Box(left_margin, round(top_y + (row_h + gap) * 2, 2), content_width, row_h),
                ]

        if count == 4:
            gap_x = 0.4
            gap_y = 0.2
            col_w = round((content_width - gap_x) / 2.0, 2)
            row_h = round((avail_h - gap_y) / 2.0, 2)
            return [
                Box(left_margin, top_y, col_w, row_h),
                Box(round(left_margin + col_w + gap_x, 2), top_y, col_w, row_h),
                Box(left_margin, round(top_y + row_h + gap_y, 2), col_w, row_h),
                Box(round(left_margin + col_w + gap_x, 2), round(top_y + row_h + gap_y, 2), col_w, row_h),
            ]

        total_gap = MixedLayoutResolver.GAP * (count - 1)
        available_height = max(1.0, avail_h - total_gap)
        weights = [MixedLayoutResolver.HEIGHT_WEIGHT.get(k, 1.0) for k in plugin_types]
        total_weight = sum(weights) or 1.0

        boxes: List[Box] = []
        current_top = top_y
        for weight in weights:
            h = round((available_height * weight) / total_weight, 2)
            boxes.append(
                Box(
                    left_margin,
                    round(current_top, 2),
                    content_width,
                    round(h, 2),
                )
            )
            current_top += h + MixedLayoutResolver.GAP
        return boxes


    @staticmethod
    def resolve(plugin_types: set[str], geometry: SlideGeometry = SLIDE_16_9) -> Dict[str, Box]:
        kinds = set(plugin_types)
        if not kinds:
            return {}

        if len(kinds) == 1:
            kind = next(iter(kinds))
            return {kind: MixedLayoutResolver.FULL}

        # -------------------------------------------------------------
        # 2-Item Layout Maps (Side-by-side or Top/Bottom)
        # -------------------------------------------------------------
        if kinds == {"diagram", "bullets"}:
            return {
                "diagram": Box(0.8, 1.3, 11.7, 1.8),
                "bullets": Box(0.8, 3.4, 11.7, 3.3),
            }

        if kinds == {"diagram", "paragraph"}:
            return {
                "diagram": Box(0.8, 1.3, 11.7, 1.8),
                "paragraph": Box(0.8, 3.4, 11.7, 3.3),
            }

        if kinds == {"paragraph", "image"}:
            return {
                "paragraph": Box(0.8, 1.5, 5.6, 4.8),
                "image": Box(6.7, 1.5, 5.8, 4.8),
            }


        if kinds == {"paragraph", "bullets"}:
            return {
                "paragraph": Box(0.8, 1.4, 11.7, 1.45),
                "bullets": Box(0.8, 3.05, 11.7, 3.65),
            }

        if kinds == {"image", "bullets"}:
            return {
                "image": Box(0.8, 1.5, 5.6, 4.8),
                "bullets": Box(6.7, 1.5, 5.8, 4.8),
            }

        if kinds == {"paragraph", "chart"}:
            return {
                "paragraph": Box(0.8, 1.5, 5.0, 4.8),
                "chart": Box(6.1, 1.5, 6.4, 4.8),
            }

        if kinds == {"bullets", "chart"}:
            return {
                "bullets": Box(0.8, 1.5, 5.0, 4.8),
                "chart": Box(6.1, 1.5, 6.4, 4.8),
            }

        if kinds == {"table", "paragraph"}:
            return {
                "paragraph": Box(0.8, 1.4, 11.7, 1.25),
                "table": Box(0.8, 2.85, 11.7, 3.85),
            }

        if kinds == {"table", "bullets"}:
            return {
                "bullets": Box(0.8, 1.4, 11.7, 1.55),
                "table": Box(0.8, 3.15, 11.7, 3.55),
            }

        if kinds == {"image", "chart"}:
            return {
                "image": Box(0.8, 1.5, 5.6, 4.8),
                "chart": Box(6.7, 1.5, 5.8, 4.8),
            }

        if kinds == {"image", "table"}:
            return {
                "image": Box(0.8, 1.5, 5.3, 4.8),
                "table": Box(6.3, 1.5, 6.2, 4.8),
            }

        if kinds == {"chart", "table"}:
            return {
                "chart": Box(0.8, 1.5, 5.3, 4.8),
                "table": Box(6.3, 1.5, 6.2, 4.8),
            }

        if kinds == {"stat", "paragraph"}:
            return {
                "stat": Box(0.8, 1.4, 11.7, 1.3),
                "paragraph": Box(0.8, 2.9, 11.7, 3.8),
            }

        if kinds == {"stat", "bullets"}:
            return {
                "stat": Box(0.8, 1.4, 11.7, 1.3),
                "bullets": Box(0.8, 2.9, 11.7, 3.8),
            }

        if kinds == {"stat", "chart"}:
            return {
                "stat": Box(0.8, 1.4, 11.7, 1.3),
                "chart": Box(0.8, 2.9, 11.7, 3.8),
            }

        if kinds == {"stat", "image"}:
            return {
                "stat": Box(0.8, 1.5, 5.6, 4.8),
                "image": Box(6.7, 1.5, 5.8, 4.8),
            }

        if kinds == {"pros_cons", "paragraph"}:
            return {
                "paragraph": Box(0.8, 1.4, 11.7, 1.3),
                "pros_cons": Box(0.8, 2.9, 11.7, 3.8),
            }

        if kinds == {"pros_cons", "bullets"}:
            return {
                "bullets": Box(0.8, 1.4, 11.7, 1.3),
                "pros_cons": Box(0.8, 2.9, 11.7, 3.8),
            }

        if kinds == {"pros_cons", "chart"}:
            return {
                "pros_cons": Box(0.8, 1.5, 5.6, 4.8),
                "chart": Box(6.7, 1.5, 5.8, 4.8),
            }

        if kinds == {"callout", "paragraph"}:
            return {
                "callout": Box(0.8, 1.4, 11.7, 1.1),
                "paragraph": Box(0.8, 2.7, 11.7, 4.0),
            }

        if kinds == {"callout", "bullets"}:
            return {
                "callout": Box(0.8, 1.4, 11.7, 1.1),
                "bullets": Box(0.8, 2.7, 11.7, 4.0),
            }

        if kinds == {"roadmap", "paragraph"}:
            return {
                "roadmap": Box(0.8, 1.4, 11.7, 2.2),
                "paragraph": Box(0.8, 3.8, 11.7, 2.9),
            }

        if kinds == {"roadmap", "bullets"}:
            return {
                "roadmap": Box(0.8, 1.4, 11.7, 2.2),
                "bullets": Box(0.8, 3.8, 11.7, 2.9),
            }

        if kinds == {"code_block", "paragraph"}:
            return {
                "code_block": Box(0.8, 1.5, 6.0, 4.8),
                "paragraph": Box(7.1, 1.5, 5.4, 4.8),
            }

        if kinds == {"code_block", "bullets"}:
            return {
                "code_block": Box(0.8, 1.5, 6.0, 4.8),
                "bullets": Box(7.1, 1.5, 5.4, 4.8),
            }

        if kinds == {"speaker_card", "paragraph"}:
            return {
                "speaker_card": Box(0.8, 1.5, 4.8, 4.8),
                "paragraph": Box(5.9, 1.5, 6.6, 4.8),
            }

        if kinds == {"speaker_card", "bullets"}:
            return {
                "speaker_card": Box(0.8, 1.5, 4.8, 4.8),
                "bullets": Box(5.9, 1.5, 6.6, 4.8),
            }

        if kinds == {"kpi_grid", "paragraph"}:
            return {
                "kpi_grid": Box(0.8, 1.4, 11.7, 1.5),
                "paragraph": Box(0.8, 3.1, 11.7, 3.6),
            }

        if kinds == {"kpi_grid", "bullets"}:
            return {
                "kpi_grid": Box(0.8, 1.4, 11.7, 1.5),
                "bullets": Box(0.8, 3.1, 11.7, 3.6),
            }

        if kinds == {"stat", "table"}:
            return {
                "stat": Box(0.8, 1.4, 11.7, 1.3),
                "table": Box(0.8, 2.9, 11.7, 3.8),
            }

        if kinds == {"diagram", "chart"}:
            return {
                "diagram": Box(0.8, 1.4, 11.7, 1.8),
                "chart": Box(0.8, 3.4, 11.7, 3.3),
            }

        if kinds == {"roadmap", "chart"}:
            return {
                "roadmap": Box(0.8, 1.4, 11.7, 2.2),
                "chart": Box(0.8, 3.8, 11.7, 2.9),
            }

        # -------------------------------------------------------------
        # 3-Item Layout Maps (3-Column or Top-Full/Bottom-Split)
        # -------------------------------------------------------------
        if kinds == {"diagram", "paragraph", "bullets"}:
            return {
                "diagram": Box(0.8, 1.4, 11.7, 1.30),
                "paragraph": Box(0.8, 2.85, 11.7, 1.30),
                "bullets": Box(0.8, 4.35, 11.7, 2.35),
            }

        if kinds == {"diagram", "bullets", "chart"}:
            return {
                "diagram": Box(0.8, 1.4, 11.7, 1.35),
                "bullets": Box(0.8, 2.95, 5.6, 3.75),
                "chart": Box(6.7, 2.95, 5.8, 3.75),
            }

        if kinds == {"diagram", "paragraph", "chart"}:
            return {
                "diagram": Box(0.8, 1.4, 11.7, 1.35),
                "paragraph": Box(0.8, 2.95, 5.6, 3.75),
                "chart": Box(6.7, 2.95, 5.8, 3.75),
            }

        if kinds == {"stat", "bullets", "chart"}:
            return {
                "stat": Box(0.8, 1.4, 11.7, 1.30),
                "bullets": Box(0.8, 2.90, 5.6, 3.80),
                "chart": Box(6.7, 2.90, 5.8, 3.80),
            }

        if kinds == {"kpi_grid", "bullets", "chart"}:
            return {
                "kpi_grid": Box(0.8, 1.4, 11.7, 1.40),
                "bullets": Box(0.8, 3.00, 5.6, 3.70),
                "chart": Box(6.7, 3.00, 5.8, 3.70),
            }

        if kinds == {"callout", "paragraph", "bullets"}:
            return {
                "callout": Box(0.8, 1.4, 11.7, 1.10),
                "paragraph": Box(0.8, 2.70, 11.7, 1.50),
                "bullets": Box(0.8, 4.40, 11.7, 2.30),
            }

        if kinds == {"image", "chart", "bullets"}:
            return {
                "image": Box(0.8, 1.5, 3.65, 4.8),
                "chart": Box(4.75, 1.5, 3.65, 4.8),
                "bullets": Box(8.70, 1.5, 3.8, 4.8),
            }

        if kinds == {"paragraph", "image", "chart"}:
            return {
                "paragraph": Box(0.8, 1.5, 3.65, 4.8),
                "image": Box(4.75, 1.5, 3.65, 4.8),
                "chart": Box(8.70, 1.5, 3.8, 4.8),
            }

        if kinds == {"paragraph", "image", "table"}:
            return {
                "paragraph": Box(0.8, 1.5, 3.65, 4.8),
                "image": Box(4.75, 1.5, 3.65, 4.8),
                "table": Box(8.70, 1.5, 3.8, 4.8),
            }

        if kinds == {"bullets", "image", "table"}:
            return {
                "bullets": Box(0.8, 1.5, 3.65, 4.8),
                "image": Box(4.75, 1.5, 3.65, 4.8),
                "table": Box(8.70, 1.5, 3.8, 4.8),
            }

        if kinds == {"paragraph", "bullets", "table"}:
            return {
                "paragraph": Box(0.8, 1.4, 11.7, 1.15),
                "bullets": Box(0.8, 2.75, 11.7, 1.65),
                "table": Box(0.8, 4.60, 11.7, 2.10),
            }

        if kinds == {"paragraph", "bullets", "chart"}:
            return {
                "paragraph": Box(0.8, 1.4, 11.7, 1.10),
                "bullets": Box(0.8, 2.70, 5.2, 3.95),
                "chart": Box(6.25, 2.70, 6.25, 3.95),
            }

        # -------------------------------------------------------------
        # 4-Item 2x2 Grid Layout Map
        # -------------------------------------------------------------
        if len(kinds) == 4:
            ordered_4 = [k for k in ["bento_grid", "split_layout", "process_flow", "diagram", "stat", "kpi_grid", "callout", "pros_cons", "roadmap", "code_block", "speaker_card", "paragraph", "bullets", "chart", "table", "image"] if k in kinds]
            if len(ordered_4) == 4:
                return {
                    ordered_4[0]: Box(0.8, 1.4, 5.6, 2.45),
                    ordered_4[1]: Box(6.8, 1.4, 5.7, 2.45),
                    ordered_4[2]: Box(0.8, 4.05, 5.6, 2.65),
                    ordered_4[3]: Box(6.8, 4.05, 5.7, 2.65),
                }


        return MixedLayoutResolver._dynamic_layout(kinds)

    @staticmethod
    def _dynamic_layout(kinds: set[str]) -> Dict[str, Box]:
        ordered_kinds = [k for k in ["bento_grid", "split_layout", "process_flow", "diagram", "stat", "kpi_grid", "callout", "pros_cons", "roadmap", "code_block", "speaker_card", "paragraph", "bullets", "chart", "table", "image"] if k in kinds]
        if not ordered_kinds:
            ordered_kinds = list(kinds)

        count = len(ordered_kinds)
        if count == 1:
            return {ordered_kinds[0]: MixedLayoutResolver.FULL}

        if count == 4:
            return {
                ordered_kinds[0]: Box(0.8, 1.4, 5.6, 2.45),
                ordered_kinds[1]: Box(6.8, 1.4, 5.7, 2.45),
                ordered_kinds[2]: Box(0.8, 4.05, 5.6, 2.65),
                ordered_kinds[3]: Box(6.8, 4.05, 5.7, 2.65),
            }

        total_gap = MixedLayoutResolver.GAP * (count - 1)
        available_height = MixedLayoutResolver.HEIGHT - total_gap
        weights = [MixedLayoutResolver.HEIGHT_WEIGHT.get(kind, 1.0) for kind in ordered_kinds]
        total_weight = sum(weights) or 1.0

        result: Dict[str, Box] = {}
        current_top = MixedLayoutResolver.TOP

        for kind, weight in zip(ordered_kinds, weights):
            height = available_height * weight / total_weight
            result[kind] = Box(
                MixedLayoutResolver.LEFT,
                round(current_top, 2),
                MixedLayoutResolver.WIDTH,
                round(height, 2),
            )
            current_top += height + MixedLayoutResolver.GAP

        return result


# ---------------------------------------------------------------------
# Fluid Adaptive Geometry Solver (Zero Collisions & Content Aware)
# ---------------------------------------------------------------------

class FluidGeometrySolver:
    """
    Calculates dynamic 2D bounding boxes based on:
    1. Content Density (text length, bullet point count, table rows, image aspect ratio)
    2. Slide Canvas Geometry (16:9 vs 4:3)
    3. Auto Flow Orientation (Horizontal Split vs Vertical Stack vs Multi-Column vs 2x2 Grid)
    """

    @staticmethod
    def estimate_content_weight(kind: str, data: Dict[str, Any]) -> float:
        kind = (kind or "").lower().strip()
        data = data if isinstance(data, dict) else {}

        if kind == "bullets":
            pts = data.get("points") or []
            count = len(pts) if isinstance(pts, list) else 1
            return max(0.8, min(2.5, 0.6 + (count * 0.25)))
        elif kind == "paragraph":
            txt = str(data.get("text") or "")
            length = len(txt)
            return max(0.6, min(2.2, 0.6 + (length / 250.0)))
        elif kind == "table":
            rows = len(data.get("rows") or []) if isinstance(data.get("rows"), list) else 3
            return max(1.0, min(2.5, 0.8 + (rows * 0.3)))
        elif kind in {"chart", "diagram", "code_block"}:
            return 1.4
        elif kind in {"image", "speaker_card", "pros_cons", "roadmap"}:
            return 1.2
        elif kind in {"stat", "kpi_grid", "callout"}:
            return 0.9
        return 1.0

    @staticmethod
    def resolve_fluid(plugins_data: List[Dict[str, Any]], geometry: SlideGeometry = SLIDE_16_9) -> List[Box]:
        if not plugins_data:
            return []

        count = len(plugins_data)
        margin_left = geometry.content_left
        margin_top = geometry.content_top
        avail_w = geometry.content_width
        avail_h = geometry.content_height

        if count == 1:
            return [Box(margin_left, margin_top, avail_w, avail_h)]

        # Classify flow orientation
        kinds = [(p.get("type") or "paragraph").lower() for p in plugins_data]
        weights = [FluidGeometrySolver.estimate_content_weight(k, p.get("data") or {}) for k, p in zip(kinds, plugins_data)]

        # Check for side-by-side (2 columns) split suitability
        is_2_col = (
            count == 2
            and not ({kinds[0], kinds[1]} & {"diagram"})
            and not (kinds[0] in {"table", "stat"} and kinds[1] in {"table", "stat"})
        )

        boxes: List[Box] = []

        if is_2_col:
            gap = 0.3
            col_w1 = round((avail_w - gap) * (weights[0] / (weights[0] + weights[1])), 2)
            col_w1 = max(4.0, min(7.5, col_w1))
            col_w2 = round(avail_w - col_w1 - gap, 2)

            boxes.append(Box(margin_left, margin_top, col_w1, avail_h))
            boxes.append(Box(round(margin_left + col_w1 + gap, 2), margin_top, col_w2, avail_h))
            return boxes

        # 3-Column horizontal split
        if count == 3 and set(kinds).issubset({"image", "chart", "bullets", "paragraph", "speaker_card", "callout"}):
            gap = 0.25
            col_w = round((avail_w - (gap * 2)) / 3.0, 2)
            for idx in range(3):
                l = round(margin_left + idx * (col_w + gap), 2)
                boxes.append(Box(l, margin_top, col_w, avail_h))
            return boxes

        # 4-Item 2x2 Grid
        if count == 4:
            gap_x = 0.3
            gap_y = 0.2
            col_w = round((avail_w - gap_x) / 2.0, 2)
            row_h = round((avail_h - gap_y) / 2.0, 2)

            boxes.append(Box(margin_left, margin_top, col_w, row_h))
            boxes.append(Box(round(margin_left + col_w + gap_x, 2), margin_top, col_w, row_h))
            boxes.append(Box(margin_left, round(margin_top + row_h + gap_y, 2), col_w, row_h))
            boxes.append(Box(round(margin_left + col_w + gap_x, 2), round(margin_top + row_h + gap_y, 2), col_w, row_h))
            return boxes

        # Vertical Flow Stack (N items)
        gap_y = 0.2
        total_gap = gap_y * (count - 1)
        net_h = max(1.0, avail_h - total_gap)
        total_w = sum(weights) or 1.0

        current_top = margin_top
        for w in weights:
            h = round((net_h * w) / total_w, 2)
            boxes.append(Box(margin_left, round(current_top, 2), avail_w, h))
            current_top += h + gap_y

        return boxes


# ---------------------------------------------------------------------
# Placeholders & Template Detector (No Circular Import)
# ---------------------------------------------------------------------

def safe_load_template_prs(template_file: str) -> Presentation:
    if template_file:
        try:
            candidate = Path(template_file).expanduser()
            if not candidate.is_file():
                from backend.chats.presentation.planner import resolve_template_path
                resolved = resolve_template_path(template_file)
                candidate = Path(resolved)
            if candidate.is_file():
                return Presentation(str(candidate))
        except Exception as exc:
            logger.warning("Failed to open custom template file %s: %s", template_file, exc)
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
        self.prs = safe_load_template_prs(template_file)
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

        if target in {"title_slide", "title_subtitle"}:
            if any(k in name for k in ("title", "cover", "front")):
                score += 100
            if layout.has_title:
                score += 30
            if not layout.has_body:
                score += 10

        elif target in {"title_content", "bullets_slide", "bullets"}:
            if any(k in name for k in ("content", "body", "text", "bullet", "list")):
                score += 100
            if layout.has_title and layout.has_body:
                score += 40
            if layout.placeholder_count >= 2:
                score += 10

        elif target in {"section_slide", "section_header"}:
            if any(k in name for k in ("section", "divider", "break", "header")):
                score += 100
            if layout.has_title and not layout.has_body:
                score += 20

        elif target in {"two_content", "comparison", "paragraph_2col"}:
            if any(k in name for k in ("two", "comparison", "compare", "2 content", "side")):
                score += 100
            if layout.placeholder_count >= 3:
                score += 40

        elif target == "title_only":
            if any(k in name for k in ("title only", "header only")):
                score += 100
            if layout.has_title and not layout.has_body:
                score += 40

        elif target == "blank":
            if any(k in name for k in ("blank", "empty")):
                score += 100
            if layout.placeholder_count == 0:
                score += 80

        elif target in {"content_caption", "picture_caption", "image_text"}:
            if any(k in name for k in ("caption", "picture", "visual", "quote")):
                score += 100
            if layout.placeholder_count >= 2:
                score += 30

        elif target in {"chart_slide", "chart_focus"}:
            if any(k in name for k in ("chart", "graph", "data", "analytics")):
                score += 100
            if layout.has_chart:
                score += 40
            if layout.has_title and layout.has_body:
                score += 15

        elif target in {"image_slide"}:
            if any(k in name for k in ("image", "picture", "photo", "visual")):
                score += 100
            if layout.has_picture:
                score += 40
            if layout.has_title and layout.has_body:
                score += 15

        elif target in {"table_slide", "table_focus"}:
            if any(k in name for k in ("table", "data", "content", "body")):
                score += 100
            if layout.has_table or layout.has_body:
                score += 25
            if layout.has_title:
                score += 10

        if layout.placeholder_count == 0 and target != "blank":
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
            "title_subtitle": LayoutSpec(self.pick_best_layout_index("title_subtitle")),
            "title_content": LayoutSpec(self.pick_best_layout_index("title_content")),
            "section_slide": LayoutSpec(self.pick_best_layout_index("section_slide")),
            "section_header": LayoutSpec(self.pick_best_layout_index("section_header")),
            "two_content": LayoutSpec(self.pick_best_layout_index("two_content")),
            "comparison": LayoutSpec(self.pick_best_layout_index("comparison")),
            "title_only": LayoutSpec(self.pick_best_layout_index("title_only")),
            "blank": LayoutSpec(self.pick_best_layout_index("blank")),
            "content_caption": LayoutSpec(self.pick_best_layout_index("content_caption")),
            "picture_caption": LayoutSpec(self.pick_best_layout_index("picture_caption")),
            "bullets_slide": LayoutSpec(self.pick_best_layout_index("bullets_slide")),
            "bullets": LayoutSpec(self.pick_best_layout_index("bullets_slide")),
            "paragraph_2col": LayoutSpec(self.pick_best_layout_index("two_content")),
            "chart_focus": LayoutSpec(self.pick_best_layout_index("chart_slide")),
            "chart_slide": LayoutSpec(self.pick_best_layout_index("chart_slide")),
            "image_text": LayoutSpec(self.pick_best_layout_index("picture_caption")),
            "image_slide": LayoutSpec(self.pick_best_layout_index("image_slide")),
            "table_focus": LayoutSpec(self.pick_best_layout_index("table_slide")),
            "table_slide": LayoutSpec(self.pick_best_layout_index("table_slide")),
            "mixed_content_slide": LayoutSpec(self.pick_best_layout_index("title_content")),
        }


@lru_cache(maxsize=16)
def get_layout_registry(template_file: str) -> Dict[str, LayoutSpec]:
    return TemplateDetector(template_file).build_registry()

