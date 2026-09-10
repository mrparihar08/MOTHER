from __future__ import annotations

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.database import get_db
from backend.api.models.vitya import User
from backend.api.auth import token_required
from backend.chats.services.rag_service import rag_store

router = APIRouter()
logger = logging.getLogger(__name__)


class RAGDocumentResponse(BaseModel):
    filename: str
    chunk_count: int
    char_count: int


class RAGDocumentListResponse(BaseModel):
    conversation_id: Optional[int]
    documents: List[RAGDocumentResponse]


@router.post("/upload", response_model=RAGDocumentListResponse)
async def upload_rag_documents(
    conversation_id: Optional[int] = Form(None),
    files: List[UploadFile] = File(...),
    current_user: User = Depends(token_required),
):
    """
    Upload multi-document files (PDF, CSV, TXT, DOCX), parse text content,
    chunk and index in RAG knowledge base for context-aware Q&A.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    cid = conversation_id or 0
    indexed_docs = []

    for file in files:
        filename = file.filename or "uploaded_doc.txt"
        file_bytes = await file.read()
        if len(file_bytes) == 0:
            continue

        try:
            doc_info = rag_store.index_document(cid, filename, file_bytes)
            indexed_docs.append(
                RAGDocumentResponse(
                    filename=doc_info["filename"],
                    chunk_count=doc_info["chunk_count"],
                    char_count=doc_info["char_count"],
                )
            )
        except Exception as exc:
            logger.warning("Failed to index document %s: %s", filename, exc)
            raise HTTPException(status_code=500, detail=f"Failed to index document {filename}: {str(exc)}")

    all_docs = [
        RAGDocumentResponse(
            filename=d["filename"],
            chunk_count=d["chunk_count"],
            char_count=d["char_count"],
        )
        for d in rag_store.get_documents(cid)
    ]

    return RAGDocumentListResponse(conversation_id=conversation_id, documents=all_docs)


@router.get("/documents", response_model=RAGDocumentListResponse)
def get_rag_documents(
    conversation_id: Optional[int] = None,
    current_user: User = Depends(token_required),
):
    """List uploaded documents for the active conversation."""
    cid = conversation_id or 0
    docs = [
        RAGDocumentResponse(
            filename=d["filename"],
            chunk_count=d["chunk_count"],
            char_count=d["char_count"],
        )
        for d in rag_store.get_documents(cid)
    ]
    return RAGDocumentListResponse(conversation_id=conversation_id, documents=docs)


@router.delete("/documents")
def clear_rag_documents(
    conversation_id: Optional[int] = None,
    current_user: User = Depends(token_required),
):
    """Clear uploaded document knowledge base for a conversation."""
    cid = conversation_id or 0
    rag_store.clear_documents(cid)
    return {"message": "Document knowledge base cleared successfully", "conversation_id": conversation_id}
