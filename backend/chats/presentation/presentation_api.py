from __future__ import annotations

import collections
import collections.abc

# Forward compatibility fix for python-pptx / collections
for name in ("Container", "Mapping", "MutableMapping", "Sequence", "MutableSequence", "Iterable", "Callable"):
    if not hasattr(collections, name) and hasattr(collections.abc, name):
        setattr(collections, name, getattr(collections.abc, name))

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

# Presentation Modules
from backend.chats.presentation.schemas import (
    GenerateRequest,
    GenerateResponse,
    SaveResponse,
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
    SlideOutlineItem,
    Stage1PlanResponse,
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
    clean_ai_instructions,
    ensure_conclusion_and_thankyou_slides,
    normalize_whitespace,
    normalize_slide_types,
    resolve_template_path,
    classify_prompt_domain,
)
from backend.chats.presentation.services.image_manager import ensure_plan_images
from backend.chats.presentation.exporter import save_presentation, OUTPUT_DIR
from backend.chats.presentation.renderers.ppt_renderer import PptRenderer

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
            req.prompt = topic_or_prompt
            script_response = build_gemini_slide_script(req)
            if script_response:
                ai_generated = True
                planning_prompt = script_response
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
            )

        plan = ensure_conclusion_and_thankyou_slides(plan, topic_or_prompt)
        plan = ensure_plan_images(plan, allow_image=req.allow_image)

        content_theme = normalize_whitespace(req.content_theme or req.background_theme or "")
        if not content_theme or content_theme.lower() in {"auto", "detect"}:
            content_theme = detect_theme(topic_or_prompt)

        visual_style = normalize_whitespace(req.visual_style or "")
        if not visual_style or visual_style.lower() in {"auto", "detect"}:
            visual_style = detect_visual_style(topic_or_prompt)

        prs = renderer.render(plan, content_theme=content_theme, visual_style=visual_style)
        file_path = save_presentation(prs, plan.title)

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


@router.post("/stage1-plan", response_model=Stage1PlanResponse)
async def stage1_ppt_planner(req: GenerateRequest) -> Stage1PlanResponse:
    """STAGE 1: PPT PLANNER — Topic analysis, subtopics generation, dynamic slide count decision, and slide sequence outline for User Preview."""
    try:
        topic_or_prompt = (req.topic or req.prompt or "Presentation").strip()
        req.prompt = topic_or_prompt
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
        )

        outline_sequence: List[SlideOutlineItem] = []
        if plan.structured_plan and plan.structured_plan.slides:
            for s in plan.structured_plan.slides:
                cp = s.content_plan
                dp = s.design_plan
                sub_pts = cp.content if isinstance(cp.content, list) else ([cp.content] if cp.content else [])
                outline_sequence.append(SlideOutlineItem(
                    slide_number=s.slide_number,
                    title=cp.title,
                    subtitle=cp.subtitle or "",
                    slide_type=cp.type,
                    purpose=cp.purpose,
                    key_message=cp.key_message or cp.title,
                    visual_requirement=dp.visual.get("type", "none") if isinstance(dp.visual, dict) else "none",
                    subtopics=sub_pts,
                ))
        else:
            for idx, slide in enumerate(plan.slides):
                outline_sequence.append(SlideOutlineItem(
                    slide_number=idx + 1,
                    title=slide.title or f"Slide {idx + 1}",
                    subtitle=slide.subtitle or "",
                    slide_type=slide.layout or "mixed_content_slide",
                    purpose=f"Communicate points for {slide.title}",
                    key_message=slide.title or "",
                    visual_requirement="mixed",
                    subtopics=[],
                ))

        domain = classify_prompt_domain(topic_or_prompt)

        return Stage1PlanResponse(
            title=plan.title,
            subtitle=plan.slides[0].subtitle if plan.slides else "",
            topic=topic_or_prompt,
            domain=domain,
            audience=req.audience or "General Audience",
            purpose=req.purpose or "Executive Presentation",
            recommended_slide_count=len(plan.slides),
            slide_sequence=outline_sequence,
            status="preview_ready",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/stage2-generate", response_model=GenerateResponse)
async def stage2_ppt_generator(req: GenerateRequest, request: Request, background_tasks: BackgroundTasks) -> GenerateResponse:
    """STAGE 2: PPT GENERATOR — Detailed content generation, design planning, layout selection, visuals/charts, and PPTX rendering to produce Final PPT."""
    return await generate_presentation(req, request, background_tasks)


@router.post("/plan", response_model=PresentationPlan)
async def preview_plan(req: GenerateRequest) -> PresentationPlan:
    try:
        topic_or_prompt = (req.topic or req.prompt or "Presentation").strip()
        req.prompt = topic_or_prompt
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
        )
        return ensure_plan_images(plan, allow_image=req.allow_image)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/generate", response_model=GenerateResponse)
async def generate_presentation(req: GenerateRequest, request: Request, background_tasks: BackgroundTasks) -> GenerateResponse:
    try:
        file_path, _plan, _title, telemetry = await run_in_threadpool(service.generate, req)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    background_tasks.add_task(cleanup_expired_files, max_age_hours=24)

    job_id = uuid.uuid4().hex
    filename = Path(file_path).name
    download_url = str(request.url_for("download_ppt", file_name=filename))

    return GenerateResponse(
        job_id=job_id,
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
    """Save presentation to backend, process PPTX generation, and return saved presentation details."""
    try:
        file_path, _plan, _title, telemetry = await run_in_threadpool(service.generate, req)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    background_tasks.add_task(cleanup_expired_files, max_age_hours=24)

    presentation_id = f"pres_{uuid.uuid4().hex[:12]}"
    filename = Path(file_path).name
    download_url = str(request.url_for("download_ppt", file_name=filename))

    return SaveResponse(
        presentation_id=presentation_id,
        status="saved",
        file_name=filename,
        download_url=download_url,
        message="Presentation saved successfully",
        slides_count=telemetry["slides_count"],
        theme_used=telemetry["theme_used"],
        execution_time_ms=telemetry["execution_time_ms"],
        ai_generated=telemetry["ai_generated"],
        structured_plan=_plan.structured_plan,
    )


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

@router.get("/download/{file_name}", name="download_ppt")
def download_ppt(file_name: str) -> FileResponse:
    safe_file_path = is_safe_output_path(file_name)
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


@router.get("/")
def root():
    return {
        "name": APP_NAME,
        "status": "ok",
        "endpoints": ["/plan", "/generate", "/download/{file_name}"],
        "max_slides": MAX_SLIDES,
    }
