"""Castillo Digital API — FastAPI."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.build_info import BUILD_TIMESTAMP, BUILD_VERSION
from app.config import get_settings
from app.logging_setup import configure_logging
from app.middleware.request_logging import RequestLoggingMiddleware
from app.middleware.security import SecurityHeadersMiddleware
from app.rate_limit import limiter
from app.routers import (
    admin,
    billing,
    chat,
    cognitive,
    conversations,
    diagnostic,
    health,
    hud,
    image_with_reference,
    legal,
    media,
    memory,
    google_auth,
    advanced_chat,
    finance_chat,
    meta,
    openai,
    panels,
    pdf,
    profile,
    prospection,
    retell,
    retell_custom_llm,
    support,
    usage,
    vision,
    navigation,
    voice_client,
    viability_pilot,
    trends_pilot,
    opportunities_pilot,
)

logger = logging.getLogger("ced.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from app.config import reload_settings

    settings = reload_settings()
    configure_logging(settings)
    logger.info(
        "Google tokens: client_id=%s service_role=%s web_public=%s api_public=%s (Supabase Auth provider_token)",
        "OK" if settings.google_calendar_client_id.strip() else "MISSING",
        "OK" if settings.supabase_service_role_key.strip() else "MISSING",
        settings.web_public_url.strip() or "MISSING",
        settings.api_public_url.strip() or "MISSING",
    )
    if settings.is_production():
        logger.info(
            "CED API production build=%s ts=%s",
            BUILD_VERSION,
            BUILD_TIMESTAMP,
            extra={"web_url": settings.web_public_url, "api_url": settings.api_public_url},
        )
    if not settings.openai_api_key.strip():
        logger.warning("OPENAI_API_KEY vacía — voz Realtime no funcionará")
    elif not settings.tavily_api_key.strip():
        logger.warning("TAVILY_API_KEY vacía — búsqueda web en voz fallará")
    if settings.voice_provider == "retell":
        if not settings.retell_api_key.strip():
            logger.warning("RETELL_API_KEY vacía — voz Retell no funcionará")
        else:
            from app.services.llama_service import llama_available, llama_model, use_llama

            if use_llama():
                logger.info(
                    "LLM provider=llama model=%s endpoint=%s available=%s",
                    llama_model(),
                    settings.llama_endpoint,
                    llama_available(),
                )
            elif not settings.google_api_key.strip():
                logger.warning("GOOGLE_API_KEY vacía — cerebro Gemini voz no funcionará")
            from app.services.retell_agent_setup import bootstrap_retell_if_needed

            bootstrap_retell_if_needed()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="Castillo Digital API",
        description="CED Web — auth, voz, pagos, recargas, admin",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production() else "/docs",
        redoc_url=None if settings.is_production() else "/redoc",
        openapi_url=None if settings.is_production() else "/openapi.json",
    )

    origins = settings.cors_origin_list()
    if settings.is_production() and not origins:
        logger.warning(
            "CORS sin orígenes configurados — revisa CORS_ORIGINS y WEB_PUBLIC_URL en Railway"
        )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins if settings.is_production() else (origins or ["*"]),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Request-Id",
            "X-CED-Viability-Pilot",
            "X-CED-Trends-Pilot",
        ],
    )
    application.add_middleware(SecurityHeadersMiddleware, settings=settings)
    application.add_middleware(RequestLoggingMiddleware)

    if settings.rate_limit_enabled:
        # Sin límite global: SlowAPIMiddleware rompe el upgrade WebSocket de Retell LLM.
        limiter.default_limits = []
        application.state.limiter = limiter
        application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    application.include_router(health.router)
    application.include_router(legal.router)
    application.include_router(diagnostic.router)
    application.include_router(admin.router)
    application.include_router(hud.router)
    application.include_router(panels.router)
    application.include_router(meta.router)
    application.include_router(google_auth.router)
    application.include_router(google_auth.callback_router)
    application.include_router(media.router)
    application.include_router(retell.router)
    application.include_router(retell_custom_llm.router)
    application.include_router(openai.router)
    application.include_router(image_with_reference.router)
    application.include_router(memory.router)
    application.include_router(profile.router)
    application.include_router(prospection.router)
    application.include_router(vision.router)
    application.include_router(conversations.router)
    application.include_router(billing.router)
    application.include_router(chat.router)
    application.include_router(advanced_chat.router)
    application.include_router(finance_chat.router)
    application.include_router(pdf.router)
    application.include_router(cognitive.router)
    application.include_router(usage.router)
    application.include_router(navigation.router)
    application.include_router(voice_client.router)
    application.include_router(viability_pilot.router)
    application.include_router(trends_pilot.router)
    application.include_router(opportunities_pilot.router)
    if settings.support_chat_enabled:
        application.include_router(support.router)

    @application.exception_handler(Exception)
    async def unhandled_exception(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Error interno del servidor"},
        )

    return application


app = create_app()
