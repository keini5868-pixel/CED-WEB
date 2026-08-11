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
    assert "CIERRE ESTRATÉGICO" not in s1
    assert "CIERRE ESTRATÉGICO" not in s2
    assert "CIERRE ESTRATÉGICO" in s3
    assert "Finanzas" in s3 or "plan de acción" in s3.lower()
    assert mark.called
    assert "proyección" in _FITLINE_CLOSE_AFTER_QUESTIONS.lower() or "futuro" in _FITLINE_CLOSE_AFTER_QUESTIONS.lower()
