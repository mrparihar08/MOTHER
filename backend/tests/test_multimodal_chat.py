import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from fastapi import HTTPException

from backend.app.app import app
from backend.api.auth import create_access_token
from backend.api.models.vitya import Conversation, ChatMessage, User, Base
from backend.api.database import engine, SessionLocal
from backend.chats.services.vision_service import (
    BaseVisionProvider,
    GeminiVisionProvider,
    get_vision_provider,
    set_vision_provider,
)
from backend.chats.handlers.multimodal_handler import (
    validate_image_bytes,
    handle_multimodal_chat,
    MAX_IMAGE_SIZE_BYTES,
)

client = TestClient(app)


def _generate_test_image_bytes(format="JPEG", size=(100, 100), color="blue") -> bytes:
    """Helper to generate valid dummy image bytes for testing."""
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()


class MockVisionProvider(BaseVisionProvider):
    """Mock vision provider for deterministic unit and integration tests."""

    def __init__(self, response_text="Mock visual analysis: Image shows a financial chart with upward trend."):
        self.response_text = response_text
        self.last_prompt = None
        self.last_images = None

    def analyze_multimodal(self, images_data, prompt, system_instruction=None, temperature=0.2):
        self.last_images = images_data
        self.last_prompt = prompt
        return {
            "success": True,
            "text": self.response_text,
            "model_used": "mock-vision-v1",
        }


class FailingVisionProvider(BaseVisionProvider):
    """Mock vision provider that simulates API failures."""

    def analyze_multimodal(self, images_data, prompt, system_instruction=None, temperature=0.2):
        return {
            "success": False,
            "error": "Quota exceeded",
            "text": "Vision API quota exceeded. Please try again later.",
        }


@pytest.fixture(autouse=True)
def setup_test_environment():
    Base.metadata.create_all(bind=engine)
    # Default to mock provider for fast, reliable testing
    mock_p = MockVisionProvider()
    set_vision_provider(mock_p)
    yield
    # Reset
    set_vision_provider(GeminiVisionProvider())


# -------------------------------------------------------------
# 1. IMAGE VALIDATION & SECURITY TESTS
# -------------------------------------------------------------

def test_validate_jpeg_image():
    jpeg_bytes = _generate_test_image_bytes(format="JPEG")
    is_valid, err, mime = validate_image_bytes(jpeg_bytes, "test.jpg", "image/jpeg")
    assert is_valid is True
    assert err is None
    assert mime == "image/jpeg"


def test_validate_png_image():
    png_bytes = _generate_test_image_bytes(format="PNG")
    is_valid, err, mime = validate_image_bytes(png_bytes, "test.png", "image/png")
    assert is_valid is True
    assert err is None
    assert mime == "image/png"


def test_validate_webp_image():
    webp_bytes = _generate_test_image_bytes(format="WEBP")
    is_valid, err, mime = validate_image_bytes(webp_bytes, "test.webp", "image/webp")
    assert is_valid is True
    assert err is None
    assert mime == "image/webp"


def test_validate_corrupt_or_empty_image():
    is_valid, err, _ = validate_image_bytes(b"", "empty.jpg")
    assert is_valid is False
    assert "empty or corrupted" in err

    is_valid, err, _ = validate_image_bytes(b"NOT_AN_IMAGE_RANDOM_TEXT_DATA_1234567890", "fake.jpg")
    assert is_valid is False
    assert "Invalid or corrupted" in err


def test_validate_oversized_image():
    large_fake_data = b"X" * (MAX_IMAGE_SIZE_BYTES + 1024)
    is_valid, err, _ = validate_image_bytes(large_fake_data, "large.jpg")
    assert is_valid is False
    assert "exceeds the maximum" in err


# -------------------------------------------------------------
# 2. MULTIMODAL HANDLER LOGIC & ZERO-HALLUCINATION TESTS
# -------------------------------------------------------------

