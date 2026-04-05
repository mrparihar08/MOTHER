import re
from fastapi import HTTPException

# import from the file where presentation_api.py lives
from backend.chats.utils.presentation_api import service, GenerateRequest  # adjust path if needed


def handle_presentation_request(msg: str, user_message: str):
    text = (msg or "").lower().strip()

    ppt_keywords = [
        "ppt", "pptx", "presentation", "slide", "slides",
        "make presentation", "create presentation", "generate presentation",
        "make ppt", "create ppt", "powerpoint"
    ]

    if not any(k in text for k in ppt_keywords):
        return None

    prompt = user_message.strip()

    req = GenerateRequest(
        prompt=prompt,
        include_title_slide=True,
        allow_bullets=True,
        allow_paragraph=True,
        allow_chart=True,
        allow_image=True,
        allow_section_slide=True,
        allow_table=True,
        background_theme="light",
        smart_mode=True,
    )

    try:
        file_path, plan, title = service.generate(req)
        filename = file_path.split("/")[-1]

        return {
            "type": "file",
            "content": {
                "file_name": filename,
                "download_url": f"/download/{filename}",
                "title": title,
                "slides": len(plan.slides),
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))