from __future__ import annotations

# Re-export from unified presentation AI image service for full backward compatibility
from backend.presentation.services.ai_image_service import (
    GeminiImageProvider,
    PollinationsImageProvider,
    AIImageService,
    ai_image_service,
    build_image_prompt,
    clean_prompt_for_image_gen,
    generate_ai_image,
    AI_PRESENTATION_PRESETS,
    VISUAL_TYPE_PROMPT_MAP,
)

__all__ = [
    "GeminiImageProvider",
    "PollinationsImageProvider",
    "AIImageService",
    "ai_image_service",
    "build_image_prompt",
    "clean_prompt_for_image_gen",
    "generate_ai_image",
    "AI_PRESENTATION_PRESETS",
    "VISUAL_TYPE_PROMPT_MAP",
]
