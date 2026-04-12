# services/api/core/config.py
# ─────────────────────────────────────────────────────────
# Centralised settings via pydantic-settings.
# Reads from environment variables / .env.local.
# ─────────────────────────────────────────────────────────

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings — loaded once at startup."""

    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Supabase ──────────────────────────────────────────
    NEXT_PUBLIC_SUPABASE_URL: str
    NEXT_PUBLIC_SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str

    # ── Direct Postgres (for psycopg2 / workers) ─────────
    # From `supabase status` → DB URL field
    DB_URL: str = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"

    # ── AI APIs ───────────────────────────────────────────
    OPENAI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    USE_OLLAMA: bool = False

    # ── Compliance APIs ───────────────────────────────────
    CLIMATIQ_API_KEY: str = ""
    MINDEE_API_KEY: str = ""

    # ── App ───────────────────────────────────────────────
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — import and call this everywhere."""
    return Settings()
