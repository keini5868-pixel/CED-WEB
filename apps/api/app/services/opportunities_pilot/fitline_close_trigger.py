"""Disparador de cierre estratégico FitLine tras N preguntas."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

FITLINE_QUESTIONS_BEFORE_CLOSER = 3

_QUESTIONISH = re.compile(
    r"(?is)(?:\?|¿|"
    r"\b(?:qu[eé]|c[oó]mo|cu[aá]ndo|d[oó]nde|por\s+qu[eé]|cu[aá]nto|"
    r"qui[eé]n|cu[aá]l|puedo|podr[ií]a|es\s+posible|explica|dime|"
    r"c[oó]mo\s+empiezo|vale\s+la\s+pena|funciona)\b)",
)

_FITLINE_CLOSE_AFTER_QUESTIONS = """
# CIERRE ESTRATÉGICO — MOMENTO DE PROYECCIÓN (OBLIGATORIO ESTE TURNO)
El usuario ya hizo varias preguntas sobre PM/FitLine. Deja de solo «responder dudas»
y pasa a asesoría de cierre con psicología de proyección a futuro.

En ESTA respuesta (tono profesional, cálido, sin presión agresiva):
1) Resume en 1–2 frases el valor que ya exploraron (producto/negocio/expansión América
   o el tema concreto que preguntó).
2) Haz UNA pregunta de proyección, en este espíritu (adapta el trato Señor/Señora):
   «Te quiero hacer una pregunta: ¿cómo te ves en el futuro con esta gran oportunidad?
   ¿Quieres que te ayude a estructurar un plan de acción que guardaremos en el módulo
   de Finanzas, para revisarlo juntos cuando quieras y empecemos a trabajar enfocados
   en eso?»
3) Si acepta o muestra interés: usa guardar_plan_crecimiento_franquicia con metas/pasos
   concretos (expansión América, consumo propio, prospección, seguimiento) y menciona
   que quedará en Finanzas para revisarlo después.
4) Puedes tocar un hecho de expansión americana / respaldo de la empresa SOLO si encaja
   natural — no listes cifras de golpe.
5) PROHIBIDO telemarketing, «compra ya», inventar Income Plan/precios, o repetir este
   pitch en cada turno si ya lo ofreciste y rechazó.
""".strip()


def _is_fitline_question(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 8:
        return False
    try:
        from app.services.opportunities_pilot.fitline_knowledge import (
            wants_fitline_knowledge,
        )

        if not wants_fitline_knowledge(t):
            return False
    except Exception:  # noqa: BLE001
        return False
    # Contar turnos sustantivos FitLine; exigir señal de pregunta o longitud útil
    if _QUESTIONISH.search(t) or len(t) >= 40:
        return True
    return False


def get_engagement(user_id: str) -> dict[str, Any]:
    uid = (user_id or "").strip()
    if not uid:
        return {"question_count": 0, "closer_offered": False}
    # Memoria de proceso (fallback si la migración aún no corre en Supabase).
    try:
        from app.services import voice_client_session as vcs

        sess = vcs._get(uid)
        mem_count = int(sess.get("fitline_question_count") or 0)
        mem_offered = bool(sess.get("fitline_closer_offered"))
    except Exception:  # noqa: BLE001
        mem_count, mem_offered = 0, False

    try:
        from app.services import supabase_db

        result = (
            supabase_db._client()
            .table("ced_fitline_engagement")
            .select("question_count, closer_offered")
            .eq("user_id", uid)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return {"question_count": mem_count, "closer_offered": mem_offered}
        row = rows[0]
        return {
            "question_count": max(mem_count, int(row.get("question_count") or 0)),
            "closer_offered": mem_offered or bool(row.get("closer_offered")),
        }
    except Exception:  # noqa: BLE001
        logger.warning("[FITLINE-CLOSE] get_engagement DB unavailable — using session")
        return {"question_count": mem_count, "closer_offered": mem_offered}


def _upsert_engagement(
    user_id: str, *, question_count: int, closer_offered: bool
) -> None:
    from datetime import datetime, timezone

    # Siempre espejo en sesión de voz (funciona aunque falte la tabla).
    # Patrón: _get() fuera del lock; actualizar dentro (Lock no es reentrante).
    try:
        from app.services import voice_client_session as vcs

        sess = vcs._get(user_id)
        with vcs._lock:
            sess["fitline_question_count"] = max(0, int(question_count))
            sess["fitline_closer_offered"] = bool(closer_offered)
            sess["updated_at"] = vcs._now()
    except Exception:  # noqa: BLE001
        pass

    from app.services import supabase_db

    try:
        supabase_db._client().table("ced_fitline_engagement").upsert(
            {
                "user_id": user_id,
                "question_count": max(0, int(question_count)),
                "closer_offered": bool(closer_offered),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="user_id",
        ).execute()
    except Exception:  # noqa: BLE001
        logger.warning("[FITLINE-CLOSE] upsert DB skipped — session fallback active")


def register_fitline_user_turn(user_id: str | None, user_text: str) -> dict[str, Any]:
    """Incrementa contador si es pregunta FitLine. Devuelve estado actual."""
    uid = (user_id or "").strip()
    state = {"question_count": 0, "closer_offered": False, "should_inject_closer": False}
    if not uid or not _is_fitline_question(user_text):
        if uid:
            eng = get_engagement(uid)
            state.update(eng)
            state["should_inject_closer"] = (
                eng["question_count"] >= FITLINE_QUESTIONS_BEFORE_CLOSER
                and not eng["closer_offered"]
            )
        return state

    eng = get_engagement(uid)
    count = int(eng.get("question_count") or 0) + 1
    offered = bool(eng.get("closer_offered"))
    _upsert_engagement(uid, question_count=count, closer_offered=offered)
    should = count >= FITLINE_QUESTIONS_BEFORE_CLOSER and not offered
    return {
        "question_count": count,
        "closer_offered": offered,
        "should_inject_closer": should,
    }


def mark_closer_offered(user_id: str | None) -> None:
    uid = (user_id or "").strip()
    if not uid:
        return
    eng = get_engagement(uid)
    _upsert_engagement(
        uid,
        question_count=int(eng.get("question_count") or 0),
        closer_offered=True,
    )


def append_fitline_close_trigger_if_needed(
    system: str,
    user_id: str | None,
    user_text: str,
) -> str:
    """Registra el turno y, tras 3 preguntas FitLine, inyecta overlay de cierre."""
    base = system or ""
    uid = (user_id or "").strip()
    if not uid:
        return base
    try:
        state = register_fitline_user_turn(uid, user_text)
        if not state.get("should_inject_closer"):
            return base
        mark_closer_offered(uid)
        return f"{base}\n\n{_FITLINE_CLOSE_AFTER_QUESTIONS}".strip()
    except Exception:  # noqa: BLE001
        logger.exception("[FITLINE-CLOSE] append failed")
        return base
