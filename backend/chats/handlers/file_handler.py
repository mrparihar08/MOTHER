import re
from dataclasses import dataclass
from typing import Optional, Literal, Dict # Import Dict

from fastapi.responses import StreamingResponse

from backend.api.routes.vitya import (
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
from backend.chats.utils.media_and_exports import generate_all_files, generate_qr, generate_barcode


FileType = Literal["csv", "docx", "pdf", "pptx", "unknown"]


@dataclass
class PromptIntent:
    file_type: FileType
    filename: str
    is_expense: bool = False
    is_income: bool = False
    theme: Optional[Dict] = None # Add theme field


def normalize_text(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def make_safe_filename(title: str, default: str = "chat_data") -> str:
    title = (title or "").strip()
    if not title:
        return default

    title = re.sub(r"[^\w\s\-]", "", title)
    title = re.sub(r"\s+", "_", title).strip("_")
    return title[:50] if title else default


def detect_file_type(msg: str) -> FileType:
    """
    Natural-language intent detection for file type.
    """
    msg = normalize_text(msg)

    # CSV / Excel / Spreadsheet
    if re.search(r"\b(csv|excel|spreadsheet|sheet|table)\b", msg):
        return "csv"

    # DOCX / Word / Document
    if re.search(r"\b(doc|docx|word|document|report|notes)\b", msg):
        return "docx"

    # PDF
    if re.search(r"\b(pdf|portable document)\b", msg):
        return "pdf"

    # PPT / Presentation / Slides
    if re.search(r"\b(ppt|pptx|powerpoint|slides|presentation|deck|slideshow)\b", msg):
        return "pptx"

    return "unknown"


def detect_special_type(msg: str) -> tuple[bool, bool]:
    """
    Detect expense / income special cases for CSV.
    """
    msg = normalize_text(msg)

    is_expense = bool(re.search(r"\b(expense|expenses|spend|spending|outgoing)\b", msg))
    is_income = bool(re.search(r"\b(income|incomes|salary|revenues|revenue|earnings|profit)\b", msg))

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


def make_download_response(file_obj, media_type: str, filename: str):
    return StreamingResponse(
        file_obj,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def handle_file_request(msg, user_message, current_user):
    intent = build_intent(msg, user_message)

    # Special CSV reports
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

    # DOCX
    if intent.file_type == "docx":
        file_obj = generate_doc_from_text(user_message or "", user_title=intent.filename)
        return make_download_response(
            file_obj,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            f"{intent.filename}.docx",
        )

    # PDF
    if intent.file_type == "pdf":
        file_obj = generate_pdf_from_text(user_message or "", user_title=intent.filename)
        return make_download_response(
            file_obj,
            "application/pdf",
            f"{intent.filename}.pdf",
        )

    # PPTX
    if intent.file_type == "pptx":
        file_obj = generate_ppt_from_text(
            user_message or "",
            user_title=intent.filename,
            theme=intent.theme
        )
        return make_download_response(
            file_obj,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            f"{intent.filename}.pptx",
        )

    return None