"""Centinela — guardia del super admin.

Corre en el proceso del API. Si queda activo, sigue aunque el teléfono
esté apagado. La bitácora se guarda en Supabase (migración 045) para
sobrevivir un reinicio del servidor.

No reinicia procesos. Observa voz, pagos, datos y modelos, anota errores
del proceso y, mientras la guardia sigue activa, corrige una imagen o un
documento que no coincide con lo pedido. Quien espera ve «Corrigiendo datos
para darlo con más precisión…».
"""

from __future__ import annotations

import logging
import re
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator
from uuid import uuid4

logger = logging.getLogger("ced.sentinel")

PROBE_INTERVAL_SEC = 60
LIVE_MODEL_EVERY = 15
EVENT_LIMIT = 120
ERROR_DEDUP_SEC = 300
WARN_DEDUP_SEC = 120
_WARN_LOGGER_MARKERS = ("retell", "voice", "native", "voice_tool", "ced.retell")
CORRECTING_HINT = "Corrigiendo datos para darlo con más precisión…"
PRECISION_HINT = CORRECTING_HINT
_EN_BRIEF = re.compile(
    r"(?i)\b(photorealistic|subject lock|keep these|no text|critical:|flat graphic)\b"
)
_SPANISH_MARKERS = {
    "para",
    "como",
    "sobre",
    "desde",
    "hasta",
    "donde",
    "cuando",
    "porque",
    "tambien",
    "también",
    "una",
    "con",
    "del",
    "las",
    "los",
    "por",
    "que",
}
_EN_WORDS = {
    "the",
    "and",
    "with",
    "scene",
    "background",
    "poster",
    "photorealistic",
    "keep",
    "text",
    "image",
}

_lock = threading.Lock()
_stop = threading.Event()
_thread: threading.Thread | None = None
_handler_installed = False
_sweep_n = 0
_events: list[dict[str, Any]] = []
_hints: dict[str, str] = {}
_hint_depth: dict[str, int] = {}
_error_seen: dict[tuple[str, str], float] = {}
_state: dict[str, Any] = {
    "enabled": False,
    "enabled_at": None,
    "checked_at": None,
    "checks": [],
    "persistent": False,
    "running": False,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _utc_now()).isoformat()


def reset_for_tests() -> None:
    global _sweep_n, _thread
    _stop.set()
    with _lock:
        _sweep_n = 0
        _events.clear()
        _hints.clear()
        _hint_depth.clear()
        _error_seen.clear()
        _state.update(
            {
                "enabled": False,
                "enabled_at": None,
                "checked_at": None,
                "checks": [],
                "persistent": False,
                "running": False,
            }
        )
        _thread = None
    _stop.clear()


def _is_enabled() -> bool:
    with _lock:
        return bool(_state["enabled"])


def correction_hint(user_id: str) -> str | None:
    with _lock:
        return _hints.get(user_id)


def status_or_correction(user_id: str, default: str) -> str:
    return correction_hint(user_id) or default


def begin_correction(
    user_id: str,
    *,
    area: str,
    detail: str,
    hint: str = CORRECTING_HINT,
) -> None:
    uid = (user_id or "").strip()
    if not uid:
        return
    with _lock:
        depth = _hint_depth.get(uid, 0) + 1
        _hint_depth[uid] = depth
        _hints[uid] = hint or CORRECTING_HINT
        shown = _hints[uid]
        first = depth == 1
        enabled = bool(_state["enabled"])
    if first and area == "imagen":
        _ping_waiting_screen(uid, shown)
    if first and enabled:
        _append_event(
            kind="correction",
            area=area,
            level="watch",
            title="Corrigiendo en vivo",
            detail=detail,
        )


def end_correction(user_id: str) -> None:
    uid = (user_id or "").strip()
    if not uid:
        return
    with _lock:
        depth = _hint_depth.get(uid, 0)
        if depth <= 1:
            _hint_depth.pop(uid, None)
            _hints.pop(uid, None)
            return
        _hint_depth[uid] = depth - 1


@contextmanager
def correcting(
    user_id: str,
    *,
    area: str,
    detail: str,
    hint: str = CORRECTING_HINT,
) -> Iterator[None]:
    begin_correction(user_id, area=area, detail=detail, hint=hint)
    try:
        yield
    finally:
        end_correction(user_id)


