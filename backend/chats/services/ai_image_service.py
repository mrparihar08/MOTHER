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


def clean_prompt_for_image_gen(prompt: str) -> str:
    """Clean and optimize prompt for AI image generation models."""
    if not prompt:
        return "modern abstract presentation background visual, high resolution"
    
    cleaned = re.sub(r"[^\w\s\-,.]", " ", prompt)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    
    if len(cleaned) > 200:
        cleaned = cleaned[:200].rsplit(" ", 1)[0]
        
    return cleaned or "modern technology business presentation visual"


def generate_ai_image(
    prompt: str,
    width: int = 1024,
    height: int = 768,
    seed: Optional[int] = None,
    style: str = "photorealistic",
) -> Optional[str]:
    """
    Generate a high-quality customized AI image using Pollinations AI
    with zero external API keys required.
    Saves image locally to ASSET_DIR and returns local file path or URL.
    """
    cleaned_prompt = clean_prompt_for_image_gen(prompt)
    enhanced_prompt = f"{cleaned_prompt}, {style}, highly detailed, professional presentation quality, 8k resolution, cinematic lighting"
    
    encoded_prompt = urllib.parse.quote(enhanced_prompt)
    prompt_hash = hashlib.md5(enhanced_prompt.encode("utf-8")).hexdigest()[:12]
    target_filename = f"ai_gen_{prompt_hash}.jpg"
    target_path = ASSET_DIR / target_filename
    
    if target_path.exists() and target_path.stat().st_size > 2000:
        logger.info("Using cached AI image: %s", target_path)
        return str(target_path)

    # Pollinations AI Endpoint (Zero API key needed)
    seed_param = f"&seed={seed}" if seed is not None else "&seed=42"
    pollinations_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&nologo=true{seed_param}"
    
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
            return str(target_path)
    except Exception as exc:
        logger.warning("Pollinations AI image generation failed: %s", exc)

    # Return direct URL if download failed but URL is valid
    return pollinations_url
