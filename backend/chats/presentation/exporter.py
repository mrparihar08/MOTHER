from __future__ import annotations

import os
import uuid
from pathlib import Path
from pptx import Presentation
from backend.chats.presentation.planner import safe_filename

OUTPUT_DIR = Path(os.getenv("PPT_OUTPUT_DIR", "./outputs")).resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def save_presentation(prs: Presentation, title: str) -> str:
    file_id = uuid.uuid4().hex
    filename = f"{safe_filename(title)}_{file_id}.pptx"
    file_path = OUTPUT_DIR / filename
    prs.save(str(file_path))
    return str(file_path)
