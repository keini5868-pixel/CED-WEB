"""Path rápido de charla casual en voz — KB interno o Llama, sin tools ni orquestador."""

from __future__ import annotations

import logging
import re

from app.services.retell_custom_llm import (
    _is_concept_question,
    _needs_internet_lookup,
    is_casual_conversation,
    is_meta_publish_intent,
    is_personal_vent_intent,
    is_script_demo_request,
    is_small_talk,
    is_web_research_intent,
    resolve_camera_voice_request,
    resolve_web_search_request,
)
from app.services.retell_llm_types import Utterance
from app.services.voice_intent_gate import has_explicit_module_signal

logger = logging.getLogger(__name__)

_CASUAL_BLOCK_PATTERNS = re.compile(
    r"\b("
    r"publica|publicar|recuerda|memoria|carolina|"
    r"genera(?:r|me)?|video|demo|mostrar|guion|guión|"
    r"relevante|estrategia|secuencia|seq|"
    r"c[aá]mara|camara|mira|visi[oó]n|imagen(?:es)?"
    r")\b",
    re.I,
)

LLAMA_CASUAL_MAX_TOKENS = 140
LLAMA_CASUAL_TEMPERATURE = 0.55
LLAMA_CASUAL_TIMEOUT_SEC = 8.0
LLAMA_VOICE_SAFETY_TIMEOUT_SEC = 25.0

CASUAL_VOICE_OVERLAY = """
# CHARLA CASUAL RÁPIDA
Responde en 1-2 oraciones completas, empática y directa.
NO invoques herramientas. NO prometas buscar ni investigar.
Si hay contexto interno CED en el prompt, úsalo en lenguaje natural sin leer etiquetas.
Si no hay contexto interno, razona con naturalidad como asistente personal.
""".strip()


def is_casual_voice_turn(text: str, transcript: list[Utterance] | None = None) -> bool:
    """True si el turno es charla casual sin señal explícita de módulo/herramienta."""
    norm = " ".join((text or "").strip().lower().split())
    if not norm:
        return False
    if has_explicit_module_signal(text):
        return False
    if resolve_camera_voice_request(text) is not None:
        return False
    if resolve_web_search_request(text, transcript or []) is not None:
        return False
    if (
        _needs_internet_lookup(text)
        or is_web_research_intent(text)
        or is_script_demo_request(text)
        or is_meta_publish_intent(text)
    ):
        return False
    if _CASUAL_BLOCK_PATTERNS.search(norm):
        return False
    if is_small_talk(text, transcript):
        return True
    if is_casual_conversation(text):
        return True
    if is_personal_vent_intent(text):
        return True
    if _is_concept_question(text):
        return True
    return True


def try_internal_knowledge_voice_reply(user_text: str) -> tuple[str | None, str]:
    """Lookup síncrono al KB interno. Retorna (respuesta, fuente) o (None, '')."""
    from app.services.cognitive_intents import is_internal_knowledge_query
    from app.services.internal_knowledge import (
        _HIGH_CONFIDENCE,
        best_internal_answer,
        should_use_internal_brain,
    )
    from app.services.voice_response_guard import guard_voice_response
    from app.services.voice_spoken import finalize_voice_delivery_text

    if not is_internal_knowledge_query(user_text):
        return None, ""
    hit = best_internal_answer(user_text)
    if not hit or not should_use_internal_brain(user_text, hit):
        return None, ""
    if hit.confidence < _HIGH_CONFIDENCE:
        return None, ""
    snippet = hit.summary.strip()
    if len(snippet) > 280:
        snippet = snippet[:277].rsplit(" ", 1)[0] + "..."
    safe, blocked = guard_voice_response(snippet)
    if blocked or not safe:
        return None, ""
    logger.info(
        "[RETELL-VOICE] internal_kb direct conf=%.2f title=%s",
        hit.confidence,
        hit.title[:60],
    )
    return finalize_voice_delivery_text(safe), "internal_kb"
