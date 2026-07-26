"""Environment-driven settings. Reads backend/.env (see .env.example)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Sarvam (Document Intelligence, chat, translate)
    sarvam_api_key: str = ""

    # Legal research (mirrors MiniHarvey's search environment contract).
    indian_kanoon_api_token: str = ""
    google_api_key: str = ""
    google_search_cx: str = ""
    max_search_results: int = 10

    # Supabase. `supabase_key` is the key the client uses; prefer the
    # service-role key in prod (set supabase_service_role_key and it wins).
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_role_key: str = ""
    # Private bucket used for original filings. PDFs are served through the
    # authenticated backend endpoint rather than exposing a public bucket URL.
    supabase_documents_bucket: str = "documents"

    # CORS origin for the Next.js frontend
    frontend_origin: str = "http://localhost:3000"

    # Sarvam Document Intelligence allows limited request throughput. Keep
    # parallel batch jobs conservative; increase only after observing rate limits.
    sarvam_di_max_workers: int = 3


settings = Settings()
