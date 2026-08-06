"""Orquestacion Video Edit piloto — tokens + Shotstack live / dry-run."""

from __future__ import annotations

import logging
import threading
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
    render_video_from_source,
    request_upload_url,
    shotstack_configured,
)
from app.services.video_edit_pilot.sonilo import sonilo_configured
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

_job_cache: dict[str, dict[str, Any]] = {}
_job_cache_lock = threading.Lock()


def _cache_put(job_id: str, payload: dict[str, Any]) -> None:
    with _job_cache_lock:
        _job_cache[job_id] = payload


def _cache_get(job_id: str) -> dict[str, Any] | None:
    with _job_cache_lock:
        row = _job_cache.get(job_id)
        return dict(row) if row else None


def _strip_user(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if k != "user_id"}


def pilot_status() -> dict[str, Any]:
    settings = get_settings()
    shotstack = shotstack_configured()
    sonilo = sonilo_configured()
    veo = bool(getattr(settings, "video_edit_veo_enabled", False))
    sonilo_health: dict[str, Any] = {"configured": sonilo}
    if sonilo:
        try:
            from app.services.video_edit_pilot.sonilo import account_health

            sonilo_health = account_health()
        except Exception as exc:  # noqa: BLE001
            sonilo_health = {
                "configured": True,
                "ok": False,
                "code": "health_exception",
                "message": str(exc)[:200],
            }
    trial = (sonilo_health.get("trial") or {}) if isinstance(sonilo_health, dict) else {}
    text_left = int(trial.get("text_to_sfx_remaining") or 0)
    video_left = int(trial.get("video_to_sfx_remaining") or 0)
    sonilo_note = (
        "Text→SFX / Video→SFX activo en render"
        if sonilo
        else "SONILO_API_KEY no cargada en este servicio (cues solo planificados)"
    )
    if sonilo and sonilo_health.get("ok") is False:
        sonilo_note = (
            f"Sonilo configurado pero cuenta con error: "
            f"{sonilo_health.get('code')}: {sonilo_health.get('message')}"
        )
    elif sonilo and text_left <= 0 and video_left <= 0:
        sonilo_note = (
            "Sonilo trial agotado (text-to-sfx y/o video-to-sfx). "
            "Agregue método de pago en https://platform.sonilo.com/dashboard/billing "
            "o el render seguirá en 0 clips SFX."
        )
    return {
        "ok": True,
        "pilot": True,
        "enabled": True,
        "providers": {
            "shotstack_configured": shotstack,
            "sonilo_configured": sonilo,
            "veo_enabled": veo,
            "shotstack_env": (getattr(settings, "shotstack_env", None) or "stage"),
            "sonilo": sonilo_health,
        },
        "economy": {
            "tokens_per_usd": 100,
            "tokens_per_second": 1,
            "min_billable_seconds": 30,
            "soft_cap_renders_per_day": VIDEO_EDIT_SOFT_CAP_RENDERS_PER_DAY,
            "packs": video_edit_pack_catalog(),
        },
        "mode": "live_ready" if shotstack else "dry_run",
        "notes": {
            "sonilo": sonilo_note,
            "shotstack": (
                "Edit API live"
                if shotstack
                else "Sin SHOTSTACK_API_KEY — dry-run"
            ),
        },
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


def create_browser_upload(*, filename: str = "source.mp4") -> dict[str, Any]:
    if not shotstack_configured():
        return {"ok": False, "error": "SHOTSTACK_API_KEY no configurada"}
    meta = request_upload_url(filename=filename or "source.mp4")
    return {
        "ok": True,
        "source_id": meta["source_id"],
        "upload_url": meta["upload_url"],
    }


def _persist_job(row: dict[str, Any]) -> None:
    try:
        from app.services import supabase_db

        supabase_db.insert_video_edit_job(row)
    except Exception:  # noqa: BLE001
        logger.debug("[VIDEO_EDIT] job persist skipped")


def _update_job(job_id: str, patch: dict[str, Any]) -> None:
    try:
        from app.services import supabase_db

        supabase_db.update_video_edit_job(job_id, patch)
    except Exception:  # noqa: BLE001
        logger.debug("[VIDEO_EDIT] job update skipped")


def _public_job_payload(
    *,
    job_id: str,
    user_id: str,
    status: str,
    tokens: int,
    balance_tokens: int | None,
    quote: dict[str, Any],
    timeline: dict[str, Any],
    result_url: str | None,
    message: str,
    error: str | None = None,
    sonilo: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ok = status in {"done", "dry_run", "rendering"}
    payload = {
        "ok": ok,
        "job_id": job_id,
        "user_id": user_id,
        "status": status,
        "tokens_charged": 0 if status == "failed" else tokens,
        "balance_tokens": balance_tokens,
        "quote": quote,
        "timeline": timeline,
        "result_url": result_url,
        "message": message,
        "error": error,
        "sonilo": sonilo,
        "soft_cap_remaining": soft_cap_remaining(user_id),
        "code": None if ok else "render_failed",
    }
    _cache_put(job_id, payload)
    return payload


def _sonilo_user_message(sonilo: dict[str, Any] | None) -> str:
    s = sonilo or {}
    if not s.get("attempted"):
        return "Sin SFX (SONILO_API_KEY ausente o sin cues)."
    ok = int(s.get("ok") or 0)
    if ok > 0:
        mode = s.get("mode") or "sfx"
        return f"SFX Sonilo: {ok} clip(s) via {mode}."
    err = s.get("error") or {}
    code = err.get("code") or "unknown"
    msg = err.get("message") or s.get("message") or "sin detalle"
    return f"SFX Sonilo: 0 clips — {code}: {msg}"


def _run_shotstack_background(
    *,
    job_id: str,
    user_id: str,
    tokens: int,
    quote: dict[str, Any],
    timeline: dict[str, Any],
    duration_sec: float,
    source_asset: str,
    video_bytes: bytes | None = None,
    video_filename: str = "source.mp4",
    video_content_type: str = "video/mp4",
    source_id: str | None = None,
) -> None:
    try:
        if source_id:
            live = render_video_from_source(
                source_id=source_id,
                timeline=timeline,
                duration_sec=duration_sec,
            )
        else:
            live = render_video_from_bytes(
                video_bytes or b"",
                filename=video_filename or "source.mp4",
                content_type=video_content_type or "video/mp4",
                timeline=timeline,
                duration_sec=duration_sec,
            )
        result_url = str(live.get("result_url") or "")
        updated_timeline = {
            **timeline,
            "source": {"asset": live.get("source_url") or source_asset},
        }
        sonilo_info = live.get("sonilo") if isinstance(live.get("sonilo"), dict) else {}
        bal = get_token_balance(user_id)
        _public_job_payload(
            job_id=job_id,
            user_id=user_id,
            status="done",
            tokens=tokens,
            balance_tokens=bal,
            quote=quote,
            timeline=updated_timeline,
            result_url=result_url,
            sonilo=sonilo_info,
            message=(
                "Video editado listo. Tokens descontados. "
                + _sonilo_user_message(sonilo_info)
                + " Revise el enlace de descarga abajo."
            ),
        )
        _update_job(
            job_id,
            {
                "status": "done",
                "result_url": result_url,
                "timeline": updated_timeline,
                "error": None,
                "tokens_charged": tokens,
                "metadata": {
                    "sonilo_cues": len(
                        (updated_timeline.get("sonilo") or {}).get("cues") or []
                    ),
                    "sonilo_render": sonilo_info,
                    "veo": updated_timeline.get("veo"),
                    "dry_run": False,
                    "render_id": live.get("render_id"),
                    "source_id": live.get("source_id"),
                    "aspect": live.get("aspect"),
                    "edit_tracks": len(
                        ((live.get("edit") or {}).get("timeline") or {}).get("tracks")
                        or []
                    ),
                },
            },
        )
        logger.info(
            "[VIDEO_EDIT] async done job=%s sonilo_ok=%s sonilo_msg=%s",
            job_id[:8],
            (sonilo_info or {}).get("ok"),
            (sonilo_info or {}).get("message") or _sonilo_user_message(sonilo_info),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("[VIDEO_EDIT] shotstack live failed job=%s", job_id[:8])
        error = str(exc)[:400]
        credit_tokens(
            user_id,
            tokens,
            reason="render_refund",
            metadata={"job_id": job_id, "error": error},
        )
        bal = get_token_balance(user_id)
        _public_job_payload(
            job_id=job_id,
            user_id=user_id,
            status="failed",
            tokens=tokens,
            balance_tokens=bal,
            quote=quote,
            timeline=timeline,
            result_url=None,
            message=f"Render fallo; tokens reembolsados. Detalle: {error}",
            error=error,
        )
        _update_job(
            job_id,
            {
                "status": "failed",
                "error": error,
                "tokens_charged": 0,
                "result_url": None,
            },
        )


def get_job_payload(user_id: str, job_id: str) -> dict[str, Any] | None:
    cached = _cache_get(job_id)
    if cached and cached.get("user_id") == user_id:
        return _strip_user(cached)

    try:
        from app.services import supabase_db

        row = supabase_db.get_video_edit_job(job_id, user_id)
    except Exception:  # noqa: BLE001
        row = None
    if not row:
        return None

    status = str(row.get("status") or "")
    ok = status in {"done", "dry_run", "rendering"}
    meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    sonilo_info = meta.get("sonilo_render") if isinstance(meta, dict) else None
    if status == "done":
        message = (
            "Video editado listo. "
            + _sonilo_user_message(sonilo_info if isinstance(sonilo_info, dict) else None)
        )
    elif status == "rendering":
        message = "Render en curso en Shotstack..."
    elif status == "failed":
        message = (
            f"Render fallo; tokens reembolsados. Detalle: {row.get('error') or 'error'}"
        )
    else:
        message = "Timeline lista (dry-run)."
    payload = {
        "ok": ok,
        "job_id": job_id,
        "status": status,
        "tokens_charged": row.get("tokens_charged"),
        "balance_tokens": get_token_balance(user_id),
        "timeline": row.get("timeline"),
        "result_url": row.get("result_url"),
        "message": message,
        "error": row.get("error"),
        "sonilo": sonilo_info,
        "soft_cap_remaining": soft_cap_remaining(user_id),
        "code": None if ok else "render_failed",
    }
    _cache_put(job_id, {**payload, "user_id": user_id})
    return payload


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
    source_id: str | None = None,
    allow_dry_run: bool = False,
) -> dict[str, Any]:
    """
    Flujo piloto:
    1) Soft cap diario
    2) Quote + debit tokens
    3) Timeline
    4) Live async si hay video_bytes o source_id (browser upload)
       Dry-run solo si allow_dry_run=True o Shotstack no configurado
    """
    duration_sec = max(0.1, float(duration_sec))
    script = (script or "").strip()
    source_id = (source_id or "").strip() or None

    if renders_today(user_id) >= VIDEO_EDIT_SOFT_CAP_RENDERS_PER_DAY:
        return {
            "ok": False,
            "code": "daily_soft_cap",
            "error": (
                f"Limite de {VIDEO_EDIT_SOFT_CAP_RENDERS_PER_DAY} renders/dia alcanzado. "
                "Vuelva manana o contacte soporte si necesita mas."
            ),
            "balance_tokens": get_token_balance(user_id),
            "soft_cap_remaining": 0,
        }

    if not script and not auto_transcribe:
        return {
            "ok": False,
            "code": "script_required",
            "error": "Pegue el guion o active transcripcion automatica (proximamente).",
        }

    if not script and auto_transcribe:
        script = (
            "[Transcripcion automatica pendiente — use guion manual en v1 piloto]"
        )

    # Con Shotstack live: exigir fuente ANTES de cobrar
    if (
        shotstack_configured()
        and not video_bytes
        and not source_id
        and not allow_dry_run
    ):
        return {
            "ok": False,
            "code": "missing_video",
            "error": (
                "Falta el archivo de video. Vuelva a seleccionarlo e intente de nuevo."
            ),
            "balance_tokens": get_token_balance(user_id),
        }

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
    can_live = shotstack_configured() and (bool(video_bytes) or bool(source_id))

    if can_live:
        row = {
            "id": job_id,
            "user_id": user_id,
            "status": "rendering",
            "duration_sec": duration_sec,
            "tokens_charged": tokens,
            "script": script[:8000],
            "timeline": timeline,
            "result_url": None,
            "error": None,
            "metadata": {
                "sonilo_cues": len((timeline.get("sonilo") or {}).get("cues") or []),
                "veo": timeline.get("veo"),
                "dry_run": False,
                "async": True,
                "source_id": source_id,
            },
        }
        _persist_job(row)
        payload = _public_job_payload(
            job_id=job_id,
            user_id=user_id,
            status="rendering",
            tokens=tokens,
            balance_tokens=debit.get("balance_tokens"),
            quote=quote,
            timeline=timeline,
            result_url=None,
            message=(
                "Video recibido. Render en Shotstack en curso "
                "(puede tardar 1-3 min). No cierre esta pestana."
            ),
        )
        thread = threading.Thread(
            target=_run_shotstack_background,
            kwargs={
                "job_id": job_id,
                "user_id": user_id,
                "tokens": tokens,
                "quote": quote,
                "timeline": timeline,
                "video_bytes": video_bytes,
                "video_filename": video_filename or "source.mp4",
                "video_content_type": video_content_type or "video/mp4",
                "source_id": source_id,
                "duration_sec": duration_sec,
                "source_asset": source_asset,
            },
            daemon=True,
            name=f"video-edit-{job_id[:8]}",
        )
        thread.start()
        return _strip_user(payload)

    status = "dry_run"
    message_hint = (
        "Timeline lista (dry-run). Configure SHOTSTACK_API_KEY para render en vivo. "
        "Tokens ya descontados."
    )
    row = {
        "id": job_id,
        "user_id": user_id,
        "status": status,
        "duration_sec": duration_sec,
        "tokens_charged": tokens,
        "script": script[:8000],
        "timeline": timeline,
        "result_url": None,
        "error": None,
        "metadata": {
            "sonilo_cues": len((timeline.get("sonilo") or {}).get("cues") or []),
            "veo": timeline.get("veo"),
            "dry_run": True,
        },
    }
    _persist_job(row)
    return _strip_user(
        _public_job_payload(
            job_id=job_id,
            user_id=user_id,
            status=status,
            tokens=tokens,
            balance_tokens=debit.get("balance_tokens"),
            quote=quote,
            timeline=timeline,
            result_url=None,
            message=message_hint,
            error=None,
        )
    )
