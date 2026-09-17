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

AI_STYLE_PRESETS = {
    r"(cyber|security|threat|hack|firewall|encryption|vulnerability|zero_trust)": "cybersecurity futuristic dark studio, glowing holographic shield and server node grid, cyan and purple neon highlights, cinematic lighting, 8k resolution, octane render, ultra-detailed, presentation slide visual",
    r"(ai|artificial|machine_learning|deep_learning|neural|robot|llm|gpt|genai|intelligence)": "artificial intelligence 3D neural network brain node visualization, glowing fiber optics, dark ambient background, futuristic 8k octane render, masterpiece presentation photo",
    r"(cloud|server|datacenter|aws|azure|devops|network|infrastructure|microservice)": "modern cloud computing datacenter server racks with glowing blue and white LED indicators, high tech glass architectural interior, 8k hyperrealistic photograph",
    r"(finance|stock|money|market|invest|banking|economy|revenue|trading|crypto|fintech)": "modern executive glass skyscraper office interior overlooking financial district skyline, elegant presentation stock chart hologram, Hasselblad 8k photo",
    r"(health|medical|doctor|hospital|biotech|pharma|patient|clinical|dna)": "futuristic medical research laboratory, clean blue ambient lighting, high tech microscope and DNA visualization, 8k hyperrealistic photo",
    r"(marketing|sales|growth|customer|brand|target|advertising|campaign)": "modern creative strategy agency office, strategic roadmap digital display board, executive presentation environment, 8k resolution photo",
    r"(energy|solar|green|environment|sustainability|wind|clean_tech)": "modern solar array field and offshore wind turbines, bright crisp sunlight, green technology landscape photo, 8k resolution",
    r"(real_estate|property|building|architecture|construction|housing)": "modern architectural skyscraper building exterior, sleek glass and steel facade, golden hour lighting, 8k resolution architectural photo",
}


def clean_prompt_for_image_gen(prompt: str) -> str:
    """Clean and optimize prompt for AI image generation models."""
    if not prompt:
        return "modern minimalist executive presentation backdrop, soft ambient lighting, 8k resolution"

    cleaned = re.sub(r"[^\w\s\-,.]", " ", prompt)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    for pattern, visual_style in AI_STYLE_PRESETS.items():
        if re.search(pattern, cleaned.lower()):
            return f"{cleaned}, {visual_style}"

    return f"{cleaned}, modern executive corporate presentation visual, photorealistic, 8k resolution, cinematic lighting, highly detailed"


def generate_ai_image(
    prompt: str,
    width: int = 1280,
    height: int = 720,
    seed: Optional[int] = None,
    style: str = "photorealistic",
) -> Optional[str]:
    """
    Generate a high-quality customized AI image using Pollinations AI (FLUX model)
    with zero external API keys required.
    Saves image locally to ASSET_DIR and returns local file path or URL.
    """
    enhanced_prompt = clean_prompt_for_image_gen(prompt)

    encoded_prompt = urllib.parse.quote(enhanced_prompt)
    prompt_hash = hashlib.md5(enhanced_prompt.encode("utf-8")).hexdigest()[:12]
    target_filename = f"ai_gen_{prompt_hash}.jpg"
    target_path = ASSET_DIR / target_filename

    web_url = f"/assets/{target_filename}"

    if target_path.exists() and target_path.stat().st_size > 2000:
        logger.info("Using cached AI image: %s", target_path)
        return web_url

    # Pollinations AI Endpoint with FLUX model and negative prompt filtering
    seed_val = seed if seed is not None else 42
    negative_prompt = urllib.parse.quote("blurry, distorted, low quality, ugly, text, watermark, signature, out of frame, bad anatomy")
    pollinations_url = (
        f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        f"?width={width}&height={height}&model=flux&nologo=true&seed={seed_val}&negative={negative_prompt}"
    )

    try:
        req = urllib.request.Request(
            pollinations_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "image/webp,image/apng,image/jpeg,image/*,*/*;q=0.8",
            },
        )

        with urllib.request.urlopen(req, timeout=12) as response:
            image_bytes = response.read()

        if image_bytes and len(image_bytes) > 2000:
            target_path.write_bytes(image_bytes)
            logger.info("AI Image successfully generated and saved to %s", target_path)
            return web_url
    except Exception as exc:
        logger.warning("Pollinations AI FLUX image generation failed: %s, falling back to standard endpoint", exc)

    # Fallback to standard endpoint
    fallback_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&nologo=true&seed={seed_val}"
    return fallback_url

