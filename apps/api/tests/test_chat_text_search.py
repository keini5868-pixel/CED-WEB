"""Tests — búsqueda web en chat de texto alineada con voz."""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import patch

from app.services.gemini_grounded import SEARCH_WEB_TIMEOUT_SEC, execute_search_web
from app.services.text_chat import (
    CHAT_SYSTEM_BASE,
    CHAT_TOOLS,
    _complete_chat_with_tools,
    _contains_internal_kb_leak,
    _extract_query_from_hallucination,
    _has_hallucinated_tool_code,
    _promised_web_search_without_tool,
    _run_chat_tool,
    _strip_internal_kb_from_reply,
)

TRUMP_TOOL_CODE_REPLY = (
    "Un momento, Señor. Permítame buscar...\n"
    "**tool_code**\n"
    "print(search_web(query='últimas declaraciones Donald Trump'))"
)


def test_chat_text_uses_parallel_search():
    async def fake_parallel(query: str, *, kind: str = "general"):
        return {
            "ok": True,
            "summary": "Datos recientes sobre el terremoto en Venezuela.",
            "source": "tavily",
        }

    with patch(
        "app.services.gemini_grounded.fetch_voice_brief_parallel",
        side_effect=fake_parallel,
    ):
        result = _run_chat_tool(
            "user-chat-search",
            "search_web",
            {"query": "muertes terremoto Venezuela", "kind": "news"},
        )

    import json

    data = json.loads(result)
    assert data.get("ok") is True
    assert data.get("status") == "success"
    assert "terremoto" in data.get("summary", "").lower()


def test_chat_text_search_web_timeout_17s():
    async def slow_parallel(*_a, **_k):
        await asyncio.sleep(SEARCH_WEB_TIMEOUT_SEC + 2)
        return {"ok": True, "summary": "nunca debería llegar"}

    async def run() -> dict:
        with patch(
            "app.services.gemini_grounded.fetch_voice_brief_parallel",
            side_effect=slow_parallel,
        ):
            return await execute_search_web("clima Caracas", kind="weather")

    started = time.monotonic()
    result = asyncio.run(run())
    elapsed = time.monotonic() - started

    assert result.get("ok") is False
    assert result.get("status") == "timeout"
    assert result.get("fallback") is True
    assert elapsed < SEARCH_WEB_TIMEOUT_SEC + 3


def test_chat_text_invokes_tool_not_hallucinates():
    tool_names = {t["name"] for t in CHAT_TOOLS}
    assert "search_web" in tool_names

    assert "NUNCA digas" in CHAT_SYSTEM_BASE and "search_web" in CHAT_SYSTEM_BASE
    assert "voy a buscar" in CHAT_SYSTEM_BASE.lower()

    assert _promised_web_search_without_tool("Voy a buscar esa información para usted.")
    assert not _promised_web_search_without_tool(
        "Según reportes recientes, el terremoto dejó más de cien víctimas en la región."
    )


def test_chat_detects_permission_ask_as_failed_search():
    stall = (
        "Señor, necesito hacer una búsqueda en tiempo real para darle datos "
        "precisos sobre Nosana — precio actual, volumen, casos de uso.\n\n"
        "¿Quiere que busque eso ahora para un análisis completo, o hay un "
        "ángulo específico (inversión, contenido sobre el token, estrategia comercial)?"
    )
    assert _promised_web_search_without_tool(stall)
    assert _promised_web_search_without_tool("¿Desea que lo busque ahora?")
    from app.services.text_chat import _is_web_search_followup, _needs_chat_tools

    history = [{"role": "model", "content": stall}]
    assert _is_web_search_followup("dame un resumen", history)
    assert _is_web_search_followup("ok", history)
    assert _needs_chat_tools("analiza el token nosana") is True
    assert _needs_chat_tools("naliza el token nosana") is True


def test_voice_thread_can_continue_as_text():
    from app.services.text_chat import conversation_allows_text_continue

    assert conversation_allows_text_continue({"id": "x", "channel": "voice"})
    assert conversation_allows_text_continue({"id": "x", "channel": "text"})
    assert conversation_allows_text_continue({"id": "x", "channel": "mixed"})
    assert not conversation_allows_text_continue(None)
    assert not conversation_allows_text_continue({"id": "x", "channel": "whatsapp"})


