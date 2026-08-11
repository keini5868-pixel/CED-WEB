"""Context Caching de Google para conocimiento PM International / FitLine (voz Gemini).

Cachea el prompt estático Jarvis + ficha FitLine (~10k tokens) para cobrar input
cached ($0.03/1M) en lugar de full ($0.30/1M). Los overlays dinámicos del turno
siguen en system_instruction normal.

Si la API falla o el flag está off → el caller usa el system prompt inline.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from typing import Any

from google.genai import types

logger = logging.getLogger(__name__)

# Gemini 2.5 Flash exige ≥2048 tokens para explicit cache; FitLine+base lo supera.
_MIN_CACHE_CHARS = 6_000
_LOCK = threading.Lock()
_STATE: dict[str, Any] = {
    "name": None,
    "model": None,
    "fingerprint": None,
    "expires_at": 0.0,
}


def fitline_knowledge_needed(user_id: str | None, user_text: str) -> bool:
    """True cuando el turno de voz debe incluir ficha FitLine/PM."""
    query = (user_text or "").strip()
    uid = (user_id or "").strip()
    force = False
    if uid:
        try:
            from app.services.opportunities_pilot.fitline_guide_mode import (
                user_plan_is_fitline_focus,
            )

            force = user_plan_is_fitline_focus(uid)
        except Exception:  # noqa: BLE001
            force = False
    if force:
        return True
    if not query:
        return False
    try:
        from app.services.opportunities_pilot.fitline_knowledge import (
            wants_fitline_knowledge,
        )

        return wants_fitline_knowledge(query)
    except Exception:  # noqa: BLE001
        return False


def build_fitline_context_cache_text() -> str:
    """Texto estático a cachear: identidad Jarvis + conocimiento FitLine + playbook."""
    from app.domain.ced_sales_marketing_playbook import (
        append_sales_marketing_playbook_if_needed,
    )
    from app.services.opportunities_pilot.fitline_knowledge import (
        format_fitline_knowledge_for_prompt,
    )
    from app.services.voice_llm_common import _cached_base_voice_prompt

    core = (_cached_base_voice_prompt() or "").strip()
    block = (format_fitline_knowledge_for_prompt() or "").strip()
    if not block:
        return ""
    text = f"{core}\n\n{block}" if core else block
    text = append_sales_marketing_playbook_if_needed(text, "fitline pm international")
    return text.strip()


def _fingerprint(text: str, model: str) -> str:
    raw = f"{model}\n{text}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def _ttl_seconds() -> int:
    from app.config import get_settings

    ttl = int(get_settings().fitline_gemini_context_cache_ttl_sec or 3600)
    return max(300, min(ttl, 86_400))


def context_cache_enabled() -> bool:
    from app.config import get_settings

    return bool(get_settings().fitline_gemini_context_cache)


def ensure_fitline_cached_content(
    client: Any,
    model: str,
) -> str | None:
    """Crea o reutiliza CachedContent. Devuelve resource name o None."""
    if not context_cache_enabled() or client is None:
        return None
    model_name = (model or "").strip() or "gemini-2.5-flash"
    try:
        text = build_fitline_context_cache_text()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[FITLINE-CACHE] build text failed: %s", exc)
        return None
    if len(text) < _MIN_CACHE_CHARS:
        logger.info(
            "[FITLINE-CACHE] skip — texto corto chars=%s (min=%s)",
            len(text),
            _MIN_CACHE_CHARS,
        )
        return None

    fp = _fingerprint(text, model_name)
    ttl = _ttl_seconds()
    now = time.time()

    with _LOCK:
        if (
            _STATE["name"]
            and _STATE["model"] == model_name
            and _STATE["fingerprint"] == fp
            and now < float(_STATE["expires_at"] or 0) - max(60.0, ttl * 0.15)
        ):
            return str(_STATE["name"])

    try:
        cache = client.caches.create(
            model=model_name,
            config=types.CreateCachedContentConfig(
                display_name=f"ced-fitline-{fp[:10]}",
                system_instruction=text,
                ttl=f"{ttl}s",
            ),
        )
        name = getattr(cache, "name", None) or (cache.get("name") if isinstance(cache, dict) else None)
        if not name:
            logger.warning("[FITLINE-CACHE] create sin name")
            return None
        expire_time = getattr(cache, "expire_time", None)
        expires_at = now + ttl
        if expire_time is not None:
            try:
                expires_at = float(expire_time.timestamp())  # type: ignore[union-attr]
            except Exception:  # noqa: BLE001
                expires_at = now + ttl
        with _LOCK:
            old = _STATE.get("name")
            _STATE["name"] = str(name)
            _STATE["model"] = model_name
            _STATE["fingerprint"] = fp
            _STATE["expires_at"] = expires_at
        if old and old != name:
            try:
                client.caches.delete(name=old)
            except Exception:  # noqa: BLE001
                pass
        logger.info(
            "[FITLINE-CACHE] created name=%s chars=%s ttl=%ss model=%s",
            str(name)[:48],
            len(text),
            ttl,
            model_name,
        )
        return str(name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[FITLINE-CACHE] create failed: %s", exc)
        return None


def reset_fitline_cache_state_for_tests() -> None:
    with _LOCK:
        _STATE["name"] = None
        _STATE["model"] = None
        _STATE["fingerprint"] = None
        _STATE["expires_at"] = 0.0
