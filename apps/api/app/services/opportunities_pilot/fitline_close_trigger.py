"""Disparador de cierre estratégico FitLine tras N preguntas."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

FITLINE_QUESTIONS_BEFORE_CLOSER = 3
# Tras «seguir aprendiendo», esperar al menos N preguntas FitLine más antes de reofrecer.
FITLINE_QUESTIONS_BEFORE_REOFFER = 2

_QUESTIONISH = re.compile(
    r"(?is)(?:\?|¿|"
    r"\b(?:qu[eé]|c[oó]mo|cu[aá]ndo|d[oó]nde|por\s+qu[eé]|cu[aá]nto|"
    r"qui[eé]n|cu[aá]l|puedo|podr[ií]a|es\s+posible|explica|dime|"
    r"c[oó]mo\s+empiezo|vale\s+la\s+pena|funciona)\b)",
)

_KEEP_LEARNING = re.compile(
    r"(?is)\b(?:"
    r"seguir\s+aprendiendo|seguir\s+aprend|"
    r"todav[ií]a\s+(?:no|quiero\s+aprender|estoy\s+aprendiendo)|"
    r"quiero\s+(?:seguir\s+)?aprend|"
    r"no\s+(?:estoy\s+)?list[oa]|a[uú]n\s+no|"
    r"solo\s+(?:quiero\s+)?(?:aprender|informarme|entender)|"
    r"despu[eé]s\s+(?:veamos|decido|lo\s+veo)|"
    r"m[aá]s\s+(?:adelante|tarde)|no\s+ahora|"
    r"prefiero\s+(?:aprender|informarme)\s+primero"
    r")\b",
)

_FITLINE_CLOSE_AFTER_QUESTIONS = """
# CIERRE PRIORITARIO — META 90 DÍAS (OBLIGATORIO ESTE TURNO — PRIMERO)
El usuario ya hizo varias preguntas sobre PM/FitLine.

PRIORIDAD ABSOLUTA ESTE TURNO (antes que CUALQUIER otro guion de cierre):
1) Responde en 1–2 frases lo que preguntó ahora (si aplica).
2) Haz INMEDIATAMENTE esta pregunta (adapta Señor/Señora; no la sustituyas por
   «cierre de impacto», «cierre de inversión» ni otros pitches espontáneos):
   «¿Cuánto quieres ganar en los próximos 90 días si decides entrar en el negocio hoy?»
3) Justo después, invita a armar un plan de acción personalizado en el módulo de
   Finanzas para revisar y medir resultados juntos según avancen.
4) PROHIBIDO este turno: inventar cifras de dinero, % de comisión, bonos o Income Plan.
   Si pregunta por montos/comisiones no cargados: di con honestidad que varían y
   deben consultarse con el patrocinador / Partner Area / back-office oficial.
5) PROHIBIDO este turno: otros guiones de cierre («cierre de impacto»,
   «cierre de inversión», pitch de franquicia genérico, lista de objeciones) —
   esos solo DESPUÉS de este paso de 90 días + Finanzas, en turnos posteriores.
""".strip()

_FITLINE_KEEP_LEARNING_OVERLAY = """
# USUARIO QUIERE SEGUIR APRENDIENDO (NO INSISTIR ESTE TURNO)
El usuario no está listo para la meta de 90 días / plan ahora. NO repitas la pregunta
de 90 días ni la propuesta de Finanzas en ESTA respuesta.

Haz:
1) Acepta con naturalidad (1 frase) y continúa educando con hechos de la ficha PM/FitLine.
2) Responde su duda actual con valor real — sin presión.
3) PROHIBIDO inventar cifras de dinero, comisiones o bonos.

Más adelante (otro turno, cuando el ritmo lo permita — no de inmediato), puedes reabrir
hacia UNO de estos caminos, el que mejor encaje:
  A) Plan de acción estructurado en Finanzas (meta 90 días).
  B) Inscripción ese mismo día vía enlace de patrocinio en OPPS
     (abrir_oportunidades_fitline).
  C) Si no quiere decidir solo: comunicarse con la persona que le compartió
     la oportunidad / su patrocinador.
Lee el ritmo: orgánico, profesional, sin sonar repetitivo ni desesperado.
""".strip()

_FITLINE_SOFT_REOFFER = """
# REAPERTURA NATURAL DE CIERRE (SUAVE — NO FORZAR)
Ya educaste tras un «seguir aprendiendo». Si el turno encaja, reintroduce UNA sola
opción de avance (no las tres de golpe), con tono de asesor:
  A) «Cuando quieras, podemos fijar tu meta a 90 días y dejar el plan en Finanzas.»
  B) Inscripción hoy con el enlace de patrocinio en OPPS, si muestra urgencia/decisión.
  C) Hablar con quien le compartió la oportunidad, si duda en decidir solo.
PROHIBIDO inventar cifras/comisiones. PROHIBIDO martillar si vuelve a posponer.
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


