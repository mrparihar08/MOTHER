import re
from fastapi import HTTPException

from backend.chats.utils.presentation_api import service, GenerateRequest


# -------------------------------
# Helpers
# -------------------------------

def is_structured_input(text: str) -> bool:
    """
    Detect if user already provided slide-by-slide structured content.
    """
    patterns = [
        r"slide\s*\d+",
        r"title\s*:",
        r"subtitle\s*:",
        r"bullets?\s*:",
        r"chart\s*type\s*:",
        r"table\s*:",
    ]

    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def clean_topic_prompt(text: str) -> str:
    """
    Convert generic 'make ppt on ...' style prompts into clean topic.
    """
    cleaned = re.sub(
        r"(make|create|generate)?\s*(a)?\s*(ppt|presentation|slides?|powerpoint)\s*(on|about)?",
        "",
        text,
        flags=re.IGNORECASE,
    )

    return cleaned.strip()


def build_academic_prompt(topic: str) -> str:
    """
    Force academic structured presentation generation.
    """
    return f"""
Create a professional academic PowerPoint presentation on "{topic}".

Rules:
- First slide must be a proper title slide.
- Minimum 8 slides.
- Use clear headings.
- Use bullet points where appropriate.
- Include applications, tools, advantages, challenges.
- Do NOT explain system architecture.
- Do NOT describe generation process.
"""


# -------------------------------
# Main Bridge Function
# -------------------------------

def handle_presentation_request(msg: str, user_message: str):
    text = (msg or "").lower().strip()

    ppt_keywords = [
        "ppt", "pptx", "presentation", "slide", "slides",
        "make presentation", "create presentation", "generate presentation",
        "make ppt", "create ppt", "powerpoint"
    ]

    # If not presentation request → ignore
    if not any(k in text for k in ppt_keywords):
        return None

    original_prompt = user_message.strip()

    # Decide mode
    structured_mode = is_structured_input(original_prompt)

    if structured_mode:
        prompt = original_prompt
        smart_mode = False
    else:
        topic = clean_topic_prompt(original_prompt)
        if not topic:
            topic = original_prompt

        prompt = build_academic_prompt(topic)
        smart_mode = True

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
        smart_mode=smart_mode,
    )

    try:
        file_path, plan, title = service.generate(req)
        filename = file_path.split("/")[-1]

        return {
            "type": "file",
            "content": {
                "file_name": filename,
                "download_url": f"/api/presentation/download/{filename}",
                "title": title,
                "slides": len(plan.slides) if hasattr(plan, "slides") else 0,
            },
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))