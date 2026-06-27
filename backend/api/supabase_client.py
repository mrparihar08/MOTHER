import os
from typing import Optional

from supabase import Client, create_client

_supabase_client: Optional[Client] = None


def get_supabase_client() -> Client:
    global _supabase_client

    if _supabase_client is not None:
        return _supabase_client

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if not url:
        raise ValueError("SUPABASE_URL is not set in environment variables")

    if not key:
        raise ValueError("SUPABASE_KEY is not set in environment variables")

    _supabase_client = create_client(url, key)
    return _supabase_client