def guard_is_on() -> bool:
    return _is_enabled()


def _looks_spanish(text: str) -> bool:
    sample = (text or "").strip()
    if not sample or _EN_BRIEF.search(sample):
        return False
    if re.search(r"[áéíóúñü]", sample, re.IGNORECASE):
        return True
    words = re.findall(r"[a-záéíóúñ]{3,}", sample.casefold())
    if not words:
        return False
    english = sum(1 for word in words if word in _EN_WORDS)
    if english >= 2:
        return False
    markers = sum(1 for word in words if word in _SPANISH_MARKERS)
    if markers >= 2:
        return True
    return english == 0 and len(words) >= 6


def _folded(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\wáéíóúñ ]", "", (text or "").casefold())).strip()


def _image_brief_drift_core(produced: str, requested: str) -> bool:
    req = (requested or "").strip()
    used = (produced or "").strip()
    if len(req) < 8 or not used:
        return False
    from app.services.chat_image_generation import (
        image_prompt_covers_request,
        voice_prompt_is_mismatch,
    )
    from app.services.copy_quality import (
        extract_image_visual_constraints,
        extract_literal_on_image_copy,
        prompt_honors_visual_constraints,
    )

    constraints = extract_image_visual_constraints(req)
    if constraints and not prompt_honors_visual_constraints(used, constraints):
        return True

    folded = _folded(used)
    long_literals = [
        quote.strip()
        for quote in extract_literal_on_image_copy(req)
        if len(_folded(quote)) >= 8
    ]
    if long_literals:
        return any(_folded(quote) not in folded for quote in long_literals)
    if voice_prompt_is_mismatch(used, req):
        return True
    if _looks_spanish(used) and _looks_spanish(req) and not image_prompt_covers_request(used, req):
        return True
    return False


def image_brief_needs_correction(produced: str, requested: str) -> bool:
    """Centinela imagen — siempre activo en el pipeline (no requiere guardia admin)."""
    return _image_brief_drift_core(produced, requested)


def brief_drifts_from_request(produced: str, requested: str) -> bool:
    """True con la guardia activa (PDF/imagen en chat con sentinel UI)."""
    if not _is_enabled():
        return False
    return _image_brief_drift_core(produced, requested)


def build_image_sentinel_brief(produced: str, requested: str) -> str:
    """Re-brief anclado al pedido + reglas tipográficas y de color."""
    from app.services.copy_quality import literal_typography_locks

    base = anchored_brief(produced, requested)
    locks = literal_typography_locks(requested)
    if locks and locks not in base:
        return f"{base}\n\n{locks}"[:3800]
    return base


def anchored_brief(produced: str, requested: str) -> str:
    """Devuelve el brief otra vez, anclado a lo que el usuario pidió."""
    req = (requested or "").strip()
    used = (produced or "").strip()
    from app.services.copy_quality import extract_literal_on_image_copy

    folded = _folded(used)
    missing = [
        quote.strip()
        for quote in extract_literal_on_image_copy(req)
        if len(_folded(quote)) >= 8 and _folded(quote) not in folded
    ]
    if missing:
        labels = "; ".join(missing[:5])
        return f"{used}\n\nTEXTOS EXACTOS pedidos por el usuario, sin cambiarlos: {labels}."[:3800]
    return f"Pedido exacto del usuario, no lo cambies: {req}\n\n{used}"[:3800]


def _ping_waiting_screen(user_id: str, hint: str) -> None:
    """Si hay una llamada de voz, el hilo muestra el mismo estado que el chat."""
    try:
        from app.services import voice_client_session as vcs

        if user_id not in vcs._sessions:
            return
        vcs.push_tool_event(
            user_id,
            {
                "type": "generating_image",
                "status": hint or CORRECTING_HINT,
            },
        )
    except Exception:  # noqa: BLE001
        return


