"""
Dora Service Client for Chat Service.
Calls Dora Microservice (Port 8004) over internal REST network.
"""
import os
import json
import logging
from typing import Dict, Any, List, Optional
import urllib.request
import urllib.error

logger = logging.getLogger("chat.clients.dora")

DORA_SERVICE_URL = os.getenv("DORA_SERVICE_URL", "http://dora_service:8004")


class RemoteDoraClient:
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or DORA_SERVICE_URL).rstrip("/")

    def predict_disease(self, symptoms: List[str], severity: str = "Moderate") -> Dict[str, Any]:
        """Queries Dora Service for disease triage predictions."""
        url = f"{self.base_url}/predict"
        payload = {"symptoms": symptoms, "severity": severity}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "ChatService-InternalClient"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            logger.warning(f"Failed to communicate with Dora Service at {url}: {e}")
            return {
                "status": "error",
                "message": f"Dora Service temporarily unreachable: {str(e)}",
                "predictions": [],
            }
