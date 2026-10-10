from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Optional
import requests

from backend.chats.services.unified_connector.security import (
    MAX_FETCH_BYTES,
    is_safe_url,
    sanitize_external_text,
)

logger = logging.getLogger(__name__)

USER_AGENT = "VityaAI-Bot/2.0 (+https://vitya.ai/bot; legitimate data connector; respects robots.txt)"
REQUEST_TIMEOUT = 6.0


def extract_page_content(url: str, max_chars: int = 3000) -> Optional[str]:
    """
    Safely extract readable textual summary from a public permitted webpage.
    Enforces strict SSRF protection, size limits, and prompt-injection neutralization.
    """
    if not url:
        return None

    safe, reason = is_safe_url(url)
    if not safe:
        logger.warning("Blocked page extraction for unsafe URL '%s': %s", url, reason)
        return None

    try:
        session = requests.Session()
        resp = session.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,text/plain"},
            timeout=REQUEST_TIMEOUT,
            stream=True,
        )

        if resp.status_code != 200:
            logger.info("Extraction skipped; HTTP %d for %s", resp.status_code, url)
            return None

        # Verify content type
        content_type = resp.headers.get("Content-Type", "").lower()
        if not ("text/html" in content_type or "text/plain" in content_type):
            logger.info("Non-text MIME type '%s' for %s", content_type, url)
            return None

        # Read only up to MAX_FETCH_BYTES
        content_chunks = []
        bytes_read = 0
        for chunk in resp.iter_content(chunk_size=4096):
            content_chunks.append(chunk)
            bytes_read += len(chunk)
            if bytes_read >= MAX_FETCH_BYTES:
                break

        raw_bytes = b"".join(content_chunks)
        encoding = resp.encoding or "utf-8"
        text = raw_bytes.decode(encoding, errors="ignore")

        # Strip scripts, styles, head, comments
        text = re.sub(r"(?is)<script.*?</script>", " ", text)
        text = re.sub(r"(?is)<style.*?</style>", " ", text)
        text = re.sub(r"(?is)<!--.*?-->", " ", text)
        text = re.sub(r"(?is)<head.*?</head>", " ", text)
        text = re.sub(r"(?is)<nav.*?</nav>", " ", text)
        text = re.sub(r"(?is)<footer.*?</footer>", " ", text)

        # Strip HTML tags
        clean_text = re.sub(r"<[^>]+>", " ", text)
        # Normalize whitespace
        clean_text = re.sub(r"\s+", " ", clean_text).strip()

        # Neutralize prompt injection patterns
        sanitized = sanitize_external_text(clean_text, max_chars=max_chars)
        return sanitized if len(sanitized) > 40 else None

    except Exception as exc:
        logger.warning("Error extracting page content for %s: %s", url, exc)
        return None
