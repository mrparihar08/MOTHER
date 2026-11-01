# backend/tests/test_async_jobs_and_dora_service.py
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.app.app import app
from backend.api.tasks.queue import task_queue
from backend.api.tasks.handlers import (
    handle_generate_presentation,
    handle_convert_pdf,
    handle_generate_ai_image,
    TASK_GENERATE_PRESENTATION,
    TASK_CONVERT_PDF,
    TASK_GENERATE_AI_IMAGE,
)
from services.dora_service.app import app as dora_service_app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def dora_client():
    return TestClient(dora_service_app)


def test_async_presentation_generation_endpoint(client):
    """Verify POST /api/presentation/generate-async enqueues job and returns 202 Accepted."""
    payload = {
        "topic": "Future of Autonomous Electric Vehicles",
        "num_slides": 4,
        "template_name": "clean_minimal",
        "visual_style": "minimal_stark",
    }
    res = client.post("/api/presentation/generate-async", json=payload)
    assert res.status_code == 202
    data = res.json()
    assert "job_id" in data
    assert data["status"] == "queued"
    assert "poll_url" in data
    assert "presentation_id" in data

    # Verify job status can be fetched
    job_id = data["job_id"]
    job_res = client.get(f"/api/presentation/jobs/{job_id}")
    assert job_res.status_code == 200
    job_data = job_res.json()
    assert job_data["job_id"] == job_id
    assert job_data["status"] in ("queued", "processing", "completed")


def test_export_pdf_async_endpoint(client):
    """Verify POST /api/presentation/export-pdf-async enqueues PDF task and returns 202."""
    payload = {
        "presentation_id": "pres_sample_123",
        "title": "Quarterly Financial Analysis",
        "plan": {"title": "Quarterly Financial Analysis", "slides": []},
    }
    res = client.post("/api/presentation/export-pdf-async", json=payload)
    assert res.status_code == 202
    data = res.json()
    assert "job_id" in data
    assert data["status"] == "queued"
    assert "poll_url" in data


def test_generate_ai_image_async_endpoint(client):
    """Verify POST /api/presentation/ai-image/generate-async enqueues image task and returns 202."""
    payload = {
        "prompt": "Solar powered electric transport grid",
        "width": 1280,
        "height": 720,
    }
    res = client.post("/api/presentation/ai-image/generate-async", json=payload)
    assert res.status_code == 202
    data = res.json()
    assert "job_id" in data
    assert data["status"] == "queued"
    assert "poll_url" in data


def test_async_job_status_not_found(client):
    """Verify 404 for unknown job_id."""
    res = client.get("/api/presentation/jobs/non_existent_job_123")
    assert res.status_code == 404


def test_handle_convert_pdf_task():
    """Verify handle_convert_pdf task handler executes and returns cloud URL."""
    mock_pdf_path = "outputs/sample_deck.pdf"
    with patch("backend.presentation.exporter.save_presentation_as_pdf", return_value=mock_pdf_path), \
         patch("pathlib.Path.read_bytes", return_value=b"fake-pdf-bytes"), \
         patch("backend.api.services.storage_service.storage_service.upload_file", return_value={"presigned_url": "https://s3.amazonaws.com/outputs/sample_deck.pdf"}):
        
        res = handle_convert_pdf({
            "plan": {"title": "Test Deck", "slides": []},
            "presentation_id": "pres_test_123",
            "title": "Test Deck",
        })
        assert res["presentation_id"] == "pres_test_123"
        assert "pdf_url" in res


def test_handle_generate_ai_image_task():
    """Verify handle_generate_ai_image task handler executes."""
    with patch("backend.presentation.services.ai_image_service.generate_ai_image", return_value="https://assets.mother.ai/generated_img.jpg"):
        res = handle_generate_ai_image({
            "prompt": "Modern futuristic architecture",
            "width": 1280,
            "height": 720,
        })
        assert res["image_url"] == "https://assets.mother.ai/generated_img.jpg"


def test_dora_standalone_microservice_health(dora_client):
    """Verify standalone DORA microservice health endpoint."""
    res = dora_client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "dora-clinical-microservice"
    assert data["total_diseases"] > 0


def test_dora_standalone_microservice_symptoms(dora_client):
    """Verify standalone DORA microservice symptoms endpoint."""
    res = dora_client.get("/symptoms?query=fever")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] > 0
    assert any("fever" in s for s in data["symptoms"])


def test_dora_standalone_microservice_predict(dora_client):
    """Verify standalone DORA microservice predict endpoint."""
    payload = {
        "symptoms": ["fever", "cough", "fatigue"],
        "severity": "Moderate",
        "top_k": 3,
    }
    res = dora_client.post("/predict", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "predicted_disease" in data
    assert "possible_diseases" in data
    assert len(data["possible_diseases"]) <= 3


def test_dora_client_remote_delegation():
    """Verify dora_client routes to DORA_SERVICE_URL when set."""
    from backend.chats.services.dora_client import predict_health_condition

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "predicted_disease": "Common Cold",
        "possible_diseases": [{"Disease": "Common Cold", "Similarity": 0.95}],
    }

    with patch("backend.chats.services.dora_client.DORA_SERVICE_URL", "https://dora-service.internal"), \
         patch("requests.post", return_value=mock_resp) as mock_post:
        
        res = predict_health_condition(["sneezing", "runny_nose"], top_k=2)
        assert res["predicted_disease"] == "Common Cold"
        mock_post.assert_called_once()
