from __future__ import annotations

import os
import re
import urllib.parse
import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger(__name__)

ASSET_DIR = Path(os.getenv("PPT_ASSET_DIR", "./assets")).resolve()
ASSET_DIR.mkdir(parents=True, exist_ok=True)

MIN_VALID_IMAGE_BYTES = 1000

# Google Gemini Imagen Models
PRIMARY_GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", os.getenv("IMAGEN_MODEL", "imagen-3.0-generate-002"))
FALLBACK_GEMINI_MODELS = [
    "imagen-3.0-generate-002",
    "imagen-3.0-fast-generate-001",
    "imagen-3.0-generate-001",
]

# Pollinations Models
PRIMARY_POLLINATIONS_MODEL = os.getenv("POLLINATIONS_IMAGE_MODEL", "flux")
FALLBACK_POLLINATIONS_MODELS = ["flux", "turbo", "flux-realism"]

# Visual style & presentation presets
AI_PRESENTATION_PRESETS = {
    # Cybersecurity & Defense
    r"\b(cyber|security|threat|hack|firewall|encryption|vulnerability|zero[ _]trust|soc|cloud[ _]security)\b": (
        "cybersecurity futuristic dark studio, glowing cyan and purple neon holographic shield grid, matrix data streams, "
        "ultra-detailed 8k octane render, cinematic studio lighting, masterpiece presentation visual"
    ),
    # AI & Robotics / Deep Tech
    r"\b(ai|artificial|machine[ _]learning|deep[ _]learning|neural|robot|llm|gpt|genai|intelligence|automation)\b": (
        "artificial intelligence 3D neural network brain node visualization, glowing fiber optic strands, dark ambient futuristic studio, "
        "Hasselblad 8k photography, volumetric lighting, masterpiece slide visual"
    ),
    # Cloud & Datacenter Infrastructure
    r"\b(cloud|server|datacenter|aws|azure|devops|network|infrastructure|microservice|kubernetes)\b": (
        "modern high-tech cloud computing datacenter server racks with glowing blue and white LED indicators, "
        "sleek glass architectural interior, 8k hyperrealistic photograph, pristine depth of field"
    ),
    # Finance, Fintech & Crypto
    r"\b(finance|stock|money|market|invest|banking|economy|revenue|trading|crypto|fintech|blockchain)\b": (
        "modern executive glass skyscraper office interior overlooking financial district skyline at dusk, "
        "glowing presentation stock chart hologram, Hasselblad 8k photo, ultra-luxurious corporate visual"
    ),
    # Healthcare, Medical & Biotech
    r"\b(health|medical|doctor|hospital|biotech|pharma|patient|clinical|dna|genetics|vaccine)\b": (
        "futuristic medical research laboratory with clean blue ambient lighting, high tech digital microscope and glowing DNA double helix visualization, "
        "8k hyperrealistic photo, award-winning scientific visual"
    ),
    # Marketing, Sales & Strategy
    r"\b(marketing|sales|growth|customer|brand|target|advertising|campaign|strategy|funnel)\b": (
        "modern creative strategy agency office, strategic roadmap analytics digital display board, "
        "executive presentation environment, 8k resolution photo, vibrant colors, crisp focus"
    ),
    # Clean Energy & Sustainability
    r"\b(energy|solar|green|environment|sustainability|wind|clean[ _]tech|climate|eco|carbon)\b": (
        "modern solar panel array field and offshore wind turbines, bright crisp sunlight, dramatic sky, "
        "green technology landscape photo, 8k resolution, cinematic composition"
    ),
    # Real Estate, Architecture & Smart Cities
    r"\b(real[ _]estate|property|building|architecture|construction|housing|smart[ _]city|urban)\b": (
        "modern architectural skyscraper building exterior, sleek glass and steel facade, golden hour lighting, "
        "8k resolution architectural photo, professional tilt-shift visual"
    ),
    # Education, E-Learning & Academia
    r"\b(education|school|college|university|student|learning|course|degree|study|teacher|lecture|classroom)\b": (
        "futuristic university lecture hall with interactive holographic display boards, modern collaborative learning space, "
        "bright inspiring lighting, 8k resolution photograph"
    ),
    # E-Commerce, Retail & Supply Chain
    r"\b(ecommerce|retail|shop|store|product|shopping|cart|logistics|supply[ _]chain|inventory|warehouse)\b": (
        "modern automated fulfillment center warehouse with smart sorting robotics, glowing conveyor belts, "
        "high-tech retail logistics atmosphere, 8k resolution hyperrealistic photo"
    ),
    # Automotive, Mobility & Electric Vehicles
    r"\b(car|vehicle|automotive|ev|electric[ _]vehicle|tesla|autonomous|self[ _]driving|mobility|transport)\b": (
        "sleek electric vehicle prototype on a futuristic lit showroom platform, aerodynamic design, "
        "dramatic studio spotlights, 8k resolution automotive photography"
    ),
    # Aerospace, Space & Satellite
    r"\b(space|rocket|satellite|aerospace|astronomy|galaxy|cosmos|astronaut|nasa|orbit|mission)\b": (
        "deep space exploration rocket launch or orbital satellite over earth horizon, glowing stars and nebula, "
        "cinematic IMAX 8k photography, awe-inspiring visual"
    ),
    # Gaming, XR, Virtual & Augmented Reality
    r"\b(game|gaming|esports|vr|ar|metaverse|virtual[ _]reality|augmented[ _]reality|3d|unreal[ _]engine)\b": (
        "futuristic gamer setup or immersive VR holographic environment, glowing neon RGB lighting, "
        "epic Unreal Engine 5 render, 8k resolution masterpiece"
    ),
    # Human Resources, Leadership & Workplace Culture
    r"\b(team|collaboration|leadership|hr|human[ _]resources|diversity|workplace|culture|hiring|recruitment)\b": (
        "diverse team of executive professionals collaborating in a modern glass conference room, "
        "warm natural sunlight, inspiring corporate culture photograph, 8k resolution"
    ),
    # Legal, Compliance & Ethics
    r"\b(legal|law|justice|compliance|policy|regulation|court|contract|governance|ethics)\b": (
        "modern legal law firm executive office, elegant wooden desk with scale of justice hologram, "
        "crisp professional ambient lighting, 8k resolution photo"
    ),
}

