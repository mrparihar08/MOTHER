from fastapi import HTTPException
from backend.chats.utils.presentation_api import service, GenerateRequest

def handle_presentation_request(msg: str, user_message: str):

    # 🔹 keyword check सिर्फ routing के लिए
    ppt_keywords = [
        "ppt", "pptx", "presentation", "slide", "slides",
        "make presentation", "create presentation",
        "generate presentation", "make ppt",
        "create ppt", "powerpoint"
    ]

    if not any(k in msg for k in ppt_keywords):
        return None

    # 🔥 IMPORTANT: RAW PROMPT यहीं use होगा
    prompt = (user_message or "").strip()

    if not prompt:
        return None

    # 🔥 Backend को direct भेजो
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