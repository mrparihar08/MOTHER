import base64
import io
from typing import Optional

import qrcode
import barcode
from barcode.writer import ImageWriter

from backend.chats.utils.document_generators import (
    generate_csv_from_text,
    generate_doc_from_text,
    generate_pdf_from_text,
)
from backend.chats.utils.presentation_generators import generate_ppt_from_text


def generate_qr(data: str) -> str:
    qr = qrcode.make(data)
    buffer = io.BytesIO()
    qr.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def generate_barcode(data: str) -> str:
    CODE128 = barcode.get_barcode_class("code128")
    code = CODE128(data, writer=ImageWriter())
    buffer = io.BytesIO()
    code.write(buffer)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def generate_all_files(text: str, user_title: Optional[str] = None):
    return {
        "csv": generate_csv_from_text(text, user_title=user_title),
        "docx": generate_doc_from_text(text, user_title=user_title),
        "pdf": generate_pdf_from_text(text, user_title=user_title),
        "pptx": generate_ppt_from_text(text, user_title=user_title),
    }