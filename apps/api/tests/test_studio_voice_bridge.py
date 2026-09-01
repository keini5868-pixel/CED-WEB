"""Chat de estudio (texto/archivo/imagen) visible para el cerebro de voz."""

from __future__ import annotations

from unittest.mock import patch

from app.services import voice_client_session as vcs
from app.services.voice_llm_common import build_voice_system, wants_text_chat_recall


UID = "studio-voice-bridge-user"


def setup_function() -> None:
    vcs.end_voice_publish_session(UID)


def teardown_function() -> None:
    vcs.end_voice_publish_session(UID)


def test_push_ignored_without_active_voice():
    vcs.push_studio_chat_event(UID, kind="text", text="hola desde el chat")
    assert vcs.format_studio_chat_overlay(UID) == ""


def test_text_and_file_appear_in_voice_system():
    vcs.begin_voice_publish_session(UID, "call-bridge-1")
    vcs.push_studio_chat_event(UID, kind="text", text="te envío esto por escrito")
    vcs.push_studio_chat_event(
        UID,
        kind="document",
        text="Analiza el PDF",
        filename="catalogo.pdf",
    )
    overlay = vcs.format_studio_chat_overlay(UID)
    assert "CHAT DE TEXTO EN VIVO" in overlay
    assert "te envío esto por escrito" in overlay
    assert "catalogo.pdf" in overlay

    with patch(
        "app.services.conversation_memory.load_user_context",
        return_value="",
    ), patch(
        "app.services.session_memory.get_session_memory_context",
        return_value="",
    ), patch(
        "app.services.cognitive_router.build_voice_system_extras",
        return_value="",
    ):
        prompt = build_voice_system(UID, "qué te mandé", lightweight=True)
    assert "te envío esto por escrito" in prompt
    assert "catalogo.pdf" in prompt


def test_long_text_bridge_not_truncated_at_500():
    vcs.begin_voice_publish_session(UID, "call-long")
    body = "GUION " + ("escena " * 200)
    assert len(body) > 500
    vcs.push_studio_chat_event(UID, kind="text", text=body)
    overlay = vcs.format_studio_chat_overlay(UID)
    assert "GUION" in overlay
    assert len(overlay) > 500


def test_wants_text_chat_recall():
    assert wants_text_chat_recall("leeme lo que te envie por texto")
    assert wants_text_chat_recall("usa el guion que te mandé")
    assert wants_text_chat_recall("qué te escribí en el chat")
    assert not wants_text_chat_recall("hola qué tal")


def test_recall_without_text_forbids_fitline_fill():
    with patch(
        "app.services.conversation_memory.load_user_context",
        return_value="",
    ), patch(
        "app.services.session_memory.get_session_memory_context",
        return_value="",
    ), patch(
        "app.services.cognitive_router.build_voice_system_extras",
        return_value="",
    ), patch(
        "app.services.conversation_memory.format_text_chat_for_voice_overlay",
        return_value="",
    ), patch(
        "app.services.opportunities_pilot.fitline_guide_mode.user_plan_is_fitline_focus",
        return_value=True,
    ), patch(
        "app.services.opportunities_pilot.fitline_knowledge.wants_fitline_knowledge",
        return_value=False,
    ), patch(
        "app.services.opportunities_pilot.fitline_knowledge.should_inject_fitline_for_turn",
        return_value=False,
    ), patch(
        "app.services.opportunities_pilot.fitline_knowledge.append_fitline_knowledge_if_needed",
        side_effect=lambda system, _text, force=False, user_id=None: system,
    ) as append_fit:
        prompt = build_voice_system(
            UID, "leeme lo que te envié por texto", lightweight=True
        )
    assert "SIN CONTENIDO DISPONIBLE" in prompt
    assert "PROHIBIDO rellenar con FitLine" in prompt
    assert not append_fit.called


def test_recall_injects_persisted_text_chat():
    guion = "GUION COMPLETO: escena 1 apertura, escena 2 cierre FitLine."
    with patch(
        "app.services.conversation_memory.load_user_context",
        return_value="",
    ), patch(
        "app.services.session_memory.get_session_memory_context",
        return_value="",
    ), patch(
        "app.services.cognitive_router.build_voice_system_extras",
        return_value="",
    ), patch(
        "app.services.conversation_memory.format_text_chat_for_voice_overlay",
        return_value=("[CHAT DE TEXTO RECIENTE] literal\n- Usuario: " + guion),
    ), patch(
        "app.services.opportunities_pilot.fitline_guide_mode.user_plan_is_fitline_focus",
        return_value=True,
    ), patch(
        "app.services.opportunities_pilot.fitline_knowledge.wants_fitline_knowledge",
        return_value=False,
    ), patch(
        "app.services.opportunities_pilot.fitline_knowledge.should_inject_fitline_for_turn",
        return_value=False,
    ), patch(
        "app.services.opportunities_pilot.fitline_knowledge.append_fitline_knowledge_if_needed",
        side_effect=lambda system, _text, force=False, user_id=None: system,
    ):
        prompt = build_voice_system(UID, "lee el guion que te mandé", lightweight=True)
    assert "GUION COMPLETO" in prompt
    assert "SIN CONTENIDO DISPONIBLE" not in prompt
