"""Configuración central — variables de entorno."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Siempre apps/api/.env (aunque uvicorn se lance desde otra carpeta)
_API_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _API_ROOT / ".env"


def _env_files() -> tuple[str, ...]:
    paths: list[Path] = []
    if _ENV_FILE.is_file():
        paths.append(_ENV_FILE)
    mono = _API_ROOT.parent.parent / ".env"
    if mono.is_file() and mono not in paths:
        paths.append(mono)
    return tuple(str(p) for p in paths)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files() or None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_public_url: str = "http://localhost:8000"
    web_public_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 120

    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_anon_key: str = ""
    supabase_jwt_secret: str = ""

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_elite_founding: str = ""
    stripe_price_elite_regular: str = ""

    redis_url: str = "redis://localhost:6379/0"

    google_api_key: str = ""
    gemini_live_model: str = "gemini-2.5-flash-native-audio-preview-12-2025"
    anthropic_api_key: str = ""
    tavily_api_key: str = ""

    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_api_version: str = "v21.0"
    meta_login_config_id: str = ""
    meta_oauth_scopes: str = ""
    youtube_api_key: str = ""

    super_admin_emails: str = "keini@castillodigital.com"

    resend_api_key: str = ""
    email_from: str = "CED <noreply@castillodigital.com>"

    founding_slots_max: int = 50

    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    @property
    def use_json_logs(self) -> bool:
        return self.is_production()

    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        web = self.web_public_url.strip().rstrip("/")
        if web and web not in origins:
            origins.append(web)
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    """Recarga .env (útil tras editar claves sin reiniciar el proceso)."""
    get_settings.cache_clear()
    return get_settings()
