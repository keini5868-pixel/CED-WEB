"""Stop no abre la cámara ni el mapa. Cada orden va por su lado."""

from __future__ import annotations

import asyncio

from app.services import voice_client_session as vcs
from app.services.voice_cue import is_silence_command
from app.services.voice_device_gate import camera_open_allowed, map_open_allowed
from app.services.voice_tool_executor import execute_voice_tool


def test_stop_is_not_a_camera_or_map_command():
    for phrase in ("stop", "etop", "e top", "okay set stop", "ok ced stop"):
        assert camera_open_allowed("gate-a", phrase) is False
        assert map_open_allowed("gate-a", phrase) is False


def test_camera_phrase_does_not_open_the_map():
    assert camera_open_allowed("gate-b", "activa la cámara") is True
    assert map_open_allowed("gate-b", "activa la cámara") is False
    assert camera_open_allowed("gate-b", "mira esto") is True


def test_map_phrase_does_not_open_the_camera():
    assert map_open_allowed("gate-c", "abre el mapa") is True
    assert camera_open_allowed("gate-c", "abre el mapa") is False


def test_close_camera_is_not_silence_and_does_not_open_it():
    assert is_silence_command("cierra la cámara") is False
    assert camera_open_allowed("gate-d", "cierra la cámara") is False


def test_a_later_stop_beats_an_older_camera_request():
    vcs.note_heard_line("gate-e", "stop")
    vcs.mark_stop_heard("gate-e")
    assert camera_open_allowed("gate-e", "activa la cámara") is False
    assert map_open_allowed("gate-e", "abre el mapa") is False


def test_tool_call_alone_does_not_open_the_camera():
    uid = "gate-f"
    vcs.note_heard_line(uid, "etop")
    vcs.mark_stop_heard(uid)
    result = asyncio.run(execute_voice_tool("request_camera_activation", uid, {}))
    assert result.get("silent") is True
    assert result.get("skipped") == "not_camera"
    assert vcs.is_camera_active(uid) is False

    result = asyncio.run(execute_voice_tool("activar_modo_conducir", uid, {}))
    assert result.get("skipped") == "not_map"
    assert vcs.get_active_mode(uid) != "map"
