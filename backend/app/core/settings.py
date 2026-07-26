"""Environment-driven settings. Reads backend/.env (see .env.example)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Sarvam (Document Intelligence, chat, translate)
    sarvam_api_key: str = ""

    # Supabase (service role — server only)
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # CORS origin for the Next.js frontend
    frontend_origin: str = "http://localhost:3000"


settings = Settings()
