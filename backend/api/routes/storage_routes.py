# backend/api/routes/storage_routes.py
from __future__ import annotations

import io
import mimetypes
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.api.services.storage_service import (
    sanitize_filename,
    storage_service,
    verify_local_token,
)

router = APIRouter()


class PresignedUploadRequest(BaseModel):
    filename: str = Field(..., description="Target filename")
    folder: str = Field("uploads", description="Target folder (uploads, outputs, assets)")
    content_type: str = Field("application/octet-stream", description="MIME content type")
    expires_in: int = Field(3600, ge=60, le=86400, description="Expiration time in seconds")


class PresignedUploadResponse(BaseModel):
    provider: str
    file_key: str
    upload_url: str
    method: str
    expires_in: int
    headers: Optional[dict] = None
    token: Optional[str] = None


@router.get("/presigned-url/{folder}/{filename}")
def get_presigned_url(
    folder: str,
    filename: str,
    expires_in: int = Query(3600, ge=60, le=86400),
):
    """
    Generate a presigned download URL for clients to stream directly from cloud storage.
    """
    clean_name = sanitize_filename(filename)
    url = storage_service.get_presigned_download_url(clean_name, folder=folder, expires_in=expires_in)
    return {
        "filename": clean_name,
        "folder": folder,
        "presigned_url": url,
        "provider": storage_service.provider,
        "expires_in": expires_in,
    }


@router.post("/presigned-upload-url", response_model=PresignedUploadResponse)
def get_presigned_upload_url(req: PresignedUploadRequest):
    """
    Generate a presigned upload URL enabling clients to stream files directly
    to S3 / Supabase Object Storage, bypassing the backend API.
    """
    res = storage_service.get_presigned_upload_url(
        filename=req.filename,
        folder=req.folder,
        content_type=req.content_type,
        expires_in=req.expires_in,
    )
    return res


@router.get("/signed-download")
def signed_download(
    folder: str = Query(...),
    filename: str = Query(...),
    expires: int = Query(...),
    token: str = Query(...),
):
    """
    Cryptographically verify HMAC token and stream the file (used in local storage fallback).
    """
    clean_name = sanitize_filename(filename)
    file_key = f"{folder}/{clean_name}"

    if not verify_local_token(file_key, expires, token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Presigned URL signature is invalid or has expired.",
        )

    file_bytes = storage_service.read_bytes(clean_name, folder=folder)
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    mime_type, _ = mimetypes.guess_type(clean_name)
    mime_type = mime_type or "application/octet-stream"

    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type=mime_type,
        headers={"Content-Disposition": f'inline; filename="{clean_name}"'},
    )


@router.post("/upload")
async def upload_file_endpoint(
    file: UploadFile = File(...),
    folder: str = Form("uploads"),
):
    """
    Stream and persist an uploaded file to Cloud Object Storage (or local cache).
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    filename = file.filename or "upload.bin"
    mime_type = file.content_type or "application/octet-stream"

    result = storage_service.upload_file(
        file_input=content,
        filename=filename,
        folder=folder,
        content_type=mime_type,
    )
    return result
