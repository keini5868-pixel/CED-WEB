"""Configuración central — variables de entorno."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from app.services.openai_key_utils import sanitize_openai_api_key
from pydantic import model_validator
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
    stripe_price_starter: str = ""
    stripe_price_pro: str = ""
    stripe_price_elite: str = ""
    stripe_price_founding: str = ""
    stripe_price_recharge_10: str = ""
    stripe_price_recharge_20: str = ""
    stripe_price_recharge_40: str = ""
    stripe_price_recharge_50: str = ""
    stripe_price_recharge_100: str = ""
    # Legacy aliases
    stripe_price_elite_founding: str = ""
    stripe_price_elite_regular: str = ""

    redis_url: str = "redis://localhost:6379/0"

    openai_api_key: str = ""
    openai_project_id: str = ""
    openai_model_chat: str = "gpt-4o"
    openai_model_chat_lite: str = "gpt-4o-mini"
    openai_model_voice: str = "gpt-realtime"
    openai_model_retell_llm: str = "gpt-4.1-mini-2025-04-14"
    openai_model_image: str = "gpt-image-1"
    openai_default_voice: str = "cedar"
    cost_tracking_enabled: bool = True
    cost_alert_threshold_usd: float = 200.0
    cost_alert_email: str = ""
    cache_enabled: bool = True
    cache_ttl_weather: int = 1800
    cache_ttl_news: int = 900
    cache_ttl_static: int = 86400

    google_api_key: str = ""
    google_maps_api_key: str = ""
    google_calendar_client_id: str = ""
    google_calendar_client_secret: str = ""
    """OAuth Google de Supabase Auth — si difiere del client de Railway, refresh dual."""
    google_supabase_oauth_client_id: str = ""
    google_supabase_oauth_client_secret: str = ""
    google_calendar_redirect_uri: str = ""
    google_gmail_redirect_uri: str = ""
    gemini_live_model: str = "gemini-2.5-flash-native-audio-preview-12-2025"
    gemini_voice_model: str = "gemini-2.5-flash"
    gemini_image_model: str = "gemini-2.5-flash-image"

    # Ideogram 4.0 — opción alternativa para imágenes con texto legible (aprobado
    # Keini 2026-07). NO reemplaza a Gemini; solo se usa cuando el pedido exige texto
    # literal explícito y el plan/monedero del usuario lo permite (ver copy_quality.
    # prompt_requires_ideogram_text y gemini_images._maybe_generate_with_ideogram).
    ideogram_api_key: str = ""
    ideogram_rendering_speed: str = "TURBO"
    ideogram_resolution: str = "2048x2048"

    # Cerebro conversacional local (Ollama/Llama) — reemplaza Gemini en chats y voz.
    # Chat Avanzado sigue usando Claude. Imágenes/visión siguen en Gemini.
    llm_provider: str = "llama"
    llama_endpoint: str = "http://localhost:11434"
    # llama3.1:8b: notablemente más rápido que llama2:13b en CPU y de generación
    # más moderna — mejor equilibrio velocidad/calidad para chat de texto.
    llama_model: str = "llama3.1:8b"
    # Modelo liviano solo para conversación de voz (Retell Custom LLM).
    llama_voice_model: str = "llama3.2:3b"
    # Ollama dedicado a voz — si vacío, voz usa llama_endpoint (transición).
    llama_voice_endpoint: str = ""

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

    # Voz — Retell AI (default) u OpenAI Realtime (legacy)
    voice_provider: str = "retell"
    retell_api_key: str = ""
    retell_agent_id: str = ""
    retell_llm_id: str = ""
    # Piloto Retell LLM nativo (staging) — agente separado, no toca RETELL_AGENT_ID prod
    retell_native_staging_agent_id: str = ""
    retell_native_staging_llm_id: str = ""
    retell_native_pilot_model: str = "gemini-3.0-flash"
    retell_voice_id: str = ""
    retell_webhook_secret: str = ""
    retell_auto_bootstrap: bool = False
    retell_bootstrap_secret: str = ""
    retell_llm_provider: str = "llama"
    # Prueba aislada de voz: gemini_standalone = Retell → Gemini directo, sin orquestador.
    # En production se IGNORA salvo voice_standalone_allow_prod=true (deja la voz sin tools).
    voice_test_mode: str = ""
    # Módulos orquestador habilitados en modo standalone (csv): environment, calendar, finance
    voice_standalone_modules: str = ""
    # Solo para staging deliberado. Si false (default), gemini_standalone no aplica en production.
    voice_standalone_allow_prod: bool = False
    elevenlabs_api_key: str = ""
    # Clon Jarvis en ElevenLabs — se registra en Retell al bootstrap si no hay RETELL_VOICE_ID
    elevenlabs_jarvis_voice_id: str = "UKhFmKblQwXqi7vvaALt"
    elevenlabs_jarvis_public_user_id: str = ""
    # Modelo TTS Retell: eleven_multilingual_v2 (más fiel al clon) o eleven_turbo_v2_5 (más rápido)
    retell_voice_model: str = ""
    retell_voice_speed: float = 0.0
    retell_voice_temperature: float = 0.0
    # Anti-eco manos libres (bocinas de carro/Bluetooth): "noise-and-background-speech-cancellation"
    # aísla al hablante principal y suprime la propia voz de CED si se filtra de vuelta al micrófono
    # (surcharge $0.005/min en Retell). "noise-cancellation" es el default de Retell (sin este filtro).
    retell_denoising_mode: str = "noise-and-background-speech-cancellation"
    # Más bajo que el default de Retell (docs recomiendan bajar esto para reducir falsas
    # interrupciones por ruido/voz de fondo — p.ej. eco de CED por bocinas del carro).
    retell_interruption_sensitivity: float = 0.7
    # Provider voice ID Cartesia (opcional — Retell usa RETELL_VOICE_ID en prod)
    cartesia_jarvis_voice_id: str = ""
    support_chat_enabled: bool = True

    @model_validator(mode="after")
    def resolve_openai_key_aliases(self) -> Settings:
        self.openai_api_key = sanitize_openai_api_key(self.openai_api_key)
        if self.openai_api_key:
            return self
        for alt in ("OPENAI_KEY", "OPENAI_SECRET", "OPENAI_SECRET_KEY"):
            val = sanitize_openai_api_key(os.environ.get(alt, ""))
            if val:
                self.openai_api_key = val
                break
        return self

    @model_validator(mode="after")
    def resolve_google_maps_key(self) -> Settings:
        if self.google_maps_api_key.strip():
            return self
        for alt in ("GOOGLE_MAPS_API_KEY",):
            val = os.environ.get(alt, "").strip()
            if val:
                self.google_maps_api_key = val
                break
        if not self.google_maps_api_key.strip() and self.google_api_key.strip():
            self.google_maps_api_key = self.google_api_key.strip()
        return self

    @model_validator(mode="after")
    def resolve_google_supabase_oauth_aliases(self) -> Settings:
        if not self.google_supabase_oauth_client_id.strip():
            for alt in ("GOOGLE_SUPABASE_OAUTH_CLIENT_ID", "SUPABASE_GOOGLE_CLIENT_ID"):
                val = os.environ.get(alt, "").strip()
                if val:
                    self.google_supabase_oauth_client_id = val
                    break
        if not self.google_supabase_oauth_client_secret.strip():
            for alt in (
                "GOOGLE_SUPABASE_OAUTH_CLIENT_SECRET",
                "SUPABASE_GOOGLE_CLIENT_SECRET",
            ):
                val = os.environ.get(alt, "").strip()
                if val:
                    self.google_supabase_oauth_client_secret = val
                    break
        return self

    @staticmethod
    def _normalize_google_oauth_redirect(uri: str, api_base: str, callback_path: str) -> str:
        """Callbacks OAuth viven en la API — corrige URIs apuntando al frontend (404)."""
        from urllib.parse import urlparse

        custom = (uri or "").strip()
        if not api_base:
            return custom
        api_host = urlparse(
            api_base if "://" in api_base else f"https://{api_base}"
        ).netloc.lower()
        if not custom:
            return f"{api_base.rstrip('/')}{callback_path}"
        parsed = urlparse(custom)
        redirect_host = parsed.netloc.lower()
        if redirect_host and api_host and redirect_host != api_host and "/auth/google/" in custom:
            return f"{api_base.rstrip('/')}{callback_path}"
        return custom

    @model_validator(mode="after")
    def resolve_public_urls(self) -> Settings:
        """Railway: API_PUBLIC_URL y redirect URIs OAuth desde RAILWAY_PUBLIC_DOMAIN."""
        railway = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
        if railway:
            railway_url = f"https://{railway.rstrip('/')}"
            api = self.api_public_url.strip().rstrip("/")
            if not api or "localhost" in api or api.startswith("http://127.0.0.1"):
                self.api_public_url = railway_url

        api_base = self.api_public_url.strip().rstrip("/")
        self.google_calendar_redirect_uri = self._normalize_google_oauth_redirect(
            self.google_calendar_redirect_uri,
            api_base,
            "/auth/google/calendar/callback",
        )
        self.google_gmail_redirect_uri = self._normalize_google_oauth_redirect(
            self.google_gmail_redirect_uri,
            api_base,
            "/auth/google/gmail/callback",
        )

        web_override = os.environ.get("CED_WEB_PUBLIC_URL", "").strip().rstrip("/")
        if web_override:
            self.web_public_url = web_override
        return self

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
        for extra in (
            "https://ced-web-production.up.railway.app",
            "https://cedweb-production.up.railway.app",
            "https://app.castillodigital.com",
            "http://localhost:3000",
            "http://localhost:3001",
        ):
            if extra not in origins:
                origins.append(extra)
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    """Recarga .env (útil tras editar claves sin reiniciar el proceso)."""
    get_settings.cache_clear()
    return get_settings()
