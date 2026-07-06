"""Acciones admin — super_admin."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field

from app.deps.auth import require_super_admin
from app.domain.plans import PlanId, plan_minutes_daily
from app.services import supabase_db
from app.services.admin_users import AdminUserError, create_manual_user, list_admin_users
from app.services.voice_usage import voice_access_state

router = APIRouter(prefix="/v1/admin", tags=["admin"])


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


class CreateUserBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=32)
    access_type: Literal["paid", "beta", "founding_gift", "coadmin"] = "beta"
    plan: Literal["starter", "pro", "elite", "founding", "elite_founding", "elite_regular"] = "elite"
    duration_days: int | Literal["indefinite"] = 30
    minutes_daily: int = Field(default=120, ge=0, le=9999)
    initial_balance: float = Field(default=0, ge=0, le=10000)
    password: str = Field(min_length=8, max_length=128)
    send_welcome_email: bool = True
    force_password_change: bool = True
    notify_on_first_login: bool = False
    admin_notes: str | None = Field(default=None, max_length=2000)


@router.post("/usage/reset-my-daily")
def reset_my_daily_usage(user_id: str = Depends(require_super_admin)) -> dict:
    """Renueva el cupo diario de voz del admin autenticado (solo para ti)."""
    try:
        reset_minutes = supabase_db.reset_usage_minutes_today(user_id)
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}

    state = voice_access_state(user_id)
    return {
        "ok": True,
        "reset_minutes": round(reset_minutes, 2),
        "used_minutes_today": state["used_minutes_today"],
        "plan_minutes_daily": state["plan_minutes_daily"],
        "blocked": state["blocked"],
        "access_denied": state["access_denied"],
        "access_message": state.get("access_message"),
        "usage_percent": state["usage_percent"],
    }


@router.get("/users")
def admin_list_users(
    search: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=50),
    _admin_id: str = Depends(require_super_admin),
) -> dict:
    try:
        return list_admin_users(search=search, limit=limit)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/users/create")
def admin_create_user(
    body: CreateUserBody,
    request: Request,
    admin_id: str = Depends(require_super_admin),
) -> dict:
    try:
        return create_manual_user(
            admin_id=admin_id,
            name=body.name,
            email=str(body.email),
            phone=body.phone,
            access_type=body.access_type,
            plan=body.plan,
            duration_days=body.duration_days,
            minutes_daily=body.minutes_daily,
            initial_balance=body.initial_balance,
            password=body.password,
            send_welcome_email_flag=body.send_welcome_email,
            force_password_change=body.force_password_change,
            admin_notes=body.admin_notes,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except AdminUserError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/users/defaults")
def admin_user_defaults(_admin_id: str = Depends(require_super_admin)) -> dict:
    return {
        "default_minutes_daily": plan_minutes_daily(PlanId.ELITE.value),
        "duration_options": [7, 14, 30, 60, 90, 365, "indefinite"],
        "max_creations_per_day": 10,
    }
