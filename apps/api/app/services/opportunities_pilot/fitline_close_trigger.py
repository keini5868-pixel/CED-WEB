"""Disparador de cierre estratégico FitLine tras N preguntas."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

FITLINE_QUESTIONS_BEFORE_CLOSER = 3
# Tras «seguir aprendiendo», esperar al menos N preguntas FitLine más antes de reofrecer.
FITLINE_QUESTIONS_BEFORE_REOFFER = 2
_TURN_DEBOUNCE_SEC = 8.0

_QUESTIONISH = re.compile(
    r"(?is)(?:\?|¿|"
    r"\b(?:qu[eé]|c[oó]mo|cu[aá]ndo|d[oó]nde|por\s+qu[eé]|cu[aá]nto|"
    r"qui[eé]n|cu[aá]l|puedo|podr[ií]a|es\s+posible|explica|expl[ií]came|"
    r"dime|h[aá]blame|cu[eé]ntame|"
    r"c[oó]mo\s+empiezo|vale\s+la\s+pena|funciona)\b)",
)

_ACK_ONLY = re.compile(
    r"(?is)^(ok(?:ay)?|vale|s[ií]|gracias|hmm+|aja|aj[aá]|mm+|uh+\.?|"
    r"contin[uú]a|sigue|perfecto|entendido)[\s!.]*$"
)

_FOLLOWUP_FITLINE = re.compile(
    r"(?is)\b(?:"
    r"negocio|franquicia|ntc|producto|productos|c[oó]mo\s+se\s+gana|"
    r"c[oó]mo\s+empiezo|inscrib|socio|patrocin|equipo|comisi[oó]n|"
    r"ingreso|ganar|oportunidad|optimal|activize|restorate|power\s*cocktail|"
    r"expansi[oó]n|am[eé]rica|americano|sarasota|manatee|latam|"
    r"m[eé]xico|colombia|per[uú]|chile|espa[nñ]a|ee\.?\s*uu\.?|"
    r"pm[\s\-]?labs|made\s+in\s+usa|speyer|schengen|cologne"
    r")\b"
)

_INTEREST_RE = re.compile(
    r"(?is)\b(?:"
    r"me\s+interesa|quiero\s+entrar|unirme|inscrib|empezar|comienzo|"
    r"c[oó]mo\s+empiezo|vale\s+la\s+pena|ganar|ingreso|dinero|"
    r"negocio|franquicia|socio|patrocin|vender|venta|equipo|"
    r"oportunidad|plan\s+de\s+compensaci|cu[aá]nto\s+se\s+gana|"
    r"c[oó]mo\s+funciona\s+el\s+negocio"
    r")\b"
)

_NINETY_DAY_ANSWER = re.compile(
    r"(?is)\b(?:"
    r"90\s*d[ií]as|finanzas|ganar|"
    r"\d[\d.,]*\s*(?:mil|k|\$|usd|d[oó]lar|pesos?)|"
    r"meta\s+(?:de\s+)?(?:ingreso|dinero|venta)"
    r")\b"
)

# Evita contar el mismo texto dos veces si chat/voz arma el system dos veces.
_recent_turns: dict[str, tuple[str, float]] = {}

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
# CIERRE PRIORITARIO — META 90 DÍAS (OBLIGATORIO ESTE TURNO — PRIMERO EN EL PROMPT)
REGLA SIN AMBIGÜEDAD: el usuario ya hizo su 3.ª pregunta sobre PM/FitLine con interés
real. ESTE TURNO dejas el modo educativo y lanzas el cierre de 90 días.

PRIORIDAD ABSOLUTA (antes que modo guía, «cierre de impacto», «cierre de inversión»
u otras preguntas de avance):
1) Responde en 1–2 frases lo que preguntó ahora (si aplica). Nada de monólogo largo.
2) Di INMEDIATAMENTE, en voz alta / en el chat, ESTA pregunta (adapta Señor/Señora;
   NO la sustituyas ni la dejes para después):
   «¿Cuánto quieres ganar en los próximos 90 días si decides entrar en el negocio hoy?»
3) Justo después, habla de la herramienta de Finanzas: juntos pueden estructurar un
   plan de 90 días para tomar acción concreta en el negocio de PM International,
   revisar y medir resultados.
4) VOZ: máximo 2 frases + la pregunta LITERAL + 1 frase de Finanzas. Cero «¿más info?».
5) PROHIBIDO este turno: inventar cifras, % de comisión, bonos o Income Plan.
   Montos no cargados → patrocinador / Partner Area / back-office oficial.
6) PROHIBIDO este turno: modo guía pedagógico, «cierre de impacto», «cierre de
   inversión», pitch genérico u otras preguntas de avance.
A partir de ESTE turno pasas a modo vendedor-asesor (persuasión clara hacia una
decisión: Finanzas / OPPS / patrocinador). Sin acoso ni insistencia agresiva.
""".strip()

