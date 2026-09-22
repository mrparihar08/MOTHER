from __future__ import annotations

import os
import re
import hashlib
import urllib.parse
import urllib.request
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ASSET_DIR = Path(os.getenv("PPT_ASSET_DIR", "./assets")).resolve()
ASSET_DIR.mkdir(parents=True, exist_ok=True)

MIN_VALID_IMAGE_BYTES = 2000

AI_STYLE_PRESETS = {
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


def clean_prompt_for_image_gen(prompt: str, style: str = "photorealistic") -> str:
    """Clean and optimize prompt for AI image generation models, incorporating style."""
    if not prompt:
        base_prompt = "modern minimalist executive presentation backdrop, 8k ultra HD resolution, cinematic lighting, masterpiece"
    else:
        cleaned = re.sub(r"[^\w\s\-,.]", " ", prompt)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        matched_preset = None
        for pattern, visual_style in AI_STYLE_PRESETS.items():
            if re.search(pattern, cleaned.lower()):
                matched_preset = f"{cleaned}, {visual_style}"
                break

        base_prompt = matched_preset if matched_preset else f"{cleaned}, modern executive corporate presentation visual, 8k ultra HD resolution, cinematic lighting, highly detailed masterpiece, 16:9 aspect ratio"

    if style and style.strip() and style.lower() not in base_prompt.lower():
        base_prompt = f"{base_prompt}, {style.strip()} style"

    return base_prompt


def generate_ai_image(
    prompt: str,
    width: int = 1920,
    height: int = 1080,
    seed: Optional[int] = None,
    style: str = "photorealistic",
) -> Optional[str]:
    """
    Generate a high-quality customized AI image.
    Supports Gemini Imagen API (when GEMINI_API_KEY is active) and Pollinations AI (FLUX model).
    Saves image locally to ASSET_DIR, passes it through RealESRGAN & PIL quality enhancement,
    and returns web URL or None on total failure.
    """
    enhanced_prompt = clean_prompt_for_image_gen(prompt, style=style)

    seed_val = seed if seed is not None else 42
    cache_key_raw = f"{enhanced_prompt}|{width}|{height}|{seed_val}|{style}"
    prompt_hash = hashlib.md5(cache_key_raw.encode("utf-8")).hexdigest()[:12]
    target_filename = f"ai_gen_{prompt_hash}.jpg"
    target_path = ASSET_DIR / target_filename
    web_url = f"/assets/{target_filename}"

    # Cache hit check - consistently return enhanced image quality
    if target_path.exists() and target_path.stat().st_size > MIN_VALID_IMAGE_BYTES:
        logger.info("Using cached AI image: %s", target_path)
        try:
            from backend.chats.services.image_enhancer import enhance_and_save_image
            enhanced_url = enhance_and_save_image(target_path, output_filename=target_filename, target_width=width, target_height=height)
            if enhanced_url:
                return enhanced_url
        except Exception as enh_exc:
            logger.warning("Enhancement for cached image failed: %s", enh_exc)
        return web_url

    image_bytes = None

    # Option A: Try Gemini Imagen Generation (if Gemini client & API Key configured)
    try:
        from backend.chats.services.gemini_service import get_gemini_client
        client = get_gemini_client()
        if client:
            logger.info("Generating AI image with Gemini Imagen for prompt: %s", prompt[:50])
            result = client.models.generate_images(
                model='imagen-3.0-generate-002',
                prompt=enhanced_prompt,
                config=dict(
                    number_of_images=1,
                    output_mime_type='image/jpeg',
                    aspect_ratio='16:9',
                ),
            )
            if result and hasattr(result, 'generated_images') and result.generated_images:
                image_bytes = result.generated_images[0].image.image_bytes
                logger.info("Gemini Imagen image successfully generated.")
    except Exception as gem_exc:
        logger.info("Gemini Imagen generation skipped/fallback: %s", gem_exc)

    # Option B: Pollinations AI FLUX Model (High Resolution 1080p, Zero API key required)
    encoded_prompt = urllib.parse.quote(enhanced_prompt)
    negative_prompt = urllib.parse.quote("blurry, distorted, low quality, ugly, text, watermark, signature, out of frame, bad anatomy, noise, grain")
    pollinations_url = (
        f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        f"?width={width}&height={height}&model=flux&nologo=true&seed={seed_val}&enhance=true&negative={negative_prompt}"
    )

    if not image_bytes:
        try:
            req = urllib.request.Request(
                pollinations_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "image/webp,image/apng,image/jpeg,image/*,*/*;q=0.8",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                image_bytes = response.read()
        except Exception as exc:
            logger.warning("Pollinations AI FLUX image generation failed: %s", exc)

    # Process and Save Image + Apply RealESRGAN & PIL High Definition Enhancement
    if image_bytes and len(image_bytes) > MIN_VALID_IMAGE_BYTES:
        target_path.write_bytes(image_bytes)
        logger.info("Raw AI Image saved to %s", target_path)

        try:
            from backend.chats.services.image_enhancer import enhance_and_save_image
            enhanced_url = enhance_and_save_image(target_path, output_filename=target_filename, target_width=width, target_height=height)
            if enhanced_url:
                logger.info("HD Enhanced AI Image saved to %s", enhanced_url)
                return enhanced_url
        except Exception as enh_exc:
            logger.warning("Image enhancement skipped for %s: %s", target_filename, enh_exc)

        return web_url

    # Fallback URL consistent with primary request parameters
    return pollinations_url


