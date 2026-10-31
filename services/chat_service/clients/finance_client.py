"""
Finance Service Client for Chat Service.
Calls Finance Microservice (Port 8002) over internal REST network.
"""
import os
import json
import logging
from typing import Dict, Any, Optional
import urllib.request
import urllib.error

logger = logging.getLogger("chat.clients.finance")

FINANCE_SERVICE_URL = os.getenv("FINANCE_SERVICE_URL", "http://finance_service:8002")


class RemoteFinanceClient:
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or FINANCE_SERVICE_URL).rstrip("/")

    def record_transaction(
        self,
        user_id: int,
        transaction_type: str,
        amount: float,
        category_or_source: str,
        description: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Posts internal transaction to Finance Service."""
        url = f"{self.base_url}/api/finance/internal/transaction"
        payload = {
            "user_id": user_id,
            "transaction_type": transaction_type,
            "amount": amount,
            "category_or_source": category_or_source,
            "description": description,
            "idempotency_key": idempotency_key,
        }
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
            logger.warning(f"Failed to communicate with Finance Service at {url}: {e}")
            return {
                "status": "error",
                "message": f"Finance Service temporarily unreachable: {str(e)}",
            }
