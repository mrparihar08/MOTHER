from __future__ import annotations

import collections
import collections.abc

# Forward compatibility fix for python-pptx / collections
for name in ("Container", "Mapping", "MutableMapping", "Sequence", "MutableSequence", "Iterable", "Callable"):
    if not hasattr(collections, name) and hasattr(collections.abc, name):
        setattr(collections, name, getattr(collections.abc, name))

import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from dotenv import load_dotenv

# Services
from backend.chats.services.gemini_service import generate_response
from backend.chats.services.unsplash_service import fetch_unsplash_image, fetch_unsplash_url
from backend.chats.services.ai_image_service import generate_ai_image
from backend.chats.presentation.services.cleanup_service import (
    cleanup_expired_files,
    start_periodic_cleanup,
)

from backend.chats.presentation.services.presentation_store import presentation_store
from backend.chats.presentation.schemas import (
    GenerateRequest,
    GenerateResponse,
    SaveResponse,
    PresentationDetailResponse,
    PlanPreviewResponse,
    RefineSlideRequest,
    RefineSlideResponse,
    PresentationPlan,
    StructuredPresentationPlan,
    SlideSpec,
    SlidePluginImage,
    SlidePluginBullets,
    SlidePluginParagraph,
    SlidePluginChart,
    SlidePluginTable,
    SlidePluginNotes,
    SlidePluginDiagram,
)
from backend.chats.presentation.themes import (
    detect_theme,
    detect_visual_style,
    get_theme_palette,
    get_visual_style,
    hex_to_rgb,
    is_light_color,
)
from backend.chats.presentation.geometry import MixedLayoutResolver
from backend.chats.presentation.planner import (
    PromptPlanner,
    build_gemini_slide_script,
    build_structured_plan,
    clean_ai_instructions,
    ensure_conclusion_and_thankyou_slides,
    normalize_whitespace,
    normalize_slide_types,
    resolve_template_path,
)
from backend.chats.presentation.scripts.templates import (
    get_template_preset,
    list_available_templates,
)
from backend.chats.presentation.services.image_manager import ensure_plan_images
from backend.chats.presentation.exporter import save_presentation, save_presentation_as_pdf, OUTPUT_DIR
from backend.chats.presentation.services.voiceover_service import generate_slide_voiceover, VOICEOVER_DIR, select_voice
from backend.chats.presentation.renderers.ppt_renderer import PptRenderer
from fastapi import Depends
from sqlalchemy.orm import Session
from backend.api.database import get_db
from backend.api.models.vitya import PresentationBrand
from backend.api.schemas.vitya import BrandProfileCreate, BrandProfileResponse
from pydantic import BaseModel

load_dotenv()

logger = logging.getLogger(__name__)

APP_NAME = "Vitya Presentation API"
MAX_SLIDES = int(os.getenv("PPT_MAX_SLIDES", "30"))

router = APIRouter()

# Auto-start background storage cleanup thread on module startup
try:
    start_periodic_cleanup(interval_hours=6, max_age_hours=24)
except Exception as exc:
    logger.warning("Failed to start periodic cleanup thread: %s", exc)

_raw_cors = os.getenv("PPT_CORS_ORIGINS", "*")
CORS_ORIGINS = [x.strip() for x in _raw_cors.split(",") if x.strip()] or ["*"]


# ---------------------------------------------------------------------
# Presentation Generation Service
# ---------------------------------------------------------------------

