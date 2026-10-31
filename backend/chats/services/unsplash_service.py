# Re-export from shared platform core service for backward-compatibility
from backend.api.services.unsplash_service import (
    ASSET_DIR,
    TOPIC_VISUAL_MAP,
    CURATED_UNSPLASH_CATALOG,
    clear_used_image_cache,
    safe_filename,
    expand_visual_query,
    get_curated_fallback_category,
    fetch_unsplash_photos_list,
    fetch_unsplash_image,
    fetch_unsplash_url,
)

__all__ = [
    "ASSET_DIR",
    "TOPIC_VISUAL_MAP",
    "CURATED_UNSPLASH_CATALOG",
    "clear_used_image_cache",
    "safe_filename",
    "expand_visual_query",
    "get_curated_fallback_category",
    "fetch_unsplash_photos_list",
    "fetch_unsplash_image",
    "fetch_unsplash_url",
]
