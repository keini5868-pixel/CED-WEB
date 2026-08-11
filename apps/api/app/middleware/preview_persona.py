"""ASGI middleware — propaga X-CED-Preview-As al ContextVar de request."""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

from app.services.preview_persona import HEADER_NAME, bind_preview_as, reset_preview_as


class PreviewPersonaMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        raw = b""
        for k, v in scope.get("headers") or []:
            if k.decode("latin-1").lower() == HEADER_NAME:
                raw = v
                break
        token = bind_preview_as(raw.decode("latin-1", errors="ignore"))
        try:
            await self.app(scope, receive, send)
        finally:
            reset_preview_as(token)
