"""Autenticación Bearer — Supabase JWT."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import Header, HTTPException

from app.config import get_settings


def is_super_admin(email: str | None, metadata_role: str | None = None) -> bool:
    if metadata_role == "super_admin":
        return True
    normalized = (email or "").strip().lower()
    if not normalized:
        return False
    settings = get_settings()
    allowed = {
        e.strip().lower()
        for e in settings.super_admin_emails.split(",")
        if e.strip()
    }
    return normalized in allowed


async def require_auth_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Token requerido")

    token = authorization.split(" ", 1)[1].strip()
    settings = get_settings()

    if settings.supabase_url and settings.supabase_service_role_key:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": settings.supabase_service_role_key,
                },
            )
        if response.status_code == 200:
            data = response.json()
            user_id = data.get("id")
            if user_id:
                app_meta = data.get("app_metadata") or {}
                return {
                    "id": str(user_id),
                    "email": data.get("email"),
                    "role": app_meta.get("role"),
                }
        raise HTTPException(status_code=401, detail="Sesión inválida")

    raise HTTPException(
        status_code=503,
        detail="Auth no configurado en API",
    )


async def require_user_id(authorization: str | None = Header(default=None)) -> str:
    user = await require_auth_user(authorization)
    return user["id"]


async def require_super_admin(
    authorization: str | None = Header(default=None),
) -> str:
    """Solo super_admin — para acciones admin sobre la propia cuenta."""
    user = await require_auth_user(authorization)
    if not is_super_admin(user.get("email"), user.get("role")):
        raise HTTPException(status_code=403, detail="Acceso solo para super admin")
    return user["id"]
