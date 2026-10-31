from __future__ import annotations

import os
import logging
import hashlib
from pathlib import Path
from typing import Optional, Union, Any

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

logger = logging.getLogger(__name__)

ASSET_DIR = Path(os.getenv("PPT_ASSET_DIR", "./assets")).resolve()
ASSET_DIR.mkdir(parents=True, exist_ok=True)

# Lazy RealESRGAN / PyTorch state
_HAS_REALESRGAN: Optional[bool] = None
RealESRGANCls: Any = None
RealESRGANerCls: Any = None
_torch_mod: Any = None
HAS_REALESRGAN: bool = False


def _get_realesrgan():
    """Lazily load PyTorch and RealESRGAN dependencies on demand to protect baseline RAM."""
    global _HAS_REALESRGAN, RealESRGANCls, RealESRGANerCls, _torch_mod, HAS_REALESRGAN
    if _HAS_REALESRGAN is not None:
        return _HAS_REALESRGAN, RealESRGANCls, RealESRGANerCls, _torch_mod

    try:
        import torch
        _torch_mod = torch
        try:
            # pyrefly: ignore [missing-import]
            from realesrgan.utils import RealESRGANer as r_er_cls
            RealESRGANerCls = r_er_cls
            _HAS_REALESRGAN = True
        except ImportError:
            try:
                # pyrefly: ignore [import, missing-import]
                from realesrgan import RealESRGAN as r_cls
                RealESRGANCls = r_cls
                _HAS_REALESRGAN = True
            except ImportError:
                _HAS_REALESRGAN = False
        if _HAS_REALESRGAN:
            HAS_REALESRGAN = True
            logger.info("RealESRGAN super-resolution module loaded lazily.")
    except Exception as exc:
        logger.info("RealESRGAN not available or dependencies loading: %s", exc)
        _HAS_REALESRGAN = False
        HAS_REALESRGAN = False

    return _HAS_REALESRGAN, RealESRGANCls, RealESRGANerCls, _torch_mod


def has_realesrgan() -> bool:
    has_res, _, _, _ = _get_realesrgan()
    return bool(has_res)


def load_image(image_input: Union[str, Path, Image.Image]) -> Optional[Image.Image]:
    """Helper to open an image from path or return PIL Image."""
    if isinstance(image_input, Image.Image):
        return image_input.convert("RGB")

    path_str = str(image_input)
    path = Path(path_str)
    if path.exists() and path.is_file():
        try:
            return Image.open(path).convert("RGB")
        except Exception as exc:
            logger.warning("Failed to open image path %s: %s", path, exc)
            return None

    # Handle local asset URLs like '/assets/filename.jpg'
    if path_str.startswith("/assets/"):
        local_filename = path_str.replace("/assets/", "")
        local_path = ASSET_DIR / local_filename
        if local_path.exists():
            try:
                return Image.open(local_path).convert("RGB")
            except Exception as exc:
                logger.warning("Failed to open local asset %s: %s", local_path, exc)

    return None


def upscale_with_realesrgan(img: Image.Image, scale: int = 2) -> Image.Image:
    """Upscale PIL Image using RealESRGAN model if PyTorch & CUDA/CPU available."""
    has_res, r_cls, r_er_cls, torch_mod = _get_realesrgan()
    if not has_res or torch_mod is None:
        return img

    try:
        device = torch_mod.device('cuda' if torch_mod.cuda.is_available() else 'cpu')
        if r_cls is not None:
            model = r_cls(device, scale=scale)
            model.load_weights(f'weights/RealESRGAN_x{scale}.pth', download=True)
            res = model.predict(img)
            import gc
            gc.collect()
            return res
        elif r_er_cls is not None:
            import numpy as np
            # pyrefly: ignore [missing-import]
            from basicsr.archs.rrdbnet_arch import RRDBNet
            model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
            upsampler = r_er_cls(
                scale=4,
                model_path='https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth',
                model=model,
                tile=0,
                tile_pad=10,
                pre_pad=0,
                half=False,
                device=device
            )
            img_np = np.array(img)
            output_np, _ = upsampler.enhance(img_np, outscale=scale)
            logger.info("Successfully upscaled image with RealESRGANer x%d", scale)
            res = Image.fromarray(output_np)
            import gc
            gc.collect()
            return res
    except Exception as exc:
        logger.warning("RealESRGAN upscaling fallback due to: %s", exc)
        return img

    return img


def enhance_pil_image(
    img: Image.Image,
    target_width: int = 1920,
    target_height: int = 1080,
    sharpness_factor: float = 1.35,
    contrast_factor: float = 1.15,
    color_factor: float = 1.1,
) -> Image.Image:
    """
    Applies PIL-based high precision image enhancement:
    - High quality Lanczos resize & aspect ratio fit
    - Unsharp mask edge sharpening
    - Contrast, color saturation, and sharpness balancing
    """
    # 1. High-quality resampling using Lanczos filter
    img = ImageOps.fit(img, (target_width, target_height), method=Image.Resampling.LANCZOS)

    # 2. Subtle Unsharp Mask for fine architectural / visual details
    img = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=3))

    # 3. Enhance Sharpness
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(sharpness_factor)

    # 4. Enhance Contrast
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(contrast_factor)

    # 5. Enhance Color Saturation
    enhancer = ImageEnhance.Color(img)
    img = enhancer.enhance(color_factor)

    return img


def enhance_and_save_image(
    image_input: Union[str, Path, Image.Image],
    output_filename: Optional[str] = None,
    target_width: int = 1920,
    target_height: int = 1080,
    use_super_resolution: bool = True
) -> Optional[str]:
    """
    Master function to process and enhance an image:
    1. Loads input image (File Path or PIL object)
    2. Applies RealESRGAN super-resolution (if enabled/available)
    3. Applies PIL sharpening, contrast, and high-definition color enhancement
    4. Saves output image to ASSET_DIR and returns web URL string.
    """
    img = load_image(image_input)
    if img is None:
        return None

    # RealESRGAN AI Super Resolution
    if use_super_resolution and has_realesrgan():
        img = upscale_with_realesrgan(img, scale=2)

    # PIL Processing & Enhancements
    enhanced_img = enhance_pil_image(
        img,
        target_width=target_width,
        target_height=target_height
    )

    if not output_filename:
        # Create deterministic hash from image dimensions and sample bytes
        sample_bytes = enhanced_img.tobytes()[:1000]
        img_hash = hashlib.md5(sample_bytes).hexdigest()[:12]
        output_filename = f"enhanced_{img_hash}.jpg"

    target_path = ASSET_DIR / output_filename
    enhanced_img.save(target_path, "JPEG", quality=95, optimize=True)
    logger.info("Enhanced image saved to %s", target_path)

    return f"/assets/{output_filename}"
