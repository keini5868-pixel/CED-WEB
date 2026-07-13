"""Modo avanzado (Claude) — piloto Retell nativo."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.services import voice_client_session as vcs
from app.services.claude_deep_analysis import consultar_sistema_avanzado

logger = logging.getLogger(__name__)

# Activación v1: solo esta frase (variantes se agregarán tras prueba).
_ACTIVATE_RE = re.compile(r"\bactiva(?:r)?\s+modo\s+avanzado\b", re.I)

_DEACTIVATE_RE = re.compile(
    r"\b("
    r"modo\s+normal|"
    r"sal(?:ga|ir)?\s+del\s+modo\s+avanzado|"
    r"vuelve?\s+al\s+modo\s+normal|"
    r"desactiva(?:r)?\s+modo\s+avanzado|"
    r"apaga(?:r)?\s+modo\s+avanzado|"
    r"sal(?:ga|ir)?\s+del\s+modo\s+avanzado|"
    r"salir\s+del\s+avanzado"
    r")\b",
    re.I,
)


def is_advanced_activate_phrase(text: str) -> bool:
    return bool(_ACTIVATE_RE.search((text or "").strip()))


def is_advanced_deactivate_phrase(text: str) -> bool:
    return bool(_DEACTIVATE_RE.search((text or "").strip()))


def activate_advanced_mode(user_id: str) -> dict[str, Any]:
    if vcs.is_advanced_mode_active(user_id):
        return {
            "ok": True,
            "status": "already_active",
            "spoken": "Modo avanzado ya activo, señor. Adelante con su consulta.",
            "transition": "transition_to_advanced_mode_active",
        }
    vcs.set_advanced_mode_active(user_id, True)
    logger.info("[ADVANCED] activated user=%s", user_id[:8])
    return {
        "ok": True,
        "status": "advanced_active",
        "spoken": (
            "Modo avanzado activado, señor. "
            "Puedo investigar con más profundidad. ¿Cuál es su consulta?"
        ),
        "transition": "transition_to_advanced_mode_active",
    }


def deactivate_advanced_mode(user_id: str) -> dict[str, Any]:
    was_active = vcs.is_advanced_mode_active(user_id)
    vcs.set_advanced_mode_active(user_id, False)
    logger.info("[ADVANCED] deactivated user=%s was=%s", user_id[:8], was_active)
    return {
        "ok": True,
        "status": "advanced_inactive",
        "spoken": "De vuelta en modo conversacional, señor.",
        "transition": "transition_to_general_assistant",
    }


def consult_advanced(user_id: str, query: str) -> dict[str, Any]:
    topic = (query or "").strip()
    if not topic:
        return {
            "ok": False,
            "status": "needs_query",
            "spoken": "Señor, ¿qué desea que investigue en modo avanzado?",
        }

    if is_advanced_deactivate_phrase(topic):
        return deactivate_advanced_mode(user_id)

    if not vcs.is_advanced_mode_active(user_id):
        # Idempotente: activa y consulta en el mismo turno solo si pidieron consulta
        # sin haber activado — v1 exige activate previo; guía al usuario.
        return {
            "ok": False,
            "status": "not_active",
            "spoken": (
                "Señor, el modo avanzado no está activo. "
                "Diga «activa modo avanzado» primero."
            ),
            "transition": "transition_to_general_assistant",
        }

    vcs.record_advanced_consult(user_id, topic)
    result = consultar_sistema_avanzado(topic)
    if result.get("ok") and result.get("result"):
        spoken = str(result["result"]).strip()
        logger.info(
            "[ADVANCED] consult ok user=%s len=%s topic=%s",
            user_id[:8],
            len(spoken),
            topic[:60],
        )
        return {
            "ok": True,
            "status": "answered",
            "spoken": spoken,
        }

    err = str(result.get("error") or "Sin respuesta").strip()
    logger.warning("[ADVANCED] consult fail user=%s err=%s", user_id[:8], err[:120])
    return {
        "ok": False,
        "status": "error",
        "spoken": (
            "Señor, no pude completar el análisis avanzado en este momento. "
            "¿Desea que lo intente de nuevo?"
        ),
    }
