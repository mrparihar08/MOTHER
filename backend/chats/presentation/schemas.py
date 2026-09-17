from __future__ import annotations

import os
from typing import Any, Annotated, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field

MAX_SLIDES = int(os.getenv("PPT_MAX_SLIDES", "30"))


# ---------------------------------------------------------------------
# Slide Plugin Schemas
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


class SlidePluginDiagram(BaseModel):
    type: Literal["diagram"]
    data: Dict[str, Any]


class SlidePluginStat(BaseModel):
    type: Literal["stat"]
    data: Dict[str, Any]


class SlidePluginCallout(BaseModel):
    type: Literal["callout"]
    data: Dict[str, Any]


class SlidePluginKPIGrid(BaseModel):
    type: Literal["kpi_grid"]
    data: Dict[str, Any]


class SlidePluginProsCons(BaseModel):
    type: Literal["pros_cons"]
    data: Dict[str, Any]


class SlidePluginRoadmap(BaseModel):
    type: Literal["roadmap"]
    data: Dict[str, Any]


class SlidePluginCodeBlock(BaseModel):
    type: Literal["code_block"]
    data: Dict[str, Any]


class SlidePluginSpeakerCard(BaseModel):
    type: Literal["speaker_card"]
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
        SlidePluginDiagram,
        SlidePluginStat,
        SlidePluginCallout,
        SlidePluginKPIGrid,
        SlidePluginProsCons,
        SlidePluginRoadmap,
        SlidePluginCodeBlock,
        SlidePluginSpeakerCard,
    ],
    Field(discriminator="type"),
]



# ---------------------------------------------------------------------
# 2-Stage Content & Design Planner Schemas
# ---------------------------------------------------------------------

class PresentationMetadata(BaseModel):
    title: str = Field(..., description="Main presentation title")
    subtitle: Optional[str] = Field(default="", description="Executive presentation subtitle")
    audience: Optional[str] = Field(default="General Audience", description="Target audience")
    purpose: Optional[str] = Field(default="Informative presentation", description="Presentation purpose")
    slide_count: int = Field(default=8, description="Total number of slides")


class GlobalDesignSystem(BaseModel):
    theme_name: str = Field(default="modern_corporate", description="Theme name")
    background: str = Field(default="#FFFFFF", description="Base background color hex")
    primary_color: str = Field(default="#0F172A", description="Primary brand color hex")
    secondary_color: str = Field(default="#3B82F6", description="Secondary brand color hex")
    accent_colors: List[str] = Field(default_factory=lambda: ["#10B981", "#F59E0B", "#6366F1"], description="Palette accent colors")
    text_color: str = Field(default="#1E293B", description="Primary text color hex")
    muted_text_color: str = Field(default="#64748B", description="Muted text color hex")
    font_family: str = Field(default="Inter, Arial, sans-serif", description="Font family")
    title_font_size: str = Field(default="28pt", description="Title font size")
    subtitle_font_size: str = Field(default="18pt", description="Subtitle font size")
    body_font_size: str = Field(default="14pt", description="Body font size")
    border_radius: str = Field(default="8px", description="Card border radius")
    spacing_system: str = Field(default="relaxed", description="Spacing system mode")
    visual_style: str = Field(default="modern", description="Overall visual style")


class ContentPlan(BaseModel):
    type: str = Field(..., description="Slide type (title, agenda, introduction, concept, process, chart, table, conclusion, etc.)")
    purpose: str = Field(..., description="What this slide should communicate")
    title: str = Field(..., description="Slide headline title")
    subtitle: Optional[str] = Field(default="", description="Slide subtitle if required")
    key_message: Optional[str] = Field(default="", description="One primary message for this slide")
    content: List[Any] = Field(default_factory=list, description="Concise content items, points, or data structures")
    speaker_notes: Optional[str] = Field(default="", description="Speaker notes for the presenter")


class DesignPlan(BaseModel):
    layout: str = Field(default="single_column", description="Visual layout selection")
    background: str = Field(default="default", description="Slide-specific background style")
    title_position: str = Field(default="top_left", description="Title alignment and position")
    content_alignment: str = Field(default="left", description="Content alignment")
    density: Literal["low", "medium", "high"] = Field(default="medium", description="Content density rating")
    visual: Dict[str, Any] = Field(default_factory=dict, description="Visual requirement structure (type, orientation, steps, data, etc.)")
    elements: List[Any] = Field(default_factory=list, description="Visual components and card structures")
    spacing: str = Field(default="balanced", description="Internal spacing spec")
    emphasis: List[str] = Field(default_factory=list, description="Key elements to highlight visually")


