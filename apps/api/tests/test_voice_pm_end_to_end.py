"""Prueba real del PATH DE VOZ (Retell → GeminiVoiceLlm → build_voice_system).

Simula exactamente lo que usa producción en turnos FitLine, incluyendo el caso
Context Cache (omit_static_core + omit_fitline_knowledge) donde el closer debe
seguir inyectándose.
"""

from __future__ import annotations

from unittest.mock import patch

from app.services.opportunities_pilot.fitline_gemini_cache import (
    build_fitline_context_cache_text,
)
from app.services.opportunities_pilot.fitline_knowledge import prefers_fitline_over_web
from app.services.retell_custom_llm import resolve_web_search_request
from app.services.voice_greetings import JARVIS_GREETING_POOL, pick_jarvis_greeting
from app.services.voice_llm_common import build_voice_system


def _assert_pm_knowledge(block: str) -> None:
    assert "NTC" in block or "Nutrient Transport" in block
    assert "Cologne" in block or "cologne" in block.lower()
    assert "Rolf Sorg" in block or "Speyer" in block
    assert "Activize" in block or "Restorate" in block
    assert "Sarasota" in block or "Manatee" in block or "América" in block
    assert "ASESOR COMERCIAL" in block or "CIERRE ESTRATÉGICO" in block
    # "Hi there" puede aparecer en la lista PROHIBIDO — eso es correcto.
    assert "PROHIBIDO" in block and (
        "Hi there" in block or "inglés" in block.lower() or "ingles" in block.lower()
    )


def test_voice_cache_text_has_full_pm_knowledge():
    """Lo que Gemini cachea para voz Retell (ficha completa)."""
    text = build_fitline_context_cache_text()
    assert len(text) > 6000
    _assert_pm_knowledge(text)
    assert "PM Labs" in text or "Made in USA" in text or "22 millones" in text


def test_voice_system_inline_has_pm_knowledge_and_sales():
    system = build_voice_system(
        "voice-user-1",
        "¿Qué es FitLine y cómo funciona el NTC?",
    )
    _assert_pm_knowledge(system)


def test_voice_system_with_cache_omit_still_gets_close_trigger():
    """Regresión: con cache, omit_fitline_knowledge=True no debe saltarse el closer."""
    uid = "voice-close-user"
    q1 = "¿Qué es PM International?"
    q2 = "¿Cómo es la expansión en América?"
    q3 = "¿Cómo empiezo la franquicia FitLine?"

    calls = {"n": 0}

    def fake_register(user_id, text):
        calls["n"] += 1
        # Simula engagement real para follow-ups (expansión América, etc.).
        try:
            from app.services import voice_client_session as vcs

            sess = vcs._get(user_id)
            sess["fitline_question_count"] = calls["n"]
        except Exception:  # noqa: BLE001
            pass
        return {
            "question_count": calls["n"],
            "closer_offered": False,
            "should_inject_closer": calls["n"] >= 3,
        }

    with (
        patch(
            "app.services.opportunities_pilot.fitline_guide_mode.user_plan_is_fitline_focus",
            return_value=True,
        ),
        patch(
            "app.services.opportunities_pilot.fitline_close_trigger.register_fitline_user_turn",
            side_effect=fake_register,
        ),
        patch(
            "app.services.opportunities_pilot.fitline_close_trigger.mark_closer_offered",
        ),
        patch(
            "app.services.insight_questions.capture_insight_question",
            return_value=None,
        ),
    ):
        # Path producción con Context Cache
        s1 = build_voice_system(
            uid, q1, omit_static_core=True, omit_fitline_knowledge=True
        )
        s2 = build_voice_system(
            uid, q2, omit_static_core=True, omit_fitline_knowledge=True
        )
        s3 = build_voice_system(
            uid, q3, omit_static_core=True, omit_fitline_knowledge=True
        )

    assert "CIERRE ESTRATÉGICO" not in s1 and "CIERRE PRIORITARIO" not in s1
    assert "CIERRE ESTRATÉGICO" not in s2 and "CIERRE PRIORITARIO" not in s2
    assert "CIERRE PRIORITARIO" in s3 or "90 días" in s3
    assert "Finanzas" in s3 or "plan de acción" in s3.lower()
    assert "90 días" in s3 or "90 dias" in s3.lower()
    assert "negocio" in s3.lower() or "dinero" in s3.lower() or "ganar" in s3.lower()


def test_voice_prefers_internal_knowledge_over_web():
    assert prefers_fitline_over_web("precio de Restorate FitLine") is True
    assert prefers_fitline_over_web("qué es el NTC de FitLine") is True
    decision = resolve_web_search_request("cuéntame de Activize FitLine", [])
    assert decision is None


def test_jarvis_greeting_pool_is_standard_spanish():
    for g in JARVIS_GREETING_POOL:
        low = g.lower()
        assert "hi there" not in low
        assert "what's on your mind" not in low
        assert "claro, claro" not in low
        assert "claude" not in low
        assert "gemini" not in low
    sample = pick_jarvis_greeting("greeting-test-user")
    assert isinstance(sample, str) and len(sample) > 8
    assert "hi there" not in sample.lower()
