from __future__ import annotations

from unittest.mock import patch

from app.services.manychat_brain import (
    ROLE_PRESETS,
    _fallback_greeting,
    build_behavior_prompt,
    first_name,
    inbound_text,
    manychat_response,
    subscriber_id,
    wants_cta_now,
)
from app.services.manychat_store import (
    ensure_account,
    get_account_by_secret,
    reset_memory_for_tests,
    save_account,
)


def setup_function() -> None:
    reset_memory_for_tests()


def test_accounts_are_isolated_by_user():
    a = ensure_account("user-a")
    b = ensure_account("user-b")
    assert a["webhook_secret"] != b["webhook_secret"]
    assert get_account_by_secret(a["webhook_secret"])["user_id"] == "user-a"
    assert get_account_by_secret(b["webhook_secret"])["user_id"] == "user-b"
    assert get_account_by_secret("nope") is None


def test_behavior_prompt_includes_template_and_cta():
    acc = {
        "role": "closer",
        "tone": "cercano",
        "mission": "Califica y cierra hacia el grupo.",
        "ask_lines": "¿Qué buscas?",
        "objections": "Responde y pregunta.",
        "never_say": "No inventes precios.",
        "cta_when": "ready",
        "cta_url": "https://chat.whatsapp.com/grupo-ced",
        "cta_label": "Grupo CED",
    }
    prompt = build_behavior_prompt(
        acc, "hola quiero info", contact_name="María", first_turn=True
    )
    low = prompt.lower()
    assert "mensaje directo" in low
    assert "no es publicar" in low
    assert "maría" in low
    assert "señor" in low
    assert first_name({"first_name": "Carlos"}) == "Carlos"
    assert first_name({"first_name": "Subscriber"}) == ""
    event = _fallback_greeting(
        "Ana",
        inbound="me gustaria saber de que trata el evento",
        account={"cta_url": "https://chat.whatsapp.com/x", "cta_label": "Grupo"},
        first_turn=False,
    ).lower()
    assert "evento" in event or "marketing" in event
    assert "qué vendes" not in event
    assert "califica y cierra" in low
    assert "qué buscas" in low
    assert "no inventes precios" in low
    assert "https://chat.whatsapp.com/grupo-ced" in low
    assert "cuando la persona esté lista" in low
    assert "hola quiero info" in low
    assert ROLE_PRESETS["closer"]["label"]
    assert wants_cta_now("me interesa mucho quiero entrar al evento")
    assert not wants_cta_now("me gustaria saber de que trata el evento")
    ready = build_behavior_prompt(
        acc, "quiero entrar al evento", contact_name="Dugleidis", first_turn=False
    ).lower()
    assert "enlace en esta respuesta" in ready
    assert "no alargues" in ready
    join = _fallback_greeting(
        "Dugleidis",
        inbound="quiero entrar al evento",
        account={"cta_url": "https://chat.whatsapp.com/x", "cta_label": "Grupo"},
        first_turn=False,
    ).lower()
    assert "https://chat.whatsapp.com/x" in join
    assert "embudo" not in join


def test_manychat_json_is_instagram_v2():
    payload = manychat_response(
        text="Listo. Entra al grupo.",
        callback_url="https://api.example.com/webhooks/manychat/abc",
        secret="abc",
    )
    assert payload["version"] == "v2"
    assert payload["content"]["type"] == "instagram"
    assert payload["content"]["messages"][0]["text"] == "Listo. Entra al grupo."
    assert "EDIT the attached" not in payload["content"]["messages"][0]["text"]
    cb = payload["content"]["external_message_callback"]
    assert cb["url"].endswith("/webhooks/manychat/abc")
    assert "{{last_input_text}}" in cb["payload"]["last_input_text"]
    assert cb["payload"]["first_name"] == "{{first_name}}"


def test_inbound_payload_aliases():
    assert inbound_text({"last_input_text": "hola"}) == "hola"
    assert subscriber_id({"id": 99}) == "99"


def test_behavior_post_saves_template():
    from fastapi.testclient import TestClient

    from app.deps.auth import require_user_id
    from app.main import app

    reset_memory_for_tests()
    app.dependency_overrides[require_user_id] = lambda: "owner-1"
    try:
        http = TestClient(app)
        res = http.post(
            "/v1/manychat/behavior",
            json={
                "role": "closer",
                "tone": "cercano",
                "mission": "Cierra al grupo.",
                "ask_lines": "¿Qué buscas?",
                "objections": "Responde y pregunta.",
                "never_say": "No inventes precios.",
                "cta_when": "ready",
                "cta_url": "https://chat.whatsapp.com/x",
                "cta_label": "Grupo",
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert body["mission"] == "Cierra al grupo."
        assert body["cta_url"] == "https://chat.whatsapp.com/x"
        assert body["cta_label"] == "Grupo"
    finally:
        app.dependency_overrides.clear()


def test_webhook_requires_secret_and_uses_brain():
    from fastapi.testclient import TestClient

    from app.main import app

    acc = save_account(
        "owner-1",
        {
            "enabled": True,
            "mission": "Lleva al grupo cuando esté listo.",
            "cta_url": "https://chat.whatsapp.com/x",
            "cta_label": "Grupo",
        },
    )
    secret = acc["webhook_secret"]

    with patch("app.services.manychat_brain.generate_dm_reply") as mocked:
        mocked.return_value = "Va. Aquí está el grupo https://chat.whatsapp.com/x"
        http = TestClient(app)
        bad = http.post("/webhooks/manychat/wrong", json={"last_input_text": "hola"})
        assert bad.status_code == 401
        off = save_account("owner-1", {"enabled": False})
        paused = http.post(
            f"/webhooks/manychat/{off['webhook_secret']}",
            json={"last_input_text": "hola", "id": "ig-1"},
        )
        assert paused.status_code == 200
        assert "no está activo" in paused.json()["content"]["messages"][0]["text"].lower()
        save_account("owner-1", {"enabled": True})
        ok = http.post(
            f"/webhooks/manychat/{secret}",
            json={"last_input_text": "quiero el grupo", "id": "ig-1", "name": "Ana"},
        )
        assert ok.status_code == 200
        body = ok.json()
        assert body["content"]["type"] == "instagram"
        assert "grupo" in body["content"]["messages"][0]["text"].lower()
        mocked.assert_called_once()
        prompt = mocked.call_args.args[0] if mocked.call_args.args else ""
        if not prompt:
            prompt = mocked.call_args.kwargs.get("prompt") or ""
        assert "quiero el grupo" in prompt
        assert "https://chat.whatsapp.com/x" in prompt
