"""Retomar un trabajo de otra conversación.

El historial que ve el modelo está atado a `conversation_id`, así que al abrir un
hilo nuevo y decir «retomemos el guion» CED no tenía delante el guion: contestaba
algo fuera de contexto. Aquí se detecta esa intención y se le entrega el final de
la conversación anterior como contexto.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Frases con las que el usuario da por hecho que CED recuerda el trabajo previo.
_CONTINUITY_PATTERNS = (
    r"\bretoma(?:r|mos|ndo)?\b",
    r"\bcontinu(?:a|ar|emos|amos|ando)\b",
    r"\bsig(?:ue|amos|uiendo|uamos)\b",
    r"\bseguimos\b",
    r"\bvolvamos\b",
    r"\bterminemos\b",
    r"\bcerremos\b",
    r"\bcomo (?:te )?dec[ií]a\b",
    r"\b(?:lo|el|la|los|las) que (?:ya )?(?:hablamos|hicimos|ven[ií]amos|estabamos|est[áa]bamos)\b",
    r"\bconversaci[óo]n anterior\b",
    r"\bchat anterior\b",
    r"\bel (?:de|del) (?:antes|ayer|rato)\b",
    r"\b(?:ese|aquel|el) (?:mismo )?(?:guion|guión|gui[oó]n|texto|post|reel|video|v[ií]deo|carrusel|plan|script)\b",
    r"\bmi (?:guion|guión|texto|post|reel|video|v[ií]deo|carrusel|plan|script)\b",
    r"\bel (?:guion|guión) (?:que|de)\b",
)
_CONTINUITY_RE = re.compile("|".join(_CONTINUITY_PATTERNS), re.IGNORECASE)

# Con el hilo ya en marcha el modelo tiene su propio historial: no hace falta traer otro.
FRESH_THREAD_MAX_MESSAGES = 4
PREVIOUS_TURNS = 8
MAX_BLOCK_CHARS = 3_600


def wants_previous_thread(user_text: str) -> bool:
    text = (user_text or "").strip()
    if len(text) < 6:
        return False
    return bool(_CONTINUITY_RE.search(text))


def _format_turns(turns: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for row in turns:
        content = str((row or {}).get("content") or "").strip()
        if not content:
            continue
        who = "Usuario" if str(row.get("role") or "") == "user" else "CED"
        lines.append(f"{who}: {content}")
    body = "\n\n".join(lines)
    if len(body) > MAX_BLOCK_CHARS:
        # Recortar por el principio: el final es lo que se está retomando.
        body = "…\n\n" + body[-MAX_BLOCK_CHARS:]
    return body


def previous_thread_block(
    user_id: str,
    conversation_id: str | None,
    *,
    turns: int = PREVIOUS_TURNS,
) -> str:
    """Final de la última conversación distinta de la actual, como bloque de prompt."""
    from app.services import supabase_db

    uid = (user_id or "").strip()
    if not uid:
        return ""
    current = (conversation_id or "").strip()
    try:
        recent = supabase_db.list_conversations(uid, limit=6)
    except Exception:  # noqa: BLE001
        logger.warning("[CONTINUIDAD] no se pudo listar conversaciones user=%s", uid[:8])
        return ""
    for conv in recent:
        cid = str((conv or {}).get("id") or "").strip()
        if not cid or cid == current:
            continue
        try:
            msgs = supabase_db.get_conversation_messages(cid, uid, limit=40)
        except Exception:  # noqa: BLE001
            continue
        body = _format_turns(msgs[-turns:])
        if not body:
            continue
        title = str((conv or {}).get("title") or "").strip()
        header = "# CONTINUIDAD — LO QUE VENÍAN TRABAJANDO"
        if title:
            header += f" ({title[:60]})"
        logger.info("[CONTINUIDAD] hilo=%s aportado a user=%s", cid[:8], uid[:8])
        return (
            f"{header}\n"
            "Esto viene de la conversación anterior del usuario, no de este hilo.\n"
            "Es el material real: cuando pida retomar, ajustar o cerrar algo de aquí,\n"
            "trabaja SOBRE este texto en lugar de inventar uno nuevo. No lo repitas\n"
            "completo ni anuncies que lo recuperaste; simplemente continúa.\n\n"
            f"{body}"
        )
    return ""


def append_previous_thread_if_needed(
    system: str,
    user_id: str,
    user_text: str,
    conversation_id: str | None,
    history: list[dict[str, Any]] | None = None,
) -> str:
    """Antepone el contexto anterior cuando el turno da por hecho que CED lo recuerda.

    Va delante porque el system se recorta por el final (`_trim_system`).
    """
    if not wants_previous_thread(user_text):
        return system
    real_turns = [
        row
        for row in (history or [])
        if str((row or {}).get("content") or "").strip()
    ]
    if len(real_turns) > FRESH_THREAD_MAX_MESSAGES:
        return system
    try:
        block = previous_thread_block(user_id, conversation_id)
    except Exception:  # noqa: BLE001
        logger.warning("[CONTINUIDAD] falló el bloque user=%s", (user_id or "")[:8])
        return system
    if not block:
        return system
    return f"{block}\n\n{system}"
