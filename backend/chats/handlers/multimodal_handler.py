import io
import re
import logging
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image
from sqlalchemy.orm import Session

from backend.chats.services.vision_service import get_vision_provider

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_MIME_TYPES = {
    "image/jpeg": "image/jpeg",
    "image/jpg": "image/jpeg",
    "image/png": "image/png",
    "image/webp": "image/webp",
    "image/gif": "image/gif",
    "image/bmp": "image/bmp",
}

MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB limit


def validate_image_bytes(
    image_bytes: bytes,
    filename: str = "",
    content_type: str = "",
) -> Tuple[bool, Optional[str], str]:
    """
    Validates uploaded image data for security, MIME integrity, and file size limits.
    Prevents malicious file execution and ensures Pillow can decode the image structure.
    """
    if not image_bytes or len(image_bytes) < 32:
        return False, "Uploaded image file is empty or corrupted.", ""

    if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
        return False, f"Image size exceeds the maximum allowed limit of {MAX_IMAGE_SIZE_BYTES // (1024 * 1024)}MB.", ""

    # Verify image integrity and determine standard format with PIL
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img_format = (img.format or "").upper()
            format_mime_map = {
                "JPEG": "image/jpeg",
                "JPG": "image/jpeg",
                "PNG": "image/png",
                "WEBP": "image/webp",
                "GIF": "image/gif",
                "BMP": "image/bmp",
            }
            if img_format not in format_mime_map:
                return False, f"Unsupported image format: {img_format}. Supported formats: JPG, JPEG, PNG, WEBP, GIF, BMP.", ""

            verified_mime = format_mime_map[img_format]
            return True, None, verified_mime
    except Exception as e:
        logger.warning("Pillow validation failed for image '%s': %s", filename, e)
        return False, "Invalid or corrupted image format. Please upload a valid JPG, PNG, or WEBP image.", ""


def _build_multimodal_system_instruction(user_name: Optional[str] = None) -> str:
    """Build intelligent multimodal system prompt with strict zero-hallucination and financial safety."""
    name_str = f"The user's name is {user_name}." if user_name else ""
    return (
        f"You are Vitya AI, an advanced Universal Multimodal Assistant and Financial Intelligence Companion. {name_str}\n\n"
        "CORE MULTIMODAL DIRECTIVES:\n"
        "1. UNIVERSAL IMAGE UNDERSTANDING: You can analyze all types of images: bills, receipts, invoices, bank statements, "
        "charts, graphs, handwritten notes, printed documents, screenshots, UI mockups, infographics, diagrams, objects, "
        "products, memes, posters, and ordinary photographs.\n"
        "2. USER INTENT FIRST: Address what the user asks about the image. If the user provided no text, describe the image thoroughly and highlight its key information.\n"
        "3. STRICT NO-HALLUCINATION POLICY:\n"
        "   - NEVER guess or invent prices, totals, names, dates, phone numbers, codes, or statistics.\n"
        "   - If any text, digit, or detail is blurry, cropped, handwriting is illegible, or obscured, explicitly state: 'This text/value is unclear or partially obscured in the image.'\n"
        "4. FINANCE-AWARE INTELLIGENCE (NO AUTOMATIC MODIFICATION):\n"
        "   - If the image is a bill, receipt, invoice, or financial statement, extract and organize: Merchant/Vendor, Date, Itemized list, Subtotal, Taxes, Total Amount, Currency.\n"
        "   - DO NOT claim that an expense or income has been logged automatically into their database. Instead, provide the structured summary and inform the user: 'If you would like me to add this expense to your account, just let me know!'\n"
        "5. OCR & HANDWRITING RECOGNITION:\n"
        "   - Preserve exact spelling, casing, punctuation, dates, currencies, and tabular structures.\n"
        "   - For handwritten notes or todo lists, convert them cleanly into organized markdown bullet points or checklist.\n"
        "6. CHARTS & GRAPHS ANALYSIS:\n"
        "   - Identify chart type (e.g. bar, line, pie, scatter), axes labels, legends, highest/lowest points, overall trends, and business/financial takeaways.\n"
        "7. LANGUAGE & TONE:\n"
        "   - Always match the user's language (Hinglish, Hindi, English). If user asks in Hinglish ('Is bill ka total kitna hai?'), respond in clear, natural Hinglish.\n"
        "   - Use clean, well-spaced GitHub-flavored Markdown."
    )


def handle_multimodal_chat(
    user_message: str,
    images_data: List[Dict[str, Any]],  # list of {"data": bytes, "mime_type": str, "filename": str}
    db: Session,
    current_user: Any,
    conversation_id: Optional[int] = None,
    use_web_search: bool = False,
) -> Dict[str, Any]:
    """
    Processes multimodal user requests containing one or more images along with optional text prompt.
    """
    if not images_data:
        return {
            "type": "text",
            "content": "No image was provided for visual analysis.",
            "error": True,
        }

    # Validate each image
    validated_images = []
    for idx, img in enumerate(images_data):
        img_bytes = img.get("data")
        raw_mime = img.get("mime_type", "")
        filename = img.get("filename", f"image_{idx+1}.jpg")

        is_valid, err_msg, verified_mime = validate_image_bytes(img_bytes, filename, raw_mime)
        if not is_valid:
            return {
                "type": "text",
                "content": f"⚠️ Image error ({filename}): {err_msg}",
                "error": True,
            }
        validated_images.append({
            "data": img_bytes,
            "mime_type": verified_mime,
            "filename": filename,
        })

    prompt_text = (user_message or "").strip()
    if not prompt_text:
        prompt_text = "Please analyze this image in detail. Identify its type, extract all visible text/data, and explain what is shown."

    user_name = getattr(current_user, "name", None) or getattr(current_user, "username", None)
    system_instruction = _build_multimodal_system_instruction(user_name=user_name)

    provider = get_vision_provider()
    result = provider.analyze_multimodal(
        images_data=validated_images,
        prompt=prompt_text,
        system_instruction=system_instruction,
        temperature=0.2,
    )

    if not result.get("success"):
        return {
            "type": "text",
            "content": result.get("text") or result.get("error") or "Failed to analyze image.",
            "error": True,
        }

    reply_content = result.get("text", "")

    return {
        "type": "text",
        "content": reply_content,
        "images_count": len(validated_images),
        "multimodal": True,
    }
