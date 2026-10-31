# backend/api/services/storage_service.py
"""
Storage Service:
Production-grade Unified Cloud Object Storage Abstraction for MOTHER.
Supports:
1. Supabase Storage Buckets
2. AWS S3 / Cloudflare R2 / MinIO Object Storage
3. Resilient Local Storage with HMAC-signed presigned URLs

Provides presigned download & upload URLs, direct streaming,
and prevents ephemeral cloud storage data loss on container restarts.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, BinaryIO, Dict, Optional, Tuple, Union

logger = logging.getLogger("STORAGE-SERVICE")

# Anchor root directory strictly to the project repository root
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_UPLOAD_DIR = (ROOT_DIR / "uploads").resolve()
DEFAULT_OUTPUT_DIR = (ROOT_DIR / "outputs").resolve()
DEFAULT_ASSET_DIR = (ROOT_DIR / "assets").resolve()
DEFAULT_STORE_DIR = (DEFAULT_OUTPUT_DIR / "store").resolve()

# Ensure directories exist at absolute root path
DEFAULT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_ASSET_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_STORE_DIR.mkdir(parents=True, exist_ok=True)

# Supabase Storage Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "mother-assets")

# AWS S3 / Cloudflare R2 Configuration
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("S3_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY") or os.getenv("S3_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION") or os.getenv("S3_REGION", "us-east-1")
AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET") or os.getenv("S3_BUCKET_NAME")
AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL") or os.getenv("S3_ENDPOINT_URL")  # e.g., Cloudflare R2

SECRET_KEY = os.getenv("SECRET_KEY", "mother-storage-secret-key-32b-min")


def sanitize_filename(filename: str) -> str:
    """Strip path traversal characters and sanitize filename."""
    base = os.path.basename(filename.strip().replace("\\", "/"))
    clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", base)
    return clean or "unnamed_file"


def sign_local_token(file_key: str, expires_at: int) -> str:
    """Generate SHA-256 HMAC signature for local presigned file URLs."""
    msg = f"{file_key}:{expires_at}".encode("utf-8")
    return hmac.new(SECRET_KEY.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def verify_local_token(file_key: str, expires_at: int, token: str) -> bool:
    """Cryptographically verify local presigned URL token and check expiration."""
    if time.time() > expires_at:
        return False
    expected = sign_local_token(file_key, expires_at)
    return hmac.compare_digest(expected, token)


class StorageService:
    """Unified Cloud & Local Object Storage Manager."""

    def __init__(self) -> None:
        self.root_dir = ROOT_DIR
        self.upload_dir = DEFAULT_UPLOAD_DIR
        self.output_dir = DEFAULT_OUTPUT_DIR
        self.asset_dir = DEFAULT_ASSET_DIR
        self.store_dir = DEFAULT_STORE_DIR
        self._s3_client = None
        self._s3_initialized = False

    def _get_target_dir(self, folder: str) -> Path:
        f = (folder or "outputs").lower().strip()
        if "upload" in f:
            return self.upload_dir
        elif "asset" in f:
            return self.asset_dir
        elif "store" in f:
            return self.store_dir
        return self.output_dir

    def get_safe_local_path(self, filename: str, folder: str = "outputs") -> Optional[Path]:
        """Resolves an absolute sanitized local path, strictly preventing directory traversal."""
        clean = sanitize_filename(filename)
        target_dir = self._get_target_dir(folder)
        target_path = (target_dir / clean).resolve()
        if not str(target_path).startswith(str(target_dir)):
            return None
        return target_path

    def _get_s3_client(self):
        """Lazy initialization of boto3 S3 / Cloudflare R2 client."""
        if self._s3_initialized:
            return self._s3_client

        self._s3_initialized = True
        if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY and AWS_S3_BUCKET:
            try:
                import boto3
                from botocore.config import Config

                kwargs: Dict[str, Any] = {
                    "aws_access_key_id": AWS_ACCESS_KEY_ID,
                    "aws_secret_access_key": AWS_SECRET_ACCESS_KEY,
                    "region_name": AWS_REGION,
                    "config": Config(signature_version="s3v4"),
                }
                if AWS_ENDPOINT_URL:
                    kwargs["endpoint_url"] = AWS_ENDPOINT_URL

                self._s3_client = boto3.client("s3", **kwargs)
                logger.info("Initialized S3/R2 client for bucket %s", AWS_S3_BUCKET)
            except Exception as exc:
                logger.warning("Failed to initialize S3 client: %s", exc)
                self._s3_client = None

        return self._s3_client

    @property
    def provider(self) -> str:
        """Return the active primary cloud storage provider name."""
        if self._get_s3_client() is not None:
            return "s3"
        if SUPABASE_URL and SUPABASE_KEY:
            return "supabase"
        return "local"

    # ==========================================================
    # UPLOAD OPERATIONS (Stream & Bytes)
    # ==========================================================
    def upload_file(
        self,
        file_input: Union[bytes, BinaryIO, io.BytesIO],
        filename: str,
        folder: str = "outputs",
        content_type: str = "application/octet-stream",
        expires_in: int = 3600,
    ) -> Dict[str, Any]:
        """
        Uploads file to cloud storage (S3 or Supabase) with local cache sync.
        Returns cloud presigned URL and file metadata.
        """
        clean_name = sanitize_filename(filename)
        file_key = f"{folder}/{clean_name}"

        # Normalize bytes
        if isinstance(file_input, (io.BytesIO, BinaryIO)):
            file_bytes = file_input.read()
        elif isinstance(file_input, bytes):
            file_bytes = file_input
        else:
            raise TypeError("file_input must be bytes or a binary stream")

        # 1. Sync to local disk cache
        local_path = self.get_safe_local_path(clean_name, folder=folder)
        if local_path:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(file_bytes)

        # 2. Upload to Cloud
        cloud_url: Optional[str] = None
        s3 = self._get_s3_client()

        if s3 is not None and AWS_S3_BUCKET:
            try:
                s3.put_object(
                    Bucket=AWS_S3_BUCKET,
                    Key=file_key,
                    Body=file_bytes,
                    ContentType=content_type,
                )
                cloud_url = self.get_presigned_download_url(clean_name, folder=folder, expires_in=expires_in)
                logger.info("Uploaded %s to S3/R2 (%s)", file_key, AWS_S3_BUCKET)
                return {
                    "key": file_key,
                    "filename": clean_name,
                    "provider": "s3",
                    "presigned_url": cloud_url,
                    "url": cloud_url,
                    "local_path": str(local_path) if local_path else None,
                    "size_bytes": len(file_bytes),
                    "expires_in": expires_in,
                }
            except Exception as exc:
                logger.warning("S3 upload failed for %s: %s", file_key, exc)

        if SUPABASE_URL and SUPABASE_KEY:
            try:
                from backend.api.supabase_client import get_supabase_client
                client = get_supabase_client()
                client.storage.from_(SUPABASE_STORAGE_BUCKET).upload(
                    path=file_key,
                    file=file_bytes,
                    file_options={"content-type": content_type, "upsert": "true"},
                )
                cloud_url = self.get_presigned_download_url(clean_name, folder=folder, expires_in=expires_in)
                logger.info("Uploaded %s to Supabase Storage", file_key)
                return {
                    "key": file_key,
                    "filename": clean_name,
                    "provider": "supabase",
                    "presigned_url": cloud_url,
                    "url": cloud_url,
                    "local_path": str(local_path) if local_path else None,
                    "size_bytes": len(file_bytes),
                    "expires_in": expires_in,
                }
            except Exception as exc:
                logger.warning("Supabase upload failed for %s: %s", file_key, exc)

        # 3. Fallback: Local Storage with Presigned HMAC Token
        local_presigned = self.get_presigned_download_url(clean_name, folder=folder, expires_in=expires_in)
        return {
            "key": file_key,
            "filename": clean_name,
            "provider": "local",
            "presigned_url": local_presigned,
            "url": local_presigned,
            "local_path": str(local_path) if local_path else None,
            "size_bytes": len(file_bytes),
            "expires_in": expires_in,
        }

    # Backward compatibility alias
    def save_bytes(self, file_bytes: bytes, filename: str, folder: str = "outputs", content_type: str = "application/octet-stream", upload_cloud: bool = True) -> Dict[str, Any]:
        return self.upload_file(file_bytes, filename, folder=folder, content_type=content_type)

    def upload_to_supabase(self, file_bytes: bytes, filename: str, content_type: str = "application/octet-stream") -> Optional[str]:
        parts = filename.split("/", 1)
        folder = parts[0] if len(parts) > 1 else "outputs"
        clean = parts[1] if len(parts) > 1 else parts[0]
        res = self.upload_file(file_bytes, clean, folder=folder, content_type=content_type)
        return res.get("presigned_url")

    # ==========================================================
    # PRESIGNED URLs (Download & Upload)
    # ==========================================================
    def get_presigned_download_url(self, filename: str, folder: str = "outputs", expires_in: int = 3600) -> str:
        """
        Generates a secure presigned GET URL for clients to download files directly from cloud storage.
        Falls back to cryptographic HMAC token for local development.
        """
        clean = sanitize_filename(filename)
        file_key = f"{folder}/{clean}"

        # 1. AWS S3 / Cloudflare R2 Presigned URL
        s3 = self._get_s3_client()
        if s3 is not None and AWS_S3_BUCKET:
            try:
                url = s3.generate_presigned_url(
                    ClientMethod="get_object",
                    Params={"Bucket": AWS_S3_BUCKET, "Key": file_key},
                    ExpiresIn=expires_in,
                )
                return str(url)
            except Exception as exc:
                logger.warning("Failed to generate S3 presigned URL for %s: %s", file_key, exc)

        # 2. Supabase Storage Signed URL
        if SUPABASE_URL and SUPABASE_KEY:
            try:
                from backend.api.supabase_client import get_supabase_client
                client = get_supabase_client()
                res = client.storage.from_(SUPABASE_STORAGE_BUCKET).create_signed_url(file_key, expires_in)
                if isinstance(res, dict) and "signedURL" in res:
                    return res["signedURL"]
                elif isinstance(res, str):
                    return res
                public_url = client.storage.from_(SUPABASE_STORAGE_BUCKET).get_public_url(file_key)
                if public_url:
                    return public_url
            except Exception as exc:
                logger.warning("Failed to generate Supabase signed URL for %s: %s", file_key, exc)

        # 3. Local HMAC Presigned Token Fallback
        expires_at = int(time.time()) + expires_in
        token = sign_local_token(file_key, expires_at)
        return f"/api/storage/signed-download?folder={folder}&filename={clean}&expires={expires_at}&token={token}"

    def get_presigned_upload_url(
        self,
        filename: str,
        folder: str = "uploads",
        content_type: str = "application/octet-stream",
        expires_in: int = 3600,
    ) -> Dict[str, Any]:
        """
        Generates a presigned PUT URL allowing clients to stream uploads directly
        to S3 or Supabase Storage without going through the backend web server.
        """
        clean = sanitize_filename(filename)
        file_key = f"{folder}/{clean}"

        # 1. S3 / R2 presigned PUT
        s3 = self._get_s3_client()
        if s3 is not None and AWS_S3_BUCKET:
            try:
                url = s3.generate_presigned_url(
                    ClientMethod="put_object",
                    Params={
                        "Bucket": AWS_S3_BUCKET,
                        "Key": file_key,
                        "ContentType": content_type,
                    },
                    ExpiresIn=expires_in,
                )
                return {
                    "provider": "s3",
                    "file_key": file_key,
                    "upload_url": str(url),
                    "method": "PUT",
                    "headers": {"Content-Type": content_type},
                    "expires_in": expires_in,
                }
            except Exception as exc:
                logger.warning("Failed to generate S3 presigned upload URL: %s", exc)

        # 2. Supabase Storage signed upload URL
        if SUPABASE_URL and SUPABASE_KEY:
            try:
                from backend.api.supabase_client import get_supabase_client
                client = get_supabase_client()
                # Create signed upload url if supported by supabase version
                res = client.storage.from_(SUPABASE_STORAGE_BUCKET).create_signed_upload_url(file_key)
                if isinstance(res, dict) and "signedURL" in res:
                    return {
                        "provider": "supabase",
                        "file_key": file_key,
                        "upload_url": res["signedURL"],
                        "token": res.get("token"),
                        "method": "PUT",
                        "expires_in": expires_in,
                    }
            except Exception as exc:
                logger.debug("Supabase signed upload URL not available: %s", exc)

        # 3. Local fallback upload endpoint
        expires_at = int(time.time()) + expires_in
        token = sign_local_token(file_key, expires_at)
        return {
            "provider": "local",
            "file_key": file_key,
            "upload_url": f"/api/storage/upload?folder={folder}&filename={clean}&expires={expires_at}&token={token}",
            "method": "POST",
            "expires_in": expires_in,
        }

    # ==========================================================
    # READ OPERATIONS
    # ==========================================================
    def read_bytes(self, filename: str, folder: str = "outputs") -> Optional[bytes]:
        """Reads file bytes from local disk cache or pulls from cloud storage."""
        clean = sanitize_filename(filename)
        file_key = f"{folder}/{clean}"

        # 1. Local disk hit
        local_path = self.get_safe_local_path(clean, folder=folder)
        if local_path and local_path.exists():
            return local_path.read_bytes()

        # 2. S3 pull
        s3 = self._get_s3_client()
        if s3 is not None and AWS_S3_BUCKET:
            try:
                obj = s3.get_object(Bucket=AWS_S3_BUCKET, Key=file_key)
                data = obj["Body"].read()
                if local_path:
                    local_path.write_bytes(data)
                return data
            except Exception as exc:
                logger.debug("S3 fetch failed for %s: %s", file_key, exc)

        # 3. Supabase pull
        if SUPABASE_URL and SUPABASE_KEY:
            try:
                from backend.api.supabase_client import get_supabase_client
                client = get_supabase_client()
                res = client.storage.from_(SUPABASE_STORAGE_BUCKET).download(file_key)
                if res:
                    if local_path:
                        local_path.write_bytes(res)
                    return res
            except Exception as exc:
                logger.debug("Supabase fetch failed for %s: %s", file_key, exc)

        return None


# Global Singleton Storage Service
storage_service = StorageService()
