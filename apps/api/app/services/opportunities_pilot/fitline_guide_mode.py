"""Modo Guía FitLine/PM — mentor pedagógico paso a paso (voz, chat, avanzado).

No sustituye el conocimiento curado de Oportunidades: solo cambia el ritmo y
el tono de presentación (un bloque a la vez, confirmación antes de avanzar).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from app.services import voice_client_session as vcs

logger = logging.getLogger(__name__)

Channel = Literal["voice", "chat", "advanced"]

# ── Curriculum (mismo conocimiento FitLine; presentación progresiva) ─────────

GUIDE_STEPS: tuple[dict[str, str], ...] = (
    {
        "id": "intro",
        "title": "Cómo vamos a avanzar",
        "teach": (
            "Te voy a explicar el negocio de PM International / FitLine en tres "
            "bloques simples, uno a la vez: (1) qué es la empresa y sus productos, "
            "(2) cómo se gana dinero con el modelo, (3) cómo empezar si te interesa. "
            "Sin saturar con cifras ni jerga de golpe."
        ),
        "voice_teach": (
            "Te explico FitLine en tres bloques simples, uno a la vez: "
            "empresa y productos, cómo se gana, y cómo empezar. "
            "Sin saturar."
        ),
    },
    {
        "id": "company_products",
        "title": "Qué es la empresa y los productos",
        "teach": (
            "PM International es la empresa detrás de FitLine (nutrición y bienestar). "
            "Fundada en 1993 en Speyer, Alemania, por Rolf Sorg; sede actual en "
            "Schengen, Luxemburgo. Opera en 40–45+ países. "
            "La tecnología NTC lleva nutrientes cuándo y dónde el cuerpo los necesita. "
            "Productos cotidianos: Optimal-Set (rutina diaria), PowerCocktail, "
            "Activize (energía), Restorate (minerales), Basics (fibra/probióticos). "
            "Hay más líneas (deporte, peso, microSolve); ahora basta con la base. "
            "Calidad: Cologne List® anti-dopaje, GMP en Alemania, QR de análisis."
        ),
        "voice_teach": (
            "PM International hace FitLine: nutrición desde 1993. "
            "Hoy opera en muchos países, con sede en Luxemburgo. "
            "NTC lleva nutrientes al cuerpo de forma inteligente. "
            "Productos base: Optimal-Set, PowerCocktail, Activize, Restorate y Basics. "
            "Son de calidad alta, con certificación anti-dopaje."
        ),
    },
    {
        "id": "how_earn",
        "title": "Cómo se gana dinero",
        "teach": (
            "Se gana de dos formas combinadas: (1) vendiendo productos FitLine a "
            "clientes, y (2) construyendo un equipo de crecimiento (red de "
            "franquicias / socios de negocio) con ingresos residuales ligados al "
            "volumen de producto — no al mero hecho de invitar. "
            "Los porcentajes exactos y el Income Plan actualizado viven en el "
            "Partner Area / material de tu patrocinador: CED no inventa cifras. "
            "Piensa en una tienda + un equipo que crece contigo."
        ),
        "voice_teach": (
            "Ganas vendiendo producto y, si quieres, armando un equipo de socios. "
            "Los ingresos residuales van ligados a ventas de producto, no solo a invitar. "
            "Los porcentajes exactos los ves en Partner Area con tu mentor. "
            "CED no inventa esas cifras."
        ),
    },
    {
        "id": "how_start",
        "title": "Cómo empezar",
        "teach": (
            "Pasos prácticos: (1) conoce los productos base y elige tu narrativa, "
            "(2) confirma el paquete de entrada y el Income Plan con tu enlace de "
            "patrocinio / Partner Area, (3) regístrate vía tu mentor, "
            "(4) usa CED para copy, ideas y prospección con hechos reales de FitLine. "
            "No hay atajo mágico: producto + constancia + acompañamiento."
        ),
        "voice_teach": (
            "Para empezar: conoce los productos, confirma tu paquete con tu mentor "
            "en Partner Area, regístrate, y usa CED para copy y prospección. "
            "Producto y constancia primero."
        ),
    },
    {
        "id": "close",
        "title": "Cierre y siguiente paso",
        "teach": (
            "Con eso ya tienes el mapa básico. Puedes pedirme que profundice en un "
            "producto, practiquemos un pitch, o preparemos un mensaje de prospección. "
            "Si quieres salir del modo guía, di «salir del modo guía»."
        ),
        "voice_teach": (
            "Ese es el mapa básico. Puedo profundizar en un producto o armar un pitch. "
            "Para salir, di «salir del modo guía»."
        ),
    },
)

_ACTIVATE_RE = re.compile(
    r"(?is)\b(?:"
    r"modo\s+gu[ií]a|"
    r"activa(?:r)?\s+(?:el\s+)?modo\s+gu[ií]a|"
    r"expl[ií]ca(?:me)?\s+(?:c[oó]mo\s+funciona\s+)?(?:esto|el\s+negocio|fitline|pm)"
    r"\s+desde\s+cero|"
    r"expl[ií]ca(?:me)?\s+desde\s+cero|"
    r"gu[ií]a(?:me)?\s+desde\s+cero|"
    r"ens[eé][nñ]a(?:me)?\s+(?:el\s+negocio\s+)?desde\s+cero|"
    r"soy\s+nuev[oa]\b.{0,40}\b(?:gu[ií]a|expl[ií]ca|ense[nñ]a)|"
    r"soy\s+nuev[oa]\b.{0,40}\b(?:fitline|pm\s*international|al\s+negocio)|"
    r"no\s+s[eé]\s+nada\b.{0,40}\b(?:fitline|pm|negocio)|"
    r"empiezo\s+de\s+cero\b.{0,40}\b(?:fitline|pm|negocio)?"
    r")",
)

_DEACTIVATE_RE = re.compile(
    r"(?is)\b(?:"
    r"sal(?:ir|ga)?\s+del\s+modo\s+gu[ií]a|"
    r"desactiva(?:r)?\s+(?:el\s+)?modo\s+gu[ií]a|"
    r"apaga(?:r)?\s+(?:el\s+)?modo\s+gu[ií]a|"
    r"modo\s+normal|"
    r"ya\s+no\s+(?:quiero|necesito)\s+(?:el\s+)?(?:modo\s+)?gu[ií]a|"
    r"termina(?:r)?\s+(?:el\s+)?modo\s+gu[ií]a"
    r")\b",
)

_ADVANCE_RE = re.compile(
    r"(?is)(?:^\s*(?:"
    r"s[ií]|sip|sep|ok|okay|vale|dale|"
    r"claro|entendido|entiendo|"
    r"siguiente|contin[uú]a(?:r)?|adelante|avanza|"
    r"qued[oó]\s+claro|ya\s+entend[ií]|perfecto|listo|"
    r"vamos|sigue|next"
    r")\s*[.!?]?\s*$"
    r"|\b(?:"
    r"siguiente\s+(?:paso|bloque|punto)|"
    r"contin[uú]a(?:r)?|"
    r"qued[oó]\s+claro|"
    r"ya\s+entend[ií]|"
    r"expl[ií]ca(?:me)?\s+el\s+siguiente|"
    r"pasemos\s+al\s+siguiente"
    r")\b)",
)

_REEXPLAIN_RE = re.compile(
    r"(?is)\b(?:"
    r"no(?:\s+entend[ií]|\s+queda(?:\s+claro)?|\s+me\s+queda)|"
    r"otra\s+(?:vez|forma|manera)|"
    r"m[aá]s\s+simple|"
    r"expl[ií]ca(?:lo|me)?\s+(?:otra\s+vez|de\s+otra\s+forma|m[aá]s\s+f[aá]cil)|"
    r"repite|"
    r"no\s+entend[ií]|"
    r"confus"
    r")\b",
)

_CHECK_QUESTION = (
    "¿Quedó claro esto, o prefieres que lo explique de otra forma?"
)
_CHECK_QUESTION_VOICE = (
    "¿Quedó claro, o lo explico de otra forma?"
)


def is_fitline_admin_user(user_id: str) -> bool:
    """Admins / coadmins: mentor experto sin forzar modo guía pedagógico.

    En preview socio Cierre ($20) el admin se trata como usuario nuevo.
    """
    uid = (user_id or "").strip()
    if not uid:
        return False
    try:
        from app.services.preview_persona import is_cierre_partner_preview

        if is_cierre_partner_preview(uid):
            return False
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.deps.auth import is_super_admin
        from app.services import supabase_db

        profile = supabase_db.get_profile(uid) or {}
        role = str(profile.get("role") or "").strip().lower()
        if role in ("super_admin", "coadmin", "admin"):
            return True
        return is_super_admin(profile.get("email"), profile.get("role"))
    except Exception:  # noqa: BLE001
        return False


def is_fitline_new_partner_audience(user_id: str) -> bool:
    """Socio/usuario nuevo (no admin): pedagogía por defecto."""
    return bool((user_id or "").strip()) and not is_fitline_admin_user(user_id)


def user_plan_is_fitline_focus(user_id: str) -> bool:
    uid = (user_id or "").strip()
    if not uid:
        return False
    try:
        from app.services.preview_persona import is_cierre_partner_preview

        if is_cierre_partner_preview(uid):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.domain.plans import plan_is_pm_fitline_focus
        from app.services import supabase_db

        sub = supabase_db.get_subscription(uid) or {}
        return plan_is_pm_fitline_focus(sub.get("plan_id"))
    except Exception:  # noqa: BLE001
        return False


def should_auto_start_fitline_guide(
    user_id: str,
    user_text: str,
    *,
    channel: str = "chat",
) -> bool:
    """Auto-guía pedagógica — chat sí; voz no (paridad Retell en productos/negocio).

    En voz Cierre/Realtime el socio debe oír la misma densidad Jarvis que Retell
    al preguntar por Restorate/NTC/negocio. Modo guía solo con frase explícita
    («modo guía», «desde cero», etc.).
    """
    if (channel or "chat").strip().lower() == "voice":
        return False
    uid = (user_id or "").strip()
    if not uid or is_fitline_admin_user(uid):
        return False
    if vcs.is_fitline_guide_opt_out(uid):
        return False
    if is_guide_deactivate_phrase(user_text):
        return False
    return user_plan_is_fitline_focus(uid)


def is_guide_activate_phrase(text: str) -> bool:
    return bool(_ACTIVATE_RE.search((text or "").strip()))


def is_guide_deactivate_phrase(text: str) -> bool:
    return bool(_DEACTIVATE_RE.search((text or "").strip()))


def is_guide_advance_phrase(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(_ADVANCE_RE.search(t))


def is_guide_reexplain_phrase(text: str) -> bool:
    return bool(_REEXPLAIN_RE.search((text or "").strip()))


def guide_step_count() -> int:
    return len(GUIDE_STEPS)


def get_guide_step(index: int) -> dict[str, str]:
    i = max(0, min(int(index), len(GUIDE_STEPS) - 1))
    return GUIDE_STEPS[i]


def activate_fitline_guide(user_id: str) -> dict[str, Any]:
    vcs.set_fitline_guide_opt_out(user_id, False)
    vcs.set_fitline_guide(user_id, active=True, step_index=0, reexplain=False)
    logger.info("[GUIDE] activated user=%s", (user_id or "")[:8])
    return {
        "ok": True,
        "status": "guide_active",
        "step_index": 0,
        "step_id": GUIDE_STEPS[0]["id"],
    }


def deactivate_fitline_guide(user_id: str) -> dict[str, Any]:
    was = vcs.is_fitline_guide_active(user_id)
    vcs.set_fitline_guide(user_id, active=False, step_index=0, reexplain=False)
    vcs.set_fitline_guide_opt_out(user_id, True)
    logger.info("[GUIDE] deactivated user=%s was=%s", (user_id or "")[:8], was)
    return {"ok": True, "status": "guide_inactive", "was_active": was}


def prepare_fitline_guide_turn(
    user_id: str,
    user_text: str,
    *,
    channel: Channel = "chat",
) -> dict[str, Any]:
    """Actualiza estado del modo guía según el turno. No inventa hechos."""
    uid = (user_id or "").strip()
    text = (user_text or "").strip()
    if not uid:
        return {"active": False}

    if is_guide_deactivate_phrase(text):
        deactivate_fitline_guide(uid)
        return {
            "active": False,
            "just_deactivated": True,
            "message": "Salimos del modo guía. Puedes preguntarme lo que necesites con normalidad.",
        }

    if is_guide_activate_phrase(text):
        activate_fitline_guide(uid)
        return {
            "active": True,
            "just_activated": True,
            "step_index": 0,
            "step": GUIDE_STEPS[0],
            "reexplain": False,
            "auto": False,
        }

    if not vcs.is_fitline_guide_active(uid):
        if should_auto_start_fitline_guide(uid, text, channel=channel):
            activate_fitline_guide(uid)
            return {
                "active": True,
                "just_activated": True,
                "step_index": 0,
                "step": GUIDE_STEPS[0],
                "reexplain": False,
                "auto": True,
            }
        return {"active": False}

    step_index = vcs.get_fitline_guide_step(uid)
    reexplain = False

    if is_guide_reexplain_phrase(text):
        reexplain = True
        vcs.set_fitline_guide(uid, active=True, step_index=step_index, reexplain=True)
    elif is_guide_advance_phrase(text):
        if step_index < len(GUIDE_STEPS) - 1:
            step_index += 1
        vcs.set_fitline_guide(uid, active=True, step_index=step_index, reexplain=False)
    else:
        # Pregunta dentro del guía: mantener paso; marcar que puede aclarar sin saltar.
        vcs.set_fitline_guide(uid, active=True, step_index=step_index, reexplain=False)

    step = get_guide_step(step_index)
    return {
        "active": True,
        "step_index": step_index,
        "step": step,
        "reexplain": reexplain,
        "is_last": step_index >= len(GUIDE_STEPS) - 1,
        "channel": channel,
    }


def format_guide_overlay(
    state: dict[str, Any],
    *,
    channel: Channel = "chat",
) -> str:
    """Overlay de system prompt para el turno actual del modo guía."""
    if state.get("just_deactivated"):
        return (
            "# MODO GUÍA — DESACTIVADO\n"
            f"{state.get('message') or 'Modo guía cerrado.'}\n"
            "Responde breve confirmando la salida; no sigas el curriculum."
        )
    if not state.get("active"):
        return ""

    step = state.get("step") or get_guide_step(0)
    step_index = int(state.get("step_index") or 0)
    total = len(GUIDE_STEPS)
    reexplain = bool(state.get("reexplain"))
    is_voice = channel == "voice"
    teach = step.get("voice_teach") if is_voice else step.get("teach")
    check_q = _CHECK_QUESTION_VOICE if is_voice else _CHECK_QUESTION
    pace = (
        "VOZ: máximo 2–4 oraciones cortas. Un solo concepto. Sin listas largas ni párrafos."
        if is_voice
        else
        "CHAT/AVANZADO: un bloque claro (corto). Evita volcar todo el catálogo o el Income Plan."
    )
    reexplain_line = (
        "El usuario NO entendió: reexplica el MISMO bloque con otras palabras y un "
        "ejemplo cotidiano más simple. NO avances de paso."
        if reexplain
        else
        "Si pregunta algo puntual del bloque actual, aclara y luego vuelve a ofrecer avanzar."
    )
    auto_line = ""
    if state.get("just_activated") and state.get("auto"):
        auto_line = (
            "- Este socio es nuevo (no admin): el modo guía arrancó SOLO. "
            "Empieza con el bloque intro de forma cálida y pedagógica.\n"
        )
    return (
        "# MODO GUÍA FITLINE/PM — MENTOR PEDAGÓGICO (ACTIVO)\n"
        f"Paso {step_index + 1}/{total}: {step.get('title')}\n"
        f"CONTENIDO A ENSEÑAR EN ESTE TURNO (usa SOLO esto + hechos Oportunidades):\n{teach}\n\n"
        "REGLAS DE RITMO:\n"
        f"{auto_line}"
        f"- {pace}\n"
        "- Un concepto a la vez. NO satures con % de comisión, precios de entrada "
        "ni catálogo completo.\n"
        "- Lenguaje sencillo, ejemplos cotidianos. Terminología: red de franquicias / "
        "equipo de crecimiento / socios de negocio / patrocinador.\n"
        "- PROHIBIDO decir «investigando» o buscar en web: usa el conocimiento FitLine "
        "ya inyectado.\n"
        "- NO inventes Income Plan ni precios de entrada.\n"
        f"- {reexplain_line}\n"
        f"- Cierra el bloque con exactamente esta pregunta (o muy similar): «{check_q}»\n"
        "- Si el usuario dice que entendió / siguiente → el sistema avanzará el paso "
        "en el próximo turno; enseña el bloque indicado arriba."
    )


def append_fitline_guide_if_needed(
    system: str,
    user_id: str,
    user_text: str,
    *,
    channel: Channel = "chat",
) -> str:
    """Prepara el turno de guía y añade overlay + conocimiento FitLine si aplica."""
    state = prepare_fitline_guide_turn(user_id, user_text, channel=channel)
    overlay = format_guide_overlay(state, channel=channel)
    if not overlay and not state.get("active") and not state.get("just_deactivated"):
        return system

    out = (system or "").rstrip()
    # Con guía activo asegurar ficha FitLine aunque digan solo «sí».
    if state.get("active") or state.get("just_activated"):
        already = "CONOCIMIENTO CURADO — PM International" in out or "HECHOS OBLIGATORIOS FITLINE" in out
        if not already:
            from app.services.opportunities_pilot.fitline_knowledge import (
                append_fitline_knowledge_if_needed,
                format_fitline_knowledge_for_prompt,
                wants_fitline_knowledge,
            )

            if wants_fitline_knowledge(user_text):
                out = append_fitline_knowledge_if_needed(out, user_text)
            else:
                block = format_fitline_knowledge_for_prompt()
                if block:
                    out = f"{out}\n\n{block}" if out else block

    if overlay:
        out = f"{out}\n\n{overlay}" if out else overlay
    return out


def wants_fitline_guide_context(user_id: str, user_text: str) -> bool:
    """True si hay que tratar el turno como modo guía (activo, activación o auto)."""
    if is_guide_activate_phrase(user_text):
        return True
    if (user_id or "").strip() and vcs.is_fitline_guide_active(user_id):
        return True
    return should_auto_start_fitline_guide(user_id, user_text, channel="chat")