def note_error(area: str, title: str, detail: str = "", *, quiet: bool = False) -> None:
    if not _is_enabled():
        return
    clean_title = " ".join((title or "").split())[:180] or "Error del proceso"
    key = ("error", area, clean_title)
    now = time.monotonic()
    with _lock:
        seen = _error_seen.get(key)
        if seen is not None and now - seen < ERROR_DEDUP_SEC:
            return
        _error_seen[key] = now
    _append_event(
        kind="error",
        area=area,
        level="error",
        title=clean_title,
        detail=(detail or "")[:400],
        quiet=quiet,
    )


def note_warning(area: str, title: str, detail: str = "", *, quiet: bool = False) -> None:
    """Anomalías menores (WARNING en logs de voz, tools lentas, etc.)."""
    if not _is_enabled():
        return
    clean_title = " ".join((title or "").split())[:180] or "Aviso"
    key = ("warn", area, clean_title)
    now = time.monotonic()
    with _lock:
        seen = _error_seen.get(key)
        if seen is not None and now - seen < WARN_DEDUP_SEC:
            return
        _error_seen[key] = now
    _append_event(
        kind="warn",
        area=area,
        level="watch",
        title=clean_title,
        detail=(detail or "")[:400],
        quiet=quiet,
    )


class _SentinelLogHandler(logging.Handler):
    """Anota ERROR/WARNING de voz y del proceso en la bitácora."""

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("ced.sentinel"):
            return
        area = _area_for_logger(record.name)
        try:
            if record.levelno >= logging.ERROR:
                note_error(area, record.getMessage(), record.name, quiet=True)
                return
            if record.levelno >= logging.WARNING and _logger_is_voice_scope(record.name):
                note_warning(area, record.getMessage(), record.name, quiet=True)
        except Exception:  # noqa: BLE001
            return


def _logger_is_voice_scope(name: str) -> bool:
    lowered = (name or "").lower()
    return any(marker in lowered for marker in _WARN_LOGGER_MARKERS)


def _area_for_logger(name: str) -> str:
    lowered = (name or "").lower()
    if "retell" in lowered or "voice" in lowered:
        return "voz"
    if "stripe" in lowered or "billing" in lowered:
        return "pagos"
    if "image" in lowered or "gemini" in lowered:
        return "imagen"
    if "pdf" in lowered:
        return "pdf"
    return "sistema"


def _install_handler() -> None:
    global _handler_installed
    if _handler_installed:
        return
    handler = _SentinelLogHandler(level=logging.WARNING)
    logging.getLogger().addHandler(handler)
    _handler_installed = True


def _db_ready() -> bool:
    try:
        from app.services.supabase_client import service_role_configured

        return service_role_configured()
    except Exception:  # noqa: BLE001
        return False


def _client():
    from app.services.supabase_client import get_supabase_admin

    return get_supabase_admin()


def _event_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or ""),
        "at": row.get("created_at"),
        "kind": row.get("kind") or "change",
        "area": row.get("area") or "sistema",
        "level": row.get("level") or "watch",
        "title": row.get("title") or "",
        "detail": row.get("detail") or "",
        "latency_ms": row.get("latency_ms"),
    }


def _load_persisted() -> None:
    if not _db_ready():
        with _lock:
            _state["persistent"] = False
        return
    try:
        client = _client()
        state_res = (
            client.table("ced_sentinel_state")
            .select("enabled,enabled_at,checked_at,checks")
            .eq("id", "main")
            .limit(1)
            .execute()
        )
        ev_res = (
            client.table("ced_sentinel_events")
            .select("id,created_at,kind,area,level,title,detail,latency_ms")
            .order("created_at", desc=True)
            .limit(EVENT_LIMIT)
            .execute()
        )
    except Exception:  # noqa: BLE001
        logger.warning("[SENTINEL] sin persistencia — aplica la migración 045")
        with _lock:
            _state["persistent"] = False
        return
    rows = state_res.data or []
    loaded = [_event_from_row(row) for row in reversed(ev_res.data or [])]
    with _lock:
        _state["persistent"] = True
        if rows:
            row = rows[0]
            _state["enabled"] = bool(row.get("enabled"))
            _state["enabled_at"] = row.get("enabled_at")
            _state["checked_at"] = row.get("checked_at")
            checks = row.get("checks") or []
            _state["checks"] = checks if isinstance(checks, list) else []
        _events[:] = loaded