VISUAL_TYPE_PROMPT_MAP = {
    "photo": "high-resolution award-winning studio photograph, cinematic lighting, sharp depth of field",
    "conceptual": "clean conceptual 3D isometric representation, minimalist abstract enterprise visual",
    "conceptual_image": "clean conceptual 3D isometric representation, minimalist abstract enterprise visual",
    "illustration": "premium modern digital vector illustration, crisp lines, contemporary color palette",
    "diagram": "clear clean technical diagram, structured visual infographic components, high clarity",
    "process": "sequential workflow process visual graphic, clean directional flow, modern enterprise style",
    "flowchart": "modern node and connector flowchart visual, elegant structured hierarchy",
    "architecture": "modern system architecture blueprint visualization, sleek isometric glass blocks and glowing connections",
    "infographic": "rich informative visual infographic elements, balanced composition, clear hierarchy",
    "technology": "futuristic technology visualization, glowing nodes and fiber-optic data streams, 8k render",
    "medical": "clean clinical medical visualization, scientific accuracy, luminous biology laboratory aesthetic",
    "historical": "authentic historical visual scene, rich textures, period-accurate lighting, cinematic atmosphere",
    "background": "subtle presentation background texture, clean negative space for typography, non-distracting ambient light",
    "icon": "minimalist high-contrast iconography, clean vector glyph style",
}


