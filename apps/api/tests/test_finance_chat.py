"""Tests — chat dedicado de finanzas: greeting, registro directo y routing."""

from __future__ import annotations

import json

import app.services.finance_chat as fc


def _collect_done(events: list[str]) -> dict:
    for ev in events:
        if ev.startswith("event: done"):
            data_line = [ln for ln in ev.splitlines() if ln.startswith("data: ")][0]
            return json.loads(data_line[6:])
    raise AssertionError("no done event")


def test_greeting_reply_instant():
    out = fc.send_finance_message("u1", message="hola", history=[])
    assert "finanzas" in out["response"].lower()
    assert out["model"] == fc.FINANCE_STREAM_MODEL_LABEL


def test_stream_greeting_hola_yields_token_immediately():
    events = list(fc.iter_finance_message_stream("u1", message="HOLA", history=[]))
    token_events = [ev for ev in events if ev.startswith("event: token")]
    assert token_events, "expected instant greeting token"
    done = _collect_done(events)
    assert "finanzas" in done["response"].lower()


def test_write_intent_registers(monkeypatch):
    captured = {}

    def fake_handle(user_id, text):
        captured["text"] = text
        return {"spoken": "Señor, registré un gasto de 50 USD en materiales."}

    monkeypatch.setattr(fc, "handle_finance_query_sync", fake_handle)
    out = fc.send_finance_message(
        "u1", message="gasté 50 dólares en materiales hoy", history=[]
    )
    assert "registré" in out["response"].lower()
    assert captured["text"].startswith("gasté")


def test_stream_write_intent(monkeypatch):
    monkeypatch.setattr(
        fc,
        "handle_finance_query_sync",
        lambda user_id, text: {"spoken": "Señor, anoté un ingreso de 800 USD."},
    )
    events = list(
        fc.iter_finance_message_stream(
            "u1", message="recibí 800 dólares de un cliente", history=[]
        )
    )
    done = _collect_done(events)
    assert "ingreso" in done["response"].lower()


def test_snapshot_injects_real_data(monkeypatch):
    monkeypatch.setattr(
        fc,
        "summarize_finances",
        lambda user_id, period="mes": {
            "count": 1 if period == "mes" else 0,
            "total_ingreso": 800.0,
            "total_gasto": 80.0,
            "balance": 720.0,
            "period_label": "este mes",
            "top_categories": [("materiales", 80.0)],
        },
    )
    snap = fc._finance_snapshot("u1")
    assert "DATOS REALES" in snap
    assert "ingresos" in snap.lower()


def test_snapshot_handles_errors(monkeypatch):
    def boom(user_id, period="mes"):
        raise RuntimeError("db down")

    monkeypatch.setattr(fc, "summarize_finances", boom)
    assert fc._finance_snapshot("u1") == ""


def test_instant_finance_query_reply(monkeypatch):
    monkeypatch.setattr(
        fc,
        "summarize_finances",
        lambda user_id, period="mes": {
            "count": 3,
            "total_ingreso": 1200.0,
            "total_gasto": 400.0,
            "balance": 800.0,
            "period_label": "este mes",
            "top_categories": [("materiales", 200.0)],
        },
    )
    reply = fc._instant_finance_query_reply("u1", "¿Cómo voy este mes?")
    assert reply
    assert "mes" in reply.lower()


def test_instant_finance_query_returns_fallback_on_db_error(monkeypatch):
    def boom(user_id, period="mes"):
        raise RuntimeError("db down")

    monkeypatch.setattr(fc, "summarize_finances", boom)
    reply = fc._instant_finance_query_reply("u1", "como voy este mes")
    assert reply
    assert "consultar" in reply.lower()


def test_stream_finance_query_yields_token_immediately(monkeypatch):
    monkeypatch.setattr(
        fc,
        "summarize_finances",
        lambda user_id, period="mes": {
            "count": 2,
            "total_ingreso": 500.0,
            "total_gasto": 100.0,
            "balance": 400.0,
            "period_label": "este mes",
            "top_categories": [],
        },
    )
    events = list(
        fc.iter_finance_message_stream("u1", message="¿Cómo voy este mes?", history=[])
    )
    token_events = [ev for ev in events if ev.startswith("event: token")]
    assert token_events, "expected instant finance summary token"
    done = _collect_done(events)
    assert done["response"].strip()


def test_stream_finance_query_skips_llm_path(monkeypatch):
    """Consultas tipo 'cómo voy' nunca deben entrar al stream LLM lento."""

    def fail_stream(*args, **kwargs):
        raise AssertionError("LLM stream should not run for finance queries")

    monkeypatch.setattr(fc, "_gemini_simple_reply_stream", fail_stream)
    monkeypatch.setattr(
        fc,
        "summarize_finances",
        lambda user_id, period="mes": {
            "count": 1,
            "total_ingreso": 0.0,
            "total_gasto": 300.0,
            "balance": -300.0,
            "period_label": "este mes",
            "top_categories": [],
        },
    )
    events = list(
        fc.iter_finance_message_stream("u1", message="como voy este mes", history=[])
    )
    token_events = [ev for ev in events if ev.startswith("event: token")]
    assert token_events
    done = _collect_done(events)
    assert "mes" in done["response"].lower()


def test_stream_llm_reply_yields_token_before_done(monkeypatch):
    """Cuando el stream LLM no emite deltas pero hay respuesta final, debe haber token."""
    import app.services.cloud_llm_fallback as cfb

    def fake_stream(*args, **kwargs):
        return
        yield  # pragma: no cover — generator marker

    monkeypatch.setattr(fc, "_gemini_simple_reply_stream", fake_stream)
    monkeypatch.setattr(
        cfb,
        "chat_cloud_reply",
        lambda **kwargs: "Señor, este mes lleva un balance positivo de 400 USD.",
    )
    monkeypatch.setattr(fc, "_ensure_llm_providers", lambda **kwargs: ("", "gk"))
    monkeypatch.setattr(fc, "_needs_finance_tools", lambda text, history: False)
    monkeypatch.setattr(fc, "_finance_system_with_data", lambda prompt, user_id: prompt)
    monkeypatch.setattr(fc, "_instant_finance_query_reply", lambda user_id, text: None)

    events = list(
        fc.iter_finance_message_stream(
            "u1",
            message="¿Qué me recomiendas para ahorrar más?",
            history=[],
        )
    )
    token_events = [ev for ev in events if ev.startswith("event: token")]
    assert token_events, "expected token before done when cloud fallback fills reply"
    done = _collect_done(events)
    assert "balance" in done["response"].lower() or "ahorr" in done["response"].lower()
