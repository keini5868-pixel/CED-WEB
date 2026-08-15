"""Tests — foro de insights + disparador de cierre FitLine tras 3 preguntas."""

from __future__ import annotations

from unittest.mock import patch

from app.services.insight_questions import looks_like_valuable_question
from app.services.opportunities_pilot.fitline_close_trigger import (
    FITLINE_QUESTIONS_BEFORE_CLOSER,
    _FITLINE_CLOSE_AFTER_QUESTIONS,
    append_fitline_close_trigger_if_needed,
)


def test_trivial_not_captured():
    ok, tags, _ = looks_like_valuable_question("hola")
    assert ok is False
    assert tags == []


def test_fitline_business_question_captured():
    ok, tags, priority = looks_like_valuable_question(
        "¿Cómo funciona la franquicia de FitLine en Estados Unidos?"
    )
    assert ok is True
    assert "fitline" in tags or "business" in tags
    assert priority == "high"


def test_weak_assistant_raises_priority():
    ok, tags, priority = looks_like_valuable_question(
        "¿Cuál es el precio exacto de entrada al negocio PM?",
        assistant_reply="No tengo esa información disponible ahora.",
    )
    assert ok is True
    assert "weak_answer" in tags
    assert priority == "high"


def test_closer_injects_after_three_questions():
    calls = {"n": 0}

    def fake_register(uid, text):
        calls["n"] += 1
        return {
            "question_count": calls["n"],
            "closer_offered": False,
            "should_inject_closer": calls["n"] >= FITLINE_QUESTIONS_BEFORE_CLOSER,
        }

    with (
        patch(
            "app.services.opportunities_pilot.fitline_close_trigger.register_fitline_user_turn",
            side_effect=fake_register,
        ),
        patch(
            "app.services.opportunities_pilot.fitline_close_trigger.mark_closer_offered",
        ) as mark,
    ):
        s1 = append_fitline_close_trigger_if_needed("BASE", "u1", "qué es FitLine?")
        s2 = append_fitline_close_trigger_if_needed(s1, "u1", "cómo es la expansión en América?")
        s3 = append_fitline_close_trigger_if_needed(
            s2, "u1", "cómo empiezo la franquicia?"
        )
    assert "CIERRE ESTRATÉGICO" not in s1 and "CIERRE PRIORITARIO" not in s1
    assert "CIERRE ESTRATÉGICO" not in s2 and "CIERRE PRIORITARIO" not in s2
    assert "CIERRE PRIORITARIO" in s3 or "90 días" in s3
    assert "Finanzas" in s3 or "plan de acción" in s3.lower()
    assert mark.called
    assert "90 días" in _FITLINE_CLOSE_AFTER_QUESTIONS
    assert "entrar en el negocio" in _FITLINE_CLOSE_AFTER_QUESTIONS.lower() or "90 días" in _FITLINE_CLOSE_AFTER_QUESTIONS
    assert "Finanzas" in _FITLINE_CLOSE_AFTER_QUESTIONS
    assert "cierre de impacto" in _FITLINE_CLOSE_AFTER_QUESTIONS.lower()
    assert "invent" in _FITLINE_CLOSE_AFTER_QUESTIONS.lower() or "PROHIBIDO" in _FITLINE_CLOSE_AFTER_QUESTIONS


def test_keep_learning_defers_and_soft_reoffers():
    from app.services.opportunities_pilot import fitline_close_trigger as trig
    from app.services import voice_client_session as vcs

    uid = "u-keep-learn"
    s = vcs._get(uid)
    with vcs._lock:
        s["fitline_question_count"] = 3
        s["fitline_closer_offered"] = True
        s["fitline_keep_learning"] = False
        s["fitline_questions_since_defer"] = 0
        s["fitline_soft_reoffer_done"] = False
        s["fitline_closer_reasked"] = True

    with patch("app.services.supabase_db._client", side_effect=RuntimeError("no db")):
        out = append_fitline_close_trigger_if_needed(
            "BASE", uid, "todavía quiero seguir aprendiendo un poco más"
        )
        assert "SEGUIR APRENDIENDO" in out or "NO INSISTIR" in out
        assert "90 días" not in out or "NO repitas" in out

        # Más preguntas FitLine → reapertura suave
        s2 = append_fitline_close_trigger_if_needed(
            "BASE", uid, "qué es el NTC de FitLine exactamente?"
        )
        s3 = append_fitline_close_trigger_if_needed(
            "BASE", uid, "cómo es la expansión en América FitLine?"
        )
    assert "REAPERTURA" in s3 or "Finanzas" in s3 or "OPPS" in s3
    assert "SEGUIR APRENDIENDO" not in s2 or "NO INSISTIR" not in s2


def _reset_fitline_user(uid: str) -> None:
    from app.services.opportunities_pilot import fitline_close_trigger as trig
    from app.services import voice_client_session as vcs

    trig._recent_turns.pop(uid, None)
    vcs._sessions.pop(uid, None)


