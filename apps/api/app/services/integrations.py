"""Comprobaciones de conectividad Supabase y Stripe (Fase 1)."""

from __future__ import annotations

from typing import Any

import httpx
import stripe
from supabase import create_client

from app.config import get_settings
from app.services.openai_realtime import create_realtime_session


def check_openai() -> dict[str, Any]:
    settings = get_settings()
    if not settings.openai_api_key.strip():
        return {
            "ok": False,
            "error": "missing_openai_api_key",
            "hint": "Añade OPENAI_API_KEY en Railway (servicio CED-WEB).",
        }
    result = create_realtime_session(user_id="health-check", voice_name=None)
    if not result.get("ok"):
        return {
            "ok": False,
            "error": result.get("error", "session_failed"),
            "model": settings.openai_model_voice,
        }
    return {
        "ok": True,
        "model": result.get("model"),
        "realtime_session": True,
    }


# Ping barato y sin "thinking": el modelo de voz (p.ej. 2.5-pro) con
# max_output_tokens=8 se come el presupuesto en thought tokens y el HUD
# marca ALERTA aunque la clave y Gemini estén bien.
_GEMINI_HEALTH_MODEL = "gemini-2.5-flash"


def _gemini_response_text(response: Any) -> str:
    text = (getattr(response, "text", None) or "").strip()
    if text:
        return text
    for cand in getattr(response, "candidates", None) or []:
        content = getattr(cand, "content", None)
        parts = getattr(content, "parts", None) or []
        bits: list[str] = []
        for part in parts:
            piece = getattr(part, "text", None)
            if piece:
                bits.append(str(piece))
        joined = "".join(bits).strip()
        if joined:
            return joined
    return ""


def check_google() -> dict[str, Any]:
    """Comprueba GOOGLE_API_KEY (Gemini) — chat de texto y voz."""
    settings = get_settings()
    api_key = settings.google_api_key.strip()
    if not api_key:
        return {
            "ok": False,
            "error": "missing_google_api_key",
            "hint": "Añade GOOGLE_API_KEY en Railway (servicio CED-WEB).",
        }
    model = _GEMINI_HEALTH_MODEL
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=[types.Part(text="Reply with the word ok.")])],
            config=types.GenerateContentConfig(
                max_output_tokens=32,
                temperature=0,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        text = _gemini_response_text(response)
        if text:
            return {"ok": True, "model": model, "provider": "google_gemini"}
        # La API aceptó la clave y devolvió candidatos: no es un outage.
        candidates = list(getattr(response, "candidates", None) or [])
        if candidates:
            return {
                "ok": True,
                "model": model,
                "provider": "google_gemini",
                "note": "empty_text_but_candidates",
            }
        return {"ok": False, "error": "empty_response", "model": model}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200], "model": model}


def check_gemini() -> dict[str, Any]:
    return check_google()


def check_tavily() -> dict[str, Any]:
    """Comprueba TAVILY_API_KEY — búsqueda web en chat, voz y HUD."""
    settings = get_settings()
    api_key = settings.tavily_api_key.strip()
    if not api_key:
        return {
            "ok": False,
            "error": "missing_tavily_api_key",
            "hint": "Añade TAVILY_API_KEY en Railway (servicio CED-WEB).",
        }
    try:
        with httpx.Client(timeout=8.0) as client:
            res = client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": "health check ping",
                    "max_results": 1,
                    "search_depth": "basic",
                },
            )
        if res.status_code == 200:
            data = res.json()
            return {
                "ok": True,
                "response_time": data.get("response_time"),
            }
        if res.status_code == 429:
            return {
                "ok": False,
                "error": "rate_limited",
                "detail": res.text[:200],
            }
        if res.status_code == 401:
            return {
                "ok": False,
                "error": "invalid_api_key",
                "detail": res.text[:200],
            }
        return {
            "ok": False,
            "error": f"tavily_http_{res.status_code}",
            "detail": res.text[:200],
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}


