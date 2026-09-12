"""Campos de create-web-call que el SDK del navegador necesita para conectar."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_JWT_PAYLOAD_KEYS = ("video", "inst", "call_id", "identity", "sub")


def _b64url_json(segment: str) -> dict[str, Any] | None:
    pad = segment + "=" * (-len(segment) % 4)
    try:
        raw = base64.urlsafe_b64decode(pad.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


def decode_retell_access_token_claims(access_token: str | None) -> dict[str, Any]:
    token = (access_token or "").strip()
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = _b64url_json(parts[1]) or {}
    return {k: payload.get(k) for k in _JWT_PAYLOAD_KEYS if k in payload} | {
        "payload_keys": sorted(payload.keys()),
    }


def infer_retell_web_transport(
    *,
    access_token: str | None,
    hinted: str | None = None,
    ice_servers: list[Any] | None = None,
) -> str:
    """Elige livekit vs gateway. Un token de gateway en LiveKit = Error starting call."""
    hint = str(hinted or "").strip().lower()
    if hint in {"gateway", "livekit"}:
        return hint
    if ice_servers:
        return "gateway"
    claims = decode_retell_access_token_claims(access_token)
    inst = claims.get("inst")
    if isinstance(inst, str) and inst.strip():
        return "gateway"
    video = claims.get("video")
    if isinstance(video, dict) and video and not video.get("room"):
        return "gateway"
    return "livekit"


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    for name in ("model_dump", "dict", "to_dict"):
        fn = getattr(value, name, None)
        if not callable(fn):
            continue
        try:
            dumped = fn(exclude_none=True) if name == "model_dump" else fn()
        except TypeError:
            dumped = fn()
        except Exception:  # noqa: BLE001
            continue
        if isinstance(dumped, dict):
            return dumped
    raw = getattr(value, "__dict__", None)
    return dict(raw) if isinstance(raw, dict) else {}


def serialize_ice_servers(raw: Any) -> list[dict[str, Any]] | None:
    if not raw:
        return None
    items = raw if isinstance(raw, list) else [raw]
    out: list[dict[str, Any]] = []
    for item in items:
        data = _as_dict(item)
        urls = data.get("urls") or data.get("url")
        if not urls:
            continue
        entry: dict[str, Any] = {"urls": urls}
        username = data.get("username")
        credential = data.get("credential")
        if username:
            entry["username"] = username
        if credential:
            entry["credential"] = credential
        out.append(entry)
    return out or None


def web_call_client_payload(call: Any, *, agent_id: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    data = _as_dict(call)
    access_token = (
        getattr(call, "access_token", None)
        or data.get("access_token")
        or data.get("accessToken")
    )
    call_id = (
        getattr(call, "call_id", None)
        or getattr(call, "callId", None)
        or data.get("call_id")
        or data.get("callId")
    )
    hinted = getattr(call, "transport", None) or data.get("transport")
    ice = serialize_ice_servers(
        getattr(call, "ice_servers", None) or data.get("ice_servers") or data.get("iceServers")
    )
    identity = (
        getattr(call, "identity", None)
        or getattr(call, "participant_id", None)
        or data.get("identity")
        or data.get("participant_id")
        or data.get("participantId")
    )
    url = getattr(call, "url", None) or data.get("url") or data.get("websocket_url")
    transport = infer_retell_web_transport(
        access_token=str(access_token) if access_token else None,
        hinted=str(hinted) if hinted is not None else None,
        ice_servers=ice,
    )
    payload: dict[str, Any] = {
        "ok": True,
        "access_token": access_token,
        "call_id": call_id,
        "agent_id": agent_id,
        "transport": transport,
    }
    if ice:
        payload["ice_servers"] = ice
    if isinstance(identity, str) and identity.strip():
        payload["identity"] = identity.strip()
    if isinstance(url, str) and url.strip() and transport == "livekit":
        payload["url"] = url.strip()
    if extra:
        payload.update(extra)
    logger.info(
        "[RETELL] web call ready transport=%s call=%s ice=%s",
        transport,
        call_id,
        len(ice or []),
    )
    return payload
