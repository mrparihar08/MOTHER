from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple

from backend.chats.services.unsplash_service import fetch_unsplash_image, fetch_unsplash_url, clear_used_image_cache
from backend.chats.services.ai_image_service import generate_ai_image
from backend.chats.presentation.schemas import PresentationPlan, SlidePluginImage
from backend.chats.presentation.geometry import MixedLayoutResolver

logger = logging.getLogger(__name__)


def _clean_image_topic(topic: str) -> str:
    cleaned = re.sub(
        r"(?i)^(?:introduction\ to|overview\ of|executive\ summary\ &|executive\ summary|conclusion\ &|conclusion|summary\ &|summary|key\ takeaways|strategic\ takeaways|takeaways|next\ steps|recommendations|case\ study\ on)\s*",
        "",
        topic or ""
    ).strip()
    cleaned = re.sub(r"^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$", "", cleaned).strip()
    return cleaned if len(cleaned) >= 3 else (topic or "")


def _fetch_single_image(query: str, caption: str, slide_index: int, use_ai_gen: bool) -> str:
    """Fetch an image for a specific query & slide index asynchronously in worker thread pool."""
    url = ""
    if use_ai_gen:
        try:
            url = generate_ai_image(query, seed=slide_index + 100) or ""
        except Exception as exc:
            logger.warning("AI image generation failed for query '%s': %s", query, exc)
    if not url or url.startswith("http"):
        try:
            live_url = fetch_unsplash_url(query, slide_index=slide_index) or (fetch_unsplash_url(caption, slide_index=slide_index) if caption else None)
            local_path = fetch_unsplash_image(query, slide_index=slide_index) or (fetch_unsplash_image(caption, slide_index=slide_index) if caption else None)
            url = live_url or local_path or url or ""
        except Exception as exc:
            logger.warning("Unsplash image fetch failed for query '%s': %s", query, exc)
    return url


def ensure_plan_images(plan: PresentationPlan, allow_image: bool = True) -> PresentationPlan:
    """
    Parallelized image population for presentation plans.
    Executes Unsplash & AI image fetching concurrently using ThreadPoolExecutor.
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
    seen_urls = set()

    topic_keyword = _clean_image_topic(plan.title)

    # 2. Collect existing image plugins needing resolution
    fetch_tasks: List[Tuple[Any, str, str, int]] = []  # (plugin, query, caption, s_idx)
    image_count = 0

    for s_idx, slide in enumerate(plan.slides):
        for plugin in slide.plugins:
            if plugin.type == "image":
                image_count += 1
                data = dict(plugin.data)
                url = data.get("url") or data.get("path") or ""
                caption = data.get("caption") or data.get("title") or slide.title or "Visual"

                if not url or (not url.startswith("http") and not Path(url).exists()):
                    sub_q = _clean_image_topic(slide.title or caption)
                    query = f"{topic_keyword} {sub_q}".strip()
                    fetch_tasks.append((plugin, query, caption, s_idx))
                else:
                    seen_urls.add(url)

    # 3. Parallel fetch for existing image plugins
    if fetch_tasks:
        with ThreadPoolExecutor(max_workers=min(8, len(fetch_tasks))) as executor:
            future_to_task = {
                executor.submit(_fetch_single_image, query, caption, s_idx, use_ai_gen): (plugin, query, caption)
                for plugin, query, caption, s_idx in fetch_tasks
            }
            for future in as_completed(future_to_task):
                plugin, query, caption = future_to_task[future]
                try:
                    fetched_url = future.result()
                    if fetched_url and fetched_url not in seen_urls:
                        seen_urls.add(fetched_url)
                        plugin.data["url"] = fetched_url
                        plugin.data["path"] = fetched_url
                except Exception as exc:
                    logger.warning("Parallel image resolution error: %s", exc)

    # 4. If image_count < 2, identify candidate slides for auto-enrichment and fetch concurrently
    if allow_image and image_count < 2:
        candidate_slides = []
        for idx, slide in enumerate(plan.slides):
            t_l = (slide.title or "").lower()
            if idx == 0 or "agenda" in t_l or "overview" in t_l or slide.layout in {"title_slide", "section_slide"}:
                continue
            if image_count >= 5:
                break

            plugin_types = {p.type for p in slide.plugins}
            if "image" not in plugin_types and not (plugin_types & {"chart", "table", "diagram"}):
                query = f"{slide.title or 'technology'} {plan.title}".strip()
                candidate_slides.append((slide, query, idx))

        if candidate_slides:
            with ThreadPoolExecutor(max_workers=min(6, len(candidate_slides))) as executor:
                future_to_slide = {
                    executor.submit(_fetch_single_image, query, slide.title or "innovation", idx, use_ai_gen): (slide, query, idx)
                    for slide, query, idx in candidate_slides
                }
                for future in as_completed(future_to_slide):
                    slide, query, idx = future_to_slide[future]
                    try:
                        live_url = future.result()
                        if live_url and live_url not in seen_urls and image_count < 5:
                            seen_urls.add(live_url)
                            img_plugin = SlidePluginImage(
                                type="image",
                                data={"url": live_url, "path": live_url, "caption": slide.title or "Visual Highlight", "title": slide.title or "Visual Highlight"}
                            )
                            slide.plugins.append(img_plugin)
                            if slide.layout == "title_content":
                                slide.layout = "mixed_content_slide"
                            image_count += 1

                            box_list = MixedLayoutResolver.resolve_list([p.type for p in slide.plugins])
                            for plugin, b in zip(slide.plugins, box_list):
                                if b:
                                    plugin.data["box"] = {"left": b.left, "top": b.top, "width": b.width, "height": b.height}
                    except Exception as exc:
                        logger.warning("Parallel enrichment image resolution error: %s", exc)

    return plan