class PresentationService:
    def __init__(self) -> None:
        self.planner = PromptPlanner()

    def generate(self, req: GenerateRequest) -> tuple[str, PresentationPlan, str, Dict[str, Any]]:
        import time
        start_time = time.time()
        template_file = resolve_template_path(req.template_name)
        renderer = PptRenderer(template_file=template_file)
        ai_generated = False
        topic_or_prompt = (req.topic or req.prompt or "Presentation").strip()
        if not req.prompt:
            req.prompt = topic_or_prompt

        user_subtopics = req.subtopics or self.planner.extract_user_subtopics(topic_or_prompt)

        if req.plan is not None:
            if isinstance(req.plan, dict):
                if "presentation" in req.plan and "slides" in req.plan:
                    s_plan = StructuredPresentationPlan(**req.plan)
                    plan = s_plan.to_presentation_plan()
                    plan.structured_plan = s_plan
                else:
                    plan = PresentationPlan(**req.plan)
            elif isinstance(req.plan, StructuredPresentationPlan):
                s_plan = req.plan
                plan = s_plan.to_presentation_plan()
                plan.structured_plan = s_plan
            else:
                plan = req.plan
        else:
            planning_prompt = build_gemini_slide_script(req)
            if planning_prompt:
                ai_generated = True
            else:
                planning_prompt = topic_or_prompt

            plan = self.planner.plan(
                planning_prompt,
                include_title_slide=req.include_title_slide,
                allow_bullets=req.allow_bullets,
                allow_paragraph=req.allow_paragraph,
                allow_chart=req.allow_chart,
                allow_image=req.allow_image,
                allow_section_slide=req.allow_section_slide,
                allow_table=req.allow_table,
                smart_mode=req.smart_mode,
                slide_types=normalize_slide_types(req.slide_types),
                target_slide_count=req.slide_count,
                language=req.language,
                user_subtopics=user_subtopics,
            )

        plan = ensure_conclusion_and_thankyou_slides(plan, topic_or_prompt)
        plan = ensure_plan_images(plan, allow_image=req.allow_image)

        content_theme = normalize_whitespace(req.content_theme or req.background_theme or "")
        if not content_theme or content_theme.lower() in {"auto", "detect"}:
            if req.template_name:
                preset = get_template_preset(req.template_name)
                content_theme = preset.get("theme") or detect_theme(topic_or_prompt)
            else:
                content_theme = detect_theme(topic_or_prompt)

        visual_style = normalize_whitespace(req.visual_style or "")
        if not visual_style or visual_style.lower() in {"auto", "detect"}:
            visual_style = detect_visual_style(topic_or_prompt)

        is_template_mode = bool(req.template_name and req.template_name.strip() and req.template_name.lower() not in ("auto", "none"))
        prs = renderer.render(plan, content_theme=content_theme, visual_style=visual_style, is_template_mode=is_template_mode)
        if getattr(req, "export_format", "pptx") == "pdf":
            file_path = save_presentation_as_pdf(plan, plan.title, presentation_id=req.presentation_id)
        else:
            file_path = save_presentation(prs, plan.title, presentation_id=req.presentation_id)

        execution_time_ms = round((time.time() - start_time) * 1000, 2)
        telemetry = {
            "slides_count": len(plan.slides),
            "theme_used": content_theme,
            "execution_time_ms": execution_time_ms,
            "ai_generated": ai_generated,
        }

        return file_path, plan, plan.title, telemetry



service = PresentationService()


# ---------------------------------------------------------------------
# REST API Endpoints
# ---------------------------------------------------------------------

@router.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@router.get("/unsplash/search")
def search_unsplash_image(query: str) -> Dict[str, str]:
    """Search Unsplash for an exact topic query and return live HD image URL."""
    url = fetch_unsplash_url(query) or fetch_unsplash_image(query) or ""
    return {"query": query, "url": url}


@router.get("/ai-image/generate")
def generate_ai_image_api(prompt: str) -> Dict[str, str]:
    """Generate a realistic custom AI image for slides using Pollinations AI."""
    url_or_path = generate_ai_image(prompt)
    return {"prompt": prompt, "url": url_or_path or ""}