def is_keep_learning_response(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 6:
        return False
    return bool(_KEEP_LEARNING.search(t))


def get_engagement(user_id: str) -> dict[str, Any]:
    uid = (user_id or "").strip()
    if not uid:
        return {
            "question_count": 0,
            "closer_offered": False,
            "keep_learning": False,
            "questions_since_defer": 0,
            "soft_reoffer_done": False,
        }
    # Memoria de proceso (fallback si la migración aún no corre en Supabase).
    try:
        from app.services import voice_client_session as vcs

        sess = vcs._get(uid)
        mem_count = int(sess.get("fitline_question_count") or 0)
        mem_offered = bool(sess.get("fitline_closer_offered"))
        mem_learn = bool(sess.get("fitline_keep_learning"))
        mem_since = int(sess.get("fitline_questions_since_defer") or 0)
        mem_soft = bool(sess.get("fitline_soft_reoffer_done"))
    except Exception:  # noqa: BLE001
        mem_count, mem_offered, mem_learn, mem_since, mem_soft = 0, False, False, 0, False

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
            return {
                "question_count": mem_count,
                "closer_offered": mem_offered,
                "keep_learning": mem_learn,
                "questions_since_defer": mem_since,
                "soft_reoffer_done": mem_soft,
            }
        row = rows[0]
        return {
            "question_count": max(mem_count, int(row.get("question_count") or 0)),
            "closer_offered": mem_offered or bool(row.get("closer_offered")),
            "keep_learning": mem_learn,
            "questions_since_defer": mem_since,
            "soft_reoffer_done": mem_soft,
        }
    except Exception:  # noqa: BLE001
        logger.warning("[FITLINE-CLOSE] get_engagement DB unavailable — using session")
        return {
            "question_count": mem_count,
            "closer_offered": mem_offered,
            "keep_learning": mem_learn,
            "questions_since_defer": mem_since,
            "soft_reoffer_done": mem_soft,
        }


def _upsert_engagement(
    user_id: str,
    *,
    question_count: int,
    closer_offered: bool,
    keep_learning: bool | None = None,
    questions_since_defer: int | None = None,
    soft_reoffer_done: bool | None = None,
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
            if keep_learning is not None:
                sess["fitline_keep_learning"] = bool(keep_learning)
            if questions_since_defer is not None:
                sess["fitline_questions_since_defer"] = max(0, int(questions_since_defer))
            if soft_reoffer_done is not None:
                sess["fitline_soft_reoffer_done"] = bool(soft_reoffer_done)
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
    state = {
        "question_count": 0,
        "closer_offered": False,
        "should_inject_closer": False,
        "keep_learning": False,
        "should_inject_keep_learning": False,
        "should_soft_reoffer": False,
    }
    if not uid:
        return state

    eng = get_engagement(uid)
    keep = bool(eng.get("keep_learning"))
    since = int(eng.get("questions_since_defer") or 0)
    soft_done = bool(eng.get("soft_reoffer_done"))
    offered = bool(eng.get("closer_offered"))
    count = int(eng.get("question_count") or 0)

    # Tras haber ofrecido el closer de 90 días, detectar «seguir aprendiendo».
    if offered and is_keep_learning_response(user_text):
        _upsert_engagement(
            uid,
            question_count=count,
            closer_offered=True,
            keep_learning=True,
            questions_since_defer=0,
            soft_reoffer_done=False,
        )
        state.update(
            {
                "question_count": count,
                "closer_offered": True,
                "keep_learning": True,
                "should_inject_keep_learning": True,
            }
        )
        return state

    if not _is_fitline_question(user_text):
        state.update(
            {
                "question_count": count,
                "closer_offered": offered,
                "keep_learning": keep,
            }
        )
        state["should_inject_closer"] = (
            count >= FITLINE_QUESTIONS_BEFORE_CLOSER and not offered and not keep
        )
        return state

    count = count + 1
    if keep:
        since = since + 1

    should_closer = (
        count >= FITLINE_QUESTIONS_BEFORE_CLOSER and not offered and not keep
    )
    should_soft = (
        keep
        and not soft_done
        and since >= FITLINE_QUESTIONS_BEFORE_REOFFER
        and offered
    )

    _upsert_engagement(
        uid,
        question_count=count,
        closer_offered=offered,
        keep_learning=keep,
        questions_since_defer=since if keep else 0,
        soft_reoffer_done=soft_done,
    )
    return {
        "question_count": count,
        "closer_offered": offered,
        "keep_learning": keep,
        "should_inject_closer": should_closer,
        "should_inject_keep_learning": False,
        "should_soft_reoffer": should_soft,
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
        keep_learning=bool(eng.get("keep_learning")),
        questions_since_defer=int(eng.get("questions_since_defer") or 0),
        soft_reoffer_done=bool(eng.get("soft_reoffer_done")),
    )


def mark_soft_reoffer_done(user_id: str | None) -> None:
    uid = (user_id or "").strip()
    if not uid:
        return
    eng = get_engagement(uid)
    _upsert_engagement(
        uid,
        question_count=int(eng.get("question_count") or 0),
        closer_offered=bool(eng.get("closer_offered")),
        keep_learning=bool(eng.get("keep_learning")),
        questions_since_defer=int(eng.get("questions_since_defer") or 0),
        soft_reoffer_done=True,
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
        if state.get("should_inject_keep_learning"):
            return f"{base}\n\n{_FITLINE_KEEP_LEARNING_OVERLAY}".strip()
        if state.get("should_inject_closer"):
            mark_closer_offered(uid)
            return f"{base}\n\n{_FITLINE_CLOSE_AFTER_QUESTIONS}".strip()
        if state.get("should_soft_reoffer"):
            mark_soft_reoffer_done(uid)
            return f"{base}\n\n{_FITLINE_SOFT_REOFFER}".strip()
        return base
    except Exception:  # noqa: BLE001
        logger.exception("[FITLINE-CLOSE] append failed")
        return base
