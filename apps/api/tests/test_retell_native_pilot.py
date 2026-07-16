"""Tests — piloto Retell LLM nativo (get_environment gateway)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.retell_native_pilot import (
    RETELL_NATIVE_PILOT_PROMPT,
    build_get_environment_tool,
    build_native_pilot_tools,
    estimate_general_assistant_token_floor,
    get_pilot_metrics_snapshot,
    record_tool_metric,
    resolve_environment_tool_query,
)


def test_build_get_environment_tool_has_static_filler():
    tool = build_get_environment_tool(api_public_url="https://api.example.com")
    assert tool["name"] == "get_environment"
    assert tool["execution_message_type"] == "static_text"
    assert "consultando el clima" in tool["execution_message_description"].lower()
    assert tool.get("enable_typing_sound") is True
    assert "tardar" in tool["execution_message_description"].lower()


def test_phase_a_general_assistant_token_floor_under_retell_threshold():
    """Fase A: piso sin historial debe quedar bajo el surcharge Retell (~4k) y ~3.8k objetivo."""
    est = estimate_general_assistant_token_floor()
    assert est["tool_count"] == 41
    assert est["floor_tokens_no_history"] < 4000
    assert est["floor_tokens_no_history"] <= 3800
    assert est["under_threshold"] is True


def test_build_native_pilot_tools_includes_read_and_finance_write():
    tools = build_native_pilot_tools(api_public_url="https://api.example.com")
    names = {t["name"] for t in tools}
    assert names == {
        "get_environment",
        "list_calendar_events",
        "calendar_prepare_write",
        "calendar_confirm_write",
        "calendar_cancel_write",
        "read_gmail",
        "gmail_prepare_send",
        "gmail_confirm_send",
        "gmail_cancel_send",
        "search_web",
        "play_youtube_video",
        "pause_youtube_video",
        "resume_youtube_video",
        "close_youtube_player",
        "generate_image",
        "generar_pdf",
        "check_meta_networks",
        "meta_prepare_publish",
        "meta_confirm_publish",
        "meta_cancel_publish",
        "enable_prospection",
        "disable_prospection",
        "prospection_report",
        "read_social_comments",
        "open_drive_map",
        "search_nearby_places",
        "show_route",
        "start_drive_navigation",
        "stop_drive_navigation",
        "navigation_status",
        "read_finances",
        "finance_prepare_write",
        "finance_confirm_write",
        "finance_cancel_write",
        "activate_camera",
        "deactivate_camera",
        "analyze_camera_frame",
        "search_visible_product",
        "activate_advanced_mode",
        "consult_advanced",
        "deactivate_advanced_mode",
    }


def test_camera_tools_have_fillers_and_timeouts():
    from app.services.retell_native_pilot import (
        build_activate_camera_tool,
        build_analyze_camera_frame_tool,
        build_search_visible_product_tool,
    )

    activate = build_activate_camera_tool(api_public_url="https://api.example.com")
    assert "Activando la cámara" in activate["execution_message_description"]
    assert activate["timeout_ms"] == 12_000

    analyze = build_analyze_camera_frame_tool(api_public_url="https://api.example.com")
    assert "analizando" in analyze["execution_message_description"].lower()
    assert analyze["timeout_ms"] == 45_000

    search = build_search_visible_product_tool(api_public_url="https://api.example.com")
    assert "buscando información" in search["execution_message_description"].lower()
    assert search["timeout_ms"] == 45_000


def test_activate_camera_idempotent_when_already_active():
    import asyncio

    from app.services.retell_native_pilot import execute_activate_camera_tool

    async def run():
        with patch(
            "app.services.voice_tool_executor.execute_voice_tool",
            new_callable=AsyncMock,
            return_value={"ok": True, "spoken": "Cámara activa, señor. Lista para analizar."},
        ) as mock_exec:
            out = await execute_activate_camera_tool(
                user_id="user-cam-1",
                payload={"call": {"call_id": "c1"}},
                args={},
            )
            return out, mock_exec

    out, mock_exec = asyncio.run(run())
    assert "Cámara activa" in out["result"]
    assert "activando" not in out["result"].lower()
    mock_exec.assert_awaited_once()
    assert mock_exec.await_args.args[0] == "request_camera_activation"


def test_analyze_camera_frame_calls_vision_executor():
    import asyncio

    from app.services.retell_native_pilot import execute_analyze_camera_frame_tool

    async def run():
        with patch(
            "app.services.voice_tool_executor.execute_voice_tool",
            new_callable=AsyncMock,
            return_value={"ok": True, "spoken": "Es un frasco de proteína MyProtein."},
        ) as mock_exec:
            out = await execute_analyze_camera_frame_tool(
                user_id="user-cam-2",
                payload={"call": {"call_id": "c2"}},
                args={"question": "qué es esto"},
            )
            return out, mock_exec

    out, mock_exec = asyncio.run(run())
    assert "MyProtein" in out["result"]
    mock_exec.assert_awaited_once()
    assert mock_exec.await_args.args[0] == "analyze_camera_frame"


def test_search_visible_product_uses_last_vision_without_recapture():
    import asyncio

    from app.services import voice_client_session as vcs
    from app.services.retell_native_pilot import execute_search_visible_product_tool

    vcs.set_last_vision_summary("user-cam-3", "Es un frasco de proteína MyProtein Impact Whey.")

    async def run():
        with patch(
            "app.services.voice_tool_executor.execute_voice_tool",
            new_callable=AsyncMock,
            return_value={
                "ok": True,
                "spoken": "Se vende en Amazon por alrededor de 40 dólares.",
            },
        ) as mock_exec:
            out = await execute_search_visible_product_tool(
                user_id="user-cam-3",
                payload={"call": {"call_id": "c3"}},
                args={"question": "dónde lo compro"},
            )
            return out, mock_exec

    out, mock_exec = asyncio.run(run())
    assert "Amazon" in out["result"] or "40" in out["result"]
    mock_exec.assert_awaited_once()
    assert mock_exec.await_args.args[0] == "search_web"
    vcs.set_last_vision_summary("user-cam-3", "")


def test_build_native_pilot_states_restrict_confirm_tools():
    from app.services.retell_native_pilot import (
        STATE_FINANCE_CONFIRM_PENDING,
        STATE_GENERAL_ASSISTANT,
        build_native_pilot_states,
    )

    states, starting = build_native_pilot_states(api_public_url="https://api.example.com")
    assert starting == STATE_GENERAL_ASSISTANT
    by_name = {s["name"]: s for s in states}
    general_tools = {t["name"] for t in by_name[STATE_GENERAL_ASSISTANT]["tools"]}
    confirm_tools = {t["name"] for t in by_name[STATE_FINANCE_CONFIRM_PENDING]["tools"]}
    assert "finance_prepare_write" in general_tools
    assert "finance_confirm_write" in general_tools
    assert "finance_cancel_write" in general_tools
    assert "read_finances" in general_tools
    assert "read_gmail" in general_tools
    assert "gmail_prepare_send" in general_tools
    assert "gmail_confirm_send" in general_tools
    assert "gmail_cancel_send" in general_tools
    assert "search_web" in general_tools
    assert "meta_prepare_publish" in general_tools
    assert "meta_confirm_publish" in general_tools
    assert "check_meta_networks" in general_tools
    assert "open_drive_map" in general_tools
    assert "search_nearby_places" in general_tools
    assert "show_route" in general_tools
    assert "start_drive_navigation" in general_tools
    assert "stop_drive_navigation" in general_tools
    assert "navigation_status" in general_tools
    assert "get_environment" in general_tools
    assert "activate_camera" in general_tools
    assert "analyze_camera_frame" in general_tools
    assert "search_visible_product" in general_tools
    assert "deactivate_camera" in general_tools
    assert "activate_advanced_mode" in general_tools
    assert "consult_advanced" in general_tools
    assert "deactivate_advanced_mode" in general_tools
    assert "generate_image" in general_tools
    assert "generar_pdf" in general_tools
    assert "finance_confirm_write" in confirm_tools
    assert "finance_cancel_write" in confirm_tools
    assert "read_finances" in confirm_tools
    assert "get_environment" in confirm_tools
    assert "finance_prepare_write" not in confirm_tools
    assert "activate_camera" not in confirm_tools
    assert "gmail_prepare_send" not in confirm_tools

    from app.services.retell_native_pilot import (
        PUBLISH_CONFIRM_STATE_PROMPT,
        STATE_ADVANCED_MODE_ACTIVE,
        STATE_GMAIL_CONFIRM_PENDING,
        STATE_PUBLISH_CONFIRM_PENDING,
    )

    gmail_tools = {t["name"] for t in by_name[STATE_GMAIL_CONFIRM_PENDING]["tools"]}
    assert gmail_tools == {
        "read_gmail",
        "gmail_confirm_send",
        "gmail_cancel_send",
        "get_environment",
        "read_finances",
    }
    assert "gmail_prepare_send" not in gmail_tools

    publish_tools = {t["name"] for t in by_name[STATE_PUBLISH_CONFIRM_PENDING]["tools"]}
    assert publish_tools == {
        "check_meta_networks",
        "meta_confirm_publish",
        "meta_cancel_publish",
        "get_environment",
        "read_finances",
        "read_gmail",
        "list_calendar_events",
        "search_web",
    }
    assert "meta_prepare_publish" not in publish_tools
    publish_edge = by_name[STATE_PUBLISH_CONFIRM_PENDING]["edges"][0]["description"]
    assert "OBLIGATORIO" in publish_edge
    assert "transition_to_general_assistant" in PUBLISH_CONFIRM_STATE_PROMPT
    advanced_tools = {t["name"] for t in by_name[STATE_ADVANCED_MODE_ACTIVE]["tools"]}
    assert advanced_tools == {
        "consult_advanced",
        "deactivate_advanced_mode",
        "get_environment",
        "read_finances",
        "generate_image",
        "generar_pdf",
    }
    assert "read_gmail" not in advanced_tools
    assert "activate_camera" not in advanced_tools
    assert "finance_prepare_write" not in advanced_tools
    assert "gmail_prepare_send" not in advanced_tools
    assert "search_web" not in advanced_tools
    assert "meta_prepare_publish" not in advanced_tools


def test_native_image_pdf_tools_have_fillers_and_timeouts():
    from app.services.retell_native_pilot import (
        build_generate_image_tool,
        build_generar_pdf_tool,
    )

    img = build_generate_image_tool(api_public_url="https://api.example.com")
    assert img["name"] == "generate_image"
    assert img["speak_during_execution"] is True
    assert "generando su imagen" in img["execution_message_description"].lower()
    assert img["timeout_ms"] == 60_000
    assert img["url"].endswith("/v1/retell/tools/generate_image")
    assert "prompt" in img["parameters"]["properties"]

    pdf = build_generar_pdf_tool(api_public_url="https://api.example.com")
    assert pdf["name"] == "generar_pdf"
    assert "preparando su pdf" in pdf["execution_message_description"].lower()
    assert pdf["timeout_ms"] == 45_000
    assert pdf.get("enable_typing_sound") is True
    assert "tardar" in pdf["execution_message_description"].lower()
    assert pdf["url"].endswith("/v1/retell/tools/generar_pdf")


def test_pilot_prompt_includes_image_pdf_rules():
    assert "generate_image" in RETELL_NATIVE_PILOT_PROMPT
    assert "generar_pdf" in RETELL_NATIVE_PILOT_PROMPT
    assert "NUNCA digas que la imagen o el PDF están listos" in RETELL_NATIVE_PILOT_PROMPT


def test_execute_generate_image_delegates_to_voice_executor():
    import asyncio

    from app.services.retell_native_pilot import execute_generate_image_tool

    async def run():
        with patch(
            "app.services.voice_tool_executor.execute_voice_tool",
            new_callable=AsyncMock,
            return_value={
                "ok": True,
                "spoken": "Imagen generada, señor. Ya la puede ver en pantalla.",
                "url": "https://cdn.example.com/img.png",
            },
        ) as mock_exec:
            out = await execute_generate_image_tool(
                user_id="u-img",
                payload={"call": {"call_id": "c1"}},
                args={"prompt": "un café al atardecer"},
            )
            mock_exec.assert_awaited_once()
            assert mock_exec.await_args.args[0] == "generate_image"
            assert mock_exec.await_args.args[2]["prompt"] == "un café al atardecer"
            assert out["ok"] is True
            assert "pantalla" in out["result"].lower()
            return out

    asyncio.run(run())


def test_execute_generar_pdf_delegates_to_voice_executor():
    import asyncio

    from app.services.retell_native_pilot import execute_generar_pdf_tool

    async def run():
        with patch(
            "app.services.voice_tool_executor.execute_voice_tool",
            new_callable=AsyncMock,
            return_value={
                "ok": True,
                "spoken": "PDF listo, señor. Título: Tareas. Ya está en su historial.",
                "file_id": "pdf-1",
            },
        ) as mock_exec:
            out = await execute_generar_pdf_tool(
                user_id="u-pdf",
                payload={"call": {"call_id": "c2"}},
                args={"titulo": "Tareas", "contenido": "1. Comprar café"},
            )
            mock_exec.assert_awaited_once()
            assert mock_exec.await_args.args[0] == "generar_pdf"
            assert mock_exec.await_args.args[2]["titulo"] == "Tareas"
            assert out["ok"] is True
            assert "historial" in out["result"].lower()
            return out

    asyncio.run(run())


def test_pilot_prompt_includes_search_web_rules():
    # Fase A: reglas en prompt corto; routing clima vs search en schemas + tip.
    assert "search_web" in RETELL_NATIVE_PILOT_PROMPT
    assert "get_environment" in RETELL_NATIVE_PILOT_PROMPT
    assert "clima" in RETELL_NATIVE_PILOT_PROMPT.lower()


def test_pilot_prompt_includes_map_navigation_rules():
    from app.services.retell_native_pilot import (
        SEARCH_NEARBY_PLACES_DESCRIPTION,
        SHOW_ROUTE_DESCRIPTION,
        START_DRIVE_NAVIGATION_DESCRIPTION,
    )

    # Fase A: frases de mapa viven en descriptions de tool (schemas), no en catálogo textual.
    assert "muéstrame la ruta" in SHOW_ROUTE_DESCRIPTION
    assert "inicia la ruta" in START_DRIVE_NAVIGATION_DESCRIPTION
    assert "destino" in SEARCH_NEARBY_PLACES_DESCRIPTION.lower() or "llévame" in SEARCH_NEARBY_PLACES_DESCRIPTION.lower()


def test_execute_map_tools_delegate_to_voice_executor():
    import asyncio

    from app.services.retell_native_pilot import (
        execute_open_drive_map_tool,
        execute_search_nearby_places_tool,
        execute_show_route_tool,
        execute_start_drive_navigation_tool,
    )

    payload = {"call": {"call_id": "call-map-1"}}

    async def _run():
        with patch(
            "app.services.voice_tool_executor.execute_voice_tool",
            new_callable=AsyncMock,
            return_value={"ok": True, "spoken": "Mapa listo, señor."},
        ) as mock_exec:
            await execute_open_drive_map_tool(user_id="u1", payload=payload, args={})
            assert mock_exec.await_args.args[0] == "activar_modo_conducir"

            mock_exec.reset_mock()
            await execute_search_nearby_places_tool(
                user_id="u1", payload=payload, args={"query": "Torre Eiffel"}
            )
            assert mock_exec.await_args.args[0] == "search_nearby_places"
            assert mock_exec.await_args.args[2]["query"] == "Torre Eiffel"

            mock_exec.reset_mock()
            with patch(
                "app.services.navigation_session.get_place_options",
                return_value=[{"name": "A", "lat": 1.0, "lng": 2.0}],
            ), patch(
                "app.services.navigation_session.get_route",
                return_value=None,
            ):
                await execute_show_route_tool(user_id="u1", payload=payload, args={})
            assert mock_exec.await_args.args[0] == "start_navigation"
            assert mock_exec.await_args.args[2].get("option_index") == 0
            assert mock_exec.await_args.args[2].get("confirm") is not True

            mock_exec.reset_mock()
            await execute_start_drive_navigation_tool(
                user_id="u1", payload=payload, args={}
            )
            assert mock_exec.await_args.args[0] == "start_navigation"
            assert mock_exec.await_args.args[2].get("confirm") is True

    asyncio.run(_run())


def test_build_search_web_tool_has_filler():
    from app.services.retell_native_pilot import build_search_web_tool

    tool = build_search_web_tool(api_public_url="https://api.example.com")
    assert tool["name"] == "search_web"
    assert "investigando" in tool["execution_message_description"].lower()
    assert tool["timeout_ms"] == 25_000


def test_execute_search_web_tool_uses_voice_executor():
    import asyncio

    from app.services.retell_native_pilot import execute_search_web_tool

    payload = {
        "call": {"call_id": "call_search_1"},
        "args": {"query": "noticias de OpenAI hoy"},
    }

    async def _run():
        with patch(
            "app.services.voice_tool_executor.execute_voice_tool",
            new_callable=AsyncMock,
            return_value={"ok": True, "spoken": "Señor, OpenAI anunció una actualización."},
        ) as mock_exec:
            result = await execute_search_web_tool(
                user_id="user-1",
                payload=payload,
                args=payload["args"],
            )
            mock_exec.assert_awaited_once()
            assert mock_exec.await_args.args[0] == "search_web"
            assert mock_exec.await_args.args[2]["query"] == "noticias de OpenAI hoy"
            return result

    result = asyncio.run(_run())
    assert result["ok"] is True
    assert "OpenAI" in result["result"]


def test_pilot_prompt_includes_advanced_rules():
    assert "activa modo avanzado" in RETELL_NATIVE_PILOT_PROMPT
    assert "consult_advanced" in RETELL_NATIVE_PILOT_PROMPT
    assert "deactivate" in RETELL_NATIVE_PILOT_PROMPT.lower()


def test_pilot_prompt_includes_camera_rules():
    assert "activate" in RETELL_NATIVE_PILOT_PROMPT.lower()
    assert "analyze_camera_frame" in RETELL_NATIVE_PILOT_PROMPT
    assert "search_visible_product" in RETELL_NATIVE_PILOT_PROMPT
    assert "NUNCA inventar" in RETELL_NATIVE_PILOT_PROMPT


def test_consult_advanced_tool_has_filler():
    from app.services.retell_native_pilot import build_consult_advanced_tool

    tool = build_consult_advanced_tool(api_public_url="https://api.example.com")
    assert tool["name"] == "consult_advanced"
    assert "sistema avanzado" in tool["execution_message_description"].lower()
    assert tool["timeout_ms"] == 45_000


def test_pilot_prompt_includes_standalone_identity():
    assert "Eres CED" in RETELL_NATIVE_PILOT_PROMPT
    assert "get_environment" in RETELL_NATIVE_PILOT_PROMPT
    assert "charla casual" in RETELL_NATIVE_PILOT_PROMPT.lower()


def test_resolve_environment_tool_query_prefers_args():
    payload = {"call": {"transcript_object": [{"role": "user", "content": "Charlotte"}]}}
    query = resolve_environment_tool_query(payload, {"query": "clima hoy en Charlotte"})
    assert query == "clima hoy en Charlotte"


def test_resolve_environment_tool_query_falls_back_to_transcript():
    payload = {
        "call": {
            "transcript_object": [
                {"role": "agent", "content": "Hola"},
                {"role": "user", "content": "¿cómo está el clima hoy?"},
            ]
        }
    }
    query = resolve_environment_tool_query(payload, {})
    assert "clima" in query


def test_execute_get_environment_tool_records_latency():
    import asyncio

    from app.services.retell_native_pilot import execute_get_environment_tool

    payload = {
        "call": {"call_id": "call_test_1"},
        "args": {"query": "clima hoy"},
    }

    async def _run():
        with patch(
            "app.modules.environment_module.handle_environment_query_sync",
            return_value={"spoken": "Señor, 24 grados en Charlotte."},
        ):
            return await execute_get_environment_tool(
                user_id="user-1",
                payload=payload,
                args=payload["args"],
            )

    result = asyncio.run(_run())
    assert result["ok"] is True
    assert "24 grados" in result["result"]
    assert result["latency_ms"] >= 0
    metrics = get_pilot_metrics_snapshot()
    assert metrics["environment_invocations"] >= 1


def test_get_environment_endpoint_without_user_id():
    client = TestClient(app)
    response = client.post(
        "/v1/retell/tools/get_environment",
        json={"name": "get_environment", "args": {"query": "clima hoy"}},
    )
    # En dev sin RETELL_WEBHOOK_SECRET la firma no se exige; debe degradar sin user_id.
    assert response.status_code == 200
    body = response.json()
    assert "result" in body
    assert "identifiqu" in body["result"].lower() or "usuario" in body["result"].lower()


def test_native_pilot_status_requires_auth():
    client = TestClient(app)
    response = client.get("/v1/retell/native-pilot/status")
    assert response.status_code in {401, 403, 422}


def test_record_tool_metric_rolling_window():
    for idx in range(5):
        record_tool_metric(
            call_id=f"call-{idx}",
            tool_name="get_environment",
            latency_ms=100 + idx,
            ok=True,
            query=f"clima {idx}",
        )
    snap = get_pilot_metrics_snapshot()
    assert snap["get_environment"]["invocations"] >= 5
    assert snap["get_environment"]["avg_latency_ms"] is not None


def test_calendar_read_sync_rejects_create():
    from app.modules.calendar_module import handle_calendar_read_sync

    result = handle_calendar_read_sync("user-1", "agéndame cita mañana a las 3")
    spoken = result["spoken"].lower()
    assert "confirmación" in spoken or "agéndame" in spoken
    assert "sí" in spoken


def test_calendar_api_call_refreshes_on_401():
    from app.modules.calendar_module import _calendar_api_call, _handle_calendar_query

    calls = {"n": 0}

    def _fn(access: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.HTTPStatusError(
                "unauthorized",
                request=httpx.Request("GET", "https://google.example/events"),
                response=httpx.Response(401),
            )
        assert access == "fresh-token"
        return "ok"

    with patch(
        "app.modules.calendar_module.get_valid_access_token",
        return_value="stale-token",
    ):
        with patch(
            "app.modules.calendar_module.force_refresh_access_token",
            return_value="fresh-token",
        ):
            assert _calendar_api_call("user-1", _fn) == "ok"
            assert calls["n"] == 2


def test_resolve_calendar_windows_hoy_y_manana():
    from app.modules.calendar_module import _resolve_calendar_windows

    windows = _resolve_calendar_windows("¿qué tengo hoy o eventos de mañana?")
    labels = [label for _, _, label in windows]
    assert labels == ["hoy", "mañana"]


def test_handle_calendar_query_hoy_y_manana_with_events():
    from app.modules.calendar_module import _handle_calendar_query

    with patch(
        "app.modules.calendar_module._calendar_api_call",
        side_effect=lambda _uid, fn: fn("token"),
    ):
        with patch(
            "app.modules.calendar_module.list_events",
            side_effect=[["Hoy 9:00 AM — Standup"], ["Mañana 2:00 PM — Doctor"]],
        ):
            spoken = _handle_calendar_query("user-1", "¿qué tengo hoy o eventos de mañana?")
    assert "Standup" in spoken
    assert "Doctor" in spoken
    assert "hoy" in spoken.lower()
    assert "mañana" in spoken.lower()


def test_gmail_read_sync_redirects_voice_send_to_confirm_flow():
    from app.modules.gmail_module import handle_gmail_read_sync

    result = handle_gmail_read_sync("user-1", "envía un email a juan@test.com")
    spoken = result["spoken"].lower()
    assert "confirmación" in spoken or "confirme" in spoken
    assert "sí" in spoken
    assert "formulario" not in spoken


def test_gmail_read_sync_returns_full_body_via_helper():
    from app.modules.gmail_module import GMAIL_VOICE_BODY_LIMIT, _message_content_for_voice
    from app.services.google_gmail_api import MessageBodyResult

    long_body = "A" * 2000
    with patch(
        "app.modules.gmail_module.fetch_message_body_detail",
        return_value=MessageBodyResult(text=long_body, source="plain", ok=True),
    ):
        content, ok, _source, _mime = _message_content_for_voice("token", {"id": "msg-1", "subject": "Hola"})
    assert ok is True
    assert len(content) == GMAIL_VOICE_BODY_LIMIT


def test_gmail_read_sync_leeme_el_de_sender():
    from app.modules.gmail_module import handle_gmail_read_sync

    with patch("app.modules.gmail_module._gmail_api_call") as call:
        call.side_effect = lambda _uid, fn: fn("token")
        with patch("app.modules.gmail_module.list_messages") as list_msgs:
            list_msgs.return_value = [
                {
                    "id": "m1",
                    "from_name": "Jun Medina",
                    "subject": "Work Schedule for Monday",
                    "from": "jun@x.com",
                    "snippet": "Work Schedule for Monday",
                }
            ]
            with patch("app.modules.gmail_module.fetch_message_body_detail") as fetch_body:
                from app.services.google_gmail_api import MessageBodyResult

                fetch_body.return_value = MessageBodyResult(
                    text="Shift starts 8:00 AM. Break at 12:00.",
                    source="html",
                    ok=True,
                )
                out = handle_gmail_read_sync("user-1", "léeme el de Jun Medina")
    assert "Shift starts 8:00 AM" in out["spoken"]
    assert "Señor, de Jun Medina" in out["spoken"]
    assert "INSTRUCCIÓN" not in out["spoken"]
    assert "CUERPO_LITERAL" not in out["spoken"]


def test_gmail_body_followup_uses_last_read_cache():
    from app.modules.gmail_module import handle_gmail_read_sync
    from app.services import voice_client_session as vcs
    from app.services.google_gmail_api import MessageBodyResult

    vcs.set_gmail_last_read(
        "user-1",
        {
            "id": "cached-msg",
            "from_name": "Jun Medina",
            "subject": "Work Schedule",
            "snippet": "snippet",
        },
    )
    with patch("app.modules.gmail_module._gmail_api_call", side_effect=lambda _uid, fn: fn("token")):
        with patch(
            "app.modules.gmail_module.fetch_message_body_detail",
            return_value=MessageBodyResult(
                text="Full schedule: 8am standup, 2pm review.",
                source="plain",
                ok=True,
            ),
        ):
            out = handle_gmail_read_sync("user-1", "léeme el contenido del correo")
    assert "8am standup" in out["spoken"]
    vcs.set_gmail_last_read("user-1", None)


def test_gmail_snippet_only_reports_unavailable_not_subject():
    from app.modules.gmail_module import _message_content_for_voice
    from app.services.google_gmail_api import MessageBodyResult

    with patch(
        "app.modules.gmail_module.fetch_message_body_detail",
        return_value=MessageBodyResult(
            text="Work Schedule for Monday, July 13th, 2026",
            source="snippet",
            ok=False,
            snippet="Work Schedule for Monday, July 13th, 2026",
        ),
    ):
        content, ok, source, _mime = _message_content_for_voice(
            "token",
            {
                "id": "m1",
                "subject": "Work Schedule for Monday, July 13th, 2026",
                "snippet": "Work Schedule for Monday, July 13th, 2026",
            },
        )
    assert ok is False
    assert source == "snippet"
    assert "No pude obtener el cuerpo completo" in content


def test_gmail_literal_format_three_distinct_bodies():
    from app.modules.gmail_module import format_gmail_literal_voice

    samples = [
        ("Ana", "Factura", "Total a pagar: 120 USD antes del viernes."),
        ("Carlos", "Reunión", "Nos vemos a las 3pm en la oficina central."),
        ("Jun Medina", "Horario lunes", "El turno empieza a las 8:00, no a las 9."),
    ]
    for from_name, subject, body in samples:
        out = format_gmail_literal_voice(from_name=from_name, subject=subject, body=body)
        assert body in out
        assert "Señor, de" in out
        assert "CUERPO_LITERAL" not in out


def test_finance_read_sync_redirects_write_to_prepare_flow():
    from app.modules.finance_module import handle_finance_read_sync

    result = handle_finance_read_sync("user-1", "gasté 50 en materiales")
    assert "confirmación" in result["spoken"].lower()
