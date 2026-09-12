from __future__ import annotations

import base64
import json
from types import SimpleNamespace

from app.services.retell_web_call import (
    infer_retell_web_transport,
    serialize_ice_servers,
    web_call_client_payload,
)


def _jwt(payload: dict) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"eyJhbGciOiJub25lIn0.{body}.sig"


def test_infer_gateway_from_inst_claim() -> None:
    token = _jwt(
        {
            "sub": "client",
            "identity": "client",
            "inst": "i-01adc7920a8b4b62f",
            "call_id": "call_abc",
            "video": {"canPublish": True, "canSubscribe": True, "roomJoin": True},
        }
    )
    assert infer_retell_web_transport(access_token=token) == "gateway"


def test_infer_livekit_from_room_claim() -> None:
    token = _jwt(
        {
            "iss": "APIkey",
            "sub": "client",
            "video": {"room": "call_old", "roomJoin": True},
        }
    )
    assert infer_retell_web_transport(access_token=token) == "livekit"


def test_explicit_hint_wins() -> None:
    token = _jwt({"inst": "i-x"})
    assert (
        infer_retell_web_transport(access_token=token, hinted="livekit") == "livekit"
    )


def test_ice_servers_force_gateway() -> None:
    assert (
        infer_retell_web_transport(
            access_token="not-a-jwt",
            ice_servers=[{"urls": "stun:stun.l.google.com:19302"}],
        )
        == "gateway"
    )


def test_web_call_payload_strips_token_neighbours() -> None:
    call = SimpleNamespace(
        access_token="tok",
        call_id="call_1",
        transport="gateway",
        ice_servers=[SimpleNamespace(urls=["stun:example"], username="u", credential="c")],
        identity="client",
        url="wss://should-not-pass.example",
    )
    payload = web_call_client_payload(call, agent_id="agent_1")
    assert payload["ok"] is True
    assert payload["transport"] == "gateway"
    assert payload["call_id"] == "call_1"
    assert payload["identity"] == "client"
    assert "url" not in payload
    assert payload["ice_servers"] == [
        {"urls": ["stun:example"], "username": "u", "credential": "c"}
    ]


def test_serialize_ice_accepts_url_alias() -> None:
    assert serialize_ice_servers([{"url": "stun:x"}]) == [{"urls": "stun:x"}]