def test_real_third_fitline_question_fires_90_day_at_prompt_start():
    """Camino real (sin mock de register): 3.ª pregunta → overlay al INICIO."""
    uid = "u-90d-real-path"
    _reset_fitline_user(uid)
    qs = [
        "qué es FitLine?",
        "cómo es la expansión en América de PM International?",
        "cómo empiezo la franquicia FitLine?",
    ]
    with patch("app.services.supabase_db._client", side_effect=RuntimeError("no db")):
        s1 = append_fitline_close_trigger_if_needed("BASE EDUCATIVO", uid, qs[0])
        s2 = append_fitline_close_trigger_if_needed("BASE EDUCATIVO", uid, qs[1])
        s3 = append_fitline_close_trigger_if_needed("BASE EDUCATIVO", uid, qs[2])
        s4 = append_fitline_close_trigger_if_needed(
            "BASE EDUCATIVO", uid, "y cómo funciona el NTC de FitLine?"
        )

    assert "CIERRE PRIORITARIO" not in s1
    assert "CIERRE PRIORITARIO" not in s2
    assert s3.startswith("# CIERRE PRIORITARIO")
    assert "¿Cuánto quieres ganar en los próximos 90 días" in s3
    assert "Finanzas" in s3
    assert "entrar en el negocio hoy" in s3.lower()
    assert "MODO VENDEDOR" in s4
    assert "CIERRE PRIORITARIO" not in s4


def test_hablame_de_fitline_counts_and_followup_without_brand():
    uid = "u-90d-followup"
    _reset_fitline_user(uid)
    with patch("app.services.supabase_db._client", side_effect=RuntimeError("no db")):
        append_fitline_close_trigger_if_needed("B", uid, "háblame de FitLine")
        append_fitline_close_trigger_if_needed("B", uid, "qué es PM International?")
        s3 = append_fitline_close_trigger_if_needed(
            "B", uid, "cómo se gana con la franquicia?"
        )
    assert s3.startswith("# CIERRE PRIORITARIO")


def test_same_text_twice_does_not_skip_to_closer_early():
    uid = "u-90d-dup"
    _reset_fitline_user(uid)
    q = "qué es FitLine y el NTC?"
    with patch("app.services.supabase_db._client", side_effect=RuntimeError("no db")):
        s1 = append_fitline_close_trigger_if_needed("B", uid, q)
        s1b = append_fitline_close_trigger_if_needed("B", uid, q)
        s2 = append_fitline_close_trigger_if_needed(
            "B", uid, "cómo es la expansión FitLine en América?"
        )
        s3 = append_fitline_close_trigger_if_needed(
            "B", uid, "cómo empiezo la franquicia FitLine?"
        )
    assert "CIERRE PRIORITARIO" not in s1
    assert "CIERRE PRIORITARIO" not in s1b
    assert "CIERRE PRIORITARIO" not in s2
    assert s3.startswith("# CIERRE PRIORITARIO")


def test_guide_yields_when_90_day_closer_is_active():
    from app.services.opportunities_pilot.fitline_guide_mode import (
        append_fitline_guide_if_needed,
    )

    uid = "u-90d-guide-yield"
    _reset_fitline_user(uid)
    with patch("app.services.supabase_db._client", side_effect=RuntimeError("no db")):
        append_fitline_close_trigger_if_needed("B", uid, "qué es FitLine?")
        append_fitline_close_trigger_if_needed("B", uid, "qué es PM International?")
        closer = append_fitline_close_trigger_if_needed(
            "B", uid, "cómo empiezo la franquicia FitLine?"
        )
        guided = append_fitline_guide_if_needed(
            closer, uid, "cómo empiezo la franquicia FitLine?", channel="chat"
        )
    assert guided == closer
    assert "MODO GUÍA" not in guided


def test_voice_cache_path_real_register_fires_on_third_question():
    from app.services.voice_llm_common import build_voice_system

    uid = "u-90d-voice-real"
    _reset_fitline_user(uid)
    qs = [
        "¿Qué es PM International?",
        "¿Cómo es la expansión en América FitLine?",
        "¿Cómo empiezo la franquicia FitLine?",
    ]
    with (
        patch(
            "app.services.opportunities_pilot.fitline_guide_mode.user_plan_is_fitline_focus",
            return_value=True,
        ),
        patch("app.services.supabase_db._client", side_effect=RuntimeError("no db")),
        patch(
            "app.services.insight_questions.capture_insight_question",
            return_value=None,
        ),
    ):
        s1 = build_voice_system(
            uid, qs[0], omit_static_core=True, omit_fitline_knowledge=True
        )
        s2 = build_voice_system(
            uid, qs[1], omit_static_core=True, omit_fitline_knowledge=True
        )
        s3 = build_voice_system(
            uid, qs[2], omit_static_core=True, omit_fitline_knowledge=True
        )
    assert "CIERRE PRIORITARIO" not in s1
    assert "CIERRE PRIORITARIO" not in s2
    assert "CIERRE PRIORITARIO" in s3
    assert s3.find("CIERRE PRIORITARIO") <= 80
    assert "90 días" in s3
    assert "Finanzas" in s3
