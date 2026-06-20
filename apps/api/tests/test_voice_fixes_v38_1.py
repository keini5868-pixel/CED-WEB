"""Tests fixes v38.1 — cámara ACK, dedupe FB, anti-código."""

from __future__ import annotations

import time

import pytest

from app.services.meta_publish_dedupe import find_duplicate_publish, record_publish
from app.services import voice_client_session as vcs


def test_meta_publish_dedupe_similar_content():
    user = "user-test-dedupe"
    record_publish(user, "El sistema CED ha llegado", "post_123", platform="facebook")
    dup = find_duplicate_publish(user, "el sistema ced ha llegado!", platform="facebook")
    assert dup == "post_123"
    assert find_duplicate_publish(user, "otro mensaje totalmente distinto", platform="facebook") is None


def test_meta_publish_dedupe_window_expires():
    user = "user-test-window"
    record_publish(user, "mensaje corto", "post_a", platform="facebook")
    from app.services import meta_publish_dedupe as mod

    with mod._LOCK:
        mod._RECENT[f"{user}:facebook"] = [(time.time() - 31, "mensaje corto", "post_a")]
    assert find_duplicate_publish(user, "mensaje corto", platform="facebook") is None


def test_camera_ack_requires_stream_present():
    uid = "user-camera-ack"
    vcs.set_camera_active(uid, True, stream_present=False)
    assert vcs.is_camera_active(uid) is False
    status = vcs.get_camera_status(uid)
    assert status["camera_active"] is True
    assert status["camera_stream_present"] is False

    vcs.set_camera_active(uid, True, stream_present=True)
    assert vcs.is_camera_active(uid) is True


def test_wait_camera_ack_success(monkeypatch):
    import asyncio

    from app.services import voice_tool_executor as vte

    uid = "user-wait-ack"
    calls = {"n": 0}

    def fake_active(user_id: str, *, max_age_sec: float = 45.0) -> bool:
        calls["n"] += 1
        return calls["n"] >= 2

    monkeypatch.setattr(vte.vcs, "is_camera_active", fake_active)
    monkeypatch.setattr(
        vte.vcs,
        "get_camera_status",
        lambda _uid: {"camera_active": True, "camera_stream_present": True, "age_sec": 0.1},
    )
    ok = asyncio.run(vte._wait_camera_ack(uid, 2.0))
    assert ok is True
