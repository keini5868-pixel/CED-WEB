"""Autenticación Bearer — Supabase JWT."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import Header, HTTPException
from jose import JWTError, jwt

from app.config import get_settings
from app.services.async_sync import run_sync
from app.services.user_id_utils import normalize_user_id


def _user_from_jwt_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    user_id = payload.get("sub")
    if not user_id:
        return None
    app_meta = payload.get("app_metadata") or {}
    email = payload.get("email")
    if not email:
        user_meta = payload.get("user_metadata") or {}
        email = user_meta.get("email")
    return {
        "id": str(user_id),
        "email": email,
        "role": app_meta.get("role"),
    }


def _verify_jwt_locally(token: str, jwt_secret: str) -> dict[str, Any] | None:
    secret = jwt_secret.strip()
    if not secret:
        return None
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except JWTError:
        return None
    return _user_from_jwt_payload(payload)


async def _verify_jwt_with_supabase(token: str) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.supabase_url:
        return None

    user = await run_sync(_verify_jwt_with_supabase_sdk, token)
    if user:
        return user

    api_keys = [
        settings.supabase_service_role_key.strip(),
        settings.supabase_anon_key.strip(),
    ]
    seen: set[str] = set()
    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/user"

    async with httpx.AsyncClient(timeout=10.0) as client:
        for api_key in api_keys:
            if not api_key or api_key in seen:
                continue
            seen.add(api_key)
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": api_key,
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
    return None


def _verify_jwt_with_supabase_sdk(token: str) -> dict[str, Any] | None:
    settings = get_settings()
    url = settings.supabase_url.strip()
    if not url:
        return None

    api_keys = [
        settings.supabase_service_role_key.strip(),
        settings.supabase_anon_key.strip(),
    ]
    seen: set[str] = set()
    for api_key in api_keys:
        if not api_key or api_key in seen:
            continue
        seen.add(api_key)
        try:
            from supabase import create_client

            client = create_client(url, api_key)
            result = client.auth.get_user(token)
            user = result.user if result else None
            if not user or not user.id:
                continue
            app_meta = user.app_metadata or {}
            return {
                "id": str(user.id),
                "email": user.email,
                "role": app_meta.get("role"),
            }
        except Exception:  # noqa: BLE001
            continue
    return None


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

    if not settings.supabase_url:
        raise HTTPException(
            status_code=503,
            detail="Auth no configurado en API",
        )

    user = _verify_jwt_locally(token, settings.supabase_jwt_secret)
    if user is None:
        user = await _verify_jwt_with_supabase(token)
    if user:
        return user

    if not settings.supabase_service_role_key.strip() and not settings.supabase_jwt_secret.strip():
        raise HTTPException(
            status_code=503,
            detail="Auth no configurado en API (falta SUPABASE_JWT_SECRET o SERVICE_ROLE)",
        )

    raise HTTPException(
        status_code=401,
        detail="Sesión inválida o expirada. Vuelve a iniciar sesión.",
    )


async def require_user_id(authorization: str | None = Header(default=None)) -> str:
    user = await require_auth_user(authorization)
    return normalize_user_id(user["id"])


async def require_super_admin(
    authorization: str | None = Header(default=None),
) -> str:
    """Solo super_admin — para acciones admin sobre la propia cuenta."""
    user = await require_auth_user(authorization)
    if not is_super_admin(user.get("email"), user.get("role")):
        raise HTTPException(status_code=403, detail="Acceso solo para super admin")
    return user["id"]