def build_image_prompt(
    topic: str = "",
    slide_title: str = "",
    slide_content: str = "",
    slide_type: str = "",
    visual_type: str = "photo",
    theme: str = "",
    style: str = "Professional",
    custom_instructions: str = "",
    aspect_ratio: str = "16:9",
    text_position: str = "left",
) -> str:
    """
    Builds a slide-aware, presentation-optimized visual prompt.
    Includes subject context, visual type guidance, aspect ratio directives,
    and presentation-grade negative prompts (no watermarks, ample negative space for slide text).
    """
    topic_clean = (topic or "").strip()
    title_clean = (slide_title or "").strip()
    content_clean = (slide_content or "").strip()

    # Determine visual style description
    vt_key = (visual_type or "photo").lower().strip()
    vtype_desc = VISUAL_TYPE_PROMPT_MAP.get(vt_key, VISUAL_TYPE_PROMPT_MAP["photo"])

    # Base subject description
    subject_parts = []
    if title_clean:
        subject_parts.append(f"Visual depiction of '{title_clean}'")
    if topic_clean and topic_clean.lower() not in title_clean.lower():
        subject_parts.append(f"in the domain of {topic_clean}")
    if content_clean:
        # Extract main core takeaway (first 120 chars)
        short_content = content_clean.replace("\n", " ")[:120].strip()
        subject_parts.append(f"illustrating {short_content}")

    core_subject = ", ".join(subject_parts) if subject_parts else "modern executive presentation visual"

    # Style descriptor
    style_clean = (style or "Professional").strip()

    # Preset keyword enhancement
    preset_enhancement = ""
    for pattern, visual_style_text in AI_PRESENTATION_PRESETS.items():
        if re.search(pattern, f"{topic_clean} {title_clean} {content_clean}".lower()):
            preset_enhancement = visual_style_text
            break

    # Negative space instruction based on slide layout
    space_instruction = "wide cinematic composition with balanced negative space on the left side for slide text"
    if text_position == "right":
        space_instruction = "wide composition with balanced negative space on the right side for slide text"
    elif text_position == "center":
        space_instruction = "centered subject with clean unobtrusive background margins"

    # Assemble components
    prompt_segments = [
        core_subject,
        vtype_desc,
        f"{style_clean} aesthetic",
    ]
    if preset_enhancement:
        prompt_segments.append(preset_enhancement)
    if theme and theme.lower() not in {"auto", "detect", "none"}:
        prompt_segments.append(f"{theme} color palette")
    if custom_instructions and custom_instructions.strip():
        prompt_segments.append(custom_instructions.strip())

    prompt_segments.extend([
        space_instruction,
        f"{aspect_ratio} widescreen presentation aspect ratio",
        "ultra-high quality, pristine 8k render, professional corporate presentation aesthetic, no text on image, no watermarks, no distorted artifacts"
    ])

    final_prompt = ", ".join([p for p in prompt_segments if p])
    final_prompt = re.sub(r"\s+", " ", final_prompt).strip()
    return final_prompt


def clean_prompt_for_image_gen(
    prompt: str,
    style: str = "photorealistic",
    is_presentation: bool = False,
) -> str:
    """
    Clean and optimize prompt for general / presentation generation.
    """
    if not prompt or not prompt.strip():
        return "breathtaking cinematic masterpiece, ultra-detailed 8k resolution, award-winning photography, volumetric lighting"

    cleaned = re.sub(r"[^\w\s\-,.:;'\"()%/]", " ", prompt)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if is_presentation:
        matched_preset = None
        for pattern, visual_style in AI_PRESENTATION_PRESETS.items():
            if re.search(pattern, cleaned.lower()):
                matched_preset = f"{cleaned}, {visual_style}"
                break
        base_prompt = matched_preset if matched_preset else f"{cleaned}, modern executive corporate presentation visual, 8k ultra HD resolution, cinematic lighting, highly detailed masterpiece, 16:9 aspect ratio, no watermarks, no text overlay"
    else:
        words = cleaned.split()
        if len(words) > 12:
            base_prompt = cleaned
        elif len(words) <= 3:
            base_prompt = f"{cleaned}, highly detailed {style}, 8k resolution, beautiful composition, cinematic lighting, sharp focus, masterpiece"
        else:
            base_prompt = f"{cleaned}, photorealistic, ultra-detailed 8k resolution, cinematic lighting, professional photography, masterpiece"

    if style and style.strip() and style.lower() not in base_prompt.lower() and not is_presentation:
        base_prompt = f"{base_prompt}, {style.strip()} style"

    return base_prompt


