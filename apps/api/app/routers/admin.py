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


class LlamaPullBody(BaseModel):
    model: str = Field(min_length=1, max_length=64)


@router.post("/llama/pull")
def admin_llama_pull_model(
    body: LlamaPullBody,
    _admin_id: str = Depends(require_super_admin),
) -> dict:
    """Descarga un modelo en el Ollama de texto (ced-llama) desde dentro de la
    red privada de Railway — útil porque no hay acceso de shell al contenedor.
    Solo admin. No cambia LLAMA_MODEL; eso sigue siendo manual en Railway."""
    import httpx

    from app.services.llama_service import _ollama_base

    base = _ollama_base()
    model = body.model.strip()
    try:
        with httpx.Client(timeout=600.0) as client:
            with client.stream(
                "POST", f"{base}/api/pull", json={"model": model, "stream": True}
            ) as resp:
                last: dict = {}
                for line in resp.iter_lines():
                    if not line:
                        continue
                    import json as _json

                    try:
                        last = _json.loads(line)
                    except _json.JSONDecodeError:
                        continue
        return {"ok": True, "model": model, "last_status": last}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "model": model, "error": str(exc)[:300]}


@router.get("/llama/models")
def admin_llama_list_models(_admin_id: str = Depends(require_super_admin)) -> dict:
    """Lista modelos descargados en ced-llama."""
    import httpx

    from app.services.llama_service import _ollama_base

    base = _ollama_base()
    try:
        with httpx.Client(timeout=15.0) as client:
            res = client.get(f"{base}/api/tags")
            res.raise_for_status()
            data = res.json()
        return {"ok": True, "models": [m.get("name") for m in data.get("models") or []]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:300]}


@router.get("/module-usage/summary")
def admin_module_usage_summary(
    _admin_id: str = Depends(require_super_admin),
    since: str | None = Query(
        default=None,
        description="ISO datetime UTC inclusive (ej. 2026-07-01T00:00:00Z)",
    ),
    until: str | None = Query(
        default=None,
        description="ISO datetime UTC exclusive",
    ),
) -> dict:
    """Resumen de metering VIABLE / Tendencias / Oportunidades."""
    from datetime import datetime

    from app.services.module_usage import summarize_module_usage

    def _parse(raw: str | None) -> datetime | None:
        if not raw or not raw.strip():
            return None
        text = raw.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Fecha inválida: {raw}",
            ) from exc

    try:
        return summarize_module_usage(since=_parse(since), until=_parse(until))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail="No se pudo leer module_usage.",
        ) from exc
