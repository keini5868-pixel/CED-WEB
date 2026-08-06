"""Cliente Sonilo Text→SFX / Video→SFX (api.sonilo.com)."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_BASE = "https://api.sonilo.com/v1"
_POLL_INTERVAL = 2.5
_MAX_WAIT = 120.0
_USER_AGENT = "CED-VideoEditPilot/1.0 (+https://cedweb-production.up.railway.app)"

# Errores que no vale la pena reintentar en el mismo job
_FATAL_HTTP = {401, 402, 403}


def sonilo_configured() -> bool:
    return bool(_api_key())


def _api_key() -> str:
    settings = get_settings()
    key = (getattr(settings, "sonilo_api_key", None) or "").strip()
    if key:
        return key
    import os

    for name in ("SONILO_API_KEY", "SONILO_KEY", "SONILO_TOKEN", "SONILO_SECRET"):
        val = (os.environ.get(name) or "").strip()
        if val:
            return val
    return ""


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Accept": "application/json",
        "User-Agent": _USER_AGENT,
    }


def _error_payload(
    *,
    stage: str,
    http_status: int | None = None,
    code: str | None = None,
    message: str,
    detail: str | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "stage": stage,
        "http_status": http_status,
        "code": code or "sonilo_error",
        "message": (message or "Sonilo error")[:400],
        "detail": (detail or "")[:500] or None,
    }


def _parse_api_error(response: httpx.Response) -> dict[str, Any]:
    body_text = (response.text or "")[:500]
    code = f"http_{response.status_code}"
    message = body_text or response.reason_phrase or f"HTTP {response.status_code}"
    try:
        data = response.json() or {}
        if isinstance(data, dict):
            code = str(data.get("code") or code)
            message = str(
                data.get("message") or data.get("error") or message
            )[:400]
    except Exception:  # noqa: BLE001
        pass
    if response.status_code == 402:
        code = code if code not in {"http_402"} else "payment_required"
    if response.status_code == 401:
        code = "auth_invalid"
    return _error_payload(
        stage="http",
        http_status=response.status_code,
        code=code,
        message=message,
        detail=body_text,
    )


def account_health() -> dict[str, Any]:
    """Estado de cuenta Sonilo (trial/servicios). Nunca lanza."""
    if not sonilo_configured():
        return {
            "ok": False,
            "configured": False,
            "code": "not_configured",
            "message": "SONILO_API_KEY ausente",
        }
    try:
        with httpx.Client(timeout=20.0) as client:
            res = client.get(f"{_BASE}/account/services", headers=_headers())
        if res.status_code >= 400:
            err = _parse_api_error(res)
            logger.warning(
                "[SONILO] account/services HTTP %s code=%s msg=%s",
                err.get("http_status"),
                err.get("code"),
                err.get("message"),
            )
            return {"ok": False, "configured": True, **err}
        data = res.json() or {}
        trial = data.get("trial") if isinstance(data, dict) else {}
        text_trial = (trial or {}).get("text_to_sfx") or {}
        video_trial = (trial or {}).get("video_to_sfx") or {}
        return {
            "ok": True,
            "configured": True,
            "available_services": list(data.get("available_services") or []),
            "trial": {
                "text_to_sfx_remaining": int(text_trial.get("remaining") or 0),
                "text_to_sfx_used": int(text_trial.get("used") or 0),
                "video_to_sfx_remaining": int(video_trial.get("remaining") or 0),
                "video_to_sfx_used": int(video_trial.get("used") or 0),
            },
            "message": "Sonilo cuenta OK",
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("[SONILO] account_health failed: %s", exc)
        return {
            "ok": False,
            "configured": True,
            "code": "account_probe_failed",
            "message": str(exc)[:300],
        }


def _find_audio_url(payload: Any) -> str | None:
    if isinstance(payload, str) and payload.startswith(("http://", "https://")):
        return payload
    if isinstance(payload, dict):
        for key in (
            "url",
            "sfx_url",
            "audio_url",
            "output_url",
            "download_url",
            "sfx",
            "audio",
            "result",
        ):
            found = _find_audio_url(payload.get(key))
            if found:
                return found
        for nested in payload.values():
            found = _find_audio_url(nested)
            if found:
                return found
    if isinstance(payload, list):
        for nested in payload:
            found = _find_audio_url(nested)
            if found:
                return found
    return None


def _poll_task(client: httpx.Client, task_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + _MAX_WAIT
    last_status = ""
    while time.monotonic() < deadline:
        poll = client.get(f"{_BASE}/tasks/{task_id}", headers=_headers())
        if poll.status_code >= 400:
            err = _parse_api_error(poll)
            err["stage"] = "poll"
            logger.warning(
                "[SONILO] poll HTTP %s code=%s msg=%s task=%s",
                err.get("http_status"),
                err.get("code"),
                err.get("message"),
                task_id[:8],
            )
            return err
        task = poll.json() or {}
        status = str(task.get("status") or task.get("state") or "").lower()
        last_status = status
        if status in {"succeeded", "success", "done", "completed"}:
            url = _find_audio_url(task)
            if url:
                logger.info("[SONILO] sfx ready task=%s", task_id[:8])
                return {"ok": True, "url": url, "task_id": task_id, "raw_status": status}
            err = _error_payload(
                stage="poll",
                code="succeeded_without_url",
                message="Sonilo marcó éxito pero no devolvió URL de audio",
                detail=str(task)[:500],
            )
            logger.warning("[SONILO] %s task=%s detail=%s", err["code"], task_id[:8], err["detail"])
            return err
        if status in {"failed", "error", "cancelled", "canceled"}:
            err = _error_payload(
                stage="poll",
                code=str((task.get("error") or {}).get("code") if isinstance(task.get("error"), dict) else "task_failed"),
                message=str(
                    (task.get("error") if isinstance(task.get("error"), str) else None)
                    or (task.get("error") or {}).get("message")
                    if isinstance(task.get("error"), dict)
                    else task.get("error")
                    or task.get("message")
                    or f"Sonilo task {status}"
                )[:400],
                detail=str(task)[:500],
            )
            logger.warning(
                "[SONILO] task failed status=%s code=%s msg=%s task=%s",
                status,
                err.get("code"),
                err.get("message"),
                task_id[:8],
            )
            return err
        time.sleep(_POLL_INTERVAL)
    err = _error_payload(
        stage="poll",
        code="timeout",
        message=f"Timeout esperando Sonilo task (último status={last_status or 'unknown'})",
    )
    logger.warning("[SONILO] timeout task=%s last=%s", task_id[:8], last_status)
    return err


def _submit_multipart(path: str, fields: dict[str, str]) -> dict[str, Any]:
    if not sonilo_configured():
        return _error_payload(
            stage="submit",
            code="not_configured",
            message="SONILO_API_KEY ausente",
        )
    files = {k: (None, str(v)) for k, v in fields.items()}
    try:
        with httpx.Client(timeout=60.0) as client:
            submit = client.post(f"{_BASE}{path}", headers=_headers(), files=files)
            if submit.status_code >= 400:
                err = _parse_api_error(submit)
                err["stage"] = "submit"
                logger.warning(
                    "[SONILO] submit %s HTTP %s code=%s msg=%s",
                    path,
                    err.get("http_status"),
                    err.get("code"),
                    err.get("message"),
                )
                return err
            payload = submit.json() or {}
            task_id = str(
                payload.get("task_id")
                or payload.get("taskId")
                or payload.get("id")
                or ""
            ).strip()
            if not task_id:
                err = _error_payload(
                    stage="submit",
                    code="missing_task_id",
                    message="Sonilo no devolvió task_id",
                    detail=str(payload)[:500],
                )
                logger.warning("[SONILO] submit sin task_id path=%s detail=%s", path, err["detail"])
                return err
            logger.info(
                "[SONILO] submit ok path=%s task=%s http=%s",
                path,
                task_id[:8],
                submit.status_code,
            )
            return _poll_task(client, task_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[SONILO] submit/poll failed path=%s: %s", path, exc)
        return _error_payload(
            stage="submit",
            code="exception",
            message=str(exc)[:300],
        )


def generate_sfx_result(prompt: str, *, duration_sec: float = 2.0) -> dict[str, Any]:
    """Genera SFX por texto. Devuelve {ok, url?} o error estructurado."""
    prompt = (prompt or "").strip()[:2000]
    if not prompt:
        return _error_payload(
            stage="submit",
            code="empty_prompt",
            message="Prompt SFX vacío",
        )
    duration = max(1, min(180, int(round(float(duration_sec)))))
    return _submit_multipart(
        "/text-to-sfx",
        {
            "prompt": prompt,
            "duration": str(duration),
            "audio_format": "mp3",
        },
    )


def generate_sfx_url(prompt: str, *, duration_sec: float = 2.0) -> str | None:
    """Compat: URL o None (errores ya logueados en generate_sfx_result)."""
    result = generate_sfx_result(prompt, duration_sec=duration_sec)
    if result.get("ok") and result.get("url"):
        return str(result["url"])
    return None


def generate_video_sfx_result(
    video_url: str,
    *,
    prompt: str | None = None,
) -> dict[str, Any]:
    """SFX alineado al video (POST /v1/video-to-sfx)."""
    video_url = (video_url or "").strip()
    if not video_url.startswith(("http://", "https://")):
        return _error_payload(
            stage="submit",
            code="invalid_video_url",
            message="video_url inválida para Sonilo video-to-sfx",
        )
    fields = {
        "video_url": video_url,
        "audio_format": "mp3",
    }
    p = (prompt or "").strip()[:2000]
    if p:
        fields["prompt"] = p
    return _submit_multipart("/video-to-sfx", fields)


def resolve_cues_to_audio_clips(
    cues: list[dict[str, Any]],
    *,
    max_cues: int = 4,
    video_url: str | None = None,
    script_hint: str | None = None,
) -> dict[str, Any]:
    """
    Resuelve SFX → clips Shotstack.

    Preferencia:
    1) video-to-sfx si hay video_url (mejor sync)
    2) text-to-sfx por cue

    Ante 401/402/403: fail-fast (no quemar más llamadas).
    """
    clips: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    mode_used: str | None = None
    fatal: dict[str, Any] | None = None

    def _is_fatal(err: dict[str, Any]) -> bool:
        status = err.get("http_status")
        code = str(err.get("code") or "")
        if status in _FATAL_HTTP:
            return True
        if code in {
            "trial_exhausted",
            "payment_required",
            "auth_invalid",
            "insufficient_balance",
        }:
            return True
        return False

    # 1) Video→SFX (una pista alineada)
    if video_url:
        prompt = (
            (script_hint or "").strip()[:500]
            or "realistic Foley, short transitions, impacts and ambience synced to visible cuts"
        )
        mode_used = "video_to_sfx"
        result = generate_video_sfx_result(video_url, prompt=prompt)
        if result.get("ok") and result.get("url"):
            # Duración del clip: Shotstack corta/alarga con length; usamos tramo amplio.
            # El asset audio se coloca desde 0; length lo decide el caller vía duration.
            clips.append(
                {
                    "asset": {
                        "type": "audio",
                        "src": str(result["url"]),
                        "volume": 0.9,
                    },
                    "start": 0.0,
                    "length": None,  # rellenado por shotstack con duration_sec
                    "sonilo_mode": "video_to_sfx",
                    "task_id": result.get("task_id"),
                }
            )
            logger.info("[SONILO] video-to-sfx clip ready")
        else:
            errors.append({**result, "mode": "video_to_sfx"})
            if _is_fatal(result):
                fatal = result
                logger.error(
                    "[SONILO] FATAL video-to-sfx code=%s http=%s msg=%s — abortando SFX",
                    result.get("code"),
                    result.get("http_status"),
                    result.get("message"),
                )
            else:
                logger.warning(
                    "[SONILO] video-to-sfx falló; intento text-to-sfx cues. code=%s msg=%s",
                    result.get("code"),
                    result.get("message"),
                )

    # 2) Text→SFX por cue si aún no hay clips.
    # Auth inválida → no reintentar. Trial/pago de video-to-sfx ≠ trial de text-to-sfx.
    skip_text = bool(fatal and fatal.get("code") in {"auth_invalid"})
    if not clips and not skip_text:
        mode_used = "text_to_sfx" if mode_used is None else mode_used
        for idx, cue in enumerate((cues or [])[:max_cues]):
            if not isinstance(cue, dict):
                continue
            prompt = str(cue.get("prompt") or "").strip()
            if not prompt:
                continue
            start = float(cue.get("start") or 0)
            dur = float(cue.get("duration_sec") or 2.0)
            dur = max(1.0, min(12.0, dur))
            result = generate_sfx_result(prompt, duration_sec=dur)
            if result.get("ok") and result.get("url"):
                clips.append(
                    {
                        "asset": {
                            "type": "audio",
                            "src": str(result["url"]),
                            "volume": 0.85,
                        },
                        "start": round(max(0.0, start), 3),
                        "length": round(dur, 3),
                        "sonilo_mode": "text_to_sfx",
                        "task_id": result.get("task_id"),
                    }
                )
                continue
            errors.append({**result, "mode": "text_to_sfx", "cue_index": idx})
            logger.warning(
                "[SONILO] text-to-sfx cue=%s code=%s http=%s msg=%s",
                idx,
                result.get("code"),
                result.get("http_status"),
                result.get("message"),
            )
            if _is_fatal(result):
                fatal = result
                logger.error(
                    "[SONILO] FATAL text-to-sfx code=%s http=%s msg=%s — stop cues",
                    result.get("code"),
                    result.get("http_status"),
                    result.get("message"),
                )
                break

    attempted = bool(video_url) or bool(cues)
    ok = len(clips)
    failed = max(0, (1 if video_url else 0) + min(max_cues, len(cues or [])) - ok)
    # Recalcular failed de forma más honesta
    if video_url and any(e.get("mode") == "video_to_sfx" for e in errors) and not any(
        c.get("sonilo_mode") == "video_to_sfx" for c in clips
    ):
        failed = max(failed, 1)
    failed = max(failed, len(errors))

    primary_error = fatal or (errors[0] if errors else None)
    summary_msg = None
    if ok == 0 and primary_error:
        summary_msg = (
            f"Sonilo sin clips: {primary_error.get('code')} — "
            f"{primary_error.get('message')}"
        )
    elif ok == 0 and attempted:
        summary_msg = "Sonilo sin clips: sin cues válidos o API no respondió"
    elif ok > 0 and errors:
        summary_msg = (
            f"Sonilo parcial: {ok} clips OK; "
            f"errores={len(errors)} ({(errors[0] or {}).get('code')})"
        )

    meta = {
        "attempted": attempted,
        "ok": ok,
        "failed": failed,
        "mode": mode_used,
        "errors": errors[:8],
        "error": primary_error,
        "message": summary_msg,
        "clips": clips,
    }
    if ok == 0 and attempted:
        logger.error("[SONILO] resolve → 0 clips | %s", summary_msg)
    else:
        logger.info(
            "[SONILO] resolve ok=%s failed=%s mode=%s msg=%s",
            ok,
            failed,
            mode_used,
            summary_msg,
        )
    return meta
