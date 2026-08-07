"""Voz: FitLine Oportunidades + playbook al pedir producto/marca."""

from __future__ import annotations

from app.services.voice_llm_common import build_base_voice_system


def test_voice_system_injects_fitline_for_activise():
    system = build_base_voice_system("user-test", "dame una idea de copy para vender Activise")
    assert "Oportunidades" in system or "Activize" in system
    assert "PLAYBOOK INTERNO" in system or "AIDA" in system


def test_voice_system_skips_fitline_on_greeting():
    system = build_base_voice_system("user-test", "hola")
    assert "CONOCIMIENTO CURADO — PM International" not in system
