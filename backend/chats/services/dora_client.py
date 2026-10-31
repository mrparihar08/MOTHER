# backend/chats/services/dora_client.py
"""
Decoupled DORA Health Intelligence Client & Circuit Breaker.
Isolates Chat from the DORA clinical ML engine.
If DORA service is slow, fails, or is migrated to a microservice,
Chatbot continues functioning safely without crashing.
"""

import logging
import os
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger("DORA-CLIENT")

# Optional microservice URL (when DORA runs as an independent microservice)
DORA_SERVICE_URL = os.getenv("DORA_SERVICE_URL", "").rstrip("/")

_cached_symptoms: Optional[List[str]] = None


def get_known_symptoms() -> List[str]:
    """Retrieve known symptom list with fallback and in-memory cache."""
    global _cached_symptoms
    if _cached_symptoms is not None:
        return _cached_symptoms

    # If DORA microservice is configured
    if DORA_SERVICE_URL:
        try:
            resp = requests.get(f"{DORA_SERVICE_URL}/api/dora/symptoms", timeout=3)
            if resp.status_code == 200:
                _cached_symptoms = resp.json().get("symptoms", [])
                return _cached_symptoms
        except Exception as exc:
            logger.warning("Failed to fetch symptoms from DORA microservice: %s", exc)

    # Safe local engine import
    try:
        from backend.dora.engine import engine
        if hasattr(engine, "symptom_list") and engine.symptom_list:
            _cached_symptoms = list(engine.symptom_list)
            return _cached_symptoms
    except Exception as exc:
        logger.warning("Local DORA engine not accessible for symptom list: %s", exc)

    # Fallback common symptoms if engine is offline
    _cached_symptoms = [
        "fever", "cough", "headache", "fatigue", "nausea", "vomiting", "diarrhea",
        "chest_pain", "breathlessness", "dizziness", "chills", "body_pain",
        "joint_pain", "stomach_pain", "sore_throat", "skin_rash", "itching"
    ]
    return _cached_symptoms


def predict_health_condition(symptoms: List[str], top_k: int = 3) -> Dict[str, Any]:
    """
    Predict health conditions given a list of symptoms.
    Uses DORA microservice if configured, otherwise safely delegates to local engine with fault tolerance.
    """
    if not symptoms:
        return {"possible_diseases": []}

    # Microservice mode
    if DORA_SERVICE_URL:
        try:
            resp = requests.post(
                f"{DORA_SERVICE_URL}/api/dora/predict",
                json={"symptoms": symptoms, "severity": "Moderate"},
                timeout=5,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as exc:
            logger.warning("DORA microservice prediction error: %s", exc)

    # Safe local engine delegation
    try:
        from backend.dora.engine import engine
        return engine.predict(symptoms, top_k=top_k)
    except Exception as exc:
        logger.error("Local DORA engine prediction failed: %s", exc)
        return {"possible_diseases": [], "error": str(exc)}
