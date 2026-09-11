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
    stripe_price_cierre: str = ""
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
    # Solo modelos Realtime. Si en Railway queda un chat model (p.ej. gpt-4.1-mini),
    # openai_realtime.py lo ignora y usa gpt-realtime-mini.
    openai_model_voice: str = "gpt-realtime-mini"
    openai_model_retell_llm: str = "gpt-4.1-mini-2025-04-14"
    openai_model_image: str = "gpt-image-1.5"
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
    gemini_live_model: str = "gemini-2.5-flash-native-audio-preview-12-2025"
    gemini_voice_model: str = "gemini-2.5-flash"
    gemini_image_model: str = "gemini-3.1-flash-image"
    # Context Caching explícito (Google) para base Jarvis + ficha FitLine/PM.
    # Baja input de ~$0.30/1M a ~$0.03/1M en esos tokens. Fallback inline si falla.
    fitline_gemini_context_cache: bool = True
    fitline_gemini_context_cache_ttl_sec: int = 3600

    # Ideogram 4.0 — fallback tipográfico si GPT Image no está o falla. El motor
    # preferido para texto literal es GPT Image (OPENAI_API_KEY + openai_model_image).
    # Se activa solo con prompt_requires_precise_text (ver copy_quality + gemini_images).
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
    # WhatsApp Cloud API (Embedded Signup + webhook). El verify token se copia en Meta.
    whatsapp_verify_token: str = ""
    whatsapp_embedded_signup_config_id: str = ""
    # Precio de venta del módulo WhatsApp CED (margen sobre el canal 360dialog).
    whatsapp_addon_price_usd: float = 29.0

    super_admin_emails: str = "keini@castillodigital.com,keini5868@gmail.com"

    resend_api_key: str = ""
    email_from: str = "CED <noreply@ced-castillo.com>"

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
    # Módulos orquestador habilitados en modo standalone (csv): environment, finance
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
    # Módulo Análisis de Producto (producción). Kill-switch: VIABILITY_MODULE_ENABLED=false
    viability_module_enabled: bool = True
    # Módulo Análisis de Tendencia (producción). Kill-switch: TRENDS_MODULE_ENABLED=false
    trends_module_enabled: bool = True
    # Módulo oportunidades (producción). Kill-switch: OPPORTUNITIES_MODULE_ENABLED=false
    opportunities_module_enabled: bool = True
    # Enlace personal FitLine / paquete manager (sección Afiliación)
    opportunities_fitline_sponsor_url: str = ""
    # Live Tavily en cada apertura de ficha OPPS — OFF por defecto (cero gasto).
    # OPPORTUNITIES_LIVE_SEARCH=true solo para refrescos admin puntuales.
    opportunities_live_search: bool = False
    # Pocket Option demo (solo admin). DEFAULT OFF. Nunca en planes/landing.
    pocket_option_module_enabled: bool = False
    pocket_option_ssid: str = ""
    pocket_option_asset: str = "EURUSD_otc"
    pocket_option_amount: float = 1.0
    pocket_option_interval_seconds: int = 300
    pocket_option_expiry_seconds: int = 60
    pocket_option_strategy_bos_enabled: bool = True
    pocket_option_strategy_alt_enabled: bool = False
    # Video Edit módulo piloto — DEFAULT OFF. URL ?videoEditModule=pilot + header.
    video_edit_module_pilot: bool = False
    # Automatización embudo IG/FB→WA — DEFAULT OFF.
    # AUTOMATION_MODULE_ENABLED=true + ?automationModule=pilot
    automation_module_enabled: bool = False
    # Si OFF: IG/FB solo dry-run (log, sin envíos). ON tras Advanced Access Meta.
    automation_ig_fb_live_enabled: bool = False
    # Teléfono E.164 para wa.me en respuestas automáticas (fallback del usuario).
    automation_default_whatsapp_e164: str = ""
    # Verify token Meta webhook (Instagram/Facebook). Si vacío, usa whatsapp_verify_token.
    automation_webhook_verify_token: str = ""
    # Alias opcionales (mismo app Meta):
    instagram_app_id: str = ""
    instagram_app_secret: str = ""
    shotstack_api_key: str = ""
    shotstack_env: str = "stage"  # stage | v1
    sonilo_api_key: str = ""
    # Veo Lite — OFF por defecto incluso dentro del piloto
    video_edit_veo_enabled: bool = False
    # Stripe packs tokens video ($10/$20/$50) — opcionales; fallback price_data
    stripe_price_video_edit_10: str = ""
    stripe_price_video_edit_20: str = ""
    stripe_price_video_edit_50: str = ""


    @model_validator(mode="after")
    def resolve_sonilo_key_aliases(self) -> Settings:
        if (self.sonilo_api_key or "").strip():
            self.sonilo_api_key = self.sonilo_api_key.strip()
            return self
        for alt in ("SONILO_API_KEY", "SONILO_KEY", "SONILO_TOKEN", "SONILO_SECRET"):
            val = (os.environ.get(alt) or "").strip()
            if val:
                self.sonilo_api_key = val
                break
        return self

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
    def resolve_public_urls(self) -> Settings:
        """Railway: API_PUBLIC_URL desde RAILWAY_PUBLIC_DOMAIN."""
        railway = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
        if railway:
            railway_url = f"https://{railway.rstrip('/')}"
            api = self.api_public_url.strip().rstrip("/")
            if not api or "localhost" in api or api.startswith("http://127.0.0.1"):
                self.api_public_url = railway_url

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
        # Orígenes de deploy legítimos. Localhost solo fuera de production.
        extras = (
            "https://ced-castillo.com",
            "https://www.ced-castillo.com",
            "https://ced-web-production.up.railway.app",
            "https://cedweb-production.up.railway.app",
        )
        if not self.is_production():
            extras = extras + (
                "http://localhost:3000",
                "http://localhost:3001",
                "https://app.castillodigital.com",
            )
        for extra in extras:
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