def test_live_market_query_is_not_bare_news():
    from app.services.cognitive_intents import (
        is_live_market_query,
        is_news_intent,
        is_web_research_intent,
        requires_live_web,
    )
    from app.services.text_chat import _can_stream_chat_text

    assert is_news_intent("dame un resumen") is False
    assert is_live_market_query("analiza el token nosana") is True
    assert is_live_market_query("es un token de la red de solana se llama nosana") is True
    assert is_web_research_intent("analiza el token nosana") is True
    assert requires_live_web("analiza el token nosana") is True
    assert is_live_market_query("qué es un embudo de ventas") is False
    assert _can_stream_chat_text("analiza el token nosana") is True
    assert _can_stream_chat_text("dame un resumen") is True


def test_chat_detects_tool_code_hallucination():
    assert _has_hallucinated_tool_code(TRUMP_TOOL_CODE_REPLY)
    assert _promised_web_search_without_tool(TRUMP_TOOL_CODE_REPLY)
    assert "tool_code" in CHAT_SYSTEM_BASE.lower()
    assert "print(search_web" in CHAT_SYSTEM_BASE.lower()


def test_chat_extracts_query_from_hallucination():
    query = _extract_query_from_hallucination(TRUMP_TOOL_CODE_REPLY)
    assert query == "últimas declaraciones Donald Trump"
    assert _extract_query_from_hallucination("sin código aquí") is None


def test_chat_retries_with_real_function_calling():
    tool_code_response = {
        "content": [{"type": "text", "text": TRUMP_TOOL_CODE_REPLY}],
    }
    real_tool_response = {
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "search_web",
                "input": {
                    "query": "últimas declaraciones Donald Trump",
                    "kind": "news",
                },
            }
        ],
    }
    final_response = {
        "content": [
            {
                "type": "text",
                "text": "Según fuentes recientes, Trump declaró sobre comercio internacional.",
            }
        ],
    }
    call_count = {"n": 0}

    def fake_anthropic(**_kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return tool_code_response
        if call_count["n"] == 2:
            return real_tool_response
        return final_response

    search_payload = json.dumps(
        {
            "ok": True,
            "status": "success",
            "summary": "Trump habló sobre aranceles y política exterior esta semana.",
        }
    )

    with patch("app.services.text_chat._anthropic_request", side_effect=fake_anthropic):
        with patch("app.services.text_chat._run_chat_tool", return_value=search_payload):
            reply, pdf, img = _complete_chat_with_tools(
                "user-trump",
                api_key="test-key",
                system="system",
                messages=[{"role": "user", "content": "dame info Trump"}],
            )

    assert call_count["n"] >= 2
    assert "Trump" in reply or "aranceles" in reply
    assert pdf is None
    assert img is None


def test_chat_system_hides_internal_kb_from_user():
    assert "Conocimiento interno CED" in CHAT_SYSTEM_BASE
    assert "NUNCA incluyas" in CHAT_SYSTEM_BASE
    assert "solo como contexto" in CHAT_SYSTEM_BASE.lower() or "contexto interno" in CHAT_SYSTEM_BASE.lower()


def test_chat_system_delivers_full_ai_prompts():
    assert "listo para copiar" in CHAT_SYSTEM_BASE.lower()
    assert "---" in CHAT_SYSTEM_BASE
    assert "estructura" in CHAT_SYSTEM_BASE.lower()


def test_internal_kb_leak_detection_and_strip():
    from app.services.text_chat import _strip_internal_kb_from_reply

    leaked = (
        "Conocimiento interno CED (priorizar sobre suposiciones):\n"
        "- [Marketing digital] SEO básico para negocios: SEO es clave..."
    )
    assert _contains_internal_kb_leak(leaked)
    assert _contains_internal_kb_leak("Texto con [Marketing digital] embebido")
    stripped = _strip_internal_kb_from_reply(leaked)
    assert not _contains_internal_kb_leak(stripped) or stripped == ""
