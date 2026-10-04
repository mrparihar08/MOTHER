import re
from dataclasses import dataclass
from typing import Optional, Literal, Dict, Tuple
from fastapi.responses import StreamingResponse

from backend.finance.routes.vitya import (
    download_expenses_csv,
    download_incomes_csv,
)
from backend.chats.utils.text_utils import extract_title
from backend.chats.utils.document_generators import (
    generate_csv_from_text,
    generate_doc_from_text,
    generate_pdf_from_text,
)
from backend.chats.utils.presentation_generators import generate_ppt_from_text
from backend.chats.utils.themes import detect_theme

FileType = Literal["csv", "docx", "pdf", "pptx", "unknown"]

FILE_COMMAND_TRIGGERS = [
    "/file", "/export", "/download", "/pdf", "/csv", "/docx", "/doc", "/pptx", "/ppt",
    "export", "download", "generate file", "make file", "create document",
    "save as", "export to", "download as", "send file", "file bhejo", "download karo"
]


@dataclass
class PromptIntent:
    file_type: FileType
    filename: str
    is_expense: bool = False
    is_income: bool = False
    theme: Optional[Dict] = None


def normalize_text(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def make_safe_filename(title: str, default: str = "vitya_export") -> str:
    title = (title or "").strip()
    if not title:
        return default

    # Remove non-alphanumeric chars
    cleaned = re.sub(r"[^\w\s\-]", "", title)
    cleaned = re.sub(r"\s+", "_", cleaned).strip("_")
    return cleaned[:50] if cleaned else default


def has_file_intent(msg: str) -> bool:
    """Check if message expresses an explicit intent to export/download a file."""
    t = normalize_text(msg)
    return any(re.search(rf"\b{re.escape(k)}\b", t) for k in FILE_COMMAND_TRIGGERS) or t.startswith("/")


def detect_file_type(msg: str) -> FileType:
    t = normalize_text(msg)

    if re.search(r"\b(pptx|ppt|powerpoint|slides|presentation|deck)\b", t):
        return "pptx"

    if re.search(r"\b(csv|excel|spreadsheet|sheet|xlsx)\b", t):
        return "csv"

    if re.search(r"\b(docx|doc|word\s+doc|word\s+file)\b", t):
        return "docx"

    if re.search(r"\b(pdf|portable document)\b", t):
        return "pdf"

    return "unknown"


def detect_special_type(msg: str) -> Tuple[bool, bool]:
    t = normalize_text(msg)
    is_expense = bool(re.search(r"\b(expense|expenses|kharcha|spending|spends)\b", t))
    is_income = bool(re.search(r"\b(income|incomes|salary|aamdani|kamai|earnings)\b", t))
    return is_expense, is_income


def build_intent(msg: str, user_message: Optional[str]) -> PromptIntent:
    msg_norm = normalize_text(msg)
    raw_title = extract_title(user_message or "", user_title=None)
    filename = make_safe_filename(raw_title)

    file_type = detect_file_type(msg_norm)
    is_expense, is_income = detect_special_type(msg_norm)
    theme = detect_theme(user_message or "")

    return PromptIntent(
        file_type=file_type,
        filename=filename,
        is_expense=is_expense,
        is_income=is_income,
        theme=theme,
    )


def make_download_response(file_obj, media_type: str, filename: str) -> StreamingResponse:
    return StreamingResponse(
        file_obj,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def handle_file_request(msg: str, user_message: str, current_user, force: bool = False):
    """
    Handles export and document generation requests (CSV, DOCX, PDF, PPTX).
    Ensures normal chat queries containing words like 'report' or 'notes' are not falsely hijacked.
    """
    # Verify explicit file export intent unless forced by mode parameter
    if not force and not has_file_intent(msg):
        return None

    intent = build_intent(msg, user_message)

    if intent.file_type == "unknown":
        if force:
            intent.file_type = "csv"
        else:
            return None

    # 1. CSV / Excel Export
    if intent.file_type == "csv":
        if intent.is_expense:
            return download_expenses_csv(current_user)
        if intent.is_income:
            return download_incomes_csv(current_user)

        file_obj = generate_csv_from_text(user_message or "", user_title=intent.filename)
        return make_download_response(
            file_obj,
            "text/csv",
            f"{intent.filename}.csv",
        )

    # 2. DOCX Word Document
    if intent.file_type == "docx":
        file_obj = generate_doc_from_text(user_message or "", user_title=intent.filename)
        return make_download_response(
            file_obj,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            f"{intent.filename}.docx",
        )

    # 3. PDF Document
    if intent.file_type == "pdf":
        file_obj = generate_pdf_from_text(user_message or "", user_title=intent.filename)
        return make_download_response(
            file_obj,
            "application/pdf",
            f"{intent.filename}.pdf",
        )

    # 4. PPTX Presentation Slides
    if intent.file_type == "pptx":
        file_obj = generate_ppt_from_text(user_message or "", user_title=intent.filename)
        return make_download_response(
            file_obj,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            f"{intent.filename}.pptx",
        )

    return None