class TwoStageSlide(BaseModel):
    slide_number: int = Field(..., description="1-indexed slide number")
    content_plan: ContentPlan = Field(..., description="WHAT the slide communicates")
    design_plan: DesignPlan = Field(..., description="HOW the slide visually presents it")


class StructuredPresentationPlan(BaseModel):
    presentation: PresentationMetadata
    design_system: GlobalDesignSystem
    slides: List[TwoStageSlide]

    def to_presentation_plan(self) -> PresentationPlan:
        """Converts structured 2-stage presentation plan into flat PresentationPlan for rendering."""
        converted_slides: List[SlideSpec] = []
        for s in self.slides:
            cp = s.content_plan
            dp = s.design_plan
            plugins: List[SlidePlugin] = []

            stype = cp.type.lower().strip()

            # Map content into appropriate plugins based on content_plan and design_plan
            if stype in {"chart", "statistics"} and isinstance(dp.visual, dict) and dp.visual.get("data"):
                v_data = dp.visual.get("data", {})
                plugins.append(SlidePluginChart(type="chart", data={
                    "chart_type": dp.visual.get("chart_type") or v_data.get("chart_type", "column"),
                    "title": cp.title,
                    "categories": v_data.get("categories", []),
                    "values": v_data.get("values", []),
                    "series_name": v_data.get("series_name", "Metrics"),
                    "series_map": v_data.get("series_map", {}),
                }))
            elif stype == "table" and isinstance(dp.visual, dict) and dp.visual.get("data"):
                t_data = dp.visual.get("data", {})
                plugins.append(SlidePluginTable(type="table", data={
                    "title": cp.title,
                    "headers": t_data.get("headers", []),
                    "rows": t_data.get("rows", []),
                }))
            elif stype in {"process", "workflow", "timeline", "architecture", "cycle", "hierarchy", "roadmap"} or (isinstance(dp.visual, dict) and dp.visual.get("steps")):
                steps_raw = dp.visual.get("steps") or cp.content
                steps_str = " ➔ ".join(f"[{str(step)}]" for step in steps_raw) if isinstance(steps_raw, list) else str(steps_raw)
                plugins.append(SlidePluginDiagram(type="diagram", data={
                    "diagram": steps_str,
                    "diagram_type": dp.visual.get("type", stype),
                    "header": cp.title,
                }))

            # Convert bullets or paragraph content
            if cp.content:
                if isinstance(cp.content, list) and all(isinstance(x, str) for x in cp.content):
                    if stype in {"title", "thank_you"}:
                        pass
                    elif len(cp.content) == 1 and len(cp.content[0]) > 120:
                        plugins.append(SlidePluginParagraph(type="paragraph", data={"text": cp.content[0]}))
                    else:
                        plugins.append(SlidePluginBullets(type="bullets", data={
                            "title": cp.title,
                            "points": cp.content,
                            "bullet_style": "check" if stype in {"conclusion", "key_takeaways"} else "auto",
                            "show_card": stype in {"three_cards", "four_cards", "concept", "two_column"},
                        }))
                elif isinstance(cp.content, str) and cp.content.strip():
                    plugins.append(SlidePluginParagraph(type="paragraph", data={"text": cp.content}))

            if cp.speaker_notes:
                plugins.append(SlidePluginNotes(type="notes", data={"notes": cp.speaker_notes}))

            # Map 2-stage layout name to legacy layout name
            layout_map = {
                "title": "title_slide",
                "thank_you": "title_slide",
                "section": "section_slide",
                "chart": "chart_slide",
                "statistics": "chart_slide",
                "table": "table_slide",
            }
            layout_name = layout_map.get(stype, "mixed_content_slide" if plugins else "bullets_slide")

            converted_slides.append(SlideSpec(
                layout=layout_name,
                title=cp.title,
                subtitle=cp.subtitle or cp.key_message or "",
                plugins=plugins,
            ))

        return PresentationPlan(
            title=self.presentation.title,
            theme={
                "name": self.design_system.theme_name,
                "background": self.design_system.background,
                "primary": self.design_system.primary_color,
                "secondary": self.design_system.secondary_color,
                "accent": self.design_system.accent_colors[0] if self.design_system.accent_colors else "#3B82F6",
                "text": self.design_system.text_color,
            },
            slides=converted_slides,
        )


# ---------------------------------------------------------------------
# Stage 1: PPT Planner Models (Outline & Structure Generation for Preview)
# ---------------------------------------------------------------------

