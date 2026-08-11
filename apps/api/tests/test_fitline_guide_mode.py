"""Tests — Modo Guía FitLine/PM (mentor pedagógico)."""

from __future__ import annotations

from app.services import voice_client_session as vcs
from app.services.opportunities_pilot.fitline_guide_mode import (
    GUIDE_STEPS,
    append_fitline_guide_if_needed,
    format_guide_overlay,
    is_guide_activate_phrase,
    is_guide_advance_phrase,
    is_guide_deactivate_phrase,
    is_guide_reexplain_phrase,
    prepare_fitline_guide_turn,
)
from app.services.opportunities_pilot.fitline_knowledge import format_fitline_knowledge_for_prompt
from app.services.text_chat import _build_chat_system_light
from app.services.voice_llm_common import build_base_voice_system

USER = "guide-test-user-001"


def setup_function() -> None:
    vcs.clear_fitline_guide(USER)
    vcs.set_fitline_guide_opt_out(USER, False)


def test_auto_guide_for_cierre_non_admin(monkeypatch):
    from app.services.opportunities_pilot import fitline_guide_mode as gm

    monkeypatch.setattr(gm, "is_fitline_admin_user", lambda _uid: False)
    monkeypatch.setattr(gm, "user_plan_is_fitline_focus", lambda _uid: True)
    vcs.clear_fitline_guide(USER)
    vcs.set_fitline_guide_opt_out(USER, False)

    # Voz: sin auto-guía (paridad Retell en productos).
    st_voice = prepare_fitline_guide_turn(USER, "hola qué es FitLine", channel="voice")
    assert st_voice.get("active") is not True

    # Chat: sí auto-guía para socio nuevo Cierre.
    st = prepare_fitline_guide_turn(USER, "hola qué es FitLine", channel="chat")
    assert st.get("active") is True
    assert st.get("just_activated") is True
    assert st.get("auto") is True


def test_admin_skips_auto_guide(monkeypatch):
    from app.services.opportunities_pilot import fitline_guide_mode as gm

    monkeypatch.setattr(gm, "is_fitline_admin_user", lambda _uid: True)
    monkeypatch.setattr(gm, "user_plan_is_fitline_focus", lambda _uid: True)
    vcs.clear_fitline_guide(USER)

    st = prepare_fitline_guide_turn(USER, "hola qué es FitLine", channel="voice")
    assert st.get("active") is False


def test_opt_out_blocks_auto_reentry(monkeypatch):
    from app.services.opportunities_pilot import fitline_guide_mode as gm

    monkeypatch.setattr(gm, "is_fitline_admin_user", lambda _uid: False)
    monkeypatch.setattr(gm, "user_plan_is_fitline_focus", lambda _uid: True)
    prepare_fitline_guide_turn(USER, "hola", channel="voice")
    prepare_fitline_guide_turn(USER, "salir del modo guía", channel="voice")
    st = prepare_fitline_guide_turn(USER, "qué es Activize", channel="voice")
    assert st.get("active") is False
    assert vcs.is_fitline_guide_opt_out(USER) is True


def test_activate_phrases():
    assert is_guide_activate_phrase("modo guía")
    assert is_guide_activate_phrase("explícame cómo funciona esto desde cero")
    assert is_guide_activate_phrase("soy nuevo, guíame")
    assert is_guide_activate_phrase("enséñame el negocio desde cero")
    assert is_guide_activate_phrase("activa modo guía")
    assert not is_guide_activate_phrase("hola cómo estás")
    assert not is_guide_activate_phrase("precio de Restorate")


def test_advance_and_reexplain_phrases():
    assert is_guide_advance_phrase("sí")
    assert is_guide_advance_phrase("quedó claro")
    assert is_guide_advance_phrase("siguiente")
    assert is_guide_reexplain_phrase("no entendí")
    assert is_guide_reexplain_phrase("explícalo de otra forma")
    assert is_guide_deactivate_phrase("salir del modo guía")


def test_guide_progresses_steps():
    st = prepare_fitline_guide_turn(USER, "modo guía", channel="chat")
    assert st["active"] is True
    assert st["step_index"] == 0
    assert st["step"]["id"] == "intro"

    st = prepare_fitline_guide_turn(USER, "sí", channel="chat")
    assert st["step_index"] == 1
    assert st["step"]["id"] == "company_products"

    st = prepare_fitline_guide_turn(USER, "siguiente", channel="chat")
    assert st["step_index"] == 2
    assert st["step"]["id"] == "how_earn"

    st = prepare_fitline_guide_turn(USER, "no entendí", channel="chat")
    assert st["step_index"] == 2
    assert st["reexplain"] is True

    st = prepare_fitline_guide_turn(USER, "salir del modo guía", channel="chat")
    assert st["active"] is False
    assert st.get("just_deactivated") is True


def test_overlay_voice_is_shorter_than_chat():
    step = GUIDE_STEPS[1]
    chat = format_guide_overlay(
        {"active": True, "step_index": 1, "step": step, "reexplain": False},
        channel="chat",
    )
    voice = format_guide_overlay(
        {"active": True, "step_index": 1, "step": step, "reexplain": False},
        channel="voice",
    )
    assert "MODO GUÍA" in chat and "MODO GUÍA" in voice
    assert "Quedó claro" in chat or "quedó claro" in chat.lower()
    assert len(voice) < len(chat) or "2–4 oraciones" in voice or "2-4 oraciones" in voice
    assert "Income Plan" in chat or "no invent" in chat.lower()


def test_chat_and_voice_systems_inject_guide():
    format_fitline_knowledge_for_prompt.cache_clear()
    vcs.clear_fitline_guide(USER)
    chat = _build_chat_system_light(USER, "explícame cómo funciona esto desde cero")
    assert "MODO GUÍA" in chat
    assert "Oportunidades" in chat or "FitLine" in chat
    assert vcs.is_fitline_guide_active(USER)

    voice = build_base_voice_system(USER, "sí")
    assert "MODO GUÍA" in voice
    # Tras «sí» debe haber avanzado al bloque empresa/productos
    assert vcs.get_fitline_guide_step(USER) == 1


def test_append_idempotent_knowledge_block():
    format_fitline_knowledge_for_prompt.cache_clear()
    vcs.clear_fitline_guide(USER)
    base = "SYSTEM"
    out1 = append_fitline_guide_if_needed(base, USER, "modo guía", channel="chat")
    assert out1.count("HECHOS OBLIGATORIOS FITLINE") == 1
    # Segundo append en mismo proceso con guía ya activa y «ok» no debe duplicar hechos
    # (prepare avanza paso, pero el bloque de hechos es uno).
    out2 = append_fitline_guide_if_needed(out1, USER, "ok", channel="chat")
    assert out2.count("HECHOS OBLIGATORIOS FITLINE") == 1
