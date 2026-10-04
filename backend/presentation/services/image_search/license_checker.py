from __future__ import annotations

import logging
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)


def normalize_license_name(raw_license: str, license_url: str = "") -> str:
    """Normalizes raw license string into canonical license name."""
    if not raw_license:
        if "creativecommons.org/publicdomain/zero" in license_url.lower():
            return "CC0 1.0"
        elif "creativecommons.org/licenses/by/" in license_url.lower():
            return "CC BY 4.0"
        elif "creativecommons.org/licenses/by-sa/" in license_url.lower():
            return "CC BY-SA 4.0"
        return "Unknown"

    lic = raw_license.strip().upper()
    lic = re.sub(r"^CC\s+", "CC ", lic)

    if "CC0" in lic or "PUBLIC DOMAIN" in lic or lic in {"ZERO", "PDM"}:
        return "CC0 1.0"
    elif "BY-NC-ND" in lic:
        return "CC BY-NC-ND 4.0"
    elif "BY-NC-SA" in lic:
        return "CC BY-NC-SA 4.0"
    elif "BY-NC" in lic:
        return "CC BY-NC 4.0"
    elif "BY-ND" in lic:
        return "CC BY-ND 4.0"
    elif "BY-SA" in lic:
        return "CC BY-SA 4.0"
    elif lic in {"BY", "CC BY", "CC-BY", "CC BY 2.0", "CC BY 3.0", "CC BY 4.0"} or "ATTRIBUTION" in lic:
        return "CC BY 4.0"
    elif "PD" in lic or "COMMONS" in lic:
        return "Public Domain"

    return raw_license.strip()


def evaluate_license(raw_license: str, license_url: str = "") -> Dict[str, Any]:
    """
    Evaluates raw license metadata into structured licensing classification.
    Returns:
        {
            "license": str,
            "license_url": str,
            "license_status": "commercial_safe" | "non_commercial" | "attribution_required" | "unknown",
            "commercial_use": bool,
            "attribution_required": bool,
            "modification_allowed": bool
        }
    """
    norm_name = normalize_license_name(raw_license, license_url)
    lic_upper = norm_name.upper()

    canonical_url = license_url or ""
    if not canonical_url:
        if "CC0" in lic_upper:
            canonical_url = "https://creativecommons.org/publicdomain/zero/1.0/"
        elif "CC BY-SA" in lic_upper:
            canonical_url = "https://creativecommons.org/licenses/by-sa/4.0/"
        elif "CC BY-NC" in lic_upper:
            canonical_url = "https://creativecommons.org/licenses/by-nc/4.0/"
        elif "CC BY" in lic_upper:
            canonical_url = "https://creativecommons.org/licenses/by/4.0/"

    if "CC0" in lic_upper or "PUBLIC DOMAIN" in lic_upper or lic_upper == "PDM":
        return {
            "license": norm_name,
            "license_url": canonical_url,
            "license_status": "commercial_safe",
            "commercial_use": True,
            "attribution_required": False,
            "modification_allowed": True,
        }

    if "NC" in lic_upper:
        return {
            "license": norm_name,
            "license_url": canonical_url,
            "license_status": "non_commercial",
            "commercial_use": False,
            "attribution_required": True,
            "modification_allowed": "ND" not in lic_upper,
        }

    if any(k in lic_upper for k in ["CC BY", "BY-SA", "BY-ND", "ATTRIBUTION"]):
        return {
            "license": norm_name,
            "license_url": canonical_url,
            "license_status": "attribution_required",
            "commercial_use": True,
            "attribution_required": True,
            "modification_allowed": "ND" not in lic_upper,
        }

    if not raw_license or norm_name == "Unknown" or not any(k in lic_upper for k in ["CC0", "PUBLIC DOMAIN", "CC BY", "BY-SA", "BY-ND", "NC", "UNSPLASH"]):
        return {
            "license": norm_name,
            "license_url": canonical_url,
            "license_status": "unknown",
            "commercial_use": False,
            "attribution_required": True,
            "modification_allowed": True,
        }

    return {
        "license": norm_name,
        "license_url": canonical_url,
        "license_status": "commercial_safe",
        "commercial_use": True,
        "attribution_required": True,
        "modification_allowed": True,
    }


def build_attribution_string(title: str, creator: str, license_name: str, provider: str = "") -> str:
    """Generates standard attribution string for presentation slides and metadata."""
    t = (title or "").strip() or "Untitled Visual"
    c = (creator or "").strip() or "Unknown Creator"
    l = (license_name or "").strip() or "Public Domain"

    if l.upper() in {"CC0", "CC0 1.0", "PUBLIC DOMAIN"}:
        return f"Image: {t} — {c} — Public Domain"

    return f"Image: {t} — {c} — {l}"
