"""360dialog adapter — envío Cloud API con D360-API-KEY."""

from __future__ import annotations

from app.services.whatsapp_360 import is_360dialog
from app.services.whatsapp_cloud import send_text_for_account


def test_is_360dialog_provider():
    assert is_360dialog({"provider": "360dialog"}) is True
    assert is_360dialog({"provider": "meta"}) is False
    assert is_360dialog({}) is False


def test_send_text_for_account_uses_360_host(monkeypatch):
    captured: dict[str, object] = {}

    def fake_d360(*, api_key: str, to: str, body: str):
        captured["api_key"] = api_key
        captured["to"] = to
        captured["body"] = body
        return {"messages": [{"id": "wamid.x"}]}

    monkeypatch.setattr(
        "app.services.whatsapp_360.send_text_d360",
        fake_d360,
    )
    acc = {
        "provider": "360dialog",
        "access_token": "key-test",
        "phone_number_id": "123",
    }
    out = send_text_for_account(acc, to="18005551212", body="Hola")
    assert out["messages"][0]["id"] == "wamid.x"
    assert captured["api_key"] == "key-test"
    assert captured["to"] == "18005551212"
