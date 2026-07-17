"""Tests — tracker de conexiones WS del Custom LLM (fix reconexión Retell).

Bug real confirmado en logs de producción: al reconectar el WebSocket LLM
(`auto_reconnect`), el backend perdía el estado "ya saludé" y volvía a
enviar el saludo de bienvenida a mitad de una llamada en curso (ej. justo
tras pedir una canción en YouTube), generando una respuesta fantasma que
confundía al flujo de confirmación. Estas pruebas fijan el comportamiento
correcto: `greeting_sent` sobrevive una reconexión del MISMO call_id.
"""

from __future__ import annotations

import time

from app.services import retell_ws_tracker as tracker


def test_greeting_state_survives_reconnect():
    call_id = "call-reconnect-1"
    tracker.mark_ws_connected(call_id)
    assert tracker.has_greeting_been_sent(call_id) is False

    tracker.mark_greeting_sent(call_id)
    assert tracker.has_greeting_been_sent(call_id) is True

    # Retell reconecta el WS LLM para la MISMA llamada (auto_reconnect) tras
    # un blip de red — no debe resetear que ya saludamos.
    tracker.mark_ws_disconnected(call_id)
    tracker.mark_ws_connected(call_id)
    assert tracker.has_greeting_been_sent(call_id) is True


def test_fresh_call_id_starts_without_greeting():
    call_id = "call-fresh-1"
    tracker.mark_ws_connected(call_id)
    assert tracker.has_greeting_been_sent(call_id) is False


def test_disconnect_does_not_drop_row_immediately():
    call_id = "call-reconnect-2"
    tracker.mark_ws_connected(call_id)
    tracker.mark_greeting_sent(call_id)
    tracker.mark_ws_disconnected(call_id)

    rows = {row["call_id"]: row for row in tracker.active_ws_calls()}
    assert call_id in rows
    assert rows[call_id]["is_connected"] is False
    assert rows[call_id]["greeting_sent"] is True


def test_stale_disconnected_rows_get_pruned(monkeypatch):
    call_id = "call-stale-1"
    tracker.mark_ws_connected(call_id)
    tracker.mark_ws_disconnected(call_id)

    with tracker._lock:
        row = tracker._by_call.get(call_id)
        assert row is not None
        row["disconnected_at"] = time.time() - 700.0  # más allá del TTL de stale

    rows = {row["call_id"]: row for row in tracker.active_ws_calls()}
    assert call_id not in rows
