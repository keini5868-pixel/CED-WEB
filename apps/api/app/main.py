"""Castillo Digital API — FastAPI."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import get_settings
from app.logging_setup import configure_logging
from app.middleware.request_logging import RequestLoggingMiddleware
from app.middleware.security import SecurityHeadersMiddleware
from app.rate_limit import limiter
from app.routers import admin, billing, chat, conversations, gemini, health, hud, memory, meta, panels, prospection, usage, vision

logger = logging.getLogger("ced.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from app.config import reload_settings

    settings = reload_settings()
    configure_logging(settings)
    if settings.is_production():
        logger.info(
            "CED API production",
            extra={"web_url": settings.web_public_url, "api_url": settings.api_public_url},
        )
    elif not settings.google_api_key.strip():
        logger.warning("GOOGLE_API_KEY vacía — revisa apps/api/.env")
    elif not settings.tavily_api_key.strip():
        logger.warning("TAVILY_API_KEY vacía — búsqueda web en voz fallará")
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
        raise RuntimeError("CORS_ORIGINS o WEB_PUBLIC_URL requeridos en producción")

    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins if settings.is_production() else (origins or ["*"]),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
    )
    application.add_middleware(SecurityHeadersMiddleware, settings=settings)
    application.add_middleware(RequestLoggingMiddleware)

    if settings.rate_limit_enabled:
        limiter.default_limits = [f"{settings.rate_limit_per_minute}/minute"]
        application.state.limiter = limiter
        application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        application.add_middleware(SlowAPIMiddleware)

    application.include_router(health.router)
    application.include_router(admin.router)
    application.include_router(hud.router)
    application.include_router(panels.router)
    application.include_router(meta.router)
    application.include_router(gemini.router)
    application.include_router(memory.router)
    application.include_router(prospection.router)
    application.include_router(vision.router)
    application.include_router(conversations.router)
    application.include_router(billing.router)
    application.include_router(chat.router)
    application.include_router(usage.router)

    @application.exception_handler(Exception)
    async def unhandled_exception(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Error interno del servidor"},
        )

    return application


app = create_app()