def test_multimodal_handler_with_text():
    mock_p = MockVisionProvider("Detailed chart analysis: Q3 revenue peaked at INR 50,000.")
    set_vision_provider(mock_p)

    img_bytes = _generate_test_image_bytes("JPEG")
    images_data = [{"data": img_bytes, "mime_type": "image/jpeg", "filename": "chart.jpg"}]

    res = handle_multimodal_chat(
        user_message="Is chart mein Q3 revenue kitna hai?",
        images_data=images_data,
        db=None,
        current_user=None,
    )
    assert res["type"] == "text"
    assert "Q3 revenue peaked" in res["content"]
    assert res["images_count"] == 1
    assert mock_p.last_prompt == "Is chart mein Q3 revenue kitna hai?"


def test_multimodal_handler_image_only_fallback_prompt():
    mock_p = MockVisionProvider("This image depicts a handwritten note with 3 checklist items.")
    set_vision_provider(mock_p)

    img_bytes = _generate_test_image_bytes("PNG")
    images_data = [{"data": img_bytes, "mime_type": "image/png", "filename": "note.png"}]

    res = handle_multimodal_chat(
        user_message="",
        images_data=images_data,
        db=None,
        current_user=None,
    )
    assert res["type"] == "text"
    assert "handwritten note" in res["content"]
    # Check default prompt was used
    assert "analyze this image in detail" in mock_p.last_prompt.lower()


def test_multimodal_handler_multiple_images():
    mock_p = MockVisionProvider("Comparison: Image 1 shows July expenses, Image 2 shows August expenses.")
    set_vision_provider(mock_p)

    img1 = _generate_test_image_bytes("JPEG", color="red")
    img2 = _generate_test_image_bytes("JPEG", color="green")
    images_data = [
        {"data": img1, "mime_type": "image/jpeg", "filename": "july.jpg"},
        {"data": img2, "mime_type": "image/jpeg", "filename": "august.jpg"},
    ]

    res = handle_multimodal_chat(
        user_message="Compare these two expense reports",
        images_data=images_data,
        db=None,
        current_user=None,
    )
    assert res["images_count"] == 2
    assert len(mock_p.last_images) == 2


def test_multimodal_handler_vision_failure():
    set_vision_provider(FailingVisionProvider())
    img_bytes = _generate_test_image_bytes("JPEG")
    images_data = [{"data": img_bytes, "mime_type": "image/jpeg", "filename": "bill.jpg"}]

    res = handle_multimodal_chat(
        user_message="Scan this bill",
        images_data=images_data,
        db=None,
        current_user=None,
    )
    assert res.get("error") is True
    assert "quota" in res["content"].lower()


# -------------------------------------------------------------
# 3. FASTAPI ENDPOINT INTEGRATION TESTS
# -------------------------------------------------------------

def test_multimodal_endpoint_unauthorized():
    img_bytes = _generate_test_image_bytes("JPEG")
    response = client.post(
        "/api/chat/multimodal",
        data={"message": "What is this?"},
        files={"files": ("photo.jpg", img_bytes, "image/jpeg")},
    )
    assert response.status_code == 401


def test_multimodal_endpoint_success():
    token = create_access_token({"user_id": 1, "email": "test@user.com", "username": "testuser"})
    img_bytes = _generate_test_image_bytes("PNG")

    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/api/chat/multimodal",
        headers=headers,
        data={"message": "Describe this image in Hinglish"},
        files={"files": ("test.png", img_bytes, "image/png")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "text"
    assert "content" in data
    assert data["images_count"] == 1


def test_multimodal_endpoint_invalid_image_format_400():
    token = create_access_token({"user_id": 1, "email": "test@user.com", "username": "testuser"})
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/api/chat/multimodal",
        headers=headers,
        data={"message": "Explain this"},
        files={"files": ("bad.txt", b"plain text is not an image", "text/plain")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("error") is True
    assert "Image error" in data["content"]


def test_existing_text_chat_endpoint_intact():
    token = create_access_token({"user_id": 1, "email": "test@user.com", "username": "testuser"})
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/api/chat/",
        headers=headers,
        json={"message": "hello vitya"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "content" in data or "text" in data
