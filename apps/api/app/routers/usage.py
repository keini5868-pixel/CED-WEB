"""Tracking de minutos Gemini Live + saldo."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.domain.plans import CED_ELITE, USAGE_WARNING_PERCENT
from app.services import supabase_db
from app.services.admin_users import get_user_access

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
def usage_balance(user_id: str = Depends(require_user_id)) -> dict:
    try:
        used = supabase_db.get_usage_minutes_today(user_id)
    except RuntimeError:
        used = 0.0

    allowed, access_msg, plan_minutes = get_user_access(user_id)
    sub = supabase_db.get_subscription(user_id)
    total = plan_minutes
    pct = (used / plan_minutes * 100) if plan_minutes else 0
    blocked = (used >= plan_minutes) or not allowed

    return {
        "plan_id": (sub or {}).get("plan_id") or "elite_founding",
        "is_founding_member": bool((sub or {}).get("price_locked_for_life")),
        "price_locked_for_life": bool((sub or {}).get("price_locked_for_life")),
        "plan_minutes_daily": plan_minutes,
        "used_minutes_today": round(used, 2),
        "recharge_balance_usd": 0.0,
        "bonus_minutes_from_balance": 0,
        "total_available_minutes": total if allowed else 0,
        "warning_at_percent": USAGE_WARNING_PERCENT,
        "blocked": blocked,
        "access_denied": not allowed,
        "access_message": access_msg if not allowed else None,
        "usage_percent": round(pct, 1),
        "timezone": "America/Mexico_City",
    }


@router.post("/session/start")
def session_start(user_id: str = Depends(require_user_id)) -> dict:
    balance = usage_balance(user_id)
    if balance.get("access_denied"):
        raise HTTPException(
            status_code=403,
            detail=balance.get("access_message") or "Acceso no disponible.",
        )
    if balance["blocked"]:
        raise HTTPException(
            status_code=402,
            detail="Has alcanzado tu límite diario de voz. Recarga saldo o continúa mañana.",
        )

    session_id = str(uuid4())
    _active_sessions[session_id] = {
        "user_id": user_id,
        "started_at": __import__("time").time(),
    }

    try:
        conv = supabase_db.create_conversation(user_id)
        conversation_id = conv.get("id")
    except RuntimeError:
        conversation_id = None

    return {
        "session_id": session_id,
        "conversation_id": conversation_id,
        "used_minutes_today": balance["used_minutes_today"],
        "plan_minutes_daily": balance["plan_minutes_daily"],
    }


@router.post("/session/tick")
def session_tick(
    body: SessionTickBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    meta = _active_sessions.get(body.session_id)
    if not meta or meta.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    minutes = body.seconds / 60.0
    try:
        used = supabase_db.add_usage_minutes(
            user_id,
            minutes,
            session_id=body.session_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    plan_minutes = get_user_access(user_id)[2]
    return {
        "used_minutes_today": round(used, 2),
        "plan_minutes_daily": plan_minutes,
        "blocked": used >= plan_minutes,
        "usage_percent": round(used / plan_minutes * 100, 1) if plan_minutes else 0,
    }


@router.post("/session/end")
def session_end(
    session_id: str | None = None,
    body: SessionEndBody | None = Body(default=None),
    user_id: str = Depends(require_user_id),
) -> dict:
    """Cierra sesión de uso. Idempotente si ya terminó o API reinició."""
    sid = (body.session_id if body else None) or session_id
    if not sid:
        raise HTTPException(status_code=400, detail="session_id requerido")

    meta = _active_sessions.pop(sid, None)
    balance = usage_balance(user_id)
    if not meta or meta.get("user_id") != user_id:
        return {**balance, "already_ended": True, "session_id": sid}
    return {**balance, "already_ended": False, "session_id": sid}
