"""Tests — instrumentación de latencia en LlamaVoiceLlm."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from app.services.llama_voice_llm import LlamaVoiceLlm
from app.services.retell_llm_types import ResponseRequiredRequest, Utterance
from app.services.voice_latency import get_turn, start_turn


def test_llama_voice_marks_latency_on_conversational_reply() -> None:
    llm = LlamaVoiceLlm()
    llm.set_latency_context("call-test", 42)
    start_turn("call-test", 42)

    async def run() -> str | None:
        with patch(
            "app.services.llama_voice_llm.call_llama_chat",
            return_value="Respuesta de prueba, señor.",
        ):
            req = ResponseRequiredRequest(
                interaction_type="response_required",
                response_id=42,
                transcript=[Utterance(role="user", content="¿Qué es la fotosíntesis?")],
            )
            return await llm.draft_conversational_response(req)

    reply = asyncio.run(run())
    assert reply
    turn = get_turn("call-test", 42)
    assert turn is not None
    assert turn.llm_request_ts is not None
    assert turn.llm_first_token_ts is not None
    assert turn.path == "conversational"


def test_llama_voice_stream_marks_first_token() -> None:
    llm = LlamaVoiceLlm()
    llm.set_latency_context("call-stream", 7)
    start_turn("call-stream", 7)

    def fake_stream(**kwargs):  # noqa: ANN003
        yield "Hola"
        yield " señor."

    async def run() -> list[str]:
        with patch(
            "app.services.llama_service.iter_llama_chat_stream",
            side_effect=lambda **kwargs: fake_stream(**kwargs),
        ):
            req = ResponseRequiredRequest(
                interaction_type="response_required",
                response_id=7,
                transcript=[Utterance(role="user", content="Explícame el universo")],
            )
            chunks: list[str] = []
            async for event in llm.draft_response(req):
                if event.content:
                    chunks.append(event.content)
            return chunks

    chunks = asyncio.run(run())
    assert chunks
    turn = get_turn("call-stream", 7)
    assert turn is not None
    assert turn.llm_request_ts is not None
    assert turn.llm_first_token_ts is not None
    assert turn.path == "llama_stream"


def test_llama_payload_includes_keep_alive() -> None:
    from app.services import llama_service as ls

    captured: dict = {}

    class FakeResponse:
        status_code = 200

        def json(self) -> dict:
            return {"message": {"content": "ok"}}

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:  # noqa: ANN002
            return None

        def post(self, url: str, json: dict) -> FakeResponse:  # noqa: A002
            captured.update(json)
            return FakeResponse()

    with patch.object(ls, "llama_model_ready", return_value=True):
        with patch.object(ls.httpx, "Client", FakeClient):
            ls.call_llama_chat(
                system="test",
                messages=[{"role": "user", "content": "hola"}],
            )
    assert captured.get("keep_alive") == "24h"
