# backend/tests/test_dora_integration.py
"""
Integration tests for DORA Medical Knowledge Engine, Gemini AI, and MOTHER Chatbot.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.app.app import app
from backend.dora.engine import engine
from backend.dora.routes import extract_symptoms_from_text
from backend.chats.handlers.dora_handler import handle_dora_health, is_health_query


@pytest.fixture
def client():
    return TestClient(app)


def test_dora_engine_initialization():
    """Verify DORA engine loads dataset, records, and vectorizer properly."""
    assert len(engine.disease_records) > 0
    assert len(engine.symptom_list) > 0
    assert engine.vectorizer is not None
    assert engine.model is not None


def test_dora_engine_prediction():
    """Verify DORA engine correctly predicts conditions given symptoms."""
    res = engine.predict(["fever", "cough", "fatigue"], top_k=3)
    assert "predicted_disease" in res
    assert "possible_diseases" in res
    assert len(res["possible_diseases"]) > 0
    
    top = res["possible_diseases"][0]
    assert "Disease" in top
    assert "Specialist" in top
    assert "Precautions" in top
    assert "Recommended_Tests" in top
    assert "Urgency" in top


def test_dora_symptom_extraction():
    """Verify symptom extraction from natural language text."""
    text = "I have a high fever, severe headache, and joint pain for two days."
    extracted = extract_symptoms_from_text(text)
    assert len(extracted) > 0
    assert any("fever" in s or "headache" in s or "pain" in s for s in extracted)


def test_is_health_query_detection():
    """Verify health query detector accurately flags health vs non-health queries."""
    assert is_health_query("I have a persistent cough and sore throat") is True
    assert is_health_query("What specialist should I see for stomach pain?") is True
    assert is_health_query("Calculate my BMI, height 175cm weight 70kg") is True
    assert is_health_query("Tell me about DORA health assistant") is True
    assert is_health_query("Spent 500 on groceries yesterday") is False


def test_dora_info_endpoint(client):
    """Test GET /api/dora/ info endpoint."""
    response = client.get("/api/dora/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "DORA Health Intelligence Module"
    assert data["status"] == "online"
    assert "Google Gemini" in data["ai_powered_by"]


def test_dora_symptoms_and_diseases_endpoints(client):
    """Test GET /api/dora/symptoms and GET /api/dora/diseases."""
    res1 = client.get("/api/dora/symptoms")
    assert res1.status_code == 200
    assert "symptoms" in res1.json()

    res2 = client.get("/api/dora/diseases")
    assert res2.status_code == 200
    assert "diseases" in res2.json()


def test_dora_predict_endpoint(client):
    """Test POST /api/dora/predict."""
    payload = {
        "symptoms": ["headache", "fever", "chills"],
        "severity": "Moderate",
        "duration_days": 2
    }
    response = client.post("/api/dora/predict", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "predicted_disease" in data
    assert "primary_details" in data
    assert "Specialist" in data["primary_details"]


def test_dora_chat_emergency_handling(client):
    """Test POST /api/dora/chat emergency triage detection."""
    payload = {
        "messages": [
            {"role": "user", "content": "I am experiencing severe chest pain and cannot breathe!"}
        ]
    }
    response = client.post("/api/dora/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data.get("is_emergency") is True
    assert "URGENT MEDICAL ALERT" in data.get("reply", "")


@patch("backend.dora.routes.generate_response")
def test_dora_chat_with_gemini(mock_gemini, client):
    """Test POST /api/dora/chat with Gemini AI response."""
    mock_gemini.return_value = "Here is clinical guidance: Please stay hydrated and rest."
    
    payload = {
        "messages": [
            {"role": "user", "content": "I have a mild fever and dry cough since yesterday. What should I do?"}
        ]
    }
    response = client.post("/api/dora/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data.get("is_emergency") is False
    assert "Here is clinical guidance" in data.get("reply", "")
    assert mock_gemini.called


def test_dora_health_assessment_endpoint(client):
    """Test POST /api/dora/health-assessment."""
    payload = {
        "age": 28,
        "gender": "male",
        "height_cm": 178,
        "weight_kg": 72,
        "activity_level": "moderate",
        "has_smoker_history": False,
        "has_diabetes_history": False,
        "has_hypertension": False
    }
    response = client.post("/api/dora/health-assessment", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["bmi"] > 0
    assert "bmi_category" in data
    assert "bmr_calories" in data
    assert "daily_maintenance_calories" in data
    assert "recommended_daily_water_liters" in data


@patch("backend.chats.handlers.dora_handler.generate_response")
def test_handle_dora_health_chatbot_handler(mock_gemini):
    """Test handle_dora_health integration with Gemini for chatbot queries."""
    mock_gemini.return_value = "### DORA Clinical Advice\nRest well and monitor body temperature."
    
    res = handle_dora_health("i have fever and body pain", "I have fever and body pain")
    assert res is not None
    assert res["type"] == "dora"
    assert "Rest well" in res["content"]
    assert "health_data" in res
    assert res["health_data"]["is_emergency"] is False

