"""Tests — Gmail voz devuelve datos reales (inbox, retry, errores claros)."""

from __future__ import annotations

from unittest.mock import patch

import httpx

from app.modules.gmail_module import (
    _format_gmail_error,
    handle_gmail_query_sync,
)


def test_read_latest_uses_inbox_not_category():
    with patch("app.modules.gmail_module._gmail_api_call") as call:
        call.side_effect = lambda _uid, fn: fn("token")
        with patch("app.modules.gmail_module.list_inbox_messages") as inbox:
            inbox.return_value = [
                {
                    "id": "1",
                    "from_name": "Ana",
                    "from": "ana@x.com",
                    "subject": "Hola",
                    "relative_date": "hoy",
                    "snippet": "Texto del snippet",
                }
            ]
            with patch(
                "app.modules.gmail_module.fetch_message_body_detail",
                side_effect=RuntimeError("body fail"),
            ):
                out = handle_gmail_query_sync(
                    "user-1",
                    "me puedes leer el ultimo Gmail que me llego?",
                )
    assert "Ana" in out["spoken"]
    assert "Hola" in out["spoken"]
    assert "No pude obtener el cuerpo completo" in out["spoken"]
    inbox.assert_called_once()


def test_gmail_401_returns_reconnect_message():
    err = httpx.HTTPStatusError(
        "401",
        request=httpx.Request("GET", "https://gmail.googleapis.com"),
        response=httpx.Response(401),
    )
    assert "reconexión" in _format_gmail_error(err).lower()


def test_gmail_api_call_retries_on_401():
    calls: list[str] = []

    def fn(access: str) -> str:
        calls.append(access)
        if access == "old":
            raise httpx.HTTPStatusError(
                "401",
                request=httpx.Request("GET", "https://gmail.googleapis.com"),
                response=httpx.Response(401),
            )
        return "ok"

    from app.modules.gmail_module import _gmail_api_call

    with patch("app.modules.gmail_module.get_valid_access_token", return_value="old"):
        with patch(
            "app.modules.gmail_module.force_refresh_access_token",
            return_value="new",
        ) as refresh:
            assert _gmail_api_call("user-1", fn) == "ok"
    refresh.assert_called_once()
    assert calls == ["old", "new"]
