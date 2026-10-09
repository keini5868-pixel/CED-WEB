"""Generación de imágenes en chat (texto y modo avanzado) — capa compartida."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.services.chat_intents import (
    assistant_offered_image_act,
    history_has_active_image_thread,
    history_has_pending_image_brief,
    is_anaphoric_image_subject,
    is_bare_affirmation,
    is_casual_chat_interrupt,
    is_explicit_image_command,
    is_exploratory_talk,
    is_generate_image_intent,
    is_image_choice_confirmation,
    is_image_meta_talk,
    is_image_subject_correction,
    is_pdf_intent,
    is_script_narrative_request,
    is_text_ideation_request,
    is_text_work_request,
    is_vague_image_subject,
    is_visual_design_exploration,
    last_assistant_image_concept,
    last_assistant_visual_description,
    last_concrete_image_user_prompt,
    last_user_visual_context,
    parse_followup_image_prompt,
    parse_generate_image_prompt,
    points_at_prior_visual,
    visual_episode_history,
    resolve_anaphoric_image_prompt,
    resolve_confirmed_image_prompt,
    user_requests_from_scratch_compose,
    user_requests_prior_reference,
    user_requests_new_image_piece,
    user_requests_image_edit,
    user_keeps_same_image_piece,
    user_insists_on_pending_image,
    image_request_needs_new_or_edit_clarification,
    compose_visual_thread_brief,
    is_simple_photo_edit_request,
    wants_image_reference_edit,
)
from app.services.marketing_creative import (
    build_display_label,
    extract_product_subject,
    is_image_creation_request,
    is_marketing_creative_intent,
    resolve_image_creation_from_text,
    strip_creative_user_noise,
)

DIRECT_IMAGE_MAX_CHARS = 8000
IMAGE_NEW_OR_EDIT_CLARIFICATION = "¿Nueva pieza o modificar la anterior?"
_PROMPT_COVER_STOPWORDS = {
    "con",
    "que",
    "una",
    "uno",
    "los",
    "las",
    "del",
    "para",
    "por",
    "el",
    "la",
    "de",
    "en",
    "un",
    "y",
    "o",
    "a",
    "the",
    "and",
    "fondo",
    "texto",
    "flyer",
    "imagen",
    "genera",
    "hazme",
    "crea",
}

logger = logging.getLogger(__name__)

_VISION_ANALYSIS_MARKERS = (
    "**Qué es**",
    "**Detalle visible**",
    "Qué es —",
    "**Contexto**",
    "**Observaciones**",
)

_IMAGE_WAIT_FILLER = re.compile(
    r"\b("
    r"un\s+momento"
    r"|en\s+seguida"
    r"|dame\s+un\s+(?:momento|segundo)"
    r"|estoy\s+generando"
    r"|voy\s+a\s+generar"
    r"|generando\s+(?:la\s+|las?\s+)?(?:imagen|foto|creativo|letras|texto|tipograf)"
    r"|va\.\s*generando"
    r"|perm[ií]teme\s+generar"
    r"|ahora\s+mismo\s+(?:la\s+)?genero"
    r")\b",
    re.I,
)


def extract_vision_context_from_history(history: list[dict[str, str]] | None) -> str:
    for row in reversed(history or []):
        role = str(row.get("role") or "").lower()
        if role not in ("assistant", "model"):
            continue
        content = (row.get("content") or "").strip()
        if not content:
            continue
        if any(marker in content for marker in _VISION_ANALYSIS_MARKERS):
            return content[:3500]
    return ""


def _recent_chat_context(history: list[dict[str, str]], *, limit: int = 8) -> str:
    chunks: list[str] = []
    for row in (history or [])[-limit:]:
        content = (row.get("content") or "").strip()
        if content:
            chunks.append(content)
    return " ".join(chunks)


def build_enriched_generation_context(
    user_text: str,
    history: list[dict[str, str]] | None,
    *,
    user_id: str,
    conversation_id: str | None,
) -> str:
    """Hechos visuales del historial/visión — sin etiquetas meta que Gemini pinte en la foto.

    El pedido actual del usuario va en `prompt`, no aquí. Duplicarlo con
    «Instrucciones actuales del usuario…» hacía que el modelo lo dibujara como tipografía.
    """
    from app.services.publish_image_context import get_session_vision_analysis

    parts: list[str] = []
    vision = get_session_vision_analysis(user_id, conversation_id)
    if not vision:
        vision = extract_vision_context_from_history(history)
    if vision:
        parts.append(vision[:3500])
    recent = _recent_chat_context(history or [])
    if recent:
        # Evita reinyectar el mismo pedido del usuario como “contexto”.
        clean = (user_text or "").strip()
        if clean and clean in recent:
            recent = recent.replace(clean, " ").strip()
        if recent:
            parts.append(recent[:2200])
    return "\n\n".join(parts)[:4000]


def build_active_image_thread_context(
    history: list[dict[str, str]] | None,
    *,
    user_id: str = "",
    conversation_id: str | None = None,
    user_text: str = "",
) -> str:
    """Ancla del hilo visual para respuestas de texto conectadas al mismo diseño."""
    from app.services.publish_image_context import (
        get_session_vision_analysis,
        has_publishable_image,
    )

    if user_text and is_text_work_request(user_text):
        return ""

    in_thread = history_has_active_image_thread(history)
    has_session_image = bool(user_id) and has_publishable_image(user_id, conversation_id)
    has_visual_anchor = bool(
        last_concrete_image_user_prompt(history)
        or last_assistant_visual_description(history)
        or last_assistant_image_concept(history)
        or (user_id and get_session_vision_analysis(user_id, conversation_id))
        or extract_vision_context_from_history(history)
    )
    if not in_thread and not has_session_image and not has_visual_anchor:
        return ""

    sections: list[str] = [
        "HILO VISUAL ACTIVO (contexto interno — no lo copies al usuario):",
        "El usuario itera sobre el MISMO diseño o imagen. Mantén continuidad visual.",
    ]
    vision = ""
    if user_id:
        vision = get_session_vision_analysis(user_id, conversation_id) or ""
    if not vision:
        vision = extract_vision_context_from_history(history)
    if vision:
        sections.append(f"Análisis de la imagen de referencia:\n{vision[:2800]}")

    prior = last_concrete_image_user_prompt(history)
    if prior:
        sections.append(f"Último brief visual del usuario: {prior[:900]}")

    user_ctx = last_user_visual_context(history)
    if user_ctx:
        sections.append(f"Contexto visual reciente del usuario: {user_ctx[:700]}")

    desc = last_assistant_visual_description(history)
    if desc:
        sections.append(f"Descripción visual previa: {desc[:1200]}")

    concept = last_assistant_image_concept(history)
    if concept and concept != desc:
        sections.append(f"Concepto pendiente: {concept[:900]}")

    sections.append(
        "ITERACIÓN DE DISEÑO (estilo ChatGPT):\n"
        "- Si piden ejemplos, opciones, variantes o «cómo se vería» SIN pedir generar/renderizar: "
        "responde en TEXTO con 2-4 variantes concretas del MISMO diseño (mismo sujeto, layout, marca).\n"
        "- NO invoques generate_image ni prometas imagen hasta que digan explícitamente "
        "«genera», «hazlo», «créala», «genérala», «muéstrame la imagen», etc.\n"
        "- «Esa imagen», «la de hace rato», «el flyer» = el diseño de arriba, no uno nuevo al azar.\n"
        "- Un ajuste (color, texto, fondo, oscuridad) = la MISMA pieza: conserva sujeto, layout y copy.\n"
        "- Cuando pidan renderizar, conserva el hilo visual; el backend usará la referencia de sesión."
    )
    return "\n\n".join(sections)[:6000]


def effective_user_prompt(text: str, history: list[dict[str, str]] | None) -> str:
    t = (text or "").strip()
    from app.services.image_text_ritual import compose_confirmed_overlay_prompt

    overlay_prompt = compose_confirmed_overlay_prompt(t, history)
    if overlay_prompt:
        return overlay_prompt
    if user_insists_on_pending_image(t, history):
        prior = last_concrete_image_user_prompt(history) or last_user_visual_context(
            history
        )
        if prior:
            return prior
    from app.services.copy_quality import (
        build_flat_color_field_prompt,
        user_requests_flat_rebuild,
    )

    if user_requests_flat_rebuild(t) and (
        history_has_active_image_thread(history)
        or last_concrete_image_user_prompt(history)
    ):
        prior = last_concrete_image_user_prompt(history) or last_user_visual_context(
            history
        )
        return build_flat_color_field_prompt(t, prior or "")
    if user_keeps_same_image_piece(t, history) or (
        wants_image_reference_edit(t) and history_has_active_image_thread(history)
    ):
        prior = last_concrete_image_user_prompt(history) or last_user_visual_context(
            history
        )
        if prior and prior.strip().lower() != t.lower():
            return (
                f"{prior.strip()}\n\nAjuste sobre la misma imagen "
                f"(conserva sujeto, composición y textos; no inventes otra escena): {t}"
            )[:4000]
        if prior:
            return prior
    if user_requests_from_scratch_compose(t):
        composed = compose_visual_thread_brief(t, history)
        if composed:
            return composed
    parsed = parse_generate_image_prompt(t)
    needs_thread = bool(
        parsed
        and (
            is_vague_image_subject(parsed)
            or points_at_prior_visual(t)
            or points_at_prior_visual(parsed)
        )
    )
    if needs_thread:
        resolved = resolve_anaphoric_image_prompt(t, history)
        if resolved:
            return resolved
        prior = last_concrete_image_user_prompt(history)
        if prior:
            return prior
        concept = last_assistant_image_concept(history)
        if concept:
            return concept
    if parsed:
        return parsed
    confirmed = resolve_confirmed_image_prompt(t, history)
    if confirmed:
        return confirmed
    followup = parse_followup_image_prompt(t, history)
    if followup:
        prior = last_concrete_image_user_prompt(history) or last_user_visual_context(history)
        if prior and prior.strip().lower() != followup.strip().lower():
            return (
                f"{prior.strip()}\n\nAjuste sobre la misma imagen "
                f"(conserva sujeto, composición y textos; no inventes otra escena): {followup}"
            )[:4000]
        return followup
    if wants_image_reference_edit(t) and history_has_active_image_thread(history):
        prior = last_concrete_image_user_prompt(history) or last_user_visual_context(history)
        if prior and prior.strip().lower() != t.lower():
            return (
                f"{prior.strip()}\n\nAjuste sobre la misma imagen "
                f"(conserva sujeto, composición y textos; no inventes otra escena): {t}"
            )[:4000]
    cleaned = strip_creative_user_noise(t)
    return cleaned or t


def should_use_reference_generation(
    text: str,
    history: list[dict[str, str]] | None,
    *,
    user_id: str,
    conversation_id: str | None,
) -> bool:
    """Solo ruta con referencia si el pedido lo pide de forma explícita.

    Tener bytes de imagen en sesión (p.ej. tras analizar o tras un edit fallido)
    NO debe forzar generate_image_with_reference en un «genera una imagen de X»
    plano: eso dejaba el chat atascado en el path de referencia tras un fallo.
    """
    from app.services.publish_image_context import (
        disarm_generated_edit_reference,
        get_last_uploaded_image_for_session,
        get_session_vision_analysis,
        resolve_reference_image_bytes,
        session_image_usable_for_edit,
        _row_is_user_upload,
    )

    if not resolve_reference_image_bytes(user_id, conversation_id):
        return False
    if user_requests_from_scratch_compose(text):
        return False
    if user_insists_on_pending_image(text, history):
        return False
    from app.services.copy_quality import user_requests_flat_rebuild

    if user_requests_flat_rebuild(text):
        return False
    new_piece = user_requests_new_image_piece(text, history) and not user_requests_prior_reference(
        text
    )
    row = get_last_uploaded_image_for_session(user_id, conversation_id)
    is_upload = _row_is_user_upload(row)
    if new_piece:
        # Foto subida + análisis: creativo sobre esa toma. Generación previa: pieza nueva.
        if is_upload and is_marketing_creative_intent(text) and (
            extract_vision_context_from_history(history)
            or get_session_vision_analysis(user_id, conversation_id)
        ):
            return True
        disarm_generated_edit_reference(user_id, conversation_id)
        return False
    if not session_image_usable_for_edit(user_id, conversation_id):
        # Un PNG generado sigue sirviendo si piden «otra igual / déjala así»,
        # aunque el armado de un turno ya se haya consumido. Un fallo/mismatch no.
        row = get_last_uploaded_image_for_session(user_id, conversation_id)
        hard_fail = bool(
            row
            and (
                row.get("generation_ok") is False or row.get("prompt_match") is False
            )
        )
        if hard_fail or not user_keeps_same_image_piece(text, history):
            return False
    # Variación / edición / «igual a la que te pasé» / «mismos precios».
    if wants_image_reference_edit(text) or user_requests_image_edit(text):
        return True
    # Follow-up corto que continúa editando el hilo visual.
    if parse_followup_image_prompt(text, history):
        return True
    # Tras analizar/subir una foto, un creativo usa esa pieza — no un flyer nuevo suelto.
    if is_upload and is_marketing_creative_intent(text) and (
        extract_vision_context_from_history(history)
        or get_session_vision_analysis(user_id, conversation_id)
    ):
        return True
    # Mismo diseño del hilo: anáfora o referencia explícita al generar otra vez.
    if history_has_active_image_thread(history) and is_generate_image_intent(text):
        parsed = parse_generate_image_prompt(text) or text
        if user_requests_prior_reference(text) or is_anaphoric_image_subject(parsed):
            return True
    return False


def should_take_direct_image_path(
    text: str,
    history: list[dict[str, str]] | None,
) -> bool:
    """True si el turno debe generar imagen de forma directa (sin narrar «un momento»).

    Los briefs largos (fondo + tipografía + overlays) DEBEN entrar aquí: el límite
    anterior de 500 chars desviaba a Claude/texto y terminaba en stall silencioso.
    """
    from app.services.copy_quality import normalize_image_request_typos

    t = normalize_image_request_typos((text or "").strip())
    if not t or is_pdf_intent(t):
        return False
    if len(t) > DIRECT_IMAGE_MAX_CHARS:
        return False
    from app.services.copy_quality import prompt_requires_ideogram_text

    if is_text_work_request(t) or is_text_ideation_request(t):
        return False
    if is_exploratory_talk(t) and not is_explicit_image_command(t):
        return False
    if is_visual_design_exploration(t, history):
        return False
    from app.services.copy_quality import (
        user_requests_background_change,
        user_requests_flat_rebuild,
    )

    if history_has_active_image_thread(history) and (
        user_requests_flat_rebuild(t) or user_requests_background_change(t)
    ):
        return True
    if user_insists_on_pending_image(t, history) and (
        history_has_pending_image_brief(history)
        or last_concrete_image_user_prompt(history)
        or history_has_active_image_thread(history)
    ):
        return True
    if is_image_meta_talk(t):
        return False
    if is_text_work_request(t):
        return False
    if is_script_narrative_request(t) and not is_generate_image_intent(t):
        return False
    from app.services.image_text_ritual import needs_overlay_readback

    if user_requests_from_scratch_compose(t) and (
        history_has_active_image_thread(history)
        or last_concrete_image_user_prompt(history)
    ):
        return True
    if is_bare_affirmation(t):
        return assistant_offered_image_act(history)
    if is_image_choice_confirmation(t):
        return assistant_offered_image_act(history) or (
            is_explicit_image_command(t) and history_has_pending_image_brief(history)
        )
    if needs_overlay_readback(t, history):
        return False
    if user_insists_on_pending_image(t, history) and (
        history_has_pending_image_brief(history)
        or last_concrete_image_user_prompt(history)
    ):
        return True
    # «Agrégale texto…» sobre imagen del hilo — path visual aunque no diga «genera imagen».
    if prompt_requires_ideogram_text(t) and (
        wants_image_reference_edit(t) or user_requests_prior_reference(t)
    ):
        return True
    # Intent de imagen gana a «cambio de tema» / small-talk (listas con «clima», etc.).
    if is_generate_image_intent(t):
        return True
    if user_requests_from_scratch_compose(t) and (
        history_has_active_image_thread(history)
        or last_concrete_image_user_prompt(history)
    ):
        return True
    if is_casual_chat_interrupt(t):
        return False
    if parse_followup_image_prompt(t, history):
        return True
    if history_has_active_image_thread(history) and (
        wants_image_reference_edit(t) or is_simple_photo_edit_request(t)
    ):
        return True
    if is_image_creation_request(t, history) and not is_exploratory_talk(t):
        return True
    return False


def looks_like_visual_image_prompt(prompt: str) -> bool:
    """True si el prompt del LLM ya describe la escena (no solo «la primera»)."""
    t = (prompt or "").strip()
    if len(t) < 36:
        return False
    return bool(
        re.search(
            r"(?i)\b(imagen|foto|logo|flyer|banner|creativo|frase|wordmark|"
            r"pm\s*international|fitline|tipograf|headline|composici[oó]n|"
            r"castillo|ced\s*&\s*pm)\b",
            t,
        )
    )


def should_generate_image_from_voice_turn(
    user_text: str,
    llm_prompt: str = "",
    history: list[dict[str, str]] | None = None,
) -> bool:
    """Voz: pedido explícito, o confirmación de una frase ya propuesta para la imagen."""
    t = (user_text or "").strip()
    if should_take_direct_image_path(t, history):
        return True
    if is_image_choice_confirmation(t) and assistant_offered_image_act(history) and (
        looks_like_visual_image_prompt(llm_prompt)
        or history_has_pending_image_brief(history)
    ):
        return True
    return False


def resolve_voice_image_prompt(
    user_text: str,
    llm_prompt: str = "",
    history: list[dict[str, str]] | None = None,
) -> str:
    t = (user_text or "").strip()
    llm = (llm_prompt or "").strip()
    if is_generate_image_intent(t):
        parsed = parse_generate_image_prompt(t)
        if parsed and (
            is_vague_image_subject(parsed)
            or points_at_prior_visual(t)
            or points_at_prior_visual(parsed)
        ):
            return effective_user_prompt(t, history) or t
        return t
    from app.services.copy_quality import user_requests_flat_rebuild

    if (
        wants_image_reference_edit(t)
        or parse_followup_image_prompt(t, history)
        or points_at_prior_visual(t)
        or user_requests_flat_rebuild(t)
    ):
        return effective_user_prompt(t, history) or t
    if is_image_choice_confirmation(t):
        if looks_like_visual_image_prompt(llm):
            return llm
        rebuilt = resolve_confirmed_image_prompt(t, history)
        if rebuilt:
            return rebuilt
        if llm:
            return llm
    return t or llm


_ASSISTANT_BREAKS_UTTERANCE_JOIN = re.compile(
    r"(?i)listo|pantalla|imagen generada|aqu[ií] est[aá]|no pude|otra generaci"
)


def join_same_image_request_utterances(
    history: list[dict[str, str]] | None,
    *,
    max_turns: int = 4,
) -> str:
    """Une turnos consecutivos del usuario del mismo pedido (STT partido)."""
    chunks: list[str] = []
    for row in reversed(history or []):
        role = str(row.get("role") or "").lower()
        content = (row.get("content") or "").strip()
        if not content:
            continue
        if role in {"assistant", "model", "agent"}:
            if _ASSISTANT_BREAKS_UTTERANCE_JOIN.search(content) or len(content) > 160:
                break
            continue
        if role in {"user", "customer"}:
            chunks.append(content)
            if len(chunks) >= max_turns:
                break
        elif chunks:
            break
    if not chunks:
        return ""
    latest = chunks[0]
    # Dos pedidos completos distintos: quédate con el último.
    if (
        len(chunks) >= 2
        and is_generate_image_intent(latest)
        and is_generate_image_intent(chunks[1])
        and len(latest.split()) >= 8
        and len(chunks[1].split()) >= 8
    ):
        return latest
    chunks.reverse()
    return re.sub(r"\s+", " ", " ".join(chunks)).strip()


def utterance_too_thin_for_prompt(heard: str, args_prompt: str) -> bool:
    h = re.sub(r"\s+", " ", (heard or "").strip())
    a = re.sub(r"\s+", " ", (args_prompt or "").strip())
    if not h:
        return True
    words = h.split()
    if len(words) < 5:
        return True
    if a and len(words) * 2 < len(a.split()) and len(h) * 2 < len(a):
        return True
    return False


def heard_is_prompt_fragment(heard: str, args_prompt: str) -> bool:
    h = re.sub(r"[^\wáéíóúñ ]+", "", (heard or "").strip().casefold())
    a = re.sub(r"[^\wáéíóúñ ]+", "", (args_prompt or "").strip().casefold())
    if not h or not a or len(h) < 3:
        return False
    return h in a and len(h.split()) <= 6


def image_prompt_covers_request(used: str, requested: str) -> bool:
    """True si prompt_used conserva lo esencial de args.prompt / el pedido."""
    from app.services.copy_quality import extract_literal_on_image_copy

    req = (requested or "").strip()
    used_l = re.sub(r"\s+", " ", (used or "").strip()).casefold()
    if not req:
        return True
    if not used_l:
        return False
    for quote in extract_literal_on_image_copy(req):
        qn = re.sub(r"\s+", " ", quote).casefold()
        q_alnum = re.sub(r"[^\wáéíóúñ ]", "", qn)
        used_alnum = re.sub(r"[^\wáéíóúñ ]", "", used_l)
        if len(q_alnum) >= 8 and q_alnum not in used_alnum:
            return False
    words = [
        w
        for w in re.findall(r"[a-záéíóúñ]{4,}", req.casefold())
        if w not in _PROMPT_COVER_STOPWORDS
    ]
    if not words:
        return True
    hits = sum(1 for w in words if w in used_l)
    return hits >= max(2, int(len(words) * 0.45))


def pick_voice_image_source_prompt(
    *,
    args_prompt: str,
    heard: str,
    history: list[dict[str, str]] | None = None,
) -> str:
    """args.prompt manda; el utterance crudo respalda si falta o si el LLM reescribió el sujeto."""
    args = (args_prompt or "").strip()
    joined = join_same_image_request_utterances(history)
    heard_s = (joined or heard or "").strip()
    thin = bool(
        heard_s
        and (
            utterance_too_thin_for_prompt(heard_s, args)
            or heard_is_prompt_fragment(heard_s, args)
        )
    )
    if args and (not heard_s or thin):
        return args
    if heard_s and not args:
        return heard_s
    if args and heard_s:
        from app.services.copy_quality import (
            extract_locked_slogan,
            user_requests_overlay_correction,
        )

        if user_requests_overlay_correction(heard_s):
            return heard_s
        if extract_locked_slogan(heard_s) and not extract_locked_slogan(args):
            return heard_s
        if image_prompt_covers_request(args, heard_s):
            return args
        if is_generate_image_intent(heard_s) or looks_like_visual_image_prompt(heard_s):
            return heard_s
        return args
    return args or heard_s


def voice_prompt_is_mismatch(prompt_used: str, args_prompt: str) -> bool:
    """Falso éxito: se usó un fragmento STT en vez del args.prompt completo."""
    args = (args_prompt or "").strip()
    used = (prompt_used or "").strip()
    if not args:
        return False
    if image_prompt_covers_request(used, args):
        return False
    return utterance_too_thin_for_prompt(used, args) or heard_is_prompt_fragment(used, args)


def reply_is_image_wait_filler(text: str) -> bool:
    """True si la respuesta solo promete generar sin adjuntar imagen."""
    t = (text or "").strip()
    if not t or len(t) > 280:
        return False
    return bool(_IMAGE_WAIT_FILLER.search(t))


def _format_error(raw_error: str) -> str:
    err = (raw_error or "").strip() or "No pude generar la imagen."
    if "no devolvió imagen" in err.lower():
        # Gemini no devolvió imagen tras varios intentos/modelos sin excepción ni
        # motivo explícito. Dos causas típicas: (a) personajes/marcas con derechos
        # de autor (Marvel, DC, etc.) bloqueados por el filtro de contenido, o
        # (b) un límite temporal de la API. No hubo imagen generada en ningún caso;
        # decirlo con honestidad y sin afirmar la causa como certeza (antes se
        # aseguraba "es por copyright", lo cual es engañoso si en realidad fue un
        # límite temporal — y también engañoso el hint genérico de "sea más
        # concreto", porque el problema no es vaguedad del pedido).
        return (
            "No pude generar la imagen: no se generó ninguna imagen. Puede ser que el "
            "sistema bloqueara el pedido — por ejemplo si describe un personaje o marca "
            "con derechos de autor protegidos — o un límite temporal del servicio. "
            "Puedo intentarlo de nuevo, o si es un personaje con marca registrada, "
            "puedo crear algo similar sin usar esa marca específica."
        )
    if err.lower().startswith("no pude generar la imagen"):
        return err
    return f"No pude generar la imagen: {err}"


def _merge_creative_user_request(prompt: str, user_text: str) -> str:
    """Añade el pedido del usuario al brief creativo sin etiquetas meta pintables."""
    from app.services.gemini_images import strip_image_generation_instruction, strip_image_prompt_meta

    clean = strip_image_prompt_meta(strip_image_generation_instruction(user_text or ""))
    base = strip_image_prompt_meta((prompt or "").strip())
    if not clean or clean.lower() in base.lower():
        return base[:3800]
    return f"{base.rstrip()}\n\nPedido visual del usuario: {clean[:900]}"[:3800]

def run_chat_image_generation(
    user_id: str,
    conversation_id: str | None,
    text: str,
    history: list[dict[str, str]] | None,
    *,
    plan_id: str | None = None,
    allow_reference: bool = True,
) -> dict[str, Any]:
    """
    Ejecuta generación de imagen para chat. Nunca devuelve ok=True sin url.

    allow_reference=False: solo descripción de texto, sin editar la imagen de sesión.
    """
    from app.services.gemini_images import generate_image
    from app.services.image_reference_generator import generate_image_with_reference
    from app.services.publish_image_context import (
        get_last_image_generation_prompt,
        register_text_chat_image_url,
        resolve_reference_image_bytes,
        session_image_usable_for_edit,
    )

    from app.services.copy_quality import (
        CED_ASSISTANT_TAGLINE,
        build_direct_image_prompt,
        build_reference_logo_on_scene_prompt,
        build_reference_scene_edit_prompt,
        build_reference_text_edit_prompt,
        is_ced_wordmark_only_request,
        is_text_only_flyer_request,
        compose_persuasive_overlay_lines,
        lock_on_image_spelling,
        lock_spanish_image_subject,
        normalize_image_request_typos,
        official_brand_likeness_note,
        prompt_requires_ideogram_text,
        resolve_image_text_mode,
        safe_image_display_caption,
        summarize_overlay_labels_for_image,
        user_asks_for_on_image_copy,
        user_requests_background_change,
        user_requests_flat_rebuild,
        user_requests_overlay_correction,
        extract_locked_slogan,
        is_scene_instruction_caption,
        build_flat_color_field_prompt,
        user_requests_ced_branding,
        wants_ced_tagline_lock,
    )
    from app.services.image_art_expander import expand_image_scene
    from app.services.image_text_ritual import (
        delivery_caption_for_image,
        locked_overlay_lines,
    )

    user_text = normalize_image_request_typos((text or "").strip())
    history = visual_episode_history(history)
    overlay_fix = user_requests_overlay_correction(user_text)
    insist = user_insists_on_pending_image(user_text, history)
    new_piece = (not overlay_fix) and (
        insist
        or (
            user_requests_new_image_piece(user_text, history)
            and not user_requests_prior_reference(user_text)
        )
    )
    if (
        allow_reference
        and session_image_usable_for_edit(user_id, conversation_id)
        and image_request_needs_new_or_edit_clarification(user_text)
        and not new_piece
        and not user_requests_image_edit(user_text)
    ):
        return {
            "ok": False,
            "error": "needs_clarification",
            "code": "needs_clarification",
            "reply": IMAGE_NEW_OR_EDIT_CLARIFICATION,
            "url": None,
        }
    effective = effective_user_prompt(user_text, history)
    effective = lock_spanish_image_subject(effective)
    subject_fix = is_image_subject_correction(user_text)
    flat_rebuild = (not new_piece) and user_requests_flat_rebuild(user_text)
    if flat_rebuild and "FLAT graphic poster" not in effective:
        prior = last_concrete_image_user_prompt(history) or ""
        effective = build_flat_color_field_prompt(user_text, prior)
    thread_prompt = get_last_image_generation_prompt(user_id, conversation_id)
    thread_edit = bool(
        not subject_fix
        and not new_piece
        and (
            parse_followup_image_prompt(user_text, history)
            or wants_image_reference_edit(user_text)
            or user_requests_image_edit(user_text)
        )
    )
    wordmark_only = is_ced_wordmark_only_request(user_text)
    copy_edit = (user_asks_for_on_image_copy(user_text) or overlay_fix) and not wordmark_only
    bg_only_edit = thread_edit and user_requests_background_change(user_text) and not flat_rebuild
    scene_only_edit = thread_edit and not copy_edit and not flat_rebuild
    if thread_prompt and thread_edit and not flat_rebuild:
        delta = user_text
        if thread_prompt.strip().lower() not in effective.lower():
            if scene_only_edit:
                effective = (
                    f"{thread_prompt.strip()}\n\nAjuste sobre la MISMA imagen: "
                    f"conserva el sujeto exacto; aplica solo el cambio pedido; "
                    f"no añadas texto: {delta}"
                )[:4000]
            else:
                effective = (
                    f"{thread_prompt.strip()}\n\nAjuste sobre la misma imagen "
                    f"(conserva sujeto, composición y textos; no inventes otra escena): {delta}"
                )[:4000]
    # Texto crítico: en un ajuste del hilo manda el pedido ACTUAL, no el brief previo.
    # Un cambio de fondo/color no debe heredar slogans PAS ni tipografía de un flyer anterior.
    wants_literal_text = copy_edit or (
        prompt_requires_ideogram_text(user_text) and not scene_only_edit
    )
    if flat_rebuild:
        wants_literal_text = True
    if not thread_edit:
        wants_literal_text = wants_literal_text or user_asks_for_on_image_copy(effective)
    if scene_only_edit:
        wants_literal_text = False
    use_reference = allow_reference and should_use_reference_generation(
        user_text,
        history,
        user_id=user_id,
        conversation_id=conversation_id,
    )
    if allow_reference and not use_reference and not new_piece and (thread_edit or wordmark_only):
        # «el castillo que acabas de generar» debe usar la última imagen del usuario,
        # aunque el conversation_id de voz no coincida con el del chat viejo.
        use_reference = bool(
            session_image_usable_for_edit(user_id, conversation_id)
            and resolve_reference_image_bytes(user_id, conversation_id)
        )
    if overlay_fix and allow_reference and resolve_reference_image_bytes(
        user_id, conversation_id
    ):
        use_reference = True
    if subject_fix or flat_rebuild:
        use_reference = False
    ref_payload = resolve_reference_image_bytes(user_id, conversation_id) if use_reference else None

    simple_photo_edit = (
        not new_piece
        and not flat_rebuild
        and (
            thread_edit
            or scene_only_edit
            or bg_only_edit
            or is_simple_photo_edit_request(user_text)
        )
        and not is_marketing_creative_intent(user_text)
    )

    creation = None
    if not simple_photo_edit:
        creation = resolve_image_creation_from_text(
            user_text,
            history,
            has_reference_image=bool(ref_payload),
        )
    display_label = ""
    success_reply = "Listo. Aquí está tu imagen generada."
    style_mode = "edit"
    locked_copy = [
        ln
        for ln in locked_overlay_lines(user_text, history)
        if not is_scene_instruction_caption(ln)
    ]
    slogan = extract_locked_slogan(user_text)
    if slogan and slogan not in locked_copy:
        locked_copy = [slogan, *[ln for ln in locked_copy if ln.casefold() != slogan.casefold()]]
    overlay_delivery = delivery_caption_for_image(user_text, history)

    if simple_photo_edit:
        display_label = "Imagen editada"
        success_reply = "Listo. Aquí está tu imagen con los cambios pedidos."
        model_prompt = effective
    elif creation:
        display_label = creation["display_label"]
        success_reply = creation.get("reply") or "Listo. Aquí está su creativo."
        style_mode = creation.get("style_mode") or "edit"
        # Solo metadata de creativo; el prompt al modelo sale del adaptador directo abajo.
        model_prompt = effective
    else:
        chat_context = _recent_chat_context(history or [])
        if is_marketing_creative_intent(user_text):
            display_label = build_display_label(extract_product_subject(chat_context))
            success_reply = "Listo, señor. Aquí está su creativo publicitario."
        model_prompt = effective

    if overlay_delivery:
        success_reply = overlay_delivery

    text_mode = resolve_image_text_mode(effective)
    visual_thread_parts: list[str] = []
    if not new_piece:
        user_ctx = last_user_visual_context(history)
        if user_ctx:
            visual_thread_parts.append(user_ctx)
        assistant_desc = last_assistant_visual_description(history)
        if assistant_desc:
            visual_thread_parts.append(assistant_desc)
    visual_thread = "\n\n".join(visual_thread_parts)
    skip_expand = bool(
        flat_rebuild or thread_edit or (not new_piece and (use_reference or locked_copy))
    )
    if skip_expand:
        enriched, expander_status = None, "skip"
    else:
        enriched, expander_status = expand_image_scene(
            effective,
            visual_thread,
            text_mode,
        )
    logger.info(
        "[CHAT:IMG-GEN] expander=%s text_mode=%s scene=%s",
        expander_status,
        text_mode,
        "rich" if enriched else "fallback_to_direct",
    )

    # Path directo: el expander solo viste la escena; la política de texto manda siempre.
    direct = build_direct_image_prompt(
        effective,
        has_reference=bool(ref_payload),
        context="",
        visual_override=enriched or "",
    )
    overlay_lines: list[str] = []
    for line in locked_copy:
        if line not in overlay_lines:
            overlay_lines.append(line)
    if (
        not scene_only_edit
        and direct.get("wants_literal_text")
        and (not thread_edit or prompt_requires_ideogram_text(user_text))
    ):
        wants_literal_text = True
    spelling_fix = wants_ced_tagline_lock(user_text) or wants_ced_tagline_lock(
        effective
    )
    # Texto persuasivo (dolor→solución) cuando piden agregar copy sin comillas.
    # Las correcciones I4/Prosaeccion no deben pintar frases PAS genéricas.
    strategy_lines: list[str] = []
    if spelling_fix:
        overlay_lines = [CED_ASSISTANT_TAGLINE]
    elif overlay_fix:
        strategy_lines = []
    elif wants_literal_text and user_asks_for_on_image_copy(user_text):
        strategy_lines = compose_persuasive_overlay_lines(user_text)
    if strategy_lines:
        for line in strategy_lines:
            if line not in overlay_lines:
                overlay_lines.append(line)
    if (
        wants_literal_text
        and ref_payload
        and not strategy_lines
        and not spelling_fix
        and not overlay_fix
        and not scene_only_edit
        and user_asks_for_on_image_copy(user_text)
    ):
        try:
            from app.services.vision_search import extract_image_overlay_labels

            for label in extract_image_overlay_labels(ref_payload[0], mime=ref_payload[1]):
                if label not in overlay_lines:
                    overlay_lines.append(label)
            overlay_lines = summarize_overlay_labels_for_image(overlay_lines, max_labels=5)
        except Exception:  # noqa: BLE001
            logger.warning("[CHAT:IMG-GEN] OCR referencia falló user=%s", user_id[:8])

    overlay_lines = [lock_on_image_spelling(ln) for ln in overlay_lines]

    tech = str(direct.get("prompt") or "").strip()
    if tech:
        model_prompt = tech
    if overlay_fix:
        from app.services.image_overlay_orchestrator import enforce_overlay_fix_prompt

        prior = thread_prompt or last_concrete_image_user_prompt(history) or ""
        model_prompt = enforce_overlay_fix_prompt(
            user_text=user_text,
            prior_prompt=prior,
            locked_copy=overlay_lines,
            has_reference=bool(ref_payload),
            history=history,
        )
    elif (scene_only_edit or wordmark_only) and ref_payload and wordmark_only:
        model_prompt = build_reference_logo_on_scene_prompt(user_text)
        overlay_lines = ["CED"]
        wants_literal_text = False
    elif scene_only_edit and ref_payload:
        model_prompt = build_reference_scene_edit_prompt(user_text)
    elif wants_literal_text and ref_payload:
        model_prompt = build_reference_text_edit_prompt(
            user_text,
            overlay_lines=overlay_lines or strategy_lines,
        )
    elif overlay_lines and wants_literal_text:
        labels = "; ".join(overlay_lines[:5])
        model_prompt = (
            f"{model_prompt} Keep these visible labels legible: {labels}."
        )[:3800]
    if new_piece and is_text_only_flyer_request(user_text):
        people_lock = (
            "sin personas ni otros elementos salvo los indicados. "
            "No people, no dancers, no extra objects except those the user named."
        )
        if "no people" not in model_prompt.lower():
            model_prompt = f"{model_prompt} {people_lock}"[:3800]

    logger.info(
        "[CHAT:IMG-GEN] direct_adapter user=%s scene=%s wants_text=%s creation=%s ref=%s overlays=%s",
        user_id[:8],
        str(direct.get("visual_brief") or "")[:100],
        wants_literal_text,
        bool(creation),
        bool(ref_payload),
        len(overlay_lines),
    )

    img_result: dict[str, Any]
    # Nunca reinyectar historial como context (fuga de temas / tipografía basura).
    history_ctx = ""

    if wants_literal_text:
        # Tipografía: GPT Image edits si hay referencia; si no, generations.
        logger.info(
            "[CHAT:IMG-GEN] literal-text path (GPT Image/Ideogram) user=%s labels=%s ref=%s",
            user_id[:8],
            len(overlay_lines),
            bool(ref_payload),
        )
        img_result = generate_image(
            user_id=user_id,
            plan_id=plan_id,
            prompt=model_prompt,
            quality="auto",
            context="",
            display_label=display_label or None,
            prefer_ideogram=True,
            reference_image=ref_payload[0] if ref_payload else None,
            reference_mime=ref_payload[1] if ref_payload else None,
        )
        if (not img_result.get("ok") or not img_result.get("url")) and ref_payload:
            logger.warning(
                "[CHAT:IMG-GEN] motor tipográfico falló; Gemini+referencia user=%s",
                user_id[:8],
            )
            img_result = generate_image_with_reference(
                user_id=user_id,
                prompt=model_prompt,
                reference_image=ref_payload[0],
                content_type=ref_payload[1],
                style_mode=style_mode if creation else "edit",
                quality="auto",
            )
    elif ref_payload:
        ref_bytes, ref_mime = ref_payload
        ref_prompt = model_prompt
        logger.info(
            "[CHAT:IMG-GEN] reference path user=%s bytes=%s conv=%s",
            user_id[:8],
            len(ref_bytes),
            (conversation_id or "")[:8],
        )
        img_result = generate_image_with_reference(
            user_id=user_id,
            prompt=ref_prompt,
            reference_image=ref_bytes,
            content_type=ref_mime,
            style_mode=style_mode if creation else "edit",
            quality="auto",
        )
        if (not img_result.get("ok") or not img_result.get("url")) and not (
            wants_image_reference_edit(user_text)
            or parse_followup_image_prompt(user_text, history)
        ):
            logger.warning(
                "[CHAT:IMG-GEN] reference failed; falling back to plain user=%s code=%s",
                user_id[:8],
                img_result.get("code"),
            )
            img_result = generate_image(
                user_id=user_id,
                plan_id=plan_id,
                prompt=model_prompt,
                quality="auto",
                context=history_ctx,
                display_label=display_label or None,
                prefer_ideogram=False,
            )
            ref_payload = None
    elif creation:
        logger.info("[CHAT:IMG-GEN] creative brief without bytes user=%s", user_id[:8])
        img_result = generate_image(
            user_id=user_id,
            plan_id=plan_id,
            prompt=model_prompt,
            quality="auto",
            context=history_ctx,
            display_label=display_label,
            prefer_ideogram=False,
        )
    else:
        logger.info("[CHAT:IMG-GEN] plain generate user=%s", user_id[:8])
        img_result = generate_image(
            user_id=user_id,
            plan_id=plan_id,
            prompt=model_prompt,
            quality="auto",
            context=history_ctx,
            display_label=display_label or None,
            prefer_ideogram=False,
        )

    if not img_result.get("ok") or not img_result.get("url"):
        err = _format_error(str(img_result.get("error") or "No pude generar la imagen."))
        logger.warning(
            "[CHAT:IMG-GEN] failed user=%s code=%s ref=%s",
            user_id[:8],
            img_result.get("code"),
            bool(ref_payload),
        )
        return {
            "ok": False,
            "error": err,
            "reply": err,
            "code": img_result.get("code"),
            "url": None,
            "display_label": display_label,
            "prompt_used": str(effective or user_text),
        }

    url = str(img_result["url"])
    # Siempre registrar para publicar (aunque conversation_id aún no exista).
    register_text_chat_image_url(
        user_id,
        conversation_id or "",
        url,
        prompt=str(effective or user_text),
        preserve_reference_bytes=bool(ref_payload) and not new_piece,
    )

    caption = safe_image_display_caption(
        str(img_result.get("caption") or display_label or ""),
        edited=bool(ref_payload or thread_edit or simple_photo_edit),
    )

    if img_result.get("ideogram_used"):
        # GPT Image / Ideogram ya renderizan tipografía — sin aviso de Gemini.
        reply = str(success_reply)
    else:
        from app.services.copy_quality import with_image_text_disclaimer

        reply = with_image_text_disclaimer(
            str(success_reply),
            user_text or model_prompt,
            "",
        )
        if img_result.get("ideogram_declined_reason") == "basic_excluded":
            reply = (
                f"{reply}\n\nCon un plan de pago (desde Starter) puedo usar un motor "
                "especializado en texto (GPT Image) para que se vea más legible, señor."
            )

    likeness = official_brand_likeness_note(user_text) or official_brand_likeness_note(
        effective
    )
    if likeness and likeness not in reply:
        reply = f"{reply}\n\n{likeness}"

    if user_requests_ced_branding(effective) and text_mode in ("decorative", "literal"):
        reply = (
            f"{reply} ¿La quieres en otra pose, flotando sobre tu interfaz, "
            "o en fondo verde para recortarla en tus videos?"
        )

    prompt_used = str(model_prompt or effective or user_text)
    logger.info(
        "[CHAT:IMG-GEN] args.prompt=%s prompt_used=%s ref=%s new_piece=%s",
        user_text[:160],
        prompt_used[:160],
        bool(ref_payload),
        new_piece,
    )
    return {
        "ok": True,
        "url": url,
        "reply": reply,
        "caption": caption,
        "quality": str(img_result.get("quality") or ""),
        "display_label": display_label,
        "used_reference": bool(ref_payload),
        "provider": img_result.get("provider"),
        "prompt_used": prompt_used,
    }


_HALLUCINATED_GENERATE_IMAGE = re.compile(
    r"(?is)"
    r"(?:"
    r"<\s*generate_image\b"
    r"|</\s*generate_image\s*>"
    r"|generate_image\s*\("
    r"|generate_image\s*\{"
    r")"
)
_HALLUCINATED_JSON_PROMPT = re.compile(
    r"""(?:generate_image\s*\(\s*)?\{[^}]*["']prompt["']\s*:\s*["']([^"']+)["']""",
    re.I | re.S,
)
_HALLUCINATED_KW_PROMPT = re.compile(
    r"""generate_image\s*\(\s*prompt\s*=\s*["']([^"']+)["']""",
    re.I,
)
_XML_GENERATE_IMAGE_BLOCK = re.compile(
    r"(?is)<\s*generate_image\b[^>]*>.*?</\s*generate_image\s*>"
)
_JSON_TOOL_BLOB = re.compile(
    r"(?is)\{[^{}]*[\"']prompt[\"']\s*:\s*[\"'].*?[\"']\s*,\s*"
    r"[\"'](?:size|style|aspect_ratio)[\"']\s*:"
    r".*?\}"
)
_FALSE_SUCCESS_MARKERS = (
    "aquí está tu",
    "aqui esta tu",
    "aquí tienes",
    "aqui tienes",
    "te presento",
    "he generado",
    "ya generé",
    "ya genere",
    "here is your",
    "here's your",
    "here is the",
    "listo, señor",
    "listo senor",
    "imagen lista",
    "imagen está lista",
    "imagen esta lista",
    "la imagen está lista",
    "la imagen esta lista",
    "foto lista",
    "hecho. la imagen",
    "generando la imagen",
)
_VISUAL_NOUNS = (
    "imagen",
    "foto",
    "árbol",
    "arbol",
    "tree",
    "creativo",
    "picture",
    "image",
    "photo",
    "flyer",
    "banner",
    "diseño",
    "diseno",
    "ilustración",
    "ilustracion",
)

# LLM pegó el prompt / brief como si fuera el resultado (sin llamar la tool).
_PROMPT_DUMP_MARKERS = (
    "prompt:",
    '"prompt":',
    "'prompt':",
    "descripción visual",
    "descripcion visual",
    "brief visual",
    "genera una imagen de alta calidad",
    "instrucciones actuales",
    '{"prompt"',
    "{'prompt'",
    "<generate_image",
    "</generate_image>",
)


def looks_like_hallucinated_generate_image(text: str) -> bool:
    t = text or ""
    if _HALLUCINATED_GENERATE_IMAGE.search(t):
        return True
    low = t.lower()
    return any(marker in low for marker in _PROMPT_DUMP_MARKERS)


def extract_hallucinated_generate_image_prompt(text: str) -> str | None:
    blob = text or ""
    match = _HALLUCINATED_JSON_PROMPT.search(blob)
    if match:
        return match.group(1).strip()
    match = _HALLUCINATED_KW_PROMPT.search(blob)
    if match:
        return match.group(1).strip()
    return None


def strip_hallucinated_generate_image_text(text: str) -> str:
    cleaned = text or ""
    cleaned = _XML_GENERATE_IMAGE_BLOCK.sub("", cleaned)
    cleaned = re.sub(r"(?is)<\s*/?\s*generate_image\b[^>]*>", "", cleaned)
    cleaned = _JSON_TOOL_BLOB.sub("", cleaned)
    cleaned = re.sub(
        r"print\s*\(\s*generate_image\s*\([^)]*\)\s*\)",
        "",
        cleaned,
        flags=re.I | re.S,
    )
    cleaned = re.sub(
        r"generate_image\s*\(\s*\{.*?\}\s*\)",
        "",
        cleaned,
        flags=re.I | re.S,
    )
    cleaned = re.sub(r"generate_image\s*\([^)]*\)", "", cleaned, flags=re.I | re.S)
    cleaned = re.sub(r"(?im)^\s*va\.\s*$", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def reply_dumps_prompt_instead_of_image(reply: str, user_text: str) -> bool:
    """True si la respuesta es esencialmente el pedido/prompt visual sin adjunto.

    Compara contra el sujeto visual (sin «genera una imagen de…»), porque el LLM
    suele devolver solo la descripción y no los verbos de pedido.
    """
    from app.services.gemini_images import strip_image_generation_instruction

    r = re.sub(r"\s+", " ", (reply or "").strip().lower())
    subject = strip_image_generation_instruction(user_text or "")
    u = re.sub(r"\s+", " ", subject.strip().lower()) or re.sub(
        r"\s+", " ", (user_text or "").strip().lower()
    )
    if len(r) < 40 or len(u) < 12:
        return False
    if re.search(r"https?://|/api/ced/media/", reply or "", re.I):
        return False
    u_tokens = {tok for tok in re.findall(r"[a-záéíóúñ0-9]{4,}", u) if tok}
    if not u_tokens:
        return False
    overlap = sum(1 for tok in u_tokens if tok in r) / len(u_tokens)
    # ≥0.65: prompt dump típico; ≥0.85 con respuesta corta ≈ eco del brief.
    if overlap >= 0.65:
        return True
    if overlap >= 0.5 and len(r) <= max(80, int(len(u) * 1.6)):
        return True
    return False


def reply_promises_image_without_attachment(text: str) -> bool:
    if looks_like_hallucinated_generate_image(text):
        return True
    lowered = (text or "").lower()
    if not lowered:
        return False
    if not any(marker in lowered for marker in _FALSE_SUCCESS_MARKERS):
        return False
    return any(noun in lowered for noun in _VISUAL_NOUNS)


def salvage_image_turn(
    user_id: str,
    conversation_id: str | None,
    user_text: str,
    history: list[dict[str, str]] | None,
    reply: str,
    image_attachment: dict[str, Any] | None,
    *,
    plan_id: str | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """
    Si el LLM alucinó generate_image(...) o prometió imagen sin adjuntarla,
    ejecuta la generación real o devuelve error claro (nunca texto crudo de tool).
    """
    if image_attachment and image_attachment.get("url"):
        if looks_like_hallucinated_generate_image(reply):
            clean = strip_hallucinated_generate_image_text(reply)
            return clean or str(image_attachment.get("caption") or "Imagen generada"), image_attachment
        return reply, image_attachment

    hallucinated = looks_like_hallucinated_generate_image(reply)
    false_success = reply_promises_image_without_attachment(reply)
    dumped = reply_dumps_prompt_instead_of_image(reply, user_text)
    explicit_image = is_generate_image_intent(user_text) and not is_text_ideation_request(
        user_text
    )
    from app.services.copy_quality import user_requests_background_change

    text_work = is_text_work_request(user_text)
    wants_image = (not text_work) and should_take_direct_image_path(user_text, history)
    if not wants_image and not text_work and explicit_image and (
        hallucinated or dumped or false_success
    ):
        # Overlay ritual no debe dejar pasar un dump XML/JSON de generate_image.
        wants_image = True
    if not wants_image and not text_work and (hallucinated or dumped or false_success) and (
        user_requests_background_change(user_text)
        or wants_image_reference_edit(user_text)
        or user_insists_on_pending_image(user_text, history)
    ):
        wants_image = True
    prompt_dump = wants_image and dumped
    wait_filler = wants_image and reply_is_image_wait_filler(reply)
    if not wants_image:
        # Claude/avanzado a menudo dice «listo, señor» y menciona diseño/imagen
        # en un análisis de texto. Eso NO es un pedido de generar PNG.
        if hallucinated or (
            false_success
            and (is_text_ideation_request(user_text) or is_exploratory_talk(user_text))
        ):
            clean = strip_hallucinated_generate_image_text(reply)
            return clean or reply, None
        return reply, image_attachment
    if (
        not hallucinated
        and not false_success
        and not wait_filler
        and not prompt_dump
    ):
        return reply, image_attachment

    logger.warning(
        "[CHAT:IMG-GEN] salvage turn user=%s wants=%s halluc=%s false_ok=%s wait=%s dump=%s",
        user_id[:8],
        wants_image,
        hallucinated,
        false_success,
        wait_filler,
        prompt_dump,
    )
    gen = run_chat_image_generation(
        user_id,
        conversation_id,
        user_text,
        history,
        plan_id=plan_id,
    )
    if gen.get("ok") and gen.get("url"):
        clean = strip_hallucinated_generate_image_text(reply)
        if not clean or false_success or hallucinated or wait_filler or prompt_dump:
            clean = str(gen.get("reply") or "Listo. Aquí está tu imagen generada.")
        attachment = {
            "url": str(gen["url"]),
            "caption": str(gen.get("caption") or "Imagen generada"),
            "prompt": str(gen.get("caption") or user_text)[:200],
            "quality": gen.get("quality"),
        }
        return clean, attachment

    err = str(gen.get("error") or gen.get("reply") or "No pude generar la imagen.")
    clean = strip_hallucinated_generate_image_text(reply)
    if clean and not hallucinated and not false_success and not wait_filler and not prompt_dump:
        return f"{clean}\n\n{err}", None
    return err, None
