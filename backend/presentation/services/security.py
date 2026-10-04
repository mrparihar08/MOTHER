from __future__ import annotations

import logging
import os
import re
import socket
from urllib.parse import urlparse
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(os.getenv("PPT_OUTPUT_DIR", "./outputs")).resolve()
ASSET_DIR = Path(os.getenv("PPT_ASSET_DIR", "./assets")).resolve()
ALLOW_ABSOLUTE_IMAGE_PATHS = os.getenv("PPT_ALLOW_ABSOLUTE_IMAGE_PATHS", "false").lower() == "true"
MAX_IMAGE_DOWNLOAD_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB limit


def sanitize_filename(filename: str) -> str:
    """Strip dangerous characters and directory traversal markers from filenames."""
    if not filename:
        return ""
    clean = os.path.basename(filename)
    clean = re.sub(r"[^\w\-. ]", "_", clean)
    clean = clean.strip("._ ")
    return clean


def is_safe_output_path(file_name: str) -> Optional[Path]:
    """
    Validates that file_name resolves strictly inside OUTPUT_DIR.
    Prevents directory traversal attacks (e.g., ../../../etc/passwd).
    """
    cleaned_name = sanitize_filename(file_name)
    if not cleaned_name or cleaned_name != file_name:
        return None

    try:
        resolved_path = (OUTPUT_DIR / cleaned_name).resolve()
        output_dir_resolved = OUTPUT_DIR.resolve()

        if resolved_path.is_relative_to(output_dir_resolved) and resolved_path.is_file():
            return resolved_path
    except Exception as exc:
        logger.warning("Path traversal check error for '%s': %s", file_name, exc)

    return None


def is_safe_url(url: str) -> bool:
    """
    SSRF Protection: Validates remote URL scheme and host to block private IP space attacks.
    """
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return False

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False

        # Block loopback, metadata IPs, and private subnets
        if hostname.lower() in {"localhost", "127.0.0.1", "::1", "169.254.169.254", "0.0.0.0"}:
            return False

        try:
            ip = socket.gethostbyname(hostname)
            if ip.startswith("127.") or ip.startswith("10.") or ip.startswith("169.254.") or ip.startswith("192.168."):
                return False
            if ip.startswith("172."):
                parts = [int(p) for p in ip.split(".")]
                if 16 <= parts[1] <= 31:
                    return False
        except Exception:
            pass  # DNS resolution failure will be handled by HTTP client timeout

        return True
    except Exception:
        return False


def is_safe_image_path(path_text: str) -> Optional[Path]:
    """
    Validates local filesystem image paths to ensure they stay within ASSET_DIR
    or authorized directories when ALLOW_ABSOLUTE_IMAGE_PATHS is enabled.
    """
    if not path_text:
        return None

    try:
        candidate = Path(path_text).resolve()
        asset_dir_resolved = ASSET_DIR.resolve()

        if candidate.is_relative_to(asset_dir_resolved) and candidate.is_file():
            return candidate

        output_dir_resolved = OUTPUT_DIR.resolve()
        if candidate.is_relative_to(output_dir_resolved) and candidate.is_file():
            return candidate

        if ALLOW_ABSOLUTE_IMAGE_PATHS and candidate.is_file():
            return candidate

    except Exception as exc:
        logger.warning("Image path safety evaluation error for '%s': %s", path_text, exc)

    return None
