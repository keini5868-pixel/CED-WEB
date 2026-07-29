"""Tests — generación de imagen/PDF por voz (pipeline compartida + eventos UI)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from app.services.voice_tool_async import IMAGE_TOOL_TIMEOUT_SEC, tool_timeout_sec
from app.services.voice_tool_executor import execute_voice_tool


def test_image_and_pdf_tool_timeouts():
    assert tool_timeout_sec("generate_image") == IMAGE_TOOL_TIMEOUT_SEC
    assert tool_timeout_sec("generate_image") == 60.0
    assert tool_timeout_sec("generar_pdf") == 35.0


def test_voice_generate_image_uses_shared_pipeline_and_pushes_event():
    pushed: list[dict] = []

    def _push(user_id: str, event: dict) -> None:
        pushed.append({"user_id": user_id, **event})

    with (
        patch(
            "app.services.chat_image_generation.run_chat_image_generation",
            return_value={
                "ok": True,
                "url": "https://cdn.example.com/cafe.png",
                "caption": "Café",
                "reply": "Listo",
            },
        ) as mock_gen,
        patch("app.services.voice_tool_executor.voice_access_state", return_value={"plan_id": "elite"}),
        patch("app.services.voice_tool_executor.vcs.push_tool_event", side_effect=_push),
    ):
        result = asyncio.run(
            execute_voice_tool(
                "generate_image",
                "user-voice-img",
                {"prompt": "un café al atardecer", "call_id": "call-1"},
            )
        )

    mock_gen.assert_called_once()
    kwargs = mock_gen.call_args.kwargs
    assert kwargs.get("allow_reference") is False
    assert kwargs.get("plan_id") == "elite"
    assert mock_gen.call_args.args[2] == "un café al atardecer"
    assert result["ok"] is True
    assert result["url"] == "https://cdn.example.com/cafe.png"
    assert "pantalla" in result["spoken"].lower()
    assert pushed and pushed[0]["type"] == "generated_image"
    assert pushed[0]["image_url"] == "https://cdn.example.com/cafe.png"


def test_voice_generate_image_prefers_raw_user_request_over_llm_rewrite():
    """Voz: el utterance crudo gana al prompt reformulado por el LLM conversacional."""
    raw = (
        "generame una imagen de un mapa holográfico digital donde pongas "
        "sistema avanzado análisis profundo EN TEXTO"
    )
    rewritten = (
        "Crea una infografía premium del sistema CED con robot corriendo "
        "y tipografía corporativa moderna"
    )

    with (
        patch(
            "app.services.chat_image_generation.run_chat_image_generation",
            return_value={
                "ok": True,
                "url": "https://cdn.example.com/map.png",
                "caption": "Mapa",
                "reply": "Listo",
            },
        ) as mock_gen,
        patch("app.services.voice_tool_executor.voice_access_state", return_value={"plan_id": "elite"}),
        patch("app.services.voice_tool_executor.vcs.push_tool_event"),
    ):
        result = asyncio.run(
            execute_voice_tool(
                "generate_image",
                "user-voice-img-raw",
                {
                    "prompt": rewritten,
                    "_user_request": raw,
                    "call_id": "call-raw",
                },
            )
        )

    assert result["ok"] is True
    assert mock_gen.call_args.args[2] == raw
    assert "sistema CED" not in mock_gen.call_args.args[2]
    assert "robot" not in mock_gen.call_args.args[2]


def test_three_modes_share_run_chat_image_generation_entry():
    """Chat, avanzado y voz convergén en la misma pipeline de imagen."""
    import inspect

    from app.services import chat_image_generation as cig
    from app.services.advanced_mode import service as adv
    from app.services import voice_tool_executor as vte

    assert callable(cig.run_chat_image_generation)
    src_adv = adv._try_direct_image.__code__.co_names
    assert "run_chat_image_generation" in src_adv
    src = inspect.getsource(vte._execute_voice_tool_body)
    assert "run_chat_image_generation" in src
    assert "_user_request" in src


def test_voice_generate_image_no_event_on_failure():
    pushed: list[dict] = []

    with (
        patch(
            "app.services.chat_image_generation.run_chat_image_generation",
            return_value={"ok": False, "error": "quota exceeded", "url": None, "reply": "quota"},
        ),
        patch("app.services.voice_tool_executor.voice_access_state", return_value={"plan_id": "elite"}),
        patch(
            "app.services.voice_tool_executor.vcs.push_tool_event",
            side_effect=lambda *a, **k: pushed.append(a),
        ),
    ):
        result = asyncio.run(
            execute_voice_tool("generate_image", "user-voice-img", {"prompt": "algo"})
        )

    assert result["ok"] is False
    assert "imagen" in result["spoken"].lower()
    assert not pushed


def test_voice_generate_image_requires_prompt():
    result = asyncio.run(execute_voice_tool("generate_image", "user-voice-img", {"prompt": ""}))
    assert result["ok"] is False
    assert "indique" in result["spoken"].lower() or "imagen" in result["spoken"].lower()


def test_voice_generar_pdf_pushes_event_on_success():
    pushed: list[dict] = []
    artifact = SimpleNamespace(file_id="pdf-abc", title="Lista de tareas")

    with (
        patch(
            "app.deps.plan_access.effective_plan_limits",
            return_value=(
                SimpleNamespace(pdf_reports=True, pdf_reports_per_day=-1),
                None,
                None,
            ),
        ),
        patch(
            "app.services.voice_tool_executor.store_pdf_with_timeout",
            return_value=artifact,
        ),
        patch(
            "app.services.voice_tool_executor.vcs.push_tool_event",
            side_effect=lambda uid, ev: pushed.append(ev),
        ),
    ):
        result = asyncio.run(
            execute_voice_tool(
                "generar_pdf",
                "user-voice-pdf",
                {
                    "titulo": "Lista de tareas",
                    "contenido": "1. Comprar café\n2. Revisar informes",
                    "call_id": "call-pdf",
                },
            )
        )

    assert result["ok"] is True
    assert "PDF listo" in result["spoken"]
    assert result["file_id"] == "pdf-abc"
    assert pushed and pushed[0]["type"] == "pdf_created"
    assert pushed[0]["file_id"] == "pdf-abc"


def test_voice_generate_image_needs_recharge_pushes_client_action_and_event():
    """Bug de gap de recarga: imagen agotada por voz debe abrir el modal, no

    solo decirlo — mismo canal client_action/tool_event que YouTube.
    """
    pushed_actions: list[dict] = []
    pushed_events: list[dict] = []

    with (
        patch(
            "app.services.chat_image_generation.run_chat_image_generation",
            return_value={
                "ok": False,
                "url": None,
                "error": "Alcanzaste el límite de imágenes. Recarga desde $10 para continuar.",
                "code": "needs_recharge",
            },
        ),
        patch("app.services.voice_tool_executor.voice_access_state", return_value={"plan_id": "free_basic"}),
        patch(
            "app.services.voice_tool_executor.vcs.push_client_action",
            side_effect=lambda uid, action, payload: pushed_actions.append(
                {"action": action, "payload": payload}
            ),
        ),
        patch(
            "app.services.voice_tool_executor.vcs.push_tool_event",
            side_effect=lambda uid, ev: pushed_events.append(ev),
        ),
    ):
        result = asyncio.run(
            execute_voice_tool("generate_image", "user-voice-img-recharge", {"prompt": "algo"})
        )

    assert result["ok"] is False
    assert result["error"] == "needs_recharge"
    assert pushed_actions and pushed_actions[0]["action"] == "recharge_needed"
    assert pushed_actions[0]["payload"]["resource"] == "image"
    assert pushed_events and pushed_events[0]["type"] == "recharge_needed"


def test_voice_generar_pdf_without_plan_and_without_balance_needs_recharge():
    """PDF por voz sin plan Pro+ y sin saldo: debe avisar recarga, no solo

    «necesitas plan Pro» — antes esta ruta nunca consultaba el monedero.
    """
    pushed_actions: list[dict] = []

    with (
        patch(
            "app.deps.plan_access.effective_plan_limits",
            return_value=(SimpleNamespace(pdf_reports=False), "ok", False),
        ),
        patch("app.services.wallet.can_afford", return_value=False),
        patch(
            "app.services.voice_tool_executor.vcs.push_client_action",
            side_effect=lambda uid, action, payload: pushed_actions.append(
                {"action": action, "payload": payload}
            ),
        ),
    ):
        result = asyncio.run(
            execute_voice_tool(
                "generar_pdf",
                "user-voice-pdf-recharge",
                {"titulo": "Reporte", "contenido": "Contenido de prueba largo suficiente."},
            )
        )

    assert result["ok"] is False
    assert result["error"] == "needs_recharge"
    assert pushed_actions and pushed_actions[0]["action"] == "recharge_needed"
    assert pushed_actions[0]["payload"]["resource"] == "pdf"


def test_voice_generar_pdf_without_plan_but_with_balance_charges_wallet():
    """PDF por voz sin plan Pro+ pero con saldo: genera y debita el monedero."""
    artifact = SimpleNamespace(file_id="pdf-wallet-1", title="Reporte pagado")
    spent: list[dict] = []

    with (
        patch(
            "app.deps.plan_access.effective_plan_limits",
            return_value=(SimpleNamespace(pdf_reports=False), "ok", False),
        ),
        patch("app.services.wallet.can_afford", return_value=True),
        patch(
            "app.services.wallet.try_spend",
            side_effect=lambda uid, resource, units=1.0: spent.append(
                {"resource": resource, "units": units}
            )
            or {"ok": True, "balance_usd": 4.9},
        ),
        patch(
            "app.services.voice_tool_executor.store_pdf_with_timeout",
            return_value=artifact,
        ),
        patch("app.services.voice_tool_executor.vcs.push_tool_event"),
    ):
        result = asyncio.run(
            execute_voice_tool(
                "generar_pdf",
                "user-voice-pdf-wallet",
                {"titulo": "Reporte pagado", "contenido": "Contenido de prueba largo suficiente."},
            )
        )

    assert result["ok"] is True
    assert result["file_id"] == "pdf-wallet-1"
    assert spent and spent[0]["resource"] == "pdf"


def test_voice_search_web_needs_recharge_pushes_client_action():
    """Búsqueda web por voz sin cupo ni saldo: debe abrir el modal de recarga."""
    pushed_actions: list[dict] = []

    with patch(
        "app.services.web_search_quota.gate_web_search",
        return_value={
            "ok": False,
            "spoken": "Señor, alcanzó el límite de búsquedas web. Recarga desde diez dólares.",
            "error": "needs_recharge",
            "code": "needs_recharge",
        },
    ), patch(
        "app.services.voice_tool_executor.vcs.push_client_action",
        side_effect=lambda uid, action, payload: pushed_actions.append(
            {"action": action, "payload": payload}
        ),
    ):
        result = asyncio.run(
            execute_voice_tool("search_web", "user-voice-search-recharge", {"query": "clima hoy"})
        )

    assert result["ok"] is False
    assert result["error"] == "needs_recharge"
    assert pushed_actions and pushed_actions[0]["action"] == "recharge_needed"
    assert pushed_actions[0]["payload"]["resource"] == "web_search"
