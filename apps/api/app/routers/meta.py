"""Meta / Instagram OAuth — conexión para carrusel HUD."""

from __future__ import annotations

import logging
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.config import get_settings
from app.deps.auth import require_user_id
from app.deps.plan_access import require_meta_social
from pydantic import BaseModel, Field

from app.services import supabase_db
from app.services.meta_social import MetaSocialError, publish_facebook, publish_instagram
from app.services.social_comments import fetch_social_comments

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/meta", tags=["meta"])

# Permisos mínimos para publicar (FB Page + IG Business). Re-conectar Meta tras cambiar scopes.
DEFAULT_META_OAUTH_SCOPES = (
    "public_profile,"
    "pages_show_list,"
    "pages_read_engagement,"
    "pages_read_user_content,"
    "pages_manage_engagement,"
    "pages_manage_posts,"
    "business_management,"
    "instagram_basic,"
    "instagram_content_publish,"
    "instagram_manage_comments"
)


def _oauth_dialog_params(settings) -> dict[str, str]:
    """Facebook Login for Business (config_id) o scope clásico — igual que CED PC."""
    redirect = f"{settings.api_public_url.rstrip('/')}/v1/meta/oauth/callback"
    config_id = settings.meta_login_config_id.strip()
    if config_id:
        return {
            "client_id": settings.meta_app_id.strip(),
            "redirect_uri": redirect,
            "config_id": config_id,
            "response_type": "code",
        }
    scopes = settings.meta_oauth_scopes.strip() or DEFAULT_META_OAUTH_SCOPES
    return {
        "client_id": settings.meta_app_id.strip(),
        "redirect_uri": redirect,
        "scope": scopes,
        "response_type": "code",
    }


@router.get("/oauth/url")
def meta_oauth_url(user_id: str = Depends(require_user_id)) -> dict:
    settings = get_settings()
    app_id = settings.meta_app_id.strip()
    if not app_id:
        raise HTTPException(
            status_code=503,
            detail="META_APP_ID no configurado en apps/api/.env",
        )
    api_version = settings.meta_api_version.strip() or "v21.0"
    params = _oauth_dialog_params(settings)
    params["state"] = user_id
    redirect = params["redirect_uri"]
    mode = "config_id" if "config_id" in params else "scope"
    scope_hint = params.get("config_id") or params.get("scope", "")
    logger.info("[META:OAUTH] url mode=%s %s", mode, str(scope_hint)[:120])
    return {
        "url": f"https://www.facebook.com/{api_version}/dialog/oauth?{urlencode(params)}",
        "redirect_uri": redirect,
    }


@router.get("/oauth/callback")
def meta_oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    settings = get_settings()
    web = settings.web_public_url.rstrip("/")
    api_version = settings.meta_api_version.strip() or "v21.0"

    if error or not code or not state:
        logger.warning("[META:OAUTH] callback error=%s", error)
        return RedirectResponse(f"{web}/dashboard?meta=error")

    app_id = settings.meta_app_id.strip()
    app_secret = settings.meta_app_secret.strip()
    if not app_id or not app_secret:
        return RedirectResponse(f"{web}/dashboard?meta=missing_config")

    redirect = f"{settings.api_public_url.rstrip('/')}/v1/meta/oauth/callback"
    user_id = state

    try:
        with httpx.Client(timeout=15.0) as client:
            token_res = client.get(
                f"https://graph.facebook.com/{api_version}/oauth/access_token",
                params={
                    "client_id": app_id,
                    "client_secret": app_secret,
                    "redirect_uri": redirect,
                    "code": code,
                },
            )
            token_data = token_res.json()
            access_token = token_data.get("access_token")
            if not access_token:
                logger.error("[META:OAUTH] token response %s", token_data)
                return RedirectResponse(f"{web}/dashboard?meta=token_failed")

            pages = client.get(
                f"https://graph.facebook.com/{api_version}/me/accounts",
                params={"access_token": access_token},
            ).json()
            page = (pages.get("data") or [{}])[0]
            page_token = page.get("access_token") or access_token
            page_id = page.get("id")

            ig_res = client.get(
                f"https://graph.facebook.com/{api_version}/{page_id}",
                params={
                    "fields": "instagram_business_account",
                    "access_token": page_token,
                },
            ).json()
            ig = (ig_res.get("instagram_business_account") or {}).get("id")
            if not ig:
                return RedirectResponse(f"{web}/dashboard?meta=no_ig")

            ig_profile = client.get(
                f"https://graph.facebook.com/{api_version}/{ig}",
                params={
                    "fields": "username,followers_count,media_count",
                    "access_token": page_token,
                },
            ).json()

        supabase_db.upsert_meta_connection(
            user_id,
            {
                "ig_user_id": ig,
                "ig_username": ig_profile.get("username"),
                "page_id": page_id,
                "access_token": page_token,
                "followers_count": ig_profile.get("followers_count"),
                "media_count": ig_profile.get("media_count"),
            },
        )
        return RedirectResponse(f"{web}/dashboard?meta=connected")
    except Exception as exc:  # noqa: BLE001
        logger.error("[META:OAUTH] %s", exc)
        return RedirectResponse(f"{web}/dashboard?meta=error")


class FacebookPublishBody(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    image_url: str | None = None
    image_data: str | None = Field(default=None, alias="imageData")

    model_config = {"populate_by_name": True}


class InstagramPublishBody(BaseModel):
    caption: str = Field(min_length=1, max_length=2200)
    image_url: str | None = None
    image_data: str | None = Field(default=None, alias="imageData")

    model_config = {"populate_by_name": True}


@router.post("/publish/facebook")
def meta_publish_facebook(
    body: FacebookPublishBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    require_meta_social(user_id)
    try:
        return publish_facebook(
            user_id,
            body.message,
            image_url=body.image_url,
            image_data=body.image_data,
        )
    except MetaSocialError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/publish/instagram")
def meta_publish_instagram(
    body: InstagramPublishBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    require_meta_social(user_id)
    try:
        return publish_instagram(
            user_id,
            body.caption,
            image_url=body.image_url,
            image_data=body.image_data,
        )
    except MetaSocialError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/comments")
def meta_read_comments(
    user_id: str = Depends(require_user_id),
    platform: str = Query(default="both"),
) -> dict:
    """Comentarios recientes de Facebook e Instagram para voz CED."""
    require_meta_social(user_id)
    return fetch_social_comments(user_id, platform=platform)


@router.get("/status")
def meta_status(user_id: str = Depends(require_user_id)) -> dict:
    conn = supabase_db.get_meta_connection(user_id)
    if not conn:
        return {"connected": False}
    return {
        "connected": bool(conn.get("access_token")),
        "username": conn.get("ig_username"),
        "followers_count": conn.get("followers_count"),
        "publish_hint": (
            "Si publicar falla, reconecta Meta en Conectar Redes "
            "(permisos pages_manage_posts e instagram_content_publish)."
        ),
    }
