"""Monitor de voz Retell — API viva vs saldo/facturación.

No crea web calls en el loop (eso cobra). El semáforo de llamadas sale de
register-call / diagnostics; el tick solo hace agent.retrieve + voice.list.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("ced.retell.health")

PROBE_INTERVAL_SEC = 300
FIRST_PROBE_DELAY_SEC = 8
ALERT_COOLDOWN_SEC = 1800

_task: asyncio.Task[None] | None = None
_stop = asyncio.Event()
_lock = threading.Lock()
_state: dict[str, Any] = {
    "voice": "unknown",
    "api_ok": False,
    "configured": False,
    "monitor_running": False,
    "last_register": None,
    "last_register_at": None,
    "last_probe_at": None,
    "last_error": None,
    "last_error_kind": None,
    "last_alert_voice": None,
    "last_alert_at": None,
    "agent_ok": False,
    "voices_ok": False,
    "voices_count": 0,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _utc_now()).isoformat()


def _reset_for_tests() -> None:
    with _lock:
        _state.update(
            {
                "voice": "unknown",
                "api_ok": False,
                "configured": False,
                "monitor_running": False,
                "last_register": None,
                "last_register_at": None,
                "last_probe_at": None,
                "last_error": None,
                "last_error_kind": None,
                "last_alert_voice": None,
                "last_alert_at": None,
                "agent_ok": False,
                "voices_ok": False,
                "voices_count": 0,
            }
        )


def classify_retell_error(exc: Exception | str | None) -> str:
    """billing | auth | not_found | rate_limit | down."""
    raw = str(exc or "").strip()
    lower = raw.lower()
    if not lower:
        return "down"
    if (
        "402" in lower
        or "payment required" in lower
        or "trial" in lower
        or "insufficient credit" in lower
        or "insufficient funds" in lower
        or "out of credit" in lower
    ):
        return "billing"
    if "401" in lower or "unauthorized" in lower or "invalid api key" in lower:
        return "auth"
    if "429" in lower or "rate limit" in lower:
        return "rate_limit"
    if "404" in lower or "not found" in lower or "422" in lower:
        return "not_found"
    return "down"


def _sanitize_error(exc: Exception | str | None) -> str | None:
    raw = str(exc or "").strip()
    if not raw:
        return None
    return raw.replace("\n", " ")[:240]


def _recompute_locked() -> str:
    if not _state["configured"]:
        voice = "unconfigured"
    elif _state["last_register"] == "billing":
        voice = "billing"
    elif not _state["api_ok"] and _state["last_probe_at"]:
        voice = "down"
    elif _state["last_register"] == "ok" and _state["api_ok"]:
        voice = "ok"
    elif _state["last_register"] == "ok" and not _state["last_probe_at"]:
        voice = "ok"
    elif _state["last_register"] in ("down", "auth", "not_found", "rate_limit"):
        kind = _state["last_register"]
        voice = "billing" if kind == "billing" else "down"
    elif _state["api_ok"]:
        voice = "unknown"
    else:
        voice = "unknown"
    _state["voice"] = voice
    return voice


def snapshot() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def public_status() -> dict[str, str]:
    snap = snapshot()
    voice = str(snap.get("voice") or "unknown")
    http_ok = voice not in ("billing", "down")
    checked = str(snap.get("last_probe_at") or snap.get("last_register_at") or "")
    return {
        "status": "ok" if http_ok else "degraded",
        "voice": voice,
        "checked_at": checked,
    }


def note_create_web_call(*, ok: bool, error: Exception | str | None = None) -> None:
    """Registrar resultado de create_web_call (register-call o diagnostics)."""
    kind = "ok" if ok else classify_retell_error(error)
    with _lock:
        _state["last_register"] = kind
        _state["last_register_at"] = _iso()
        if ok:
            _state["last_error"] = None
            _state["last_error_kind"] = None
            _state["configured"] = True
            _state["api_ok"] = True
        else:
            _state["last_error"] = _sanitize_error(error)
            _state["last_error_kind"] = kind
            _state["configured"] = True
            if kind == "auth":
                _state["api_ok"] = False
        prev = _state["voice"]
        voice = _recompute_locked()
    if voice != prev:
        logger.warning("[RETELL:HEALTH] voice %s → %s (register=%s)", prev, voice, kind)
        _schedule_alert(voice, previous=prev)


def _apply_probe_result(
    *,
    configured: bool,
    api_ok: bool,
    agent_ok: bool,
    voices_ok: bool,
    voices_count: int,
    error: str | None,
    error_kind: str | None,
) -> str:
    with _lock:
        prev = _state["voice"]
        _state["configured"] = configured
        _state["api_ok"] = api_ok
        _state["agent_ok"] = agent_ok
        _state["voices_ok"] = voices_ok
        _state["voices_count"] = voices_count
        _state["last_probe_at"] = _iso()
        if error:
            _state["last_error"] = error
            _state["last_error_kind"] = error_kind
        elif _state["last_register"] != "billing":
            _state["last_error"] = None
            _state["last_error_kind"] = None
        voice = _recompute_locked()
    if voice != prev:
        logger.warning("[RETELL:HEALTH] voice %s → %s (probe api_ok=%s)", prev, voice, api_ok)
        _schedule_alert(voice, previous=prev)
    else:
        logger.info("[RETELL:HEALTH] voice=%s api_ok=%s agent_ok=%s", voice, api_ok, agent_ok)
    return voice


def probe_cheap() -> dict[str, Any]:
    """agent.retrieve + voice.list — no create_web_call."""
    from app.config import get_settings
    from app.services.retell_agent_cache import get_retell_agent_id
    from app.services.retell_client import get_retell_client

    settings = get_settings()
    if settings.voice_provider != "retell":
        _apply_probe_result(
            configured=False,
            api_ok=False,
            agent_ok=False,
            voices_ok=False,
            voices_count=0,
            error="voice_provider_not_retell",
            error_kind="unconfigured",
        )
        return snapshot()

    client = get_retell_client()
    agent_id = (get_retell_agent_id() or settings.retell_agent_id.strip() or "").strip()
    if not client or not settings.retell_api_key.strip():
        _apply_probe_result(
            configured=False,
            api_ok=False,
            agent_ok=False,
            voices_ok=False,
            voices_count=0,
            error="retell_api_key_missing",
            error_kind="unconfigured",
        )
        return snapshot()

    agent_ok = False
    voices_ok = False
    voices_count = 0
    last_exc: Exception | None = None

    if agent_id:
        try:
            client.agent.retrieve(agent_id=agent_id)
            agent_ok = True
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("[RETELL:HEALTH] agent.retrieve failed: %s", str(exc)[:240])
    else:
        last_exc = RuntimeError("retell_agent_id_missing")

    try:
        listed = client.voice.list()
        voices = getattr(listed, "voices", None) or listed
        voices_count = len(list(voices or []))
        voices_ok = True
    except Exception as exc:  # noqa: BLE001
        last_exc = last_exc or exc
        logger.warning("[RETELL:HEALTH] voice.list failed: %s", str(exc)[:240])

    api_ok = agent_ok or voices_ok
    kind = classify_retell_error(last_exc) if last_exc and not api_ok else None
    _apply_probe_result(
        configured=True,
        api_ok=api_ok,
        agent_ok=agent_ok,
        voices_ok=voices_ok,
        voices_count=voices_count,
        error=_sanitize_error(last_exc) if last_exc and not api_ok else None,
        error_kind=kind,
    )
    return snapshot()


def probe_billing_canary() -> dict[str, Any]:
    """create_web_call único (admin). Si pasa, borra la llamada. Si 402, marca billing."""
    from app.config import get_settings
    from app.services.retell_agent_cache import get_retell_agent_id
    from app.services.retell_client import get_retell_client

    probe_cheap()
    settings = get_settings()
    client = get_retell_client()
    agent_id = (get_retell_agent_id() or settings.retell_agent_id.strip() or "").strip()
    if not client or not agent_id:
        return snapshot()
    try:
        call = client.call.create_web_call(
            agent_id=agent_id,
            metadata={"ced_probe": "voice_health"},
        )
        note_create_web_call(ok=True)
        call_id = getattr(call, "call_id", None)
        if call_id:
            try:
                client.call.delete(str(call_id))
            except Exception:  # noqa: BLE001
                logger.info("[RETELL:HEALTH] no se pudo borrar canary %s", call_id)
    except Exception as exc:  # noqa: BLE001
        note_create_web_call(ok=False, error=exc)
    return snapshot()


def _alert_to() -> str:
    from app.config import get_settings

    settings = get_settings()
    to = settings.cost_alert_email.strip()
    if to:
        return to
    emails = [e.strip() for e in settings.super_admin_emails.split(",") if e.strip()]
    return emails[0] if emails else ""


def _should_alert(voice: str, previous: str) -> bool:
    if voice in ("unknown", "unconfigured"):
        return False
    if voice == previous:
        return False
    if voice not in ("billing", "down", "ok"):
        return False
    if previous in ("unknown", "unconfigured") and voice == "ok":
        return False
    with _lock:
        last_at = _state.get("last_alert_at")
        last_voice = _state.get("last_alert_voice")
    if voice == "ok":
        return previous in ("billing", "down")
    if last_voice == voice and last_at:
        try:
            then = datetime.fromisoformat(str(last_at))
            if (_utc_now() - then).total_seconds() < ALERT_COOLDOWN_SEC:
                return False
        except ValueError:
            pass
    return True


def _schedule_alert(voice: str, *, previous: str) -> None:
    if not _should_alert(voice, previous):
        return
    thread = threading.Thread(
        target=_send_alert,
        args=(voice, previous),
        daemon=True,
        name="retell-health-alert",
    )
    thread.start()


def _send_alert(voice: str, previous: str) -> None:
    from app.services.email_resend import resend_configured, send_resend_email

    to_email = _alert_to()
    if not to_email or not resend_configured():
        logger.info("[RETELL:HEALTH] alerta %s omitida (email no configurado)", voice)
        return

    if voice == "billing":
        subject = "CED voz: saldo del proveedor"
        text = (
            "Jarvis no puede iniciar llamadas: el proveedor de voz rechazó create "
            "(saldo o trial). Recarga dashboard.retell.ai — la recarga Stripe de CED "
            "no cubre esa cuenta. GET /health/voice y GET /v1/retell/provider-health."
        )
    elif voice == "down":
        subject = "CED voz: proveedor caído"
        text = (
            "El monitor de voz no pudo hablar con el proveedor (API/agente). "
            "Revisa GET /v1/retell/provider-health."
        )
    else:
        subject = "CED voz: recuperada"
        text = (
            f"La voz volvió a funcionar (antes: {previous}). "
            "register-call aceptó o el API responde de nuevo."
        )

    html = f"""