class SlideOutlineItem(BaseModel):
    slide_number: int = Field(..., description="1-indexed slide number")
    title: str = Field(..., description="Slide structural headline title")
    subtitle: Optional[str] = Field(default="", description="Slide subtitle or brief descriptor")
    slide_type: str = Field(default="concept", description="Slide type selection")
    purpose: str = Field(..., description="Primary objective/communicative purpose of this slide")
    key_message: str = Field(..., description="Core takeaway message for audience")
    visual_requirement: Optional[str] = Field(default="none", description="Visual type (chart, diagram, image, table, cards, etc.)")
    subtopics: List[str] = Field(default_factory=list, description="Subtopics to cover in this slide")


class Stage1PlanResponse(BaseModel):
    title: str = Field(..., description="Main presentation title")
    subtitle: str = Field(default="", description="Executive presentation subtitle")
    topic: str = Field(..., description="Target topic")
    domain: str = Field(default="general", description="Classified prompt domain")
    audience: str = Field(default="General Audience", description="Target audience persona")
    purpose: str = Field(default="Executive Presentation", description="Presentation purpose")
    recommended_slide_count: int = Field(..., description="Dynamically determined optimal slide count")
    slide_sequence: List[SlideOutlineItem] = Field(..., description="Ordered slide sequence outline for user preview")
    status: Literal["preview_ready"] = Field(default="preview_ready", description="Status indicator")


# ---------------------------------------------------------------------
# Presentation Specifications
# ---------------------------------------------------------------------

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
    title_color: Optional[str] = None
    title_font_size: Optional[int] = None
    title_bold: Optional[bool] = True
    title_align: Optional[str] = None
    title_valign: Optional[str] = None
    subtitle_color: Optional[str] = None
    subtitle_font_size: Optional[int] = None
    subtitle_align: Optional[str] = None
    subtitle_valign: Optional[str] = None
    plugins: List[SlidePlugin] = Field(default_factory=list)


class PresentationPlan(BaseModel):
    title: str
    theme: Optional[Dict[str, str]] = None
    slides: List[SlideSpec]
    brand_logo: Optional[str] = None
    brand_color: Optional[str] = None
    brand_secondary_color: Optional[str] = None
    brand_font: Optional[str] = None
    brand_footer: Optional[str] = None
    use_custom_brand: bool = False
    use_ai_image_generation: bool = True
    structured_plan: Optional[StructuredPresentationPlan] = None


# ---------------------------------------------------------------------
# API Endpoint Request / Response Schemas
# ---------------------------------------------------------------------

class GenerateRequest(BaseModel):
    prompt: str = Field(default="", min_length=0)
    topic: Optional[str] = Field(default=None, description="Topic of presentation")
    audience: Optional[str] = Field(default=None, max_length=120)
    purpose: Optional[str] = Field(default=None, max_length=150)
    tone: Optional[str] = Field(default=None, max_length=120)
    language: str = Field(default="English", max_length=80)
    slide_count: Union[int, Literal["auto"], str] = Field(default=8)
    depth: Optional[Literal["basic", "medium", "detailed"]] = Field(default="medium")
    style: Optional[Literal["professional", "academic", "corporate", "modern", "minimal", "creative"]] = Field(default="professional")
    user_requirements: Optional[str] = Field(default=None)

    export_format: Optional[str] = "pptx"
    template_name: Optional[str] = None
    include_citations: bool = False
    include_speaker_notes: bool = False
    include_agenda_slide: bool = True
    use_gemini: bool = True
    use_web_search: bool = True
    use_ai_image_generation: bool = True

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
    plan: Optional[Union[PresentationPlan, StructuredPresentationPlan]] = None

    brand_logo: Optional[str] = None
    brand_color: Optional[str] = None
    brand_secondary_color: Optional[str] = None
    brand_font: Optional[str] = None
    brand_footer: Optional[str] = None
    use_custom_brand: bool = False


class GenerateResponse(BaseModel):
    job_id: str
    status: Literal["completed"]
    file_name: str
    download_url: str
    slides_count: int = 0
    theme_used: str = "default"
    execution_time_ms: float = 0.0
    ai_generated: bool = False
    title: Optional[str] = None
    plan: Optional[PresentationPlan] = None
    structured_plan: Optional[StructuredPresentationPlan] = None


class SaveResponse(BaseModel):
    presentation_id: str
    status: Literal["saved"]
    file_name: str
    download_url: str
    message: str
    slides_count: int = 0
    theme_used: str = "default"
    execution_time_ms: float = 0.0
    ai_generated: bool = False
    structured_plan: Optional[StructuredPresentationPlan] = None


class RefineSlideRequest(BaseModel):
    text: str
    action: Optional[str] = "polish"
    slide_title: Optional[str] = None
    presentation_title: Optional[str] = None


class RefineSlideResponse(BaseModel):
    refined_text: str
    refined_header: Optional[str] = None
    refined_chart: Optional[Dict[str, Any]] = None

