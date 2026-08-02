"""Orquestación Video Edit piloto — tokens + Shotstack live / dry-run."""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from app.config import get_settings
from app.domain.video_edit_economy import (
    VIDEO_EDIT_SOFT_CAP_RENDERS_PER_DAY,
    quote_render,
    tokens_for_duration_seconds,
    video_edit_pack_catalog,
)
from app.services.video_edit_pilot.shotstack import (
    render_video_from_bytes,
    shotstack_configured,
)
from app.services.video_edit_pilot.timeline import build_edit_timeline
from app.services.video_edit_pilot.tokens import (
    credit_tokens,
    debit_tokens,
    get_token_balance,
    record_render_attempt,
    renders_today,
    soft_cap_remaining,
)

logger = logging.getLogger(__name__)


def pilot_status() -> dict[str, Any]:
    settings = get_settings()
    shotstack = shotstack_configured()
    sonilo = bool(getattr(settings, "sonilo_api_key", "") or "")
    veo = bool(getattr(settings, "video_edit_veo_enabled", False))
    return {
        "ok": True,
        "pilot": True,
        "enabled": True,
        "providers": {
            "shotstack_configured": shotstack,
            "sonilo_configured": sonilo,
            "veo_enabled": veo,
            "shotstack_env": (getattr(settings, "shotstack_env", None) or "stage"),
        },
        "economy": {
            "tokens_per_usd": 100,
            "tokens_per_second": 1,
            "min_billable_seconds": 30,
            "soft_cap_renders_per_day": VIDEO_EDIT_SOFT_CAP_RENDERS_PER_DAY,
            "packs": video_edit_pack_catalog(),
        },
        "mode": "live_ready" if shotstack else "dry_run",
    }


def get_balance_payload(user_id: str) -> dict[str, Any]:
    bal = get_token_balance(user_id)
    used = renders_today(user_id)
    return {
        "ok": True,
        "balance_tokens": bal,
        "balance_seconds": bal,
        "renders_today": used,
        "soft_cap_per_day": VIDEO_EDIT_SOFT_CAP_RENDERS_PER_DAY,
        "soft_cap_remaining": soft_cap_remaining(user_id),
        "packs": video_edit_pack_catalog(),
    }


def quote_job(duration_sec: float) -> dict[str, Any]:
    q = quote_render(duration_sec)
    return {"ok": True, **q}


