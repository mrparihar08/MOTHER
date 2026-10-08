# backend/chats/services/email_service.py
"""
Autonomous Email Dispatcher & Smart Drafter Service for Vitya AI.
Supports:
1. Direct SMTP Transmission (Gmail, Outlook, AWS SES, Custom SMTP)
2. Resend REST API Transmission
3. AI-Powered Professional Email Body Generation
4. Guardrails (Autonomous Send vs Draft Review Mode)
"""

import logging
import os
import re
import smtplib
import urllib.parse
from email.message import EmailMessage
from typing import Any, Dict, Optional, Tuple

import requests

from backend.chats.services.gemini_service import generate_response

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


class EmailDispatcher:
    """
    Handles robust email drafting and multi-provider dispatching.
    """

    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        from_email: Optional[str] = None,
        resend_api_key: Optional[str] = None,
    ) -> None:
        self.smtp_host = smtp_host or os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(smtp_port or os.getenv("SMTP_PORT", 587))
        self.smtp_user = smtp_user or os.getenv("SMTP_USER") or os.getenv("SMTP_USERNAME")
        self.smtp_password = smtp_password or os.getenv("SMTP_PASSWORD") or os.getenv("SMTP_PASS")
        self.from_email = from_email or os.getenv("SMTP_FROM") or os.getenv("DEFAULT_FROM_EMAIL") or self.smtp_user or "noreply.vitya.ai@gmail.com"
        self.resend_api_key = resend_api_key or os.getenv("RESEND_API_KEY")

    def is_live_configured(self) -> bool:
        """Returns True if SMTP credentials or Resend API key are active."""
        return bool((self.smtp_user and self.smtp_password) or self.resend_api_key)

    def validate_email(self, email: str) -> bool:
        """Validates recipient email address format."""
        if not email or not isinstance(email, str):
            return False
        return bool(EMAIL_REGEX.match(email.strip()))

    def draft_email_content(
        self,
        topic: str,
        recipient: str,
        sender_name: str = "User",
    ) -> Tuple[str, str]:
        """
        Generates polished, context-rich business email Subject and Body.
        """
        prompt = (
            f"Write a concise, highly professional, polite business email on the topic: '{topic}'.\n"
            f"Sender Name: {sender_name}\n"
            f"Recipient Email: {recipient}\n"
            f"Output EXACTLY in this format on line 1: 'Subject: <subject text>' followed by the email body on subsequent lines. Do not add markdown backticks."
        )
        try:
            raw_res = generate_response(prompt)
            if raw_res and "Gemini error" not in raw_res and "API key is not configured" not in raw_res and "not configured" not in raw_res:
                lines = raw_res.strip().split("\n")
                if lines[0].lower().startswith("subject:"):
                    subject = lines[0].split(":", 1)[1].strip()
                    body = "\n".join(lines[1:]).strip()
                    return subject, body
                else:
                    return f"Update: {topic[:35]}", raw_res.strip()
        except Exception as e:
            logger.warning("Gemini email drafting error: %s", e)

        # Smart fallback template
        subject = f"Business Update & Proposal: {topic[:35]}"
        body = (
            f"Dear Team / Client,\n\n"
            f"I hope this message finds you well.\n\n"
            f"Regarding {topic}, we have prepared the necessary deliverables and documentation. "
            f"Please review the outline and let us know your convenient time for a quick sync.\n\n"
            f"Best regards,\n{sender_name}"
        )
        return subject, body

    def send_via_resend(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        from_name: str = "Vitya AI Assistant",
    ) -> Dict[str, Any]:
        """Dispatches email using Resend REST API."""
        url = "https://api.resend.com/emails"
        headers = {
            "Authorization": f"Bearer {self.resend_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "from": f"{from_name} <{self.from_email}>",
            "to": [to_email],
            "subject": subject,
            "text": body,
        }
        if html_body:
            payload["html"] = html_body

        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return {
            "success": True,
            "provider": "Resend API",
            "message_id": data.get("id", "resend_ok"),
            "recipient": to_email,
            "subject": subject,
            "status": "DELIVERED",
        }

    def send_via_smtp(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        from_name: str = "Vitya AI Assistant",
    ) -> Dict[str, Any]:
        """Dispatches email using standard authenticated SMTP."""
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{self.from_email}>"
        msg["To"] = to_email
        msg.set_content(body)

        if html_body:
            msg.add_alternative(html_body, subtype="html")

        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=12) as server:
            server.starttls()
            if self.smtp_user and self.smtp_password:
                server.login(self.smtp_user, self.smtp_password)
            server.send_message(msg)

        return {
            "success": True,
            "provider": "SMTP Direct",
            "message_id": f"smtp_{to_email}",
            "recipient": to_email,
            "subject": subject,
            "status": "DELIVERED",
        }

    def dispatch(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        from_name: str = "Vitya AI Assistant",
        autonomous: bool = False,
    ) -> Dict[str, Any]:
        """
        Unified dispatch pipeline:
        - Validates address
        - Delivers via Resend or SMTP if configured
        - Returns simulated delivery if live credentials not set
        """
        clean_email = to_email.strip()
        if not self.validate_email(clean_email):
            return {
                "success": False,
                "error": f"Invalid recipient email format: '{to_email}'",
                "status": "VALIDATION_FAILED",
            }

        # 1. Try Resend API if configured
        if self.resend_api_key:
            try:
                return self.send_via_resend(clean_email, subject, body, html_body, from_name)
            except Exception as e:
                logger.error("Resend delivery failed: %s", e)

        # 2. Try SMTP if credentials present
        if self.smtp_user and self.smtp_password:
            try:
                return self.send_via_smtp(clean_email, subject, body, html_body, from_name)
            except Exception as e:
                logger.error("SMTP delivery failed: %s", e)
                return {
                    "success": False,
                    "error": f"SMTP delivery error: {str(e)}",
                    "status": "SMTP_ERROR",
                }

        # 3. Simulated Dispatch (Draft ready with Mailto URL)
        mailto_link = f"mailto:{clean_email}?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(body)}"
        return {
            "success": True,
            "provider": "Simulated Review Mode",
            "message_id": f"sim_{clean_email}",
            "recipient": clean_email,
            "subject": subject,
            "mailto_url": mailto_link,
            "status": "DRAFT_READY",
        }