def check_anthropic() -> dict[str, Any]:
    from app.services.text_chat import CHAT_MODEL

    settings = get_settings()
    api_key = settings.anthropic_api_key.strip()
    if not api_key:
        google_key = settings.google_api_key.strip()
        if google_key:
            return {
                "ok": True,
                "model": settings.gemini_voice_model.strip() or "gemini-2.5-pro",
                "provider": "gemini_fallback",
                "hint": "Chat usa Gemini (GOOGLE_API_KEY) — Anthropic no configurada.",
            }
        return {
            "ok": False,
            "error": "missing_anthropic_api_key",
            "hint": "Añade ANTHROPIC_API_KEY o GOOGLE_API_KEY en Railway (CED-WEB).",
        }
    try:
        with httpx.Client(timeout=15.0) as client:
            res = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": CHAT_MODEL,
                    "max_tokens": 8,
                    "messages": [{"role": "user", "content": "ping"}],
                },
            )
        if res.status_code == 200:
            return {"ok": True, "model": CHAT_MODEL}
        return {
            "ok": False,
            "error": f"anthropic_http_{res.status_code}",
            "detail": res.text[:200],
            "model": CHAT_MODEL,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200], "model": CHAT_MODEL}


def check_supabase() -> dict[str, Any]:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return {"ok": False, "error": "missing_credentials"}

    try:
        client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
        result = (
            client.table("founding_registry")
            .select("slots_used, slots_max")
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return {
                "ok": False,
                "error": "founding_registry_empty",
                "hint": "Ejecuta 001_initial_schema.sql en Supabase SQL Editor",
            }
        return {"ok": True, "founding_registry": rows[0]}
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "founding_registry" in msg or "PGRST205" in msg or "42P01" in msg:
            return {
                "ok": False,
                "error": "schema_not_migrated",
                "hint": "Ejecuta apps/api/migrations/001_initial_schema.sql",
            }
        return {"ok": False, "error": msg[:200]}


def _stripe_key_mode(secret_key: str) -> str:
    key = (secret_key or "").strip()
    if key.startswith("sk_live_"):
        return "live"
    if key.startswith("sk_test_"):
        return "test"
    if key.startswith("rk_live_"):
        return "live"
    if key.startswith("rk_test_"):
        return "test"
    return "unknown"


def check_stripe() -> dict[str, Any]:
    settings = get_settings()
    if not settings.stripe_secret_key:
        return {"ok": False, "error": "missing_stripe_secret_key"}

    key_mode = _stripe_key_mode(settings.stripe_secret_key)
    try:
        stripe.api_key = settings.stripe_secret_key
        account = stripe.Account.retrieve()
        # Account.retrieve() no trae livemode; la clave sk_live_ define cobros reales.
        livemode = key_mode == "live"
        return {
            "ok": True,
            "account_id": getattr(account, "id", None),
            "livemode": livemode,
            "key_mode": key_mode,
            "charges_real_money": livemode,
        }
    except stripe.error.AuthenticationError:
        return {"ok": False, "error": "invalid_stripe_secret_key", "key_mode": key_mode}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200], "key_mode": key_mode}


def check_supabase_auth() -> dict[str, Any]:
    """Health del proyecto vía REST (anon no requerido)."""
    settings = get_settings()
    if not settings.supabase_url:
        return {"ok": False, "error": "missing_url"}

    try:
        url = f"{settings.supabase_url.rstrip('/')}/auth/v1/health"
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url)
        return {"ok": response.status_code < 500, "status_code": response.status_code}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}


def check_supabase_auth_api_key() -> dict[str, Any]:
    """Comprueba que al menos una API key (service role o anon) es válida."""
    settings = get_settings()
    url = settings.supabase_url.strip().rstrip("/")
    if not url:
        return {"ok": False, "error": "missing_url", "project_ref": None}

    project_ref = url.replace("https://", "").split(".")[0]
    keys = {
        "service_role": settings.supabase_service_role_key.strip(),
        "anon": settings.supabase_anon_key.strip(),
    }

    results: dict[str, bool] = {}
    try:
        with httpx.Client(timeout=10.0) as client:
            for name, api_key in keys.items():
                if not api_key:
                    results[name] = False
                    continue
                response = client.get(
                    f"{url}/auth/v1/user",
                    headers={
                        "apikey": api_key,
                        "Authorization": "Bearer invalid.test-token",
                    },
                )
                body = response.text
                results[name] = response.status_code == 403 and "bad_jwt" in body

        any_ok = any(results.values())
        if any_ok:
            return {
                "ok": True,
                "project_ref": project_ref,
                "keys_valid": results,
            }
        if not any(keys.values()):
            return {
                "ok": False,
                "error": "missing_api_key",
                "project_ref": project_ref,
                "keys_valid": results,
            }
        return {
            "ok": False,
            "error": "invalid_api_key",
            "project_ref": project_ref,
            "keys_valid": results,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200], "project_ref": project_ref}
