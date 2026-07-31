"""Los 3 modos deben pasar el pedido del usuario al adaptador directo (sin reescritura)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from app.services.chat_image_generation import (
    run_chat_image_generation,
    should_take_direct_image_path,
)
from app.services.copy_quality import build_direct_image_prompt
from app.services.text_chat import CHAT_SYSTEM_BASE


RAW_SCENE = (
    "generame una imagen de un mapa holográfico digital con las etiquetas "
    "sistema avanzado, análisis profundo EN TEXTO"
)
LLM_REWRITE = (
    "Infografía premium del sistema CED con tipografía corporativa y robot corriendo"
)


def test_chat_system_forbids_summarizing_image_briefs():
    low = CHAT_SYSTEM_BASE.lower()
    assert "sin reescritura" in low or "tal cual" in low
    assert "resume internamente" not in low


def test_direct_adapter_keeps_scene_rejects_ced_injection():
    direct = build_direct_image_prompt(RAW_SCENE)
    scene = direct["visual_brief"].lower()
    prompt = direct["prompt"].lower()
    assert "mapa" in scene and "hologr" in scene
    assert "sistema avanzado" in scene
    assert "sistema ced" not in prompt
    assert "robot" not in prompt
    assert direct["wants_literal_text"] is True


def test_chat_and_advanced_take_direct_path():
    assert should_take_direct_image_path(RAW_SCENE, []) is True
    assert should_take_direct_image_path(
        "un águila sobre el mar al atardecer",
        [{"role": "user", "content": "hola"}],
    ) is False or should_take_direct_image_path(
        "generame una imagen de un águila sobre el mar al atardecer",
        [],
    )


def test_run_chat_image_generation_sends_direct_prompt_not_history_mix():
    captured: dict = {}

    def _fake_generate(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "url": "https://cdn.example.com/x.png", "quality": "auto"}

    with (
        patch("app.services.gemini_images.generate_image", side_effect=_fake_generate),
        patch(
            "app.services.chat_image_generation.should_use_reference_generation",
            return_value=False,
        ),
        patch(
            "app.services.publish_image_context.register_text_chat_image_url",
        ),
    ):
        out = run_chat_image_generation(
            "user-1",
            "conv-1",
            RAW_SCENE,
            [
                {"role": "user", "content": "generame un robot corriendo"},
                {"role": "assistant", "content": "Listo"},
            ],
            plan_id="elite",
            allow_reference=False,
        )

    assert out["ok"] is True
    prompt = str(captured.get("prompt") or "").lower()
    assert "mapa" in prompt or "hologr" in prompt
    assert "robot" not in prompt
    assert "sistema ced" not in prompt


def test_chat_tool_generate_image_prefers_raw_user_over_llm_prompt():
    from app.services import text_chat as tc

    captured: dict = {}

    def _fake_run(user_id, conversation_id, text, history, **kwargs):
        captured["text"] = text
        return {
            "ok": True,
            "url": "https://cdn.example.com/y.png",
            "caption": "ok",
            "quality": "auto",
        }

    with (
        patch("app.services.supabase_db.get_subscription", return_value={"plan_id": "elite"}),
        patch(
            "app.services.chat_image_generation.run_chat_image_generation",
            side_effect=_fake_run,
        ),
    ):
        result = tc._run_chat_tool(
            "user-tool",
            "generate_image",
            {"prompt": LLM_REWRITE, "quality": "auto"},
            conversation_id="c1",
            chat_messages=[
                {"role": "user", "content": RAW_SCENE},
            ],
        )

    import json

    payload = json.loads(result)
    assert payload["ok"] is True
    assert captured["text"] == RAW_SCENE
    assert "sistema CED" not in captured["text"]


def test_voice_executor_prefers_user_request():
    from app.services.voice_tool_executor import execute_voice_tool

    captured: dict = {}

    def _fake_run(user_id, conversation_id, text, history, **kwargs):
        captured["text"] = text
        return {"ok": True, "url": "https://cdn.example.com/v.png", "caption": "ok"}

    with (
        patch(
            "app.services.chat_image_generation.run_chat_image_generation",
            side_effect=_fake_run,
        ),
        patch("app.services.voice_tool_executor.voice_access_state", return_value={"plan_id": "elite"}),
        patch("app.services.voice_tool_executor.vcs.push_tool_event"),
    ):
        out = asyncio.run(
            execute_voice_tool(
                "generate_image",
                "user-voice",
                {"prompt": LLM_REWRITE, "_user_request": RAW_SCENE, "call_id": "c1"},
            )
        )

    assert out["ok"] is True
    assert captured["text"] == RAW_SCENE


def test_advanced_direct_image_uses_shared_pipeline():
    from app.services.advanced_mode import service as adv

    with patch(
        "app.services.chat_image_generation.run_chat_image_generation",
        return_value={
            "ok": True,
            "url": "https://cdn.example.com/a.png",
            "caption": "Mapa",
            "reply": "Listo",
        },
    ) as mock_gen:
        with patch("app.services.supabase_db.get_subscription", return_value={"plan_id": "elite"}):
            result = adv._try_direct_image("user-adv", RAW_SCENE, [], "conv-adv")

    assert result is not None
    mock_gen.assert_called_once()
    assert mock_gen.call_args.args[2] == RAW_SCENE