class GeminiImageProvider:
    """
    Google Gemini Image Generation Provider using official Google GenAI SDK (Imagen 3).
    """
    def __init__(self):
        self.primary_model = os.getenv("GEMINI_IMAGE_MODEL", os.getenv("IMAGEN_MODEL", "imagen-3.0-generate-002"))
        self.fallback_models = [
            self.primary_model,
            "imagen-3.0-generate-002",
            "imagen-3.0-fast-generate-001",
            "imagen-3.0-generate-001",
        ]
        # Remove duplicate fallback models preserving order
        seen = set()
        self.models_to_try = [m for m in self.fallback_models if not (m in seen or seen.add(m))]

    def is_available(self) -> bool:
        api_key = os.getenv("GEMINI_API_KEY")
        return bool(api_key and api_key.strip())

    def generate(
        self,
        prompt: str,
        width: int = 1920,
        height: int = 1080,
        aspect_ratio: str = "16:9",
        style: str = "Professional",
        seed: Optional[int] = None,
        is_presentation: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Generates an image via Google Gemini Imagen 3 and stores it locally in ASSET_DIR.
        """
        if not self.is_available():
            logger.warning("GeminiImageProvider: GEMINI_API_KEY is not configured.")
            return None

        # Standardize aspect ratio for Gemini Imagen ("16:9", "1:1", "4:3", "3:4", "9:16")
        ar = aspect_ratio.strip() if aspect_ratio else "16:9"
        if ar not in {"16:9", "1:1", "4:3", "3:4", "9:16"}:
            ar = "16:9" if width > height else "1:1" if width == height else "9:16"

        seed_val = seed if seed is not None else 42
        cache_key_raw = f"gemini_{prompt}|{width}|{height}|{ar}|{seed_val}|{style}"
        prompt_hash = hashlib.md5(cache_key_raw.encode("utf-8")).hexdigest()[:12]
        target_filename = f"gemini_imagen_{prompt_hash}.jpg"
        target_path = ASSET_DIR / target_filename
        web_url = f"/assets/{target_filename}"

        # Cache check
        if target_path.exists() and target_path.stat().st_size > MIN_VALID_IMAGE_BYTES:
            logger.info("Using cached Gemini Imagen image: %s", target_path)
            return {
                "provider": "gemini",
                "model": self.primary_model,
                "image_url": web_url,
                "url": web_url,
                "mime_type": "image/jpeg",
                "width": width,
                "height": height,
                "aspect_ratio": ar,
                "prompt": prompt,
                "source": "Google Gemini Imagen 3",
                "generated": True,
                "license": "AI Generated (Gemini)",
                "attribution": f"Image generated via Google Gemini ({self.primary_model})",
            }

        try:
            from backend.chats.services.gemini_service import get_gemini_client
            client = get_gemini_client()
            if not client:
                logger.error("GeminiImageProvider: get_gemini_client() returned None.")
                return None

            image_bytes = None
            used_model = self.primary_model
            last_error = None

            for model_name in self.models_to_try:
                try:
                    logger.info("GeminiImageProvider: Requesting image with model '%s'...", model_name)
                    result = client.models.generate_images(
                        model=model_name,
                        prompt=prompt,
                        config=dict(
                            number_of_images=1,
                            output_mime_type="image/jpeg",
                            aspect_ratio=ar,
                        ),
                    )
                    if result and hasattr(result, "generated_images") and result.generated_images:
                        image_bytes = result.generated_images[0].image.image_bytes
                        used_model = model_name
                        logger.info("GeminiImageProvider: Image generated successfully with model '%s'.", model_name)
                        break
                except Exception as e:
                    last_error = e
                    logger.warning("GeminiImageProvider model '%s' failed: %s. Trying next fallback...", model_name, e)
                    continue

            if image_bytes and len(image_bytes) > MIN_VALID_IMAGE_BYTES:
                target_path.write_bytes(image_bytes)
                logger.info("GeminiImageProvider: Saved image to %s (%d bytes)", target_path, len(image_bytes))

                # Optional quality enhancement
                try:
                    from backend.chats.services.image_enhancer import enhance_and_save_image
                    enhanced_url = enhance_and_save_image(target_path, output_filename=target_filename, target_width=width, target_height=height)
                    if enhanced_url:
                        web_url = enhanced_url
                except Exception as enh_exc:
                    logger.debug("Image enhancement skipped for %s: %s", target_filename, enh_exc)

                return {
                    "provider": "gemini",
                    "model": used_model,
                    "image_url": web_url,
                    "url": web_url,
                    "mime_type": "image/jpeg",
                    "width": width,
                    "height": height,
                    "aspect_ratio": ar,
                    "prompt": prompt,
                    "source": "Google Gemini Imagen 3",
                    "generated": True,
                    "license": "AI Generated (Gemini)",
                    "attribution": f"Image generated via Google Gemini ({used_model})",
                }
            else:
                logger.error("GeminiImageProvider: All Gemini models failed. Last error: %s", last_error)
                return None

        except Exception as exc:
            logger.exception("GeminiImageProvider exception: %s", exc)
            return None


class PollinationsImageProvider:
    """
    Pollinations.ai Image Generation Provider via backend proxy.
    Supports official Pollinations API models (flux, turbo, etc.), customizable aspect ratio and seed.
    """
    def __init__(self):
        self.primary_model = os.getenv("POLLINATIONS_IMAGE_MODEL", "flux")
        self.fallback_models = [self.primary_model, "turbo", "flux-realism"]
        seen = set()
        self.models_to_try = [m for m in self.fallback_models if not (m in seen or seen.add(m))]
        self.api_key = os.getenv("POLLINATIONS_API_KEY", "")

    def is_available(self) -> bool:
        # Pollinations can work with or without an API key (public tier + authenticated tier)
        return True

    def _calc_dimensions(self, aspect_ratio: str, width: int, height: int) -> tuple[int, int]:
        ar = (aspect_ratio or "16:9").strip()
        if ar == "16:9":
            return (1280, 720)
        elif ar == "4:3":
            return (1024, 768)
        elif ar == "1:1":
            return (1024, 1024)
        elif ar == "9:16":
            return (720, 1280)
        elif ar == "3:4":
            return (768, 1024)
        return (width if width > 0 else 1280, height if height > 0 else 720)

    def generate(
        self,
        prompt: str,
        width: int = 1920,
        height: int = 1080,
        aspect_ratio: str = "16:9",
        style: str = "Professional",
        seed: Optional[int] = None,
        is_presentation: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Generates an image via Pollinations.ai API and stores it locally in ASSET_DIR.
        """
        w, h = self._calc_dimensions(aspect_ratio, width, height)
        seed_val = seed if seed is not None else 42

        cache_key_raw = f"pollinations_{prompt}|{w}|{h}|{aspect_ratio}|{seed_val}|{style}"
        prompt_hash = hashlib.md5(cache_key_raw.encode("utf-8")).hexdigest()[:12]
        target_filename = f"pollinations_{prompt_hash}.jpg"
        target_path = ASSET_DIR / target_filename
        web_url = f"/assets/{target_filename}"

        # Cache check
        if target_path.exists() and target_path.stat().st_size > MIN_VALID_IMAGE_BYTES:
            logger.info("Using cached Pollinations image: %s", target_path)
            return {
                "provider": "pollinations",
                "model": self.primary_model,
                "image_url": web_url,
                "url": web_url,
                "mime_type": "image/jpeg",
                "width": w,
                "height": h,
                "aspect_ratio": aspect_ratio,
                "prompt": prompt,
                "source": "Pollinations.ai",
                "generated": True,
                "license": "AI Generated (Pollinations)",
                "attribution": f"Image generated via Pollinations.ai ({self.primary_model})",
            }

        encoded_prompt = urllib.parse.quote(prompt[:800])
        headers = {"User-Agent": "VityaPresentationGenerator/2.0"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        last_error = None
        for model_name in self.models_to_try:
            try:
                pollinations_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}"
                params = {
                    "width": w,
                    "height": h,
                    "model": model_name,
                    "seed": seed_val,
                    "nologo": "true",
                    "private": "true",
                    "nofeed": "true",
                }
                if self.api_key:
                    params["key"] = self.api_key

                logger.info("PollinationsImageProvider: Requesting image from %s with model '%s'...", pollinations_url, model_name)
                resp = requests.get(pollinations_url, params=params, headers=headers, timeout=30)
                
                if resp.status_code == 200:
                    c_type = resp.headers.get("Content-Type", "").lower()
                    data = resp.content
                    if len(data) > MIN_VALID_IMAGE_BYTES and ("image" in c_type or data.startswith(b"\xff\xd8") or data.startswith(b"\x89PNG")):
                        target_path.write_bytes(data)
                        logger.info("PollinationsImageProvider: Successfully saved image to %s (%d bytes)", target_path, len(data))

                        # Optional quality enhancement
                        try:
                            from backend.chats.services.image_enhancer import enhance_and_save_image
                            enhanced_url = enhance_and_save_image(target_path, output_filename=target_filename, target_width=w, target_height=h)
                            if enhanced_url:
                                web_url = enhanced_url
                        except Exception as enh_exc:
                            logger.debug("Enhancement skipped for %s: %s", target_filename, enh_exc)

                        return {
                            "provider": "pollinations",
                            "model": model_name,
                            "image_url": web_url,
                            "url": web_url,
                            "mime_type": "image/jpeg",
                            "width": w,
                            "height": h,
                            "aspect_ratio": aspect_ratio,
                            "prompt": prompt,
                            "source": "Pollinations.ai",
                            "generated": True,
                            "license": "AI Generated (Pollinations)",
                            "attribution": f"Image generated via Pollinations.ai ({model_name})",
                        }
                    else:
                        logger.warning("Pollinations returned non-image content or insufficient bytes (%d bytes, type: %s)", len(data), c_type)
                else:
                    logger.warning("Pollinations request returned HTTP %s: %s", resp.status_code, resp.text[:120])
            except Exception as e:
                last_error = e
                logger.warning("Pollinations model '%s' failed: %s. Trying next...", model_name, e)
                continue

        logger.error("PollinationsImageProvider: All Pollinations requests failed. Last error: %s", last_error)
        return None


class AIImageService:
    """
    Unified Central AI Image Generation Service.
    Coordinates Gemini and Pollinations.ai providers, handles auto-decision logic,
    slide-aware prompt synthesis, and automatic fallback.
    """
    def __init__(self):
        self.gemini_provider = GeminiImageProvider()
        self.pollinations_provider = PollinationsImageProvider()

    def generate(
        self,
        prompt: Optional[str] = None,
        provider: str = "auto",
        aspect_ratio: str = "16:9",
        visual_type: str = "photo",
        style: str = "Professional",
        width: int = 1920,
        height: int = 1080,
        topic: str = "",
        slide_title: str = "",
        slide_content: str = "",
        slide_type: str = "",
        theme: str = "",
        custom_instructions: str = "",
        seed: Optional[int] = None,
        is_presentation: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate an AI image with provider routing:
        - "gemini": Gemini Imagen 3 only.
        - "pollinations": Pollinations.ai only.
        - "auto": Intelligent decision (Gemini preferred for complex slides/diagrams if available, falling back to Pollinations; Pollinations preferred for artistic/quick prompts, falling back to Gemini).
        """
        # Synthesize slide-aware prompt if context is supplied or prompt is minimal
        if topic or slide_title or slide_content or not prompt:
            full_prompt = build_image_prompt(
                topic=topic,
                slide_title=slide_title,
                slide_content=slide_content,
                slide_type=slide_type,
                visual_type=visual_type,
                theme=theme,
                style=style,
                custom_instructions=custom_instructions or prompt or "",
                aspect_ratio=aspect_ratio,
            )
        else:
            full_prompt = clean_prompt_for_image_gen(prompt, style=style, is_presentation=is_presentation)

        req_provider = (provider or "auto").lower().strip()

        # 1. Gemini Only
        if req_provider == "gemini":
            logger.info("AIImageService: Executing explicit Gemini provider for prompt: %s", full_prompt[:60])
            return self.gemini_provider.generate(
                prompt=full_prompt,
                width=width,
                height=height,
                aspect_ratio=aspect_ratio,
                style=style,
                seed=seed,
                is_presentation=is_presentation,
            )

        # 2. Pollinations Only
        if req_provider == "pollinations":
            logger.info("AIImageService: Executing explicit Pollinations provider for prompt: %s", full_prompt[:60])
            return self.pollinations_provider.generate(
                prompt=full_prompt,
                width=width,
                height=height,
                aspect_ratio=aspect_ratio,
                style=style,
                seed=seed,
                is_presentation=is_presentation,
            )

        # 3. AUTO Mode: Smart provider selection with graceful automatic fallback
        logger.info("AIImageService: Running in AUTO mode...")
        gemini_ready = self.gemini_provider.is_available()

        # If Gemini is ready and the visual type is complex (photo, conceptual, diagram, tech, medical), try Gemini first
        if gemini_ready:
            logger.info("AIImageService [AUTO]: Attempting primary provider Gemini...")
            gemini_result = self.gemini_provider.generate(
                prompt=full_prompt,
                width=width,
                height=height,
                aspect_ratio=aspect_ratio,
                style=style,
                seed=seed,
                is_presentation=is_presentation,
            )
            if gemini_result:
                return gemini_result
            logger.warning("AIImageService [AUTO]: Gemini provider failed or timed out. Falling back to Pollinations.ai...")

        # Fallback to Pollinations
        logger.info("AIImageService [AUTO]: Attempting provider Pollinations.ai...")
        pollinations_result = self.pollinations_provider.generate(
            prompt=full_prompt,
            width=width,
            height=height,
            aspect_ratio=aspect_ratio,
            style=style,
            seed=seed,
            is_presentation=is_presentation,
        )
        if pollinations_result:
            return pollinations_result

        # Final attempt: If Gemini wasn't attempted first (e.g. key became available or non-default config), try Gemini
        if not gemini_ready:
            logger.info("AIImageService [AUTO]: Pollinations failed, checking if Gemini is reachable as secondary...")
            gemini_result = self.gemini_provider.generate(
                prompt=full_prompt,
                width=width,
                height=height,
                aspect_ratio=aspect_ratio,
                style=style,
                seed=seed,
                is_presentation=is_presentation,
            )
            if gemini_result:
                return gemini_result

        logger.error("AIImageService [AUTO]: All image generation providers failed.")
        return None


# Global singleton instance
ai_image_service = AIImageService()


def generate_ai_image(
    prompt: str,
    width: int = 1920,
    height: int = 1080,
    seed: Optional[int] = None,
    style: str = "photorealistic",
    is_presentation: bool = False,
    provider: str = "auto",
    aspect_ratio: str = "16:9",
    topic: str = "",
    slide_title: str = "",
    slide_content: str = "",
    visual_type: str = "photo",
) -> Optional[str]:
    """
    Convenience wrapper function for backward compatibility across the codebase.
    Returns the local web URL (e.g. '/assets/gemini_imagen_xxxx.jpg') or None.
    """
    result = ai_image_service.generate(
        prompt=prompt,
        provider=provider,
        aspect_ratio=aspect_ratio,
        visual_type=visual_type,
        style=style,
        width=width,
        height=height,
        topic=topic,
        slide_title=slide_title,
        slide_content=slide_content,
        seed=seed,
        is_presentation=is_presentation,
    )
    if result and isinstance(result, dict):
        return result.get("image_url") or result.get("url")
    return None