@router.post("/stage1/plan", response_model=PlanPreviewResponse)
@router.post("/plan", response_model=PlanPreviewResponse)
async def preview_plan(req: GenerateRequest) -> PlanPreviewResponse:
    """
    STAGE 1: PPT PLANNER (Plan & User Preview Phase)
    - Topic Analysis
    - Subtopics Generation
    - Slide Count Decision (Dynamic 'auto' or user-specified)
    - Slide Sequence Planning
    - Output: USER PREVIEW Response
    """
    try:
        topic_or_prompt = (req.topic or req.prompt or "Presentation").strip()
        if not req.prompt:
            req.prompt = topic_or_prompt

        subtopics = req.subtopics or service.planner.extract_user_subtopics(topic_or_prompt)
        planning_prompt = await run_in_threadpool(build_gemini_slide_script, req)
        plan = await run_in_threadpool(
            service.planner.plan,
            planning_prompt or topic_or_prompt,
            include_title_slide=req.include_title_slide,
            allow_bullets=req.allow_bullets,
            allow_paragraph=req.allow_paragraph,
            allow_chart=req.allow_chart,
            allow_image=req.allow_image,
            allow_section_slide=req.allow_section_slide,
            allow_table=req.allow_table,
            smart_mode=req.smart_mode,
            slide_types=normalize_slide_types(req.slide_types),
            target_slide_count=req.slide_count,
            language=req.language,
            user_subtopics=subtopics,
        )
        plan = await run_in_threadpool(ensure_plan_images, plan, req.allow_image)
        structured_plan = plan.structured_plan or build_structured_plan(plan, topic_or_prompt)

        clean_topic = service.planner.extract_overall_title(req.topic or structured_plan.presentation.title or topic_or_prompt, [])

        if not subtopics:
            extracted = []
            for s in structured_plan.slides:
                stype = s.content_plan.type.lower().strip()
                stitle = s.content_plan.title.strip()
                if stype not in {"title", "thank_you", "agenda"} and stitle:
                    if not re.search(r"(?i)^(agenda|overview|table of contents|thank you|conclusion|summary|q&a)$", stitle):
                        extracted.append(stitle)
            subtopics = extracted[:30]

        slide_sequence = [
            {
                "slide_number": s.slide_number,
                "title": s.content_plan.title,
                "type": s.content_plan.type,
                "purpose": s.content_plan.purpose,
                "key_message": s.content_plan.key_message,
                "layout": s.design_plan.layout,
            }
            for s in structured_plan.slides
        ]

        return PlanPreviewResponse(
            status="preview_ready",
            topic=clean_topic,
            subtopics=subtopics,
            decided_slide_count=len(plan.slides),
            audience=req.audience or structured_plan.presentation.audience,
            purpose=req.purpose or structured_plan.presentation.purpose,
            slide_sequence=slide_sequence,
            design_system=structured_plan.design_system,
            structured_plan=structured_plan,
            plan=plan,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/stage2/generate", response_model=GenerateResponse)
@router.post("/generate", response_model=GenerateResponse)
async def generate_presentation(req: GenerateRequest, request: Request, background_tasks: BackgroundTasks) -> GenerateResponse:
    """
    STAGE 2: PPT GENERATOR (Execution & PPTX Rendering Phase)
    - Detailed Content Generation
    - Design Planning & Visual Specs
    - Layout Selection & Spacing
    - Visuals / Charts / Tables / Diagrams / Images Generation
    - PPTX Rendering
    - Output: FINAL PPT File & State Persistence
    """
    if not req.presentation_id:
        req.presentation_id = f"pres_{uuid.uuid4().hex[:12]}"

    try:
        file_path, _plan, _title, telemetry = await run_in_threadpool(service.generate, req)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    background_tasks.add_task(cleanup_expired_files, max_age_hours=24)

    job_id = uuid.uuid4().hex
    filename = Path(file_path).name
    download_url = str(request.url_for("download_ppt", file_name=filename))

    presentation_store.save(req.presentation_id, {
        "presentation_id": req.presentation_id,
        "title": _title,
        "template_name": req.template_name,
        "content_theme": telemetry["theme_used"],
        "background_theme": req.background_theme,
        "visual_style": req.visual_style,
        "slides_count": telemetry["slides_count"],
        "file_name": filename,
        "plan": _plan.model_dump(),
        "structured_plan": _plan.structured_plan.model_dump() if _plan.structured_plan else None,
    })

    return GenerateResponse(
        job_id=job_id,
        presentation_id=req.presentation_id,
        status="completed",
        file_name=filename,
        download_url=download_url,
        slides_count=telemetry["slides_count"],
        theme_used=telemetry["theme_used"],
        execution_time_ms=telemetry["execution_time_ms"],
        ai_generated=telemetry["ai_generated"],
        title=_title,
        plan=_plan,
        structured_plan=_plan.structured_plan,
    )


@router.post("/save", response_model=SaveResponse)
async def save_presentation_endpoint(req: GenerateRequest, request: Request, background_tasks: BackgroundTasks) -> SaveResponse:
    """Save presentation to backend, process PPTX generation, persist state JSON, and return saved presentation details."""
    presentation_id = req.presentation_id or f"pres_{uuid.uuid4().hex[:12]}"
    req.presentation_id = presentation_id

    try:
        file_path, _plan, _title, telemetry = await run_in_threadpool(service.generate, req)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    background_tasks.add_task(cleanup_expired_files, max_age_hours=24)

    filename = Path(file_path).name
    download_url = str(request.url_for("download_ppt", file_name=filename))

    saved_record = presentation_store.save(presentation_id, {
        "presentation_id": presentation_id,
        "title": _title,
        "template_name": req.template_name,
        "content_theme": telemetry["theme_used"],
        "background_theme": req.background_theme,
        "visual_style": req.visual_style,
        "slides_count": telemetry["slides_count"],
        "file_name": filename,
        "plan": _plan.model_dump(),
        "structured_plan": _plan.structured_plan.model_dump() if _plan.structured_plan else None,
    })

    return SaveResponse(
        presentation_id=presentation_id,
        status="saved",
        file_name=filename,
        download_url=download_url,
        message="Presentation saved successfully",
        version=saved_record.get("version", 1),
        updated_at=saved_record.get("updated_at"),
        slides_count=telemetry["slides_count"],
        theme_used=telemetry["theme_used"],
        execution_time_ms=telemetry["execution_time_ms"],
        ai_generated=telemetry["ai_generated"],
        plan=_plan,
        structured_plan=_plan.structured_plan,
    )


# ---------------------------------------------------------------------
# AI Voiceover Audio Streaming API
# ---------------------------------------------------------------------
class VoiceoverRequest(BaseModel):
    text: str
    language: Optional[str] = "en-US"
    voice: Optional[str] = None
    slide_index: Optional[int] = 0


@router.post("/voiceover/synthesize")
async def synthesize_voiceover_endpoint(req: VoiceoverRequest, request: Request) -> Dict[str, Any]:
    """Generates neural voice narration MP3 for a slide and returns streaming URL."""
    try:
        filename, file_path = await generate_slide_voiceover(
            text=req.text,
            language=req.language,
            voice=req.voice,
            slide_index=req.slide_index,
        )
        audio_url = str(request.url_for("stream_voiceover_audio", file_name=filename))
        return {
            "status": "ok",
            "filename": filename,
            "audio_url": audio_url,
            "voice_used": select_voice(req.language, req.voice),
        }
    except Exception as exc:
        logger.error("Voiceover synthesis failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Voiceover synthesis failed: {str(exc)}")


@router.get("/voiceover/audio/{file_name}", name="stream_voiceover_audio")
def stream_voiceover_audio(file_name: str) -> FileResponse:
    """Stream synthesized slide voiceover MP3 audio."""
    clean_name = Path(file_name).name
    file_path = VOICEOVER_DIR / clean_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio voiceover file not found")
    return FileResponse(
        path=str(file_path),
        filename=clean_name,
        media_type="audio/mpeg",
    )


# ---------------------------------------------------------------------
# Brand Profile Database Sync Endpoints
# ---------------------------------------------------------------------
@router.get("/brand-profile", response_model=BrandProfileResponse)
def get_brand_profile_endpoint(db: Session = Depends(get_db)) -> BrandProfileResponse:
    """Retrieve saved company brand profile from database for user."""
    brand = db.query(PresentationBrand).filter(PresentationBrand.user_id == 1).first()
    if not brand:
        brand = PresentationBrand(
            user_id=1,
            brand_name="My Brand",
            brand_logo=None,
            brand_color="#38bdf8",
            brand_secondary_color="#c084fc",
            brand_font="Inter",
            brand_footer="",
        )
        db.add(brand)
        db.commit()
        db.refresh(brand)
    return brand


@router.post("/brand-profile", response_model=BrandProfileResponse)
def save_brand_profile_endpoint(profile_in: BrandProfileCreate, db: Session = Depends(get_db)) -> BrandProfileResponse:
    """Save or update presentation brand profile in database."""
    brand = db.query(PresentationBrand).filter(PresentationBrand.user_id == 1).first()
    if not brand:
        brand = PresentationBrand(user_id=1)
        db.add(brand)
    
    brand.brand_name = profile_in.brand_name or "My Brand"
    brand.brand_logo = profile_in.brand_logo
    brand.brand_color = profile_in.brand_color or "#38bdf8"
    brand.brand_secondary_color = profile_in.brand_secondary_color or "#c084fc"
    brand.brand_font = profile_in.brand_font or "Inter"
    brand.brand_footer = profile_in.brand_footer or ""
    db.commit()
    db.refresh(brand)
    return brand


@router.get("/{presentation_id}", response_model=PresentationDetailResponse)
async def get_presentation_details(presentation_id: str, request: Request) -> PresentationDetailResponse:
    """Retrieve exact saved presentation state and metadata by presentation_id."""
    data = presentation_store.get(presentation_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Presentation '{presentation_id}' not found")

    filename = data.get("file_name") or f"{presentation_id}.pptx"
    download_url = str(request.url_for("download_ppt", file_name=filename))

    return PresentationDetailResponse(
        presentation_id=presentation_id,
        title=data.get("title", "Presentation"),
        version=data.get("version", 1),
        updated_at=data.get("updated_at"),
        created_at=data.get("created_at"),
        template_name=data.get("template_name"),
        content_theme=data.get("content_theme"),
        background_theme=data.get("background_theme"),
        visual_style=data.get("visual_style"),
        slides_count=data.get("slides_count", 0),
        file_name=filename,
        download_url=download_url,
        plan=PresentationPlan(**data["plan"]),
        structured_plan=StructuredPresentationPlan(**data["structured_plan"]) if data.get("structured_plan") else None,
    )


@router.put("/{presentation_id}", response_model=SaveResponse)
async def update_presentation_endpoint(presentation_id: str, req: GenerateRequest, request: Request, background_tasks: BackgroundTasks) -> SaveResponse:
    """Update existing presentation state and re-render exported PPTX file."""
    req.presentation_id = presentation_id
    return await save_presentation_endpoint(req, request, background_tasks)



@router.post("/cleanup")
async def trigger_manual_cleanup(max_age_hours: int = 24) -> Dict[str, Any]:
    """Manually trigger background cleanup of output files older than max_age_hours."""
    stats = await run_in_threadpool(cleanup_expired_files, max_age_hours)
    return {"status": "ok", "stats": stats}


@router.post("/refine-slide", response_model=RefineSlideResponse)
async def refine_slide_text(req: RefineSlideRequest) -> RefineSlideResponse:
    """Refine or polish slide text using AI with specific action prompts and smart offline fallback."""
    raw_text = (req.text or "").strip()
    if not raw_text:
        return RefineSlideResponse(refined_text="")

    act = (req.action or "polish").lower()

    if act in {"image", "ai_image"}:
        topic_q = f"{req.presentation_title or ''} {req.slide_title or raw_text}".strip()
        seed_val = uuid.uuid4().int % 10000
        img_url = await run_in_threadpool(generate_ai_image, topic_q, 1280, 720, seed_val)
        return RefineSlideResponse(refined_text=img_url or "")

    if act == "bullets":
        prompt = f"Convert and refine the following text into 3-4 concise, punchy executive bullet points. Return ONLY the bullet points, each starting with '• ':\n\n{raw_text}"
    elif act == "headline":
        prompt = f"Rewrite the following title/text into a single impact-driven, executive headline (under 8 words). Return ONLY the headline text:\n\n{raw_text}"
    elif act == "summarize":
        prompt = f"Summarize and refine the following text into a polished 2-sentence executive summary:\n\n{raw_text}"
    elif act == "diagram" or act == "diagram_steps":
        topic_ctx = ""
        if req.slide_title:
            topic_ctx += f" for the slide topic: '{req.slide_title}'"
        if req.presentation_title:
            topic_ctx += f" (presentation domain: '{req.presentation_title}')"

        prompt = (
            f"Convert the following text or topic into 3-5 concise, clean sequential step node labels for a visual diagram/flowchart{topic_ctx}. "
            f"The diagram MUST be strictly relevant and tailored to this specific topic. DO NOT generate generic machine learning, data engineering, "
            f"or software deployment pipeline steps unless the topic is explicitly about AI/ML or data engineering. "
            f"Format the response ONLY as bracketed steps separated by '➜', for example: [Step 1 Name] ➜ [Step 2 Name] ➜ [Step 3 Name]. "
            f"Keep node labels short (1-4 words each), concise, executive, and DO NOT include bullets, bullet points, numbers, or full sentences:\n\n{raw_text}"
        )
    elif act in {"chart", "chart_data", "metrics"}:
        topic_ctx = f"slide topic: '{req.slide_title or raw_text}'"
        if req.presentation_title:
            topic_ctx += f", presentation domain: '{req.presentation_title}'"

        prompt = (
            f"Generate real-world, highly realistic numerical statistical metrics and data points for a presentation chart on {topic_ctx}. "
            f"DO NOT return artificial linear numbers like [25, 50, 75, 100]. Provide authentic industry benchmarks, percentages, or metrics. "
            f"Format the output strictly as valid JSON with keys: "
            f'{{"title": "<Impact-driven Chart Title>", "series_name": "<Series Legend Name>", "categories": ["Cat 1", "Cat 2", "Cat 3", "Cat 4"], "values": [v1, v2, v3, v4], "chart_type": "<column|line|bar|pie|area|donut>"}}'
        )
    else:
        prompt = f"Refine and polish the following presentation text to be executive, clear, professional, and impact-driven. Return ONLY the refined text:\n\n{raw_text}"

    refined_text = ""
    refined_header = None
    refined_chart = None

    try:
        refined = await run_in_threadpool(generate_response, prompt)
        cleaned = (refined or "").strip()
        if cleaned and not cleaned.startswith("Gemini API key is not configured") and not cleaned.startswith("Gemini error"):
            if cleaned.startswith('"') and cleaned.endswith('"'):
                cleaned = cleaned[1:-1].strip()
            refined_text = cleaned
    except Exception as exc:
        logger.warning("Refine slide AI call failed: %s", exc)

    if act in {"chart", "chart_data", "metrics"} and refined_text:
        try:
            m = re.search(r"\{.*\}", refined_text, re.DOTALL)
            if m:
                chart_obj = json.loads(m.group(0))
                if isinstance(chart_obj, dict) and "categories" in chart_obj and "values" in chart_obj:
                    refined_chart = chart_obj
        except Exception as c_exc:
            logger.warning("Refine chart JSON parse failed: %s", c_exc)

    if act == "diagram" or act == "diagram_steps":
        header_target = req.slide_title or raw_text
        if header_target:
            header_prompt = f"Generate a single concise, professional diagram header/title (3-6 words) strictly relevant to the slide topic '{header_target}'. Return ONLY the title text, no quotes or markdown."
            try:
                h_raw = await run_in_threadpool(generate_response, header_prompt)
                if h_raw and not h_raw.startswith("Gemini"):
                    h_clean = h_raw.strip('"\' \n')
                    if h_clean:
                        refined_header = h_clean
            except Exception as h_exc:
                logger.warning("Diagram header AI generation failed: %s", h_exc)
                if req.slide_title:
                    refined_header = f"{req.slide_title} Process Flow"

    if not refined_text:
        if act == "bullets":
            items = [s.strip("•-* 123456789.") for s in re.split(r"[\n;,]+", raw_text) if s.strip("•-* 123456789.")]
            refined_text = "\n".join(f"• {item.capitalize()}" for item in items[:5]) if items else f"• {raw_text.capitalize()}"
        elif act == "headline":
            words = raw_text.split()
            refined_text = " ".join(w.capitalize() for w in words[:7])
        elif act == "diagram" or "➔" in raw_text or "->" in raw_text:
            steps = [s.strip("[] ") for s in re.split(r"\s*(?:➔|->|-->|\|)\s*", raw_text) if s.strip("[] ")]
            refined_text = " ➔ ".join(f"[{s.title()}]" for s in steps)
        else:
            sentences = [s.strip() for s in re.split(r"[.!?]+", raw_text) if s.strip()]
            refined_text = ". ".join(s.capitalize() for s in sentences) + "." if sentences else raw_text.capitalize()

    return RefineSlideResponse(refined_text=refined_text or raw_text, refined_header=refined_header, refined_chart=refined_chart)


from backend.chats.presentation.services.security import is_safe_output_path

@router.get("/download-presentation/{presentation_id}", name="download_presentation_by_id")
def download_presentation_by_id(presentation_id: str) -> FileResponse:
    """Download exported presentation file corresponding to the latest saved state of presentation_id."""
    data = presentation_store.get(presentation_id)
    filename = data.get("file_name") if data else f"{presentation_id}.pptx"

    safe_file_path = is_safe_output_path(filename) if filename else None
    if not safe_file_path:
        safe_file_path = is_safe_output_path(f"{presentation_id}.pptx")

    if not safe_file_path and data and "plan" in data:
        # Re-render on demand if output file was missing
        try:
            plan = PresentationPlan(**data["plan"])
            if filename.endswith(".pdf"):
                file_path_str = save_presentation_as_pdf(plan, plan.title, presentation_id=presentation_id, target_filename=filename)
            else:
                template_file = resolve_template_path(data.get("template_name"))
                renderer = PptRenderer(template_file=template_file)
                is_template_mode = bool(data.get("template_name") and data.get("template_name").strip() and data.get("template_name").lower() not in ("auto", "none"))
                prs = renderer.render(plan, content_theme=data.get("content_theme", "default"), visual_style=data.get("visual_style", "modern"), is_template_mode=is_template_mode)
                file_path_str = save_presentation(prs, plan.title, presentation_id=presentation_id, target_filename=filename)
            safe_file_path = Path(file_path_str)
        except Exception as exc:
            logger.error("Failed to re-render presentation %s on download: %s", presentation_id, exc)

    if not safe_file_path or not safe_file_path.exists():
        raise HTTPException(status_code=404, detail=f"Presentation '{presentation_id}' output file not found")

    ext = safe_file_path.name.lower().split(".")[-1]
    media_type = (
        "application/pdf"
        if ext == "pdf"
        else "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    return FileResponse(
        path=str(safe_file_path),
        filename=safe_file_path.name,
        media_type=media_type,
    )


@router.get("/download/{file_name}", name="download_ppt")
def download_ppt(file_name: str) -> FileResponse:
    safe_file_path = is_safe_output_path(file_name)
    if not safe_file_path and file_name.startswith("pres_"):
        pres_id = file_name.rsplit(".", 1)[0]
        if presentation_store.exists(pres_id):
            return download_presentation_by_id(pres_id)

    if not safe_file_path:
        raise HTTPException(status_code=404, detail="File not found")

    ext = file_name.lower().split(".")[-1]
    if ext not in ("pptx", "pdf"):
        raise HTTPException(status_code=404, detail="File not found")

    media_type = (
        "application/pdf"
        if ext == "pdf"
        else "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    return FileResponse(
        path=str(safe_file_path),
        filename=file_name,
        media_type=media_type,
    )


@router.get("/templates")
def get_templates() -> list[Dict[str, Any]]:
    """List all available predefined presentation template presets."""
    return list_available_templates()


@router.get("/shapes/catalog")
def get_shapes_catalog() -> Dict[str, Any]:
    """Returns complete catalog of presentation editor shape categories, shape types, and default styling specs."""
    return {
        "categories": [
            {
                "id": "basic_shapes",
                "name": "Basic Shapes",
                "shapes": [
                    {"id": "rectangle", "name": "Rectangle", "default_width": 200, "default_height": 120},
                    {"id": "rounded_rectangle", "name": "Rounded Rectangle", "default_width": 200, "default_height": 120},
                    {"id": "circle", "name": "Circle", "default_width": 140, "default_height": 140},
                    {"id": "oval", "name": "Oval", "default_width": 180, "default_height": 120},
                    {"id": "triangle", "name": "Triangle", "default_width": 160, "default_height": 140},
                    {"id": "diamond", "name": "Diamond", "default_width": 160, "default_height": 160},
                    {"id": "pentagon", "name": "Pentagon", "default_width": 160, "default_height": 160},
                    {"id": "hexagon", "name": "Hexagon", "default_width": 160, "default_height": 140},
                    {"id": "octagon", "name": "Octagon", "default_width": 160, "default_height": 160},
                    {"id": "parallelogram", "name": "Parallelogram", "default_width": 200, "default_height": 120},
                    {"id": "trapezoid", "name": "Trapezoid", "default_width": 200, "default_height": 120},
                    {"id": "star", "name": "Star", "default_width": 160, "default_height": 160},
                    {"id": "heart", "name": "Heart", "default_width": 160, "default_height": 150},
                    {"id": "cross", "name": "Cross", "default_width": 140, "default_height": 140},
                ],
            },
            {
                "id": "lines_connectors",
                "name": "Lines & Connectors",
                "shapes": [
                    {"id": "line", "name": "Line", "default_width": 180, "default_height": 2},
                    {"id": "arrow", "name": "Arrow", "default_width": 180, "default_height": 30},
                    {"id": "double_arrow", "name": "Double Arrow", "default_width": 180, "default_height": 30},
                    {"id": "elbow_connector", "name": "Elbow Connector", "default_width": 180, "default_height": 80},
                    {"id": "curved_connector", "name": "Curved Connector", "default_width": 180, "default_height": 80},
                    {"id": "straight_connector", "name": "Straight Connector", "default_width": 180, "default_height": 2},
                ],
            },
            {
                "id": "flowchart",
                "name": "Flowchart",
                "shapes": [
                    {"id": "process", "name": "Process", "default_width": 180, "default_height": 100},
                    {"id": "decision", "name": "Decision", "default_width": 160, "default_height": 140},
                    {"id": "data", "name": "Data (I/O)", "default_width": 180, "default_height": 100},
                    {"id": "document", "name": "Document", "default_width": 180, "default_height": 120},
                    {"id": "database", "name": "Database", "default_width": 160, "default_height": 160},
                    {"id": "start_end", "name": "Start/End (Terminator)", "default_width": 180, "default_height": 90},
                    {"id": "predefined_process", "name": "Predefined Process", "default_width": 180, "default_height": 100},
                ],
            },
            {
                "id": "callouts",
                "name": "Callouts",
                "shapes": [
                    {"id": "speech_bubble", "name": "Speech Bubble", "default_width": 220, "default_height": 140},
                    {"id": "cloud_callout", "name": "Cloud Callout", "default_width": 220, "default_height": 140},
                    {"id": "rectangular_callout", "name": "Rectangular Callout", "default_width": 220, "default_height": 140},
                    {"id": "rounded_callout", "name": "Rounded Callout", "default_width": 220, "default_height": 140},
                ],
            },
        ],
        "default_style": {
            "fill": "#3B82F6",
            "fill_type": "solid",
            "stroke": "#1E40AF",
            "stroke_width": 2,
            "stroke_style": "solid",
            "opacity": 1.0,
            "shadow": False,
            "text": "",
            "text_style": {
                "font_family": "Arial",
                "font_size": 14,
                "bold": False,
                "italic": False,
                "underline": False,
                "color": "#FFFFFF",
                "align": "center",
                "valign": "middle",
            },
        },
    }


@router.get("/")
def root():
    return {
        "name": APP_NAME,
        "status": "ok",
        "endpoints": ["/plan", "/generate", "/save", "/shapes/catalog", "/download/{file_name}", "/templates", "/voiceover/synthesize", "/brand-profile"],
        "max_slides": MAX_SLIDES,
    }


