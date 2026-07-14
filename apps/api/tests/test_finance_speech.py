"""Tests — montos y fechas habladas en finanzas (TTS natural)."""

from __future__ import annotations

from app.modules.finance_module import _confirm_pending_spoken, _confirm_spoken, parse_pending_statements
from app.services.finance_speech import (
    amount_to_spoken_es,
    due_date_to_spoken_es,
    embed_due_time_in_description,
    parse_due_time,
)
from app.services.finance_write_flow import _summarize_draft_rows


def test_amount_to_spoken_natural():
    assert amount_to_spoken_es(1000) == "mil dólares"
    assert amount_to_spoken_es(1500) == "mil quinientos dólares"
    assert "quinientos" in amount_to_spoken_es(1500.50)
    assert "centavos" in amount_to_spoken_es(1500.50)
    assert "uno, cero" not in amount_to_spoken_es(1000)
    assert "1000" not in amount_to_spoken_es(1000)


def test_parse_due_time_night():
    assert parse_due_time("el viernes a las 9 de la noche") == "21:00"
    assert parse_due_time("a las 9 pm") == "21:00"
    assert parse_due_time("a las 9:30 am") == "09:30"


def test_parse_pending_keeps_time_not_category():
    rows = parse_pending_statements(
        "anotar pago pendiente de 1000 para el viernes a las 9 de la noche"
    )
    assert len(rows) == 1
    assert rows[0]["amount"] == "1000"
    assert rows[0]["due_date"]  # viernes resuelto
    assert rows[0]["due_time"] == "21:00"
    assert rows[0]["category"] in {None, ""}


def test_confirm_pending_spoken_is_natural():
    spoken = _confirm_pending_spoken(
        [
            {
                "amount": 1000.0,
                "currency": "USD",
                "category": None,
                "due_date": "2026-07-17",
                "due_time": "21:00",
                "description": "hora 21:00. pago pendiente",
            }
        ]
    )
    assert "mil dólares" in spoken
    assert "1000" not in spoken
    assert "para para" not in spoken
    assert "a las" in spoken
    assert "noche" in spoken or "tarde" in spoken


def test_confirm_gasto_spoken_natural():
    spoken = _confirm_spoken(
        {"type": "gasto", "amount": 1500, "currency": "USD", "category": "materiales"}
    )
    assert "mil quinientos dólares" in spoken
    assert "1500" not in spoken


def test_prepare_summary_natural():
    spoken = _summarize_draft_rows(
        "pending",
        [
            {
                "amount": "1000",
                "category": None,
                "due_date": "2026-07-17",
                "due_time": "21:00",
            }
        ],
    )
    assert "mil dólares" in spoken
    assert "¿Desea que lo registre?" in spoken
    assert "para para" not in spoken


def test_embed_due_time_in_description():
    desc = embed_due_time_in_description("pago mercado", "21:00")
    assert desc and desc.startswith("hora 21:00.")
    assert due_date_to_spoken_es("2026-07-17", due_time="21:00").startswith("el viernes")
