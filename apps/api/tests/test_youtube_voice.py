"""Tests — reproductor YouTube por voz (Fase 1).

Cubre: resolvers de intención, servicio de búsqueda (HTTP mock), tools del
ejecutor de voz, módulo YouTube y registro en detector/orquestador.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.youtube_voice_intent import (
    is_youtube_intent,
    normalize_youtube_query,
    resolve_youtube_control,
    resolve_youtube_play_request,
)


# ---------------------------------------------------------------------------
# Intención — reproducir
# ---------------------------------------------------------------------------
def test_play_pon_en_youtube():
    req = resolve_youtube_play_request("pon música de Juan Luis Guerra en YouTube")
    assert req is not None
    assert req["query"] == "Juan Luis Guerra"


def test_play_reproduce_en_youtube():
    req = resolve_youtube_play_request("reproduce bachata clásica en youtube")
    assert req is not None
    assert req["query"] == "bachata clásica"


def test_play_busca_en_youtube_prefix():
    req = resolve_youtube_play_request("busca en youtube cómo cambiar un neumático")
    assert req is not None
    assert req["query"] == "cómo cambiar un neumático"


def test_play_youtube_pon_prefix():
    req = resolve_youtube_play_request("en youtube pon el último video de MrBeast")
    assert req is not None
    assert "MrBeast" in req["query"]


def test_play_strips_fillers():
    req = resolve_youtube_play_request("ponme un video de gatos en youtube por favor")
    assert req is not None
    assert req["query"] == "gatos"


def test_play_requires_youtube_mention():
    assert resolve_youtube_play_request("pon música de Juan Luis Guerra") is None


def test_play_ignores_close_command():
    assert resolve_youtube_play_request("cierra youtube") is None


def test_normalize_query_caps_length():
    assert len(normalize_youtube_query("x" * 500)) <= 120


# ---------------------------------------------------------------------------
# Intención — controles
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    ["pausa el video", "pon el video en pausa", "pausa youtube", "detén el video"],
)
def test_control_pause(text: str):
    assert resolve_youtube_control(text) == "pause"


@pytest.mark.parametrize(
    "text",
    ["reanuda el video", "continúa el video", "dale play", "quita la pausa al video"],
)
def test_control_resume(text: str):
    assert resolve_youtube_control(text) == "resume"


@pytest.mark.parametrize(
    "text",
    ["cierra youtube", "quita el panel de youtube", "cierra el reproductor", "sal de youtube"],
)
def test_control_close(text: str):
    assert resolve_youtube_control(text) == "close"


def test_control_none_for_casual_talk():
    assert resolve_youtube_control("sigue contándome de tu día") is None
    assert resolve_youtube_control("qué tal el clima hoy") is None


def test_play_request_is_not_resume():
    assert resolve_youtube_control("reproduce bachata en youtube") is None
    assert is_youtube_intent("reproduce bachata en youtube")


# ---------------------------------------------------------------------------
# Servicio de búsqueda — httpx MockTransport, sin red.
# ---------------------------------------------------------------------------
from app.services.youtube_search import (  # noqa: E402
    YouTubeSearchError,
    is_valid_video_id,
    search_youtube_video,
)

_FAKE_ITEM = {
    "id": {"videoId": "dQw4w9WgXcQ"},
    "snippet": {
        "title": "Video de prueba",
        "channelTitle": "Canal Demo",
        "thumbnails": {"medium": {"url": "https://i.ytimg.com/vi/x/mq.jpg"}},
    },
}


def _transport(handler):
    return httpx.MockTransport(handler)


def test_search_returns_video_and_sends_expected_params():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.url.params))
        return httpx.Response(200, json={"items": [_FAKE_ITEM]})

    video = search_youtube_video(
        "bachata", api_key="test-key", transport=_transport(handler)
    )
    assert video["video_id"] == "dQw4w9WgXcQ"
    assert video["title"] == "Video de prueba"
    assert video["channel_title"] == "Canal Demo"
    assert captured["type"] == "video"
    assert captured["videoEmbeddable"] == "true"
    assert captured["maxResults"] == "8"
    assert captured["part"] == "snippet"
    assert captured["q"] == "bachata"
    assert captured["key"] == "test-key"


def test_rank_prefers_title_match_over_first_api_result():
    from app.services.youtube_search import rank_youtube_candidates, _pick_from_ranked

    items = [
        {
            "id": {"videoId": "AAAAAAAAAAA"},
            "snippet": {
                "title": "Bachata Mix 2024",
                "channelTitle": "Mix Channel",
                "thumbnails": {},
            },
        },
        {
            "id": {"videoId": "BBBBBBBBBBB"},
            "snippet": {
                "title": "Propuesta Indecente - Romeo Santos (Official Video)",
                "channelTitle": "RomeoSantosVEVO",
                "thumbnails": {},
            },
        },
    ]
    ranked = rank_youtube_candidates("Propuesta Indecente Romeo Santos", items)
    picked = _pick_from_ranked(ranked)
    assert picked is not None
    assert picked["video_id"] == "BBBBBBBBBBB"
    assert picked.get("ambiguous") is False


def test_search_no_results_returns_none():
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": []})

    assert (
        search_youtube_video("zzz", api_key="k", transport=_transport(handler)) is None
    )


def test_search_invalid_video_id_skipped():
    bad = {"id": {"videoId": "corto"}, "snippet": {"title": "x"}}

    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": [bad]})

    assert (
        search_youtube_video("q", api_key="k", transport=_transport(handler)) is None
    )


def test_search_missing_api_key_raises():
    with pytest.raises(YouTubeSearchError) as exc:
        search_youtube_video("q", api_key="")
    assert exc.value.code == "missing_api_key"


def test_search_http_error_raises():
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"message": "quota"}})

    with pytest.raises(YouTubeSearchError) as exc:
        search_youtube_video("q", api_key="k", transport=_transport(handler))
    assert exc.value.code == "http_error"


def test_search_timeout_raises():
    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout")

    with pytest.raises(YouTubeSearchError) as exc:
        search_youtube_video("q", api_key="k", transport=_transport(handler))
    assert exc.value.code == "timeout"


def test_search_empty_query_returns_none():
    assert search_youtube_video("   ", api_key="k") is None


def test_video_id_validation():
    assert is_valid_video_id("dQw4w9WgXcQ")
    assert not is_valid_video_id("corto")
    assert not is_valid_video_id("con espacios!")


# ---------------------------------------------------------------------------
# Ejecutor de tools de voz — acciones al cliente
# ---------------------------------------------------------------------------
from app.services import voice_client_session as vcs  # noqa: E402
from app.services.voice_tool_executor import execute_voice_tool  # noqa: E402


def test_play_tool_pushes_client_action():
    uid = "user-youtube-play"
    vcs.consume_client_action(uid)
    vcs.consume_tool_events(uid)

    video = {
        "video_id": "dQw4w9WgXcQ",
        "title": "Video de prueba",
        "channel_title": "Canal Demo",
        "thumbnail_url": "https://i.ytimg.com/vi/x/mq.jpg",
    }
    with patch(
        "app.services.youtube_search.search_youtube_video",
        return_value=video,
    ):
        result = asyncio.run(
            execute_voice_tool("play_youtube_video", uid, {"query": "bachata"})
        )

    assert result["ok"] is True
    assert "Video de prueba" in result["spoken"]
    assert result["video"]["video_id"] == "dQw4w9WgXcQ"

    action = vcs.consume_client_action(uid)
    assert action is not None
    assert action["action"] == "youtube_play"
    assert action["payload"]["video_id"] == "dQw4w9WgXcQ"
    assert action["payload"]["title"] == "Video de prueba"

    events = vcs.consume_tool_events(uid)
    assert any(e.get("type") == "youtube_play" for e in events)
    assert vcs.get_active_mode(uid) == "youtube"


def test_play_tool_no_results_never_confirms():
    uid = "user-youtube-noresult"
    vcs.consume_client_action(uid)
    with patch(
        "app.services.youtube_search.search_youtube_video",
        return_value=None,
    ):
        result = asyncio.run(
            execute_voice_tool("play_youtube_video", uid, {"query": "zzz"})
        )
    assert result["ok"] is False
    assert result["error"] == "youtube_no_results"
    assert "no encontré" in result["spoken"].lower()
    assert vcs.consume_client_action(uid) is None


def test_play_tool_missing_key_clear_error():
    uid = "user-youtube-nokey"
    with patch(
        "app.services.youtube_search.search_youtube_video",
        side_effect=YouTubeSearchError("missing_api_key"),
    ):
        result = asyncio.run(
            execute_voice_tool("play_youtube_video", uid, {"query": "bachata"})
        )
    assert result["ok"] is False
    assert result["error"] == "youtube_api_key_missing"


def test_play_tool_empty_query_errors():
    result = asyncio.run(execute_voice_tool("play_youtube_video", "u1", {"query": ""}))
    assert result["ok"] is False
    assert result["error"] == "youtube_empty_query"


@pytest.mark.parametrize(
    ("tool", "action"),
    [
        ("pause_youtube_video", "youtube_pause"),
        ("resume_youtube_video", "youtube_resume"),
        ("close_youtube_player", "youtube_close"),
    ],
)
def test_control_tools_push_client_actions(tool: str, action: str):
    uid = f"user-youtube-{action}"
    vcs.consume_client_action(uid)
    result = asyncio.run(execute_voice_tool(tool, uid, {}))
    assert result["ok"] is True
    pushed = vcs.consume_client_action(uid)
    assert pushed is not None
    assert pushed["action"] == action
    assert pushed["payload"] == {}


def test_close_tool_clears_active_mode():
    uid = "user-youtube-close-mode"
    vcs.set_active_mode(uid, "youtube")
    asyncio.run(execute_voice_tool("close_youtube_player", uid, {}))
    assert vcs.get_active_mode(uid) is None


# ---------------------------------------------------------------------------
# Módulo YouTube — activate / handle_command
# ---------------------------------------------------------------------------
from app.modules.youtube_module import YouTubeModule  # noqa: E402


def _run_module(coro):
    return asyncio.run(coro)


def test_module_activate_play_success():
    mod = YouTubeModule()
    with patch(
        "app.modules.youtube_module.execute_voice_tool",
        new_callable=AsyncMock,
        return_value={
            "ok": True,
            "spoken": "Reproduciendo Video de prueba en YouTube, señor.",
        },
    ) as tool:
        result = _run_module(
            mod.activate(
                "pon bachata en youtube",
                user_id="u-mod-play",
                call_id="c1",
                user_text="pon bachata en youtube",
            )
        )
    assert result.ok is True
    assert result.handles_response is True
    assert result.send_filler is True
    assert "YouTube" in result.filler
    assert "Reproduciendo" in result.spoken
    tool.assert_awaited_once()
    assert tool.await_args.args[0] == "play_youtube_video"
    assert tool.await_args.args[2] == {"query": "bachata"}


def test_module_activate_play_failure_no_confirmation():
    mod = YouTubeModule()
    with patch(
        "app.modules.youtube_module.execute_voice_tool",
        new_callable=AsyncMock,
        return_value={
            "ok": False,
            "spoken": "No encontré un video de zzz en YouTube, señor.",
            "error": "youtube_no_results",
        },
    ):
        result = _run_module(
            mod.activate(
                "pon zzz en youtube",
                user_id="u-mod-fail",
                call_id="c1",
                user_text="pon zzz en youtube",
            )
        )
    assert result.ok is False
    assert "no encontré" in result.spoken.lower()
    assert "reproduciendo" not in result.spoken.lower()


def test_module_handle_pause_when_active():
    mod = YouTubeModule()
    mod._enter_active()
    with patch(
        "app.modules.youtube_module.execute_voice_tool",
        new_callable=AsyncMock,
        return_value={"ok": True, "spoken": "Video en pausa, señor."},
    ) as tool:
        result = _run_module(
            mod.handle_command(
                "pausa el video",
                user_id="u-mod-pause",
                call_id="c1",
                user_text="pausa el video",
            )
        )
    assert result.handles_response is True
    assert tool.await_args.args[0] == "pause_youtube_video"


def test_module_passive_ignores_commands():
    mod = YouTubeModule()
    result = _run_module(
        mod.handle_command(
            "pausa el video",
            user_id="u-mod-passive",
            call_id="c1",
            user_text="pausa el video",
        )
    )
    assert result.handles_response is False
    assert result.conversation_continues is True


def test_module_close_deactivates():
    mod = YouTubeModule()
    mod._enter_active()
    with patch(
        "app.modules.youtube_module.execute_voice_tool",
        new_callable=AsyncMock,
        return_value={"ok": True, "spoken": "Cerrando YouTube, señor."},
    ):
        result = _run_module(
            mod.handle_command(
                "cierra youtube",
                user_id="u-mod-close",
                call_id="c1",
                user_text="cierra youtube",
            )
        )
    assert result.ok is True
    assert mod.is_active() is False


# ---------------------------------------------------------------------------
# Registro — detector, orquestador y registry
# ---------------------------------------------------------------------------
def test_detector_strict_anchor_play():
    from app.services.module_detector import CONF_ANCHOR, detect_intent

    d = detect_intent("pon música de bad bunny en youtube", run_stage2=False)
    assert d.module == "youtube"
    assert d.confidence == CONF_ANCHOR
    assert d.activate is True


def test_detector_strict_anchor_close():
    from app.services.module_detector import CONF_ANCHOR, detect_intent

    d = detect_intent("cierra youtube", run_stage2=False)
    assert d.module == "youtube"
    assert d.confidence == CONF_ANCHOR


def test_detector_casual_youtube_mention_is_soft():
    from app.services.module_detector import CONF_SOFT, detect_intent

    d = detect_intent("ayer vi un documental en youtube muy bueno", run_stage2=False)
    assert d.module == "youtube"
    assert d.confidence == CONF_SOFT
    assert d.activate is False


def test_orchestrator_detect_module_play():
    from app.services.ced_orchestrator import detect_module

    assert detect_module("busca bachata en youtube", []) == "youtube"


def test_orchestrator_active_module_keeps_control():
    from app.services.ced_orchestrator import detect_module, is_module_command

    assert detect_module("pausa el video", [], active_module="youtube") == "youtube"
    assert is_module_command("pausa el video", "youtube", [])


def test_registry_builds_youtube_module():
    from app.modules.module_registry import MODULE_ORDER, MODULE_OVERLAYS, build_module

    assert "youtube" in MODULE_ORDER
    assert "youtube" in MODULE_OVERLAYS
    mod = build_module("youtube")
    assert mod.name == "youtube"


def test_voice_intent_gate_signals_youtube():
    from app.services.voice_intent_gate import has_explicit_module_signal

    assert has_explicit_module_signal("pon bachata en youtube")
    assert has_explicit_module_signal("pausa el video")


def test_openai_tools_include_youtube():
    from app.services.openai_voice_tools import OPENAI_REALTIME_TOOLS

    names = {t["name"] for t in OPENAI_REALTIME_TOOLS}
    assert {
        "play_youtube_video",
        "pause_youtube_video",
        "resume_youtube_video",
        "close_youtube_player",
    } <= names
    play = next(t for t in OPENAI_REALTIME_TOOLS if t["name"] == "play_youtube_video")
    assert play["parameters"]["required"] == ["query"]


def test_native_pilot_tools_include_youtube():
    from app.services.retell_native_pilot import build_native_pilot_tools

    tools = build_native_pilot_tools(api_public_url="https://api.example.com")
    by_name = {t["name"]: t for t in tools}
    assert "play_youtube_video" in by_name
    assert "pause_youtube_video" in by_name
    assert "resume_youtube_video" in by_name
    assert "close_youtube_player" in by_name
    play = by_name["play_youtube_video"]
    assert "YouTube" in play["execution_message_description"]
    assert play["url"].endswith("/v1/retell/tools/play_youtube_video")


def test_native_pilot_prompts_enforce_silence_during_music():
    """Regla exclusiva YouTube: confirmar breve y callar mientras suena la música."""
    from app.services.retell_native_pilot import (
        GENERAL_ASSISTANT_STATE_PROMPT,
        PLAY_YOUTUBE_DESCRIPTION,
        READ_TOOLS_PROMPT,
    )

    assert "SILENCIO DURANTE LA MÚSICA" in READ_TOOLS_PROMPT
    assert "no ofrezcas más ayuda" in PLAY_YOUTUBE_DESCRIPTION
    assert "SILENCIO" in GENERAL_ASSISTANT_STATE_PROMPT
    # La regla debe declararse como exclusiva de YouTube, no general.
    assert "NO aplica al resto" in READ_TOOLS_PROMPT


def test_openai_play_tool_description_enforces_silence():
    from app.services.openai_voice_tools import OPENAI_REALTIME_TOOLS

    play = next(t for t in OPENAI_REALTIME_TOOLS if t["name"] == "play_youtube_video")
    assert "SILENCIO" in play["description"]


def test_module_overlay_youtube_prohibits_offers():
    from app.modules.module_registry import MODULE_OVERLAYS

    overlay = MODULE_OVERLAYS["youtube"]
    assert "PROHIBIDO ofrecer" in overlay
    assert "silencio" in overlay.lower()