<div style="font-family:system-ui,sans-serif;background:#0a0a0a;color:#e0f7fa;padding:24px;">
  <h1 style="color:#00e5ff;font-size:18px;">CED — monitor de voz</h1>
  <p>{text}</p>
  <p style="color:#64748b;font-size:13px;">estado: {previous} → {voice}</p>
</div>
"""
    ok, err = send_resend_email(to_email=to_email, subject=subject, html=html, text=text)
    if ok:
        with _lock:
            _state["last_alert_voice"] = voice
            _state["last_alert_at"] = _iso()
        logger.info("[RETELL:HEALTH] alerta enviada a %s (%s)", to_email, voice)
    else:
        logger.warning("[RETELL:HEALTH] alerta falló: %s", err)


async def _run_loop() -> None:
    with _lock:
        _state["monitor_running"] = True
    try:
        await asyncio.sleep(FIRST_PROBE_DELAY_SEC)
        while not _stop.is_set():
            try:
                await asyncio.to_thread(probe_cheap)
            except Exception:  # noqa: BLE001
                logger.exception("[RETELL:HEALTH] probe falló")
            try:
                await asyncio.wait_for(_stop.wait(), timeout=PROBE_INTERVAL_SEC)
            except asyncio.TimeoutError:
                continue
    finally:
        with _lock:
            _state["monitor_running"] = False
        logger.info("[RETELL:HEALTH] monitor detenido")


def start_monitor_if_enabled() -> asyncio.Task[None] | None:
    global _task
    from app.config import get_settings

    settings = get_settings()
    if settings.voice_provider != "retell":
        logger.info("[RETELL:HEALTH] omitido (voice_provider=%s)", settings.voice_provider)
        return None
    if not settings.retell_api_key.strip():
        logger.warning("[RETELL:HEALTH] RETELL_API_KEY vacía — snapshot unconfigured")
        _apply_probe_result(
            configured=False,
            api_ok=False,
            agent_ok=False,
            voices_ok=False,
            voices_count=0,
            error="retell_api_key_missing",
            error_kind="unconfigured",
        )
        return None
    if _task and not _task.done():
        return _task
    _stop.clear()
    _task = asyncio.create_task(_run_loop(), name="retell-provider-health")
    logger.info("[RETELL:HEALTH] monitor cada %ss (sin create_web_call)", PROBE_INTERVAL_SEC)
    return _task


async def stop_monitor() -> None:
    global _task
    _stop.set()
    if _task and not _task.done():
        try:
            await asyncio.wait_for(_task, timeout=8)
        except (asyncio.TimeoutError, Exception):  # noqa: BLE001
            _task.cancel()
    _task = None
    with _lock:
        _state["monitor_running"] = False
