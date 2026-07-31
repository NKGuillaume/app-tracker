from functools import lru_cache

from supabase import Client, create_client

from app.config import settings


@lru_cache
def get_db() -> Client:
    """Service-role Supabase client. Backend-only — bypasses RLS, never expose this key."""
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