def _save_state() -> None:
    if not _db_ready():
        with _lock:
            _state["persistent"] = False
        return
    with _lock:
        payload = {
            "id": "main",
            "enabled": bool(_state["enabled"]),
            "enabled_at": _state.get("enabled_at"),
            "checked_at": _state.get("checked_at"),
            "checks": list(_state.get("checks") or []),
            "updated_at": _iso(),
        }
    try:
        _client().table("ced_sentinel_state").upsert(payload, on_conflict="id").execute()
    except Exception:  # noqa: BLE001
        logger.warning("[SENTINEL] no se pudo guardar el estado")
        with _lock:
            _state["persistent"] = False
        return
    with _lock:
        _state["persistent"] = True


def _save_event(event: dict[str, Any], *, quiet: bool = False) -> None:
    if not _db_ready():
        return
    try:
        _client().table("ced_sentinel_events").insert(
            {
                "id": event["id"],
                "created_at": event["at"],
                "kind": event["kind"],
                "area": event["area"],
                "level": event["level"],
                "title": event["title"],
                "detail": event["detail"],
                "latency_ms": event.get("latency_ms"),
            }
        ).execute()
    except Exception:  # noqa: BLE001
        if not quiet:
            logger.warning("[SENTINEL] no se pudo guardar un evento")
        with _lock:
            _state["persistent"] = False


def _append_event(
    *,
    kind: str,
    area: str,
    level: str,
    title: str,
    detail: str = "",
    latency_ms: int | None = None,
    quiet: bool = False,
) -> None:
    event = {
        "id": str(uuid4()),
        "at": _iso(),
        "kind": kind,
        "area": area,
        "level": level,
        "title": title[:180],
        "detail": (detail or "")[:400],
        "latency_ms": latency_ms,
    }
    with _lock:
        _events.append(event)
        if len(_events) > EVENT_LIMIT:
            del _events[: len(_events) - EVENT_LIMIT]
    _save_event(event, quiet=quiet)


def _timed(area: str, fn) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = fn()
    except Exception as exc:  # noqa: BLE001
        result = {
            "level": "error",
            "title": "Fallo al revisar",
            "detail": str(exc)[:180],
        }
    latency = int((time.perf_counter() - started) * 1000)
    if not isinstance(result, dict):
        result = {"level": "error", "title": "Fallo al revisar", "detail": area}
    result["area"] = area
    result["latency_ms"] = latency
    result["level"] = result.get("level") if result.get("level") in ("ok", "watch", "error") else "watch"
    result["title"] = str(result.get("title") or area)[:180]
    result["detail"] = str(result.get("detail") or "")[:400]
    return result


def _bounded(fn, timeout: float = 12.0) -> dict[str, Any]:
    from concurrent.futures import ThreadPoolExecutor
    from concurrent.futures import TimeoutError as FuturesTimeout

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn)
        try:
            result = future.result(timeout=timeout)
        except FuturesTimeout:
            return {"ok": False, "error": "timeout"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)[:180]}
    return result if isinstance(result, dict) else {"ok": False, "error": "respuesta_invalida"}


def _check_voice() -> dict[str, Any]:
    from app.services.retell_provider_health import snapshot

    snap = snapshot()
    voice = str(snap.get("voice") or "unknown")
    err = str(snap.get("last_error") or "")[:180]
    if voice == "ok":
        return {"level": "ok", "title": "Voz operativa", "detail": "El proveedor responde."}
    if voice == "billing":
        return {
            "level": "error",
            "title": "Voz sin saldo",
            "detail": err or "El proveedor rechazó por facturación.",
        }
    if voice == "down":
        return {
            "level": "error",
            "title": "Voz caída",
            "detail": err or "La API de voz no responde.",
        }
    if voice == "unconfigured":
        return {
            "level": "watch",
            "title": "Voz sin configurar",
            "detail": err or "Falta la clave del proveedor.",
        }
    return {
        "level": "watch",
        "title": "Voz sin sonda reciente",
        "detail": "Aún no hay una lectura del proveedor.",
    }


