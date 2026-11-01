# backend/tests/test_cloud_storage.py
import io
import time
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from backend.api.services.storage_service import (
    StorageService,
    sanitize_filename,
    sign_local_token,
    verify_local_token,
)
from backend.app.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_sanitize_filename():
    """Verify path traversal prevention in filenames."""
    assert sanitize_filename("../../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\windows\\system32\\calc.exe") == "calc.exe"
    assert sanitize_filename("my deck (final) #1.pptx") == "my_deck__final___1.pptx"


def test_local_token_signature_and_verification():
    """Verify cryptographic HMAC presigned token signing, verification and expiration."""
    file_key = "outputs/sample_deck.pptx"
    future_exp = int(time.time()) + 300
    past_exp = int(time.time()) - 300

    valid_token = sign_local_token(file_key, future_exp)
    assert verify_local_token(file_key, future_exp, valid_token) is True

    # Tampered token
    assert verify_local_token(file_key, future_exp, valid_token + "tamper") is False

    # Tampered key
    assert verify_local_token("outputs/other.pptx", future_exp, valid_token) is False

    # Expired token
    expired_token = sign_local_token(file_key, past_exp)
    assert verify_local_token(file_key, past_exp, expired_token) is False


def test_storage_service_local_upload_and_read():
    """Verify streaming upload and reading bytes via StorageService."""
    service = StorageService()
    test_content = b"Mock presentation binary data"
    test_name = "test_presigned.pptx"

    res = service.upload_file(
        file_input=test_content,
        filename=test_name,
        folder="outputs",
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )

    assert res["filename"] == test_name
    assert "presigned_url" in res
    assert res["size_bytes"] == len(test_content)

    # Read back bytes
    fetched = service.read_bytes(test_name, folder="outputs")
    assert fetched == test_content


def test_s3_presigned_url_generation():
    """Verify S3 client presigned URL generation when configured."""
    service = StorageService()
    mock_s3 = MagicMock()
    mock_s3.generate_presigned_url.return_value = "https://my-bucket.s3.amazonaws.com/outputs/test.pptx?AWSAccessKeyId=XXX&Signature=YYY"

    service._s3_client = mock_s3
    service._s3_initialized = True

    with patch("backend.api.services.storage_service.AWS_S3_BUCKET", "my-bucket"):
        url = service.get_presigned_download_url("test.pptx", folder="outputs", expires_in=1800)
        assert "https://my-bucket.s3.amazonaws.com" in url
        mock_s3.generate_presigned_url.assert_called_once()


def test_supabase_presigned_url_generation():
    """Verify Supabase Storage presigned URL generation when configured."""
    service = StorageService()
    service._s3_client = None
    service._s3_initialized = True

    mock_supabase = MagicMock()
    mock_supabase.storage.from_().create_signed_url.return_value = {
        "signedURL": "https://xyz.supabase.co/storage/v1/object/sign/mother-assets/outputs/deck.pptx?token=abc"
    }

    with patch("backend.api.services.storage_service.SUPABASE_URL", "https://xyz.supabase.co"), \
         patch("backend.api.services.storage_service.SUPABASE_KEY", "mock-key"), \
         patch("backend.api.supabase_client.get_supabase_client", return_value=mock_supabase):
        url = service.get_presigned_download_url("deck.pptx", folder="outputs")
        assert "https://xyz.supabase.co/storage/v1/object/sign" in url


def test_storage_routes_presigned_download_endpoint(client):
    """Verify GET /api/storage/presigned-url returns presigned URL."""
    res = client.get("/api/storage/presigned-url/outputs/quarterly_report.pptx")
    assert res.status_code == 200
    data = res.json()
    assert "presigned_url" in data
    assert data["filename"] == "quarterly_report.pptx"
    assert data["folder"] == "outputs"


def test_storage_routes_presigned_upload_endpoint(client):
    """Verify POST /api/storage/presigned-upload-url returns presigned upload URL."""
    payload = {
        "filename": "user_upload.pdf",
        "folder": "uploads",
        "content_type": "application/pdf",
        "expires_in": 1800,
    }
    res = client.post("/api/storage/presigned-upload-url", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "upload_url" in data
    assert data["file_key"] == "uploads/user_upload.pdf"


def test_storage_routes_signed_download_endpoint(client):
    """Verify HMAC verification on /api/storage/signed-download."""
    service = StorageService()
    filename = "download_test.txt"
    service.upload_file(b"test file content", filename=filename, folder="outputs")

    # Valid token
    exp = int(time.time()) + 300
    token = sign_local_token(f"outputs/{filename}", exp)
    res = client.get(f"/api/storage/signed-download?folder=outputs&filename={filename}&expires={exp}&token={token}")
    assert res.status_code == 200
    assert res.content == b"test file content"

    # Invalid token (403)
    res_bad = client.get(f"/api/storage/signed-download?folder=outputs&filename={filename}&expires={exp}&token=wrongtoken")
    assert res_bad.status_code == 403


def test_storage_routes_multipart_upload_endpoint(client):
    """Verify POST /api/storage/upload streams file to storage."""
    file_bytes = b"Hello cloud object storage!"
    files = {"file": ("cloud_note.txt", io.BytesIO(file_bytes), "text/plain")}
    data = {"folder": "uploads"}

    res = client.post("/api/storage/upload", files=files, data=data)
    assert res.status_code == 200
    json_data = res.json()
    assert json_data["filename"] == "cloud_note.txt"
    assert "presigned_url" in json_data
    assert json_data["size_bytes"] == len(file_bytes)
