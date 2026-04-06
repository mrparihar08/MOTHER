from fastapi import HTTPException
from backend.chats.utils.presentation_api import service, GenerateRequest


# ---------------------------------
# Main Bridge Function (FINAL CLEAN)
# ---------------------------------

def handle_presentation_request(msg: str, user_message: str):
    """
    Clean production flow:
    - Raw user message goes directly to backend
    - Backend handles planning + slide splitting internally
    - User only receives final PPT download
    """

    text = (msg or "").lower().strip()

    ppt_keywords = [
        "ppt", "pptx", "presentation", "slide", "slides",
        "make presentation", "create presentation",
        "generate presentation", "make ppt",
        "create ppt", "powerpoint"
    ]

    # Not a presentation request → ignore
    if not any(k in text for k in ppt_keywords):
        return None

    # 🔥 RAW PROMPT — no modification
    prompt = (user_message or "").strip()

    if not prompt:
        return None

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
        smart_mode=True,  # Backend handles structuring
    )

    try:
        # Everything happens internally:
        # plan → render → save
        file_path, _plan, title = service.generate(req)
        filename = file_path.split("/")[-1]

        return {
            "type": "file",
            "content": {
                "file_name": filename,
                "download_url": f"/api/presentation/download/{filename}",
                "title": title,
            },
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))