def _check_payments() -> dict[str, Any]:
    from app.services.integrations import check_stripe

    result = check_stripe()
    if result.get("ok"):
        mode = "cobros reales" if result.get("livemode") else "modo prueba"
        return {"level": "ok", "title": "Pagos operativos", "detail": f"Stripe responde ({mode})."}
    return {
        "level": "error",
        "title": "Pagos con fallo",
        "detail": str(result.get("error") or "Stripe no responde")[:180],
    }


def _check_data() -> dict[str, Any]:
    from app.services.integrations import check_supabase, check_supabase_auth

    db = check_supabase()
    auth = check_supabase_auth()
    if db.get("ok") and auth.get("ok"):
        return {"level": "ok", "title": "Datos operativos", "detail": "Base y login responden."}
    bits: list[str] = []
    if not db.get("ok"):
        bits.append(f"base: {db.get('error') or 'fallo'}")
    if not auth.get("ok"):
        bits.append(f"login: {auth.get('error') or 'fallo'}")
    return {"level": "error", "title": "Datos con fallo", "detail": " · ".join(bits)[:180]}


def _live_model_report() -> dict[str, Any] | None:
    global _sweep_n
    if _sweep_n != 1 and _sweep_n % LIVE_MODEL_EVERY != 0:
        return None
    from app.services.integrations import check_anthropic, check_gemini

    gemini = _bounded(check_gemini)
    claude = _bounded(check_anthropic)
    if gemini.get("ok") and claude.get("ok"):
        return {
            "level": "ok",
            "title": "Modelos responden",
            "detail": "Gemini y Claude contestaron la sonda.",
        }
    failed = []
    if not gemini.get("ok"):
        failed.append(f"Gemini: {gemini.get('error') or 'fallo'}")
    if not claude.get("ok"):
        failed.append(f"Claude: {claude.get('error') or 'fallo'}")
    level = "error" if len(failed) == 2 else "watch"
    title = "Modelos sin respuesta" if level == "error" else "Un modelo falló la sonda"
    return {"level": level, "title": title, "detail": " · ".join(failed)[:180]}


def _check_models() -> dict[str, Any]:
    from app.config import get_settings
    from app.services.ced_sentinel_expectations import voice_stack_report

    live = _live_model_report()
    stack = voice_stack_report()
    voice_line = stack.get("voz_conversacion") or ""
    if live is not None:
        live = dict(live)
        live["detail"] = f"{live.get('detail', '')} · {voice_line}"[:400]
        return live
    settings = get_settings()
    missing = []
    if not settings.google_api_key.strip():
        missing.append("Gemini")
    if not settings.anthropic_api_key.strip():
        missing.append("Claude")
    if not settings.openai_api_key.strip():
        missing.append("OpenAI")
    if missing:
        return {
            "level": "watch",
            "title": "Modelos incompletos",
            "detail": ("Falta clave: " + ", ".join(missing) + f" · {voice_line}")[:400],
        }
    return {
        "level": "ok",
        "title": "Modelos configurados",
        "detail": (
            "Claves presentes; sonda Gemini+Claude cada 15 min. " + voice_line
        )[:400],
    }


def _check_piloto() -> dict[str, Any]:
    from app.services.ced_sentinel_expectations import audit_voice_pilot_config

    return audit_voice_pilot_config()


def _check_herramientas() -> dict[str, Any]:
    from app.services.ced_sentinel_expectations import audit_voice_tools_parity

    audit = audit_voice_tools_parity()
    if audit.get("ok"):
        return {
            "level": "ok",
            "title": "Tools de voz cableadas",
            "detail": f"{audit['tool_count']} tools = {audit['route_count']} rutas HTTP.",
        }
    missing = audit.get("missing_routes") or []
    extra = audit.get("extra_routes") or []
    bits = []
    if missing:
        bits.append("sin ruta: " + ", ".join(missing[:6]))
    if extra:
        bits.append("ruta huérfana: " + ", ".join(extra[:6]))
    return {
        "level": "error",
        "title": "Tools de voz desalineadas",
        "detail": " · ".join(bits)[:400],
    }


