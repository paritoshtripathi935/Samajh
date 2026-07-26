"""Supabase client (server-side).

Uses the service-role key when set (bypasses RLS), otherwise SUPABASE_KEY
(the anon key works today because the pipeline tables have open demo policies).
"""
from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from app.core.settings import settings


@lru_cache(maxsize=1)
def supabase() -> Client:
    url = settings.supabase_url
    key = settings.supabase_service_role_key or settings.supabase_key
    if not url or not key:
        raise RuntimeError("Supabase not configured (set SUPABASE_URL and SUPABASE_KEY)")
    return create_client(url, key)
