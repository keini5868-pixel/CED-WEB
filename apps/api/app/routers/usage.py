"""Tracking de minutos Gemini Live + saldo."""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services import supabase_db
from app.services.async_sync import run_sync
from app.services.voice_usage import (
    ACCESS_DENIED_MESSAGES,
    voice_access_state_async,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/usage", tags=["usage"])

# Sesiones activas en memoria (Fase 2B — Redis en Fase 3)
_active_sessions: dict[str, dict] = {}


class SessionTickBody(BaseModel):
    session_id: str
    seconds: float = Field(gt=0, le=120)


class SessionEndBody(BaseModel):
    session_id: str = Field(alias="sessionId")

    model_config = {"populate_by_name": True}


@router.get("/balance")
async def usage_balance(user_id: str = Depends(require_user_id)) -> dict:
    state = await voice_access_state_async(user_id)
    if state.get("degraded"):
        import logging

        logging.getLogger(__name__).warning(
            "[USAGE] balance degraded user=%s reason=%s",
            user_id[:8],
            state.get("degraded_reason"),
        )
    state.pop("allowed", None)
    state.pop("quota_exhausted", None)
    return state


@router.post("/session/start")
async def session_start(user_id: str = Depends(require_user_id)) -> dict:
    balance = await voice_access_state_async(user_id)
    access_msg = balance.get("access_message") or ""
    if balance.get("access_denied"):
        detail = ACCESS_DENIED_MESSAGES.get(access_msg, access_msg or "Acceso no disponible.")
        raise HTTPException(status_code=403, detail=detail)
    if access_msg == "free_basic" and balance["plan_minutes_daily"] <= 0:
        raise HTTPException(
            status_code=402,
            detail="La voz no está incluida en el plan Básico gratis. Mejora tu plan o recarga.",
        )
    if balance["blocked"]:
        if balance.get("quota_exhausted"):
            raise HTTPException(
                status_code=402,
                detail="Has alcanzado tu límite diario de voz. Recarga desde $10 o adquiere un plan. El chat sigue disponible.",
            )
        raise HTTPException(
            status_code=402,
            detail="Tu plan no incluye minutos de voz hoy. Mejora tu plan o recarga saldo.",
        )

    session_id = str(uuid4())
    started_at = __import__("time").time()
    _active_sessions[session_id] = {
        "user_id": user_id,
        "started_at": started_at,
        "conversation_id": None,
    }

    conversation_id = None
    try:
        conv = await run_sync(supabase_db.create_conversation, user_id)
        conversation_id = conv.get("id") if conv else None
        _active_sessions[session_id]["conversation_id"] = conversation_id
        if not conversation_id:
            logger.error(
                "[USAGE] session_start sin conversation_id user=%s",
                user_id[:8],
            )
    except Exception as exc:  # noqa: BLE001
        # La voz puede seguir, pero el historial no se guardará sin cid.
        logger.exception(
            "[USAGE] create_conversation falló user=%s: %s",
            user_id[:8],
            exc,
        )
        conversation_id = None

    return {
        "session_id": session_id,
        "conversation_id": conversation_id,
        "used_minutes_today": balance["used_minutes_today"],
        "plan_minutes_daily": balance["plan_minutes_daily"],
    }


@router.post("/session/tick")
async def session_tick(
    body: SessionTickBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    meta = _active_sessions.get(body.session_id)
    # Tras un redeploy, _active_sessions (en memoria) se vacía. No cortes la voz
    # por eso: si no hay meta pero el usuario es válido, contabiliza igual el tick
    # de forma best-effort en vez de devolver 404 (que el frontend ve como error).
    if meta and meta.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    minutes = body.seconds / 60.0
    try:
        used_before = await run_sync(supabase_db.get_usage_minutes_today, user_id)
    except Exception:  # noqa: BLE001
        used_before = 0.0
    try:
        used = await run_sync(
            supabase_db.add_usage_minutes,
            user_id,
            minutes,
            session_id=body.session_id,
        )
    except Exception as exc:  # noqa: BLE001 — telemetría de uso: nunca 500
        import logging

        logging.getLogger(__name__).warning(
            "[USAGE] add_usage_minutes fallo (best-effort) session=%s: %s",
            body.session_id,
            exc,
        )
        # Respuesta segura sin más llamadas a DB: no bloquear la voz por telemetría.
        return {
            "used_minutes_today": 0,
            "plan_minutes_daily": 0,
            "blocked": False,
            "access_denied": False,
            "usage_percent": 0,
            "warning_level": None,
            "should_disconnect": False,
        }

    # Monedero: cobrar solo el tramo que supera el cupo del plan
    state_pre = await voice_access_state_async(user_id)
    plan_minutes = float(state_pre.get("plan_minutes_daily") or 0)
    overage = max(0.0, float(used) - max(float(used_before), plan_minutes))
    if overage > 0:
        from app.services.wallet import try_spend

        spend = await run_sync(
            try_spend,
            user_id,
            "voice_min",
            units=overage,
        )
        if not spend.get("ok"):
            state = await voice_access_state_async(user_id)
            return {
                "used_minutes_today": round(used, 2),
                "plan_minutes_daily": state["plan_minutes_daily"],
                "blocked": True,
                "access_denied": False,
                "needs_recharge": True,
                "usage_percent": state.get("usage_percent", 100),
                "warning_level": "blocked",
                "should_disconnect": True,
                "recharge_balance_usd": spend.get("balance_usd", 0),
            }

    state = await voice_access_state_async(user_id)
    if state.get("degraded"):
        import logging

        logging.getLogger(__name__).warning(
            "[USAGE] tick state degraded session=%s user=%s reason=%s",
            body.session_id,
            user_id[:8],
            state.get("degraded_reason"),
        )
        return {
            "used_minutes_today": round(float(state.get("used_minutes_today") or 0), 2),
            "plan_minutes_daily": int(state.get("plan_minutes_daily") or 0),
            "blocked": False,
            "access_denied": False,
            "usage_percent": 0,
            "warning_level": None,
            "should_disconnect": False,
            "degraded": True,
        }
    warning = _usage_warning(state.get("usage_percent", 0), state.get("blocked", False))
    return {
        "used_minutes_today": round(used, 2),
        "plan_minutes_daily": state["plan_minutes_daily"],
        "blocked": state["blocked"],
        "access_denied": state["access_denied"],
        "usage_percent": state["usage_percent"],
        "warning_level": warning,
        "should_disconnect": warning == "blocked" or state["blocked"],
    }


def _usage_warning(pct: float, blocked: bool) -> str | None:
    if blocked or pct >= 100:
        return "blocked"
    if pct >= 95:
        return "critical"
    if pct >= 80:
        return "warn"
    return None


@router.post("/session/end")
async def session_end(
    session_id: str | None = None,
    body: SessionEndBody | None = Body(default=None),
    user_id: str = Depends(require_user_id),
) -> dict:
    """Cierra sesión de uso. Idempotente si ya terminó o API reinició."""
    sid = (body.session_id if body else None) or session_id
    if not sid:
        raise HTTPException(status_code=400, detail="session_id requerido")

    meta = _active_sessions.pop(sid, None)
    balance = await usage_balance(user_id)
    if meta and meta.get("user_id") == user_id:
        try:
            from app.services.conversation_memory import finalize_voice_session_async

            finalize_voice_session_async(
                user_id=user_id,
                session_id=sid,
                conversation_id=meta.get("conversation_id"),
                started_at_epoch=float(meta.get("started_at") or __import__("time").time()),
            )
        except Exception:  # noqa: BLE001
            pass
    if not meta or meta.get("user_id") != user_id:
        return {**balance, "already_ended": True, "session_id": sid}
    return {**balance, "already_ended": False, "session_id": sid}
