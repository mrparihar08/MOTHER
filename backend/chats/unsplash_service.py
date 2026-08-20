import logging
import os
import re
import urllib.parse
from pathlib import Path
from typing import Optional
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

ASSET_DIR = Path(os.getenv("PPT_ASSET_DIR", "./assets")).resolve()
ASSET_DIR.mkdir(parents=True, exist_ok=True)


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", (name or "").strip())[:80].strip("_")
    return cleaned or "image"


def fetch_unsplash_image(query: str) -> Optional[str]:
    """Fetch a high-quality landscape image from Unsplash API for a given search query.

    Saves the fetched image into ASSET_DIR and returns the local file path.
    """
    load_dotenv()
    query = (query or "").strip()
    if not query:
        return None

    safe_name = safe_filename(query)
    target_file = ASSET_DIR / f"unsplash_{safe_name}.jpg"
    if target_file.exists():
        return str(target_file)

    unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY")
    image_url = None

    if unsplash_key:
        try:
            url = f"https://api.unsplash.com/search/photos?query={urllib.parse.quote(query)}&per_page=1&orientation=landscape"
            headers = {"Authorization": f"Client-ID {unsplash_key}"}
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results and results[0].get("urls"):
                    image_url = results[0]["urls"].get("regular") or results[0]["urls"].get("small")
        except Exception as exc:
            logger.warning("Unsplash API request failed: %s", exc)

    if not image_url:
        image_url = f"https://picsum.photos/seed/{urllib.parse.quote(safe_name)}/800/450"

    try:
        img_resp = requests.get(image_url, timeout=8)
        if img_resp.status_code == 200 and len(img_resp.content) > 1000:
            target_file.write_bytes(img_resp.content)
            return str(target_file)
    except Exception as exc:
        logger.warning("Failed to download image from %s: %s", image_url, exc)

    return None
