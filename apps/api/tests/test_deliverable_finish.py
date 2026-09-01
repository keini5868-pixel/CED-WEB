"""Entregables: cierre, anti-duplicado y presupuesto de tokens."""

from __future__ import annotations

from app.services.advanced_mode.claude_stream import stream_max_tokens
from app.services.deliverable_replies import (
    append_deliverable_finish_if_needed,
    collapse_repeated_deliverable_passages,
    is_deliverable_continuation_turn,
    is_deliverable_request,
    is_incomplete_deliverable,
    looks_truncated_mid_sentence,
    needs_deliverable_token_budget,
)
from app.services.text_chat import CHAT_DELIVERABLE_MAX_TOKENS, _finalize_chat_reply
from app.services.voice_llm_common import voice_generation_limits


def test_guion_lanzamiento_is_deliverable():
    assert is_deliverable_request(
        "ayudame a hacer un guio corto para el lanzamiento de ced"
    )
    assert is_deliverable_request("cómo puedo terminarlo")


def test_instagram_followup_is_continuation():
    history = [
        {
            "role": "assistant",
            "content": (
                "Señor, eso es oro puro. Me dije: si no lo intento, nunca sabré. "
                "Y así nació CED. ¿Listo para intentarlo?\n\n**Por qué funciona:** ..."
            ),
        }
    ]
    assert is_deliverable_continuation_turn(
        "ENTONCES TE PARECE BIEN", history
    )
    assert is_deliverable_continuation_turn(
        "ES EN IMTAGRAN Y FACE QUE LO VOY A PUBLICAR", history
    )
    assert needs_deliverable_token_budget(
        "ES EN IMTAGRAN Y FACE QUE LO VOY A PUBLICAR", history
    )


def test_stream_max_tokens_not_tiny_on_channel_pick():
    history = [
        {
            "role": "assistant",
            "content": "Y así nació CED. Un asistente que entiende tu negocio." * 5,
        }
    ]
    n = stream_max_tokens("ES EN INSTAGRAM Y FACE", history=history)
    assert n >= CHAT_DELIVERABLE_MAX_TOKENS
    assert n > 280


def test_voice_limits_raise_on_finish_turn():
    tokens, _timeout = voice_generation_limits("te parece bien")
    assert tokens >= 2000


def test_collapse_removes_stacked_script_halves():
    broken = (
        "Perfecto, señor. Pero un día tuve una idea. Me dije: "
        "*si no lo intento, nunca sabré si pueda lograrlo.*\n"
        "Y así nació **CED**. Un asistente que entiende tu negocio. "
        "Que habla tu idioma. Que te da estrategia real. "
        "Pero un día tuve una idea y me dije a mí mismo: "
        "*si no lo intento, nunca sabré si pueda lograrlo.*\n\n"
        "Y así nació **CED**. No vino de un laboratorio de Silicon Valley. "
        "Vino de la obsesión de hacer un asistente que entienda **tu negocio**—que hable"
    )
    out = collapse_repeated_deliverable_passages(broken)
    assert out.lower().count("si no lo intento") == 1
    assert "silicon valley" in out.lower() or "nació" in out.lower()


def test_truncated_mid_sentence_detected():
    assert looks_truncated_mid_sentence(
        "Vino de la obsesión de hacer un asistente que entienda tu negocio—que hable"
    )
    assert is_incomplete_deliverable(
        "Vino de la obsesión de hacer un asistente que entienda tu negocio—que hable",
        "ES EN INSTAGRAM Y FACE",
    )


def test_finalize_collapses_duplicate_script():
    raw = (
        "Y así nació CED. Un asistente que entiende tu negocio.\n\n"
        "Y así nació CED. Un asistente que entiende tu negocio. "
        "Que habla tu idioma."
    )
    out = _finalize_chat_reply(raw)
    assert out.lower().count("y así nació ced") <= 1


def test_finish_overlay_injected():
    history = [
        {
            "role": "assistant",
            "content": "Y así nació CED. Si no lo intento, nunca sabré." * 3,
        }
    ]
    out = append_deliverable_finish_if_needed(
        "BASE SYSTEM",
        "es en Instagram y Facebook",
        history,
    )
    assert "CIERRE DE ENTREGABLE" in out
