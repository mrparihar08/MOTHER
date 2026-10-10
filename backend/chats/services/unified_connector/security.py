from __future__ import annotations

import ipaddress
import logging
import re
import socket
import urllib.parse
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Cloud metadata IP & Hostnames
BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "instance-data",
}

# Prompt Injection Attack Patterns often embedded in scraped web content
PROMPT_INJECTION_PATTERNS = [
    r"(?i)\bignore\s+(?:all\s+)?previous\s+instructions\b",
    r"(?i)\byou\s+are\s+now\s+(?:in\s+)?developer\s+mode\b",
    r"(?i)\bsystem\s+prompt\s*:",
    r"(?i)<\|im_start\|>",
    r"(?i)<\|im_end\|>",
    r"(?i)\[INST\].*?\[/INST\]",
    r"(?i)\bdisregard\s+all\s+prior\s+directives\b",
    r"(?i)\bact\s+as\s+an\s+unrestricted\s+ai\b",
]

MAX_FETCH_BYTES = 512 * 1024  # 512 KB limit


def is_safe_url(url: str) -> Tuple[bool, Optional[str]]:
    """
    Strict SSRF Validator:
    Verifies that the URL scheme is HTTP/HTTPS and resolves to a public, globally routable IP address.
    Rejects:
    - Loopback (127.0.0.0/8, ::1)
    - Private IP ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
    - Link-local (169.254.0.0/16, fe80::/10)
    - Cloud metadata endpoints (169.254.169.254)
    - Non-HTTP schemes (file://, ftp://, gopher://, etc.)
    """
    if not url or not isinstance(url, str):
        return False, "Empty or invalid URL"

    try:
        parsed = urllib.parse.urlparse(url.strip())
    except Exception as e:
        return False, f"URL parse error: {e}"

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return False, f"Prohibited URL scheme: '{scheme}'. Only HTTP and HTTPS are permitted."

    hostname = (parsed.hostname or "").lower().strip()
    if not hostname:
        return False, "Missing hostname in URL"

    if hostname in BLOCKED_HOSTNAMES:
        return False, f"Prohibited host: '{hostname}'"

    # Check direct IP addresses or resolve DNS
    try:
        # Check if hostname itself is a raw IP literal
        try:
            ip_obj = ipaddress.ip_address(hostname)
            if not ip_obj.is_global or ip_obj.is_loopback or ip_obj.is_private or ip_obj.is_link_local:
                return False, f"Prohibited IP address target: {hostname}"
            return True, None
        except ValueError:
            pass  # Hostname is a domain name, proceed to DNS resolution

        # Resolve hostname to IPv4/IPv6 addresses
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        if not addr_info:
            return False, f"DNS resolution failed for '{hostname}'"

        for entry in addr_info:
            resolved_ip_str = entry[4][0]
            resolved_ip = ipaddress.ip_address(resolved_ip_str)

            if not resolved_ip.is_global or resolved_ip.is_loopback or resolved_ip.is_private or resolved_ip.is_link_local:
                logger.warning("SSRF blocked attempt to access private/link-local address: %s (%s)", hostname, resolved_ip_str)
                return False, f"Resolved IP {resolved_ip_str} is in a restricted network range."

    except socket.gaierror:
        return False, f"Could not resolve host: '{hostname}'"
    except Exception as exc:
        return False, f"Security check exception: {str(exc)}"

    return True, None


def sanitize_external_text(text: str, max_chars: int = 4000) -> str:
    """
    Sanitizes external web / feed text before injecting into LLM context:
    - Neutralizes known prompt injection exploits
    - Strips excessive whitespace and control characters
    - Caps maximum text length
    """
    if not text:
        return ""

    sanitized = text
    for pattern in PROMPT_INJECTION_PATTERNS:
        sanitized = re.sub(pattern, "[FILTERED_DIRECTIVE]", sanitized)

    # Clean non-printable control characters except standard newlines and tabs
    sanitized = "".join(ch for ch in sanitized if ch >= " " or ch in "\n\t")

    return sanitized[:max_chars].strip()