def _check_runtime_voz() -> dict[str, Any]:
    from app.services.retell_native_pilot import recent_native_tool_failures

    fails = recent_native_tool_failures(window_sec=3600.0, limit=6)
    if not fails:
        return {
            "level": "ok",
            "title": "Runtime voz limpio",
            "detail": "Sin fallos de tools nativas en la última hora.",
        }
    names = sorted({str(f.get("tool") or "?") for f in fails})
    sample = fails[0]
    preview = str(sample.get("query_preview") or "")[:80]
    return {
        "level": "watch",
        "title": "Tools fallaron en voz",
        "detail": (
            f"{len(fails)} fallo(s) reciente(s): {', '.join(names)}. "
            f"Ej.: {preview or 'sin preview'}"
        )[:400],
    }


def sweep() -> list[dict[str, Any]]:
    """Una pasada. Pensada para el hilo de guardia, no para el request."""
    global _sweep_n
    if not _is_enabled():
        return []
    with _lock:
        _sweep_n += 1
        previous = {
            str(item.get("area")): str(item.get("level"))
            for item in (_state.get("checks") or [])
            if isinstance(item, dict)
        }
    checks = [
        _timed("voz", _check_voice),
        _timed("pagos", _check_payments),
        _timed("datos", _check_data),
        _timed("modelos", _check_models),
        _timed("piloto", _check_piloto),
        _timed("herramientas", _check_herramientas),
        _timed("runtime_voz", _check_runtime_voz),
    ]
    with _lock:
        _state["checks"] = checks
        _state["checked_at"] = _iso()
    for item in checks:
        area = str(item["area"])
        level = str(item["level"])
        if previous.get(area) == level:
            continue
        _append_event(
            kind="change",
            area=area,
            level=level,
            title=str(item["title"]),
            detail=str(item["detail"]),
            latency_ms=int(item["latency_ms"]),
        )
    _save_state()
    return checks


def _thread_main() -> None:
    logger.info("[SENTINEL] guardia activa")
    while not _stop.is_set():
        if not _is_enabled():
            break
        try:
            sweep()
        except Exception:  # noqa: BLE001
            logger.exception("[SENTINEL] pasada falló")
        if _stop.wait(PROBE_INTERVAL_SEC):
            break
    with _lock:
        _state["running"] = False
    logger.info("[SENTINEL] guardia detenida")


def _start_thread() -> None:
    global _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            _state["running"] = True
            return
        _stop.clear()
        _state["running"] = True
        _thread = threading.Thread(target=_thread_main, name="ced-sentinel", daemon=True)
        _thread.start()


def public_status() -> dict[str, Any]:
    from app.services.ced_sentinel_expectations import SYSTEM_EXPECTATIONS, voice_stack_report

    with _lock:
        running = bool(_state["enabled"] and _thread is not None and _thread.is_alive())
        _state["running"] = running
        return {
            "enabled": bool(_state["enabled"]),
            "running": running,
            "persistent": bool(_state["persistent"]),
            "enabled_at": _state.get("enabled_at"),
            "checked_at": _state.get("checked_at"),
            "checks": list(_state.get("checks") or []),
            "events": list(reversed(_events)),
            "expectations": list(SYSTEM_EXPECTATIONS),
            "voice_stack": voice_stack_report(),
        }


def set_enabled(enabled: bool) -> dict[str, Any]:
    _install_handler()
    now = _iso()
    with _lock:
        _state["enabled"] = bool(enabled)
        if enabled:
            _state["enabled_at"] = now
        else:
            _state["running"] = False
    if enabled:
        _stop.clear()
        _append_event(
            kind="guard",
            area="centinela",
            level="ok",
            title="Guardia activada",
            detail="Sigue revisando aunque el teléfono esté apagado.",
        )
        _save_state()
        _start_thread()
    else:
        _append_event(
            kind="guard",
            area="centinela",
            level="watch",
            title="Guardia apagada",
            detail="Dejó de consultar. La bitácora anterior sigue visible.",
        )
        _save_state()
        _stop.set()
    return public_status()


def resume_if_enabled() -> None:
    """Llamar desde el arranque del API."""
    _install_handler()
    _load_persisted()
    if _is_enabled():
        _stop.clear()
        _start_thread()
        logger.info("[SENTINEL] reanudado desde el estado guardado")


def stop_monitor() -> None:
    _stop.set()
    with _lock:
        _state["running"] = False
