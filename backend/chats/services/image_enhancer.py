# Re-export from shared platform core service for backward-compatibility
from backend.api.services.image_enhancer import (
    ASSET_DIR,
    HAS_REALESRGAN,
    load_image,
    upscale_with_realesrgan,
    enhance_pil_image,
    enhance_and_save_image,
)

__all__ = [
    "ASSET_DIR",
    "HAS_REALESRGAN",
    "load_image",
    "upscale_with_realesrgan",
    "enhance_pil_image",
    "enhance_and_save_image",
]
