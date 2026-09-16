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


# ---------------------------------------------------------------------
# API Endpoint Request / Response Schemas
# ---------------------------------------------------------------------

class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    export_format: Optional[str] = "pptx"
    template_name: Optional[str] = None
    slide_count: int = Field(default=8, ge=3, le=MAX_SLIDES)
    audience: Optional[str] = Field(default=None, max_length=120)
    tone: Optional[str] = Field(default=None, max_length=120)
    language: str = Field(default="English", max_length=80)
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
    plan: Optional[PresentationPlan] = None

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


class RefineSlideRequest(BaseModel):
    text: str
    action: Optional[str] = "polish"


class RefineSlideResponse(BaseModel):
    refined_text: str