def plan_and_render(
    user_id: str,
    *,
    duration_sec: float,
    script: str,
    source_asset: str = "upload://pending",
    auto_transcribe: bool = False,
    video_bytes: bytes | None = None,
    video_filename: str = "source.mp4",
    video_content_type: str = "video/mp4",
) -> dict[str, Any]:
    """
    Flujo piloto:
    1) Soft cap diario
    2) Quote + debit tokens
    3) Timeline (cortes / fades / cues Sonilo planificados)
    4) Si hay SHOTSTACK_API_KEY + video_bytes → render live
       Si no → dry_run (timeline) sin reembolso (ya cobrado en dry-run previo)
    """
    duration_sec = max(0.1, float(duration_sec))
    script = (script or "").strip()

    if renders_today(user_id) >= VIDEO_EDIT_SOFT_CAP_RENDERS_PER_DAY:
        return {
            "ok": False,
            "code": "daily_soft_cap",
            "error": (
                f"Límite de {VIDEO_EDIT_SOFT_CAP_RENDERS_PER_DAY} renders/día alcanzado. "
                "Vuelva mañana o contacte soporte si necesita más."
            ),
            "balance_tokens": get_token_balance(user_id),
            "soft_cap_remaining": 0,
        }

    if not script and not auto_transcribe:
        return {
            "ok": False,
            "code": "script_required",
            "error": "Pegue el guion o active transcripción automática (próximamente).",
        }

    if not script and auto_transcribe:
        script = (
            "[Transcripción automática pendiente — use guion manual en v1 piloto]"
        )

    tokens = tokens_for_duration_seconds(duration_sec)
    quote = quote_render(duration_sec)
    bal = get_token_balance(user_id)
    if bal < tokens:
        return {
            "ok": False,
            "code": "insufficient_tokens",
            "error": (
                f"Necesita {tokens} tokens (~{tokens}s) y tiene {bal}. "
                "Compre un pack de video ($10 / $20 / $50)."
            ),
            "quote": quote,
            "balance_tokens": bal,
            "packs": video_edit_pack_catalog(),
        }

    job_id = str(uuid4())
    settings = get_settings()
    veo_enabled = bool(getattr(settings, "video_edit_veo_enabled", False))
    timeline = build_edit_timeline(
        duration_sec=duration_sec,
        script=script,
        source_asset=source_asset,
        veo_enabled=veo_enabled,
    )

    debit = debit_tokens(
        user_id,
        tokens,
        reason="render",
        duration_sec=int(round(duration_sec)),
        job_id=job_id,
        metadata={"quote": quote},
    )
    if not debit.get("ok"):
        return {
            "ok": False,
            "code": debit.get("code") or "debit_failed",
            "error": debit.get("error") or "No se pudo descontar tokens.",
            "balance_tokens": debit.get("balance_tokens", bal),
            "quote": quote,
        }

    record_render_attempt(user_id)
    result_url: str | None = None
    error: str | None = None
    status = "dry_run"
    render_meta: dict[str, Any] = {}

    can_live = shotstack_configured() and bool(video_bytes)
    if can_live:
        try:
            live = render_video_from_bytes(
                video_bytes or b"",
                filename=video_filename or "source.mp4",
                content_type=video_content_type or "video/mp4",
                timeline=timeline,
                duration_sec=duration_sec,
            )
            result_url = str(live.get("result_url") or "")
            status = "done"
            render_meta = {
                "render_id": live.get("render_id"),
                "source_id": live.get("source_id"),
                "edit": live.get("edit"),
            }
            timeline = {
                **timeline,
                "source": {"asset": live.get("source_url") or source_asset},
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("[VIDEO_EDIT] shotstack live failed job=%s", job_id[:8])
            error = str(exc)[:400]
            status = "failed"
            # Reembolso si el render live falla tras debitar
            credit_tokens(
                user_id,
                tokens,
                reason="render_refund",
                metadata={"job_id": job_id, "error": error},
            )
            debit["balance_tokens"] = get_token_balance(user_id)
    elif shotstack_configured() and not video_bytes:
        status = "dry_run"
        error = None
        message_hint = (
            "Shotstack configurado, pero falta el archivo de video en la petición "
            "(sube el MP4 de nuevo). Timeline lista; tokens descontados."
        )
    else:
        message_hint = (
            "Timeline lista (dry-run). Configure SHOTSTACK_API_KEY para render en vivo. "
            "Tokens ya descontados."
        )

    if status == "done":
        message_hint = (
            "Video editado listo. Tokens descontados. "
            "Revise el enlace de descarga abajo."
        )
    elif status == "failed":
        message_hint = (
            f"Render falló; tokens reembolsados. Detalle: {error or 'error'}"
        )

    row = {
        "id": job_id,
        "user_id": user_id,
        "status": status if status in {
            "queued", "planning", "rendering", "done", "failed", "dry_run"
        } else "failed",
        "duration_sec": duration_sec,
        "tokens_charged": 0 if status == "failed" else tokens,
        "script": script[:8000],
        "timeline": timeline,
        "result_url": result_url,
        "error": error,
        "metadata": {
            "sonilo_cues": len((timeline.get("sonilo") or {}).get("cues") or []),
            "veo": timeline.get("veo"),
            "dry_run": status == "dry_run",
            **render_meta,
        },
    }
    try:
        from app.services import supabase_db

        supabase_db.insert_video_edit_job(row)
    except Exception:  # noqa: BLE001
        logger.debug("[VIDEO_EDIT] job persist skipped")

    ok = status in {"done", "dry_run"}
    return {
        "ok": ok,
        "job_id": job_id,
        "status": status,
        "tokens_charged": 0 if status == "failed" else tokens,
        "balance_tokens": debit.get("balance_tokens"),
        "quote": quote,
        "timeline": timeline,
        "result_url": result_url,
        "message": message_hint,
        "error": error,
        "soft_cap_remaining": soft_cap_remaining(user_id),
        "code": None if ok else "render_failed",
    }
