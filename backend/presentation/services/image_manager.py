from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from backend.chats.services.unsplash_service import clear_used_image_cache
from backend.presentation.services.ai_image_service import generate_ai_image
from backend.presentation.schemas import PresentationPlan, SlidePluginImage, ImageResult
from backend.presentation.services.image_search import (
    suggest_images_for_slide,
    fetch_and_cache_image,
)

logger = logging.getLogger(__name__)


def _clean_image_topic(topic: str) -> str:
    cleaned = re.sub(
        r"(?i)^(?:introduction\ to|overview\ of|executive\ summary\ &|executive\ summary|conclusion\ &|conclusion|summary\ &|summary|key\ takeaways|strategic\ takeaways|takeaways|next\ steps|recommendations|case\ study\ on)\s*",
        "",
        topic or ""
    ).strip()
    cleaned = re.sub(r"^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$", "", cleaned).strip()
    return cleaned if len(cleaned) >= 3 else (topic or "")


def _fetch_single_image_metadata(
    presentation_topic: str,
    slide_title: str,
    slide_content: str,
    caption: str,
    slide_index: int,
    use_ai_gen: bool,
    seen_urls: Set[str],
) -> Dict[str, Any]:
    """
    Fetches image metadata using the smart discovery pipeline:
    Openverse -> Wikimedia Commons -> AI generation (if requested) -> Unsplash fallback.
    """
    res_dict: Dict[str, Any] = {
        "url": "",
        "caption": caption or slide_title or "Visual",
        "attribution": "",
        "license": "",
        "creator": "",
        "provider": "",
        "source_url": "",
    }

    # 1. Openverse / Wikimedia Discovery
    try:
        suggest_resp = suggest_images_for_slide(
            presentation_topic=presentation_topic,
            slide_title=slide_title,
            slide_content=slide_content,
            slide_index=slide_index,
            used_urls=seen_urls,
        )
        if suggest_resp.suggested_images:
            best_img: ImageResult = suggest_resp.suggested_images[0]
            res_dict["url"] = best_img.image_url
            res_dict["caption"] = best_img.title or caption or slide_title
            res_dict["attribution"] = best_img.attribution
            res_dict["license"] = best_img.license
            res_dict["creator"] = best_img.creator
            res_dict["provider"] = best_img.provider
            res_dict["source_url"] = best_img.source_url
            return res_dict
    except Exception as exc:
        logger.warning("Openverse/Wikimedia image discovery failed for slide '%s': %s", slide_title, exc)

    # 2. AI Image Generation fallback if configured
    if use_ai_gen:
        try:
            query = f"{presentation_topic} {slide_title}".strip()
            ai_url = generate_ai_image(query, seed=slide_index + 100) or ""
            if ai_url:
                res_dict["url"] = ai_url
                res_dict["provider"] = "ai"
                res_dict["attribution"] = "Image: AI Generated Visual"
                return res_dict
        except Exception as exc:
            logger.warning("AI image generation fallback failed for slide '%s': %s", slide_title, exc)

    return res_dict


def ensure_plan_images(plan: PresentationPlan, allow_image: bool = True) -> PresentationPlan:
    """
    Parallelized image discovery and licensing population for presentation plans.
    Integrates Openverse, Wikimedia Commons, and fallback visual generation.
    """
    clear_used_image_cache()

    # 1. Strip images from Agenda / Overview cover slides
    for slide in plan.slides:
        t_l = (slide.title or "").lower()
        if "agenda" in t_l or "overview" in t_l:
            slide.plugins = [p for p in slide.plugins if p.type != "image"]
            if slide.layout == "mixed_content_slide":
                slide.layout = "bullets_slide"

    use_ai_gen = getattr(plan, "use_ai_image_generation", True)
    seen_urls: Set[str] = set()

    # 2. Collect existing image plugins needing resolution
    fetch_tasks: List[Tuple[Any, str, str, int]] = []  # (plugin, s_title, s_content, s_idx)
    image_count = 0

    for s_idx, slide in enumerate(plan.slides):
        for plugin in slide.plugins:
            if plugin.type == "image":
                image_count += 1
                data = dict(plugin.data)
                url = data.get("url") or data.get("path") or ""
                caption = data.get("caption") or data.get("title") or slide.title or "Visual"

                if not url or (not url.startswith("http") and not Path(url).exists()):
                    fetch_tasks.append((plugin, slide.title or "", "", s_idx))
                else:
                    seen_urls.add(url)

    # 3. Parallel fetch for existing image plugins
    if fetch_tasks:
        with ThreadPoolExecutor(max_workers=min(8, len(fetch_tasks))) as executor:
            future_to_task = {
                executor.submit(_fetch_single_image_metadata, plan.title, s_title, s_content, s_title, s_idx, use_ai_gen, seen_urls): (plugin, s_title)
                for plugin, s_title, s_content, s_idx in fetch_tasks
            }
            for future in as_completed(future_to_task):
                plugin, s_title = future_to_task[future]
                try:
                    meta = future.result()
                    fetched_url = meta.get("url") or ""
                    if fetched_url:
                        seen_urls.add(fetched_url)
                        plugin.data["url"] = fetched_url
                        plugin.data["path"] = fetched_url
                        if meta.get("attribution"):
                            plugin.data["attribution"] = meta["attribution"]
                        if meta.get("license"):
                            plugin.data["license"] = meta["license"]
                        if meta.get("creator"):
                            plugin.data["creator"] = meta["creator"]
                        if meta.get("provider"):
                            plugin.data["provider"] = meta["provider"]
                        if meta.get("source_url"):
                            plugin.data["source_url"] = meta["source_url"]
                except Exception as exc:
                    logger.warning("Parallel image metadata resolution error: %s", exc)

    # 4. Auto-enrich presentation with images if image_count < 2
    if allow_image and image_count < 2:
        candidate_slides = []
        for idx, slide in enumerate(plan.slides):
            t_l = (slide.title or "").lower()
            if idx == 0 or "agenda" in t_l or "overview" in t_l or slide.layout in {"title_slide", "section_slide"}:
                continue
            if image_count >= 4:
                break

            has_img = any(p.type == "image" for p in slide.plugins)
            has_chart_or_table = any(p.type in {"chart", "table", "diagram"} for p in slide.plugins)
            if not has_img and not has_chart_or_table:
                candidate_slides.append((idx, slide))

        for idx, slide in candidate_slides[:2]:
            meta = _fetch_single_image_metadata(
                presentation_topic=plan.title,
                slide_title=slide.title or "",
                slide_content="",
                caption=slide.title or "Visual",
                slide_index=idx,
                use_ai_gen=use_ai_gen,
                seen_urls=seen_urls,
            )
            img_url = meta.get("url") or ""
            if img_url:
                seen_urls.add(img_url)
                img_data = {
                    "url": img_url,
                    "path": img_url,
                    "caption": slide.title or "Visual",
                    "attribution": meta.get("attribution", ""),
                    "license": meta.get("license", ""),
                    "creator": meta.get("creator", ""),
                    "provider": meta.get("provider", ""),
                    "source_url": meta.get("source_url", ""),
                }
                slide.plugins.append(SlidePluginImage(type="image", data=img_data))
                if slide.layout in {"bullets_slide", "title_content"}:
                    slide.layout = "mixed_content_slide"
                image_count += 1

    return plan
