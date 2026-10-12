"""Stop no abre la cámara ni el mapa. Cada orden va por su lado."""

from __future__ import annotations

import asyncio

from app.services import voice_client_session as vcs
from app.services.voice_cue import is_silence_command
from app.services.voice_device_gate import camera_open_allowed, map_open_allowed
from app.services.voice_tool_executor import execute_voice_tool


def test_stop_does_not_receive_the_camera_tool():
    from app.services.voice_device_gate import device_tools_for_turn

    assert "request_camera_activation" not in device_tools_for_turn("stop")
    assert "activar_modo_conducir" not in device_tools_for_turn("etop")
    assert "request_camera_activation" not in device_tools_for_turn("okay set stop")
    assert "request_camera_activation" not in device_tools_for_turn("hola, qué tal")
    assert "request_camera_activation" not in device_tools_for_turn("activa la cámara")
    assert "request_camera_activation" not in device_tools_for_turn("mira esto")
    assert "request_camera_activation" in device_tools_for_turn("CED enciende la cámara")
    assert "activar_modo_conducir" in device_tools_for_turn("abre el mapa")
    assert "request_camera_activation" not in device_tools_for_turn("abre el mapa")
    for phrase in (
        "stop",
        "etop",
        "estop",
        "esto",
        "es todo",
        "e top",
        "okay set stop",
        "ok ced stop",
    ):
        assert camera_open_allowed("gate-a", phrase) is False
        assert map_open_allowed("gate-a", phrase) is False


def test_camera_phrase_does_not_open_the_map():
    assert camera_open_allowed("gate-b", "CED enciende la cámara") is True
    assert map_open_allowed("gate-b", "CED enciende la cámara") is False
    assert camera_open_allowed("gate-b", "mira esto") is False
    assert camera_open_allowed("gate-b", "activa la cámara") is False


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


def test_stop_analyze_does_not_open_the_camera():
    uid = "gate-g"
    vcs.note_heard_line(uid, "stop")
    vcs.mark_stop_heard(uid)
    vcs.set_camera_active(uid, False)
    result = asyncio.run(execute_voice_tool("analyze_camera_frame", uid, {}))
    assert result.get("skipped") == "not_camera"
    assert vcs.is_camera_active(uid) is False
    state = vcs.get_state(uid)
    action = state.get("client_action") or {}
    assert action.get("action") != "camera_activate"


def test_stop_is_not_a_camera_request():
    from app.services.retell_custom_llm import resolve_camera_voice_request

    for phrase in ("stop", "estop", "etop", "esto", "es todo", "alto"):
        assert resolve_camera_voice_request(phrase) is None
    assert resolve_camera_voice_request("activa la cámara") is None
    assert resolve_camera_voice_request("CED enciende la cámara") == "request_camera_activation"
    assert resolve_camera_voice_request("mira esto") == "analyze_camera_frame"
    assert resolve_camera_voice_request("GRABAR") is None


def test_activa_phrase_does_not_open_via_tool():
    uid = "gate-h"
    vcs.note_heard_line(uid, "activa la cámara")
    result = asyncio.run(execute_voice_tool("request_camera_activation", uid, {}))
    assert result.get("skipped") == "not_camera"
    action = (vcs.get_state(uid).get("client_action") or {})
    assert action.get("action") != "camera_activate"


def test_grabar_does_not_open_the_camera():
    assert camera_open_allowed("gate-grabar", "GRABAR") is False
    assert camera_open_allowed("gate-grabar", "grabar") is False
    from app.services.voice_device_gate import device_tools_for_turn

    assert "request_camera_activation" not in device_tools_for_turn("GRABAR")


def test_camera_on_announcement_is_silenced_after_stopo():
    from app.services.voice_device_gate import (
        is_camera_on_announcement,
        silence_camera_status_speech,
    )

    assert is_camera_on_announcement("Cámara encendida")
    assert is_camera_on_announcement("Cámara activa, señor.")
    assert is_camera_on_announcement("Active la cámara, señor, un instante.")
    uid = "gate-announce"
    vcs.note_heard_line(uid, "stopo")
    vcs.set_voice_held(uid, True)
    assert silence_camera_status_speech("Cámara encendida", uid) is True
    assert silence_camera_status_speech("Cámara activa, señor.", uid) is True
    vcs.set_voice_held("gate-open-cam", False)
    vcs.note_heard_line("gate-open-cam", "CED enciende la cámara")
    assert (
        silence_camera_status_speech("Cámara activa, señor.", "gate-open-cam") is False
    )


def test_ok_ced_after_stop_releases_hold():
    uid = "gate-wake"
    vcs.note_heard_line(uid, "stop")
    vcs.mark_stop_heard(uid)
    vcs.set_voice_held(uid, True)
    from app.services.voice_cue import decide_cue

    action, text = decide_cue("ok ced", enabled=True, listening=False)
    assert action == "greet"
    vcs.set_voice_held(uid, False)
    assert vcs.voice_is_held(uid) is False
    assert text == ""


def test_buenos_dias_after_stop_cannot_overwrite_the_stop():
    uid = "gate-buenos"
    vcs.note_heard_line(uid, "stop")
    vcs.mark_stop_heard(uid)
    vcs.set_voice_held(uid, True)
    vcs.note_heard_line(uid, "buenos días")
    assert vcs.last_heard_line(uid) == "stop"
    assert vcs.voice_is_held(uid) is True


def test_camera_chatter_silenced_after_stop():
    from app.services.voice_device_gate import silence_camera_chatter_while_held

    uid = "gate-chatter"
    vcs.set_voice_held(uid, True)
    assert (
        silence_camera_chatter_while_held(
            "Señor, ¿qué desea que analice con la cámara?", uid
        )
        is True
    )
    vcs.set_voice_held(uid, False)


def test_should_run_orchestrator_false_while_held():
    from app.services.voice_intent_gate import should_run_orchestrator

    uid = "gate-orch-held"
    vcs.set_voice_held(uid, True)
    assert (
        should_run_orchestrator(
            "hola",
            active_module="camera",
            forced_module=None,
            user_id=uid,
        )
        is False
    )
    vcs.set_voice_held(uid, False)


def test_stopo_drops_queued_camera_and_stays_silent():
    uid = "gate-stopo"
    vcs.note_heard_line(uid, "CED enciende la cámara")
    vcs.push_client_action(uid, "camera_activate", {"heard": "CED enciende la cámara"})
    vcs.note_heard_line(uid, "stopo")
    vcs.mark_stop_heard(uid)
    vcs.set_voice_held(uid, True)
    assert camera_open_allowed(uid, "stopo") is False
    action = vcs.get_state(uid).get("client_action") or {}
    assert action.get("action") != "camera_activate"
    result = asyncio.run(execute_voice_tool("request_camera_activation", uid, {}))
    assert result.get("silent") is True
    assert "cámara" not in (result.get("spoken") or "").lower()
    assert "camara" not in (result.get("spoken") or "").lower()
