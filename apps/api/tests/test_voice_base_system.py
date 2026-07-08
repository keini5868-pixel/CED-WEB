"""Tests — prompt base ligero vs prompt legacy de voz (Fase 2 v2).

Verifica que ``build_base_voice_system`` NO precarga memoria global y que
``build_voice_system`` (producción) sigue incluyéndola vía legacy hasta Fase 3.
"""

from __future__ import annotations

from unittest.mock import patch

from app.services.voice_llm_common import build_base_voice_system, build_voice_system


FAKE_USER_CTX = (
    "# CONTEXTO DEL USUARIO (SESIONES ANTERIORES)\n"
    "## ÚLTIMAS CONVERSACIONES\n- [2026-07-01] Hablamos de finanzas."
)


def test_base_voice_system_has_ced_identity():
    prompt = build_base_voice_system(None, "hola")
    assert "CED" in prompt


def test_base_voice_system_excludes_global_memory():
    with patch(
        "app.services.conversation_memory.load_user_context",
        return_value=FAKE_USER_CTX,
    ), patch(
        "app.services.session_memory.get_session_memory_context",
        return_value="Sesión previa: tema maps.",
    ):
        prompt = build_base_voice_system("user-abc", "hola")
    assert "CONTEXTO DEL USUARIO" not in prompt
    assert "Sesión previa" not in prompt


def test_build_voice_system_still_includes_legacy_memory():
    with patch(
        "app.services.conversation_memory.load_user_context",
        return_value=FAKE_USER_CTX,
    ), patch(
        "app.services.session_memory.get_session_memory_context",
        return_value="",
    ), patch(
        "app.services.cognitive_router.build_voice_system_extras",
        return_value="",
    ):
        prompt = build_voice_system("user-abc", "hola")
    assert "CONTEXTO DEL USUARIO" in prompt


def test_base_is_shorter_than_legacy_with_memory():
    with patch(
        "app.services.conversation_memory.load_user_context",
        return_value=FAKE_USER_CTX * 3,
    ), patch(
        "app.services.session_memory.get_session_memory_context",
        return_value="x" * 500,
    ), patch(
        "app.services.cognitive_router.build_voice_system_extras",
        return_value="y" * 200,
    ):
        base = build_base_voice_system("user-abc", "hola")
        full = build_voice_system("user-abc", "hola")
    assert len(base) < len(full)


def test_base_skips_session_state_by_default():
    with patch("app.services.voice_client_session.is_camera_active", return_value=True):
        prompt = build_base_voice_system("user-abc", "hola", include_session_state=False)
    assert "ESTADO CÁMARA" not in prompt


def test_base_includes_session_state_when_requested():
    with patch("app.services.voice_client_session.is_camera_active", return_value=True), patch(
        "app.services.voice_client_session.get_last_publishable_image",
        return_value=None,
    ), patch(
        "app.services.voice_client_session.list_publishable_images",
        return_value=[],
    ), patch(
        "app.services.voice_client_session.get_active_mode_prompt",
        return_value="",
    ):
        prompt = build_base_voice_system("user-abc", "hola", include_session_state=True)
    assert "ESTADO CÁMARA" in prompt
    assert "ACTIVA" in prompt