_FITLINE_SELLER_MODE = """
# MODO VENDEDOR FITLINE (DESPUÉS DE LA PREGUNTA DE 90 DÍAS)
Ya saliste del modo educativo. Ahora eres vendedor-asesor de PM/FitLine:
guía con intención clara de avanzar hacia una decisión (plan de 90 días en Finanzas,
inscripción vía OPPS, o hablar con quien le compartió la oportunidad).
Persuade con hechos de la ficha. Máximo UNA pregunta de avance por turno.
PROHIBIDO acosar, martillar o repetir la misma pregunta si pospone.
PROHIBIDO volver a enciclopedia neutra. PROHIBIDO inventar Income Plan / precios.
Si aún no respondió cuánto quiere ganar en 90 días, puedes retomar ESA pregunta
una vez, con naturalidad — no la sustituyas por otro cierre.
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


def _normalize_turn_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _same_turn_duplicate(user_id: str, text: str) -> bool:
    uid = (user_id or "").strip()
    norm = _normalize_turn_text(text)
    if not uid or not norm:
        return False
    prev = _recent_turns.get(uid)
    now = time.time()
    if prev and prev[0] == norm and (now - prev[1]) < _TURN_DEBOUNCE_SEC:
        return True
    _recent_turns[uid] = (norm, now)
    return False


def detects_real_interest(text: str, question_count: int) -> bool:
    """Interés real: 3 preguntas FitLine ya son engagement, o señales de negocio."""
    if int(question_count or 0) >= FITLINE_QUESTIONS_BEFORE_CLOSER:
        return True
    t = (text or "").strip()
    if len(t) < 8:
        return False
    return bool(_INTEREST_RE.search(t))


def looks_like_ninety_day_answer(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 2:
        return False
    return bool(_NINETY_DAY_ANSWER.search(t))


def _is_fitline_followup(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 8:
        return False
    return bool(_FOLLOWUP_FITLINE.search(t) and (_QUESTIONISH.search(t) or len(t) >= 16))


def _is_fitline_question(text: str, *, already_engaged: bool = False) -> bool:
    t = (text or "").strip()
    if len(t) < 6 or _ACK_ONLY.match(t):
        return False
    try:
        from app.services.opportunities_pilot.fitline_knowledge import (
            wants_fitline_knowledge,
        )

        branded = bool(wants_fitline_knowledge(t))
    except Exception:  # noqa: BLE001
        branded = False
    if branded:
        return True
    if already_engaged and _is_fitline_followup(t):
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
            "closer_reasked": False,
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
        mem_reasked = bool(sess.get("fitline_closer_reasked"))
    except Exception:  # noqa: BLE001
        mem_count, mem_offered, mem_learn, mem_since, mem_soft, mem_reasked = (
            0,
            False,
            False,
            0,
            False,
            False,
        )

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
                "closer_reasked": mem_reasked,
            }
        row = rows[0]
        return {
            "question_count": max(mem_count, int(row.get("question_count") or 0)),
            "closer_offered": mem_offered or bool(row.get("closer_offered")),
            "keep_learning": mem_learn,
            "questions_since_defer": mem_since,
            "soft_reoffer_done": mem_soft,
            "closer_reasked": mem_reasked,
        }
    except Exception:  # noqa: BLE001
        logger.warning("[FITLINE-CLOSE] get_engagement DB unavailable — using session")
        return {
            "question_count": mem_count,
            "closer_offered": mem_offered,
            "keep_learning": mem_learn,
            "questions_since_defer": mem_since,
            "soft_reoffer_done": mem_soft,
            "closer_reasked": mem_reasked,
        }


def _upsert_engagement(
    user_id: str,
    *,
    question_count: int,
    closer_offered: bool,
    keep_learning: bool | None = None,
    questions_since_defer: int | None = None,
    soft_reoffer_done: bool | None = None,
    closer_reasked: bool | None = None,
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
            if closer_reasked is not None:
                sess["fitline_closer_reasked"] = bool(closer_reasked)
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
        "should_inject_seller": False,
        "keep_learning": False,
        "should_inject_keep_learning": False,
        "should_soft_reoffer": False,
        "interest": False,
        "duplicate": False,
    }
    if not uid:
        return state

    eng = get_engagement(uid)
    keep = bool(eng.get("keep_learning"))
    since = int(eng.get("questions_since_defer") or 0)
    soft_done = bool(eng.get("soft_reoffer_done"))
    offered = bool(eng.get("closer_offered"))
    count = int(eng.get("question_count") or 0)
    reasked = bool(eng.get("closer_reasked"))
    duplicate = _same_turn_duplicate(uid, user_text)

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
                "interest": True,
                "duplicate": duplicate,
            }
        )
        return state

    already = count > 0
    is_q = _is_fitline_question(user_text, already_engaged=already)
    if is_q and not duplicate:
        count = count + 1
        if keep:
            since = since + 1

    interest = detects_real_interest(user_text, count)
    should_closer = (
        count >= FITLINE_QUESTIONS_BEFORE_CLOSER
        and interest
        and not keep
        and (
            not offered
            or (
                offered
                and not reasked
                and not looks_like_ninety_day_answer(user_text)
                and is_q
            )
        )
    )
    should_seller = (
        offered
        and not keep
        and not should_closer
        and not is_keep_learning_response(user_text)
    )
    should_soft = (
        keep
        and not soft_done
        and since >= FITLINE_QUESTIONS_BEFORE_REOFFER
        and offered
        and is_q
        and not duplicate
    )

    if is_q and not duplicate:
        _upsert_engagement(
            uid,
            question_count=count,
            closer_offered=offered,
            keep_learning=keep,
            questions_since_defer=since if keep else 0,
            soft_reoffer_done=soft_done,
            closer_reasked=reasked,
        )
        try:
            from app.services.referrals import note_activity

            note_activity(uid, "chat_sales")
            note_activity(uid, "voice_pm")
        except Exception:  # noqa: BLE001
            pass
    else:
        # Turno no contable: igual reportar si ya toca inyectar (p. ej. duplicate).
        pass

    logger.info(
        "[FITLINE-CLOSE] turn user=%s count=%s q=%s interest=%s offered=%s "
        "inject=%s dup=%s",
        uid[:8],
        count,
        is_q,
        interest,
        offered,
        should_closer,
        duplicate,
    )
    return {
        "question_count": count,
        "closer_offered": offered,
        "keep_learning": keep,
        "should_inject_closer": should_closer,
        "should_inject_seller": should_seller,
        "should_inject_keep_learning": False,
        "should_soft_reoffer": should_soft,
        "interest": interest,
        "duplicate": duplicate,
    }


def mark_closer_offered(user_id: str | None, *, reasked: bool = False) -> None:
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
        closer_reasked=True if reasked else bool(eng.get("closer_reasked")),
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


def guide_should_yield_to_closer(user_id: str | None) -> bool:
    """Modo guía no puede tapar el disparador de 90 días ni el modo vendedor."""
    uid = (user_id or "").strip()
    if not uid:
        return False
    try:
        eng = get_engagement(uid)
    except Exception:  # noqa: BLE001
        return False
    if bool(eng.get("keep_learning")):
        return False
    count = int(eng.get("question_count") or 0)
    offered = bool(eng.get("closer_offered"))
    return offered or count >= FITLINE_QUESTIONS_BEFORE_CLOSER


def _prepend_overlay(base: str, overlay: str) -> str:
    """El overlay va AL INICIO: los LLM priorizan el comienzo del system."""
    body = (base or "").strip()
    block = (overlay or "").strip()
    if not block:
        return body
    if not body:
        return block
    return f"{block}\n\n{body}"


def append_fitline_close_trigger_if_needed(
    system: str,
    user_id: str | None,
    user_text: str,
) -> str:
    """Registra el turno y, tras 3 preguntas FitLine con interés, inyecta el cierre."""
    base = system or ""
    uid = (user_id or "").strip()
    if not uid:
        return base
    try:
        from app.services.opportunities_pilot.fitline_knowledge import (
            is_fitline_topic_suppressed_for,
            sync_fitline_topic_preference,
        )

        sync_fitline_topic_preference(uid, user_text)
        if is_fitline_topic_suppressed_for(uid):
            return base
    except Exception:  # noqa: BLE001
        pass
    try:
        state = register_fitline_user_turn(uid, user_text)
        if state.get("should_inject_keep_learning"):
            return _prepend_overlay(base, _FITLINE_KEEP_LEARNING_OVERLAY)
        if state.get("should_inject_closer"):
            already = bool(state.get("closer_offered"))
            mark_closer_offered(uid, reasked=True)
            logger.info(
                "[FITLINE-CLOSE] INJECT 90d user=%s count=%s reask=%s",
                uid[:8],
                state.get("question_count"),
                already,
            )
            return _prepend_overlay(base, _FITLINE_CLOSE_AFTER_QUESTIONS)
        if state.get("should_soft_reoffer"):
            mark_soft_reoffer_done(uid)
            return _prepend_overlay(base, _FITLINE_SOFT_REOFFER)
        if state.get("should_inject_seller"):
            return _prepend_overlay(base, _FITLINE_SELLER_MODE)
        return base
    except Exception:  # noqa: BLE001
        logger.exception("[FITLINE-CLOSE] append failed")
        return base
