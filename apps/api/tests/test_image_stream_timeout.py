"""Regresión: generación de imagen no debe colgar el SSE tras el deadline.

Bug prod: ThreadPoolExecutor.__exit__ hacía shutdown(wait=True) al vencer
el hard deadline → sin keepalives → UI «No pude generar la imagen a tiempo».
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from app.services import text_chat
from app.services.chat_image_generation import run_chat_image_generation
from app.services.copy_quality import orchestrate_image_generation_brief
from app.services.gemini_images import prepare_image_prompt
from app.services.publish_image_context import clear_session_image

USER = "user-img-stream-timeout"
CONV = "conv-img-stream-timeout"

CAPABILITY_PASTE = """
generame una imagen con estos detalles resumidos escritos Características del Sistema CED

## Núcleo Actual (Maduro)
- **Asistente de IA conversacional** — responde en español.
- **Mentor en ventas y prospección** — estrategia comercial.
- **Consultor de marketing digital** — Meta Ads, Instagram.
- **Memoria contextual** — recuerda lo que dijiste.

## Funcionalidades Técnicas
- **search_web** — búsqueda en tiempo real.
- **generate_image** — crea imágenes por descripción.
- **publicar_instagram** — publica contenido directo en tus redes.
"""


def setup_function(_fn):
    clear_session_image(USER, CONV)


def teardown_function(_fn):
    clear_session_image(USER, CONV)


def test_prepare_image_prompt_skips_history_when_direct():
    brief = (
        "mapa holográfico con etiquetas. Include the requested labels as clear "
        "legible on-image text."
    )
    bloated = "características " + ("detalle irrelevante del chat. " * 80)
    prepared = prepare_image_prompt(brief, bloated)
    assert "detalle irrelevante del chat" not in prepared
    assert "Include the requested labels" in prepared


def test_capability_paste_direct_brief_stays_short():
    orch = orchestrate_image_generation_brief(CAPABILITY_PASTE)
    tech = str(orch.get("technical_prompt") or "")
    assert tech
    assert len(tech) < 3800
    assert orch.get("wants_literal_text") is True
    assert "sistema" in tech.lower() or "asistente" in tech.lower()
    assert "textos exactos" not in tech.lower()


@patch("app.services.gemini_images.generate_image")
def test_capability_paste_does_not_send_bloated_context(mock_gen: MagicMock):
    mock_gen.return_value = {
        "ok": True,
        "url": "https://example.com/ced.png",
        "caption": "CED",
        "quality": "standard",
        "provider": "gemini",
        "ideogram_used": False,
    }
    history = [
        {"role": "user", "content": "hola"},
        {
            "role": "model",
            "content": "contexto largo " + ("x" * 2500),
        },
    ]
    result = run_chat_image_generation(
        USER, CONV, CAPABILITY_PASTE, history, plan_id="pro"
    )
    assert result["ok"] is True
    mock_gen.assert_called_once()
    ctx = str(mock_gen.call_args.kwargs.get("context") or "")
    assert len(ctx) < 400
    prompt = str(mock_gen.call_args.kwargs.get("prompt") or "")
    assert "xxxx" not in prompt
    assert mock_gen.call_args.kwargs.get("prefer_ideogram") is True or "caracter" in prompt.lower()

def test_generate_image_intent_uses_sse_not_blocking_gate():
    """Regresión: imagen debe entrar al stream (keepalives), no al gate bloqueante."""
    assert text_chat._can_stream_chat_text("generame una imagen de un atardecer") is True
    assert text_chat._can_stream_chat_text("hazme un PDF del análisis") is False


def test_direct_image_stream_emits_done_after_deadline_without_waiting():
    """El generador debe emitir done/error en ~deadline, no esperar al job lento."""

    def _slow_job(*_a, **_k):
        time.sleep(30)
        return {"ok": True, "url": "https://example.com/late.png", "reply": "tarde"}

    events: list[str] = []
    started = time.perf_counter()
    with (
        patch.object(text_chat, "IMAGE_STREAM_DEADLINE_SEC", 0.35),
        patch.object(text_chat, "IMAGE_STREAM_KEEPALIVE_SEC", 0.05),
        patch(
            "app.services.chat_image_generation.should_take_direct_image_path",
            return_value=True,
        ),
        patch(
            "app.services.chat_image_generation.run_chat_image_generation",
            side_effect=_slow_job,
        ),
        patch("app.services.text_chat.supabase_db.get_profile", return_value={}),
        patch("app.services.text_chat._stream_is_blocked", return_value=False),
        patch("app.services.chat_rate_limit.check_chat_rate_limit", return_value=(True, 0)),
        patch("app.deps.plan_access.chat_message_limit", return_value=100),
        patch("app.services.text_chat.get_settings") as settings,
        patch(
            "app.services.text_chat._load_stream_conversation",
            return_value=(CONV, []),
        ),
        patch("app.services.text_chat.supabase_db.append_message"),
        patch("app.services.text_chat._plan_id_for_user", return_value="pro"),
        patch("app.services.text_chat._stream_usage_snapshot", return_value={"blocked": False}),
        patch("app.services.text_chat._bump_stream_usage_cache"),
        patch("app.services.text_chat._publish_flow_requires_blocking", return_value=False),
        patch(
            "app.services.chat_intents.resolve_pdf_detail_for_turn",
            return_value=None,
        ),
        patch("app.services.llama_service.use_llama", return_value=False),
    ):
        settings.return_value = MagicMock(
            google_api_key="gk",
            anthropic_api_key="ak",
            gemini_voice_model="gemini-2.5-flash",
        )
        for chunk in text_chat.iter_send_message_stream(
            USER, content="generame una imagen de un atardecer"
        ):
            events.append(chunk)

    elapsed = time.perf_counter() - started
    assert elapsed < 3.0, f"SSE bloqueó esperando al job: {elapsed:.2f}s"
    joined = "".join(events)
    assert "event: done" in joined
    assert "tardó demasiado" in joined or "No pude generar" in joined
    assert "https://example.com/late.png" not in joined


def test_direct_image_stream_emits_done_even_if_persist_fails():
    """Regresión: fallo de DB tras generar no debe dejar «Respuesta incompleta»."""

    events: list[str] = []
    with (
        patch(
            "app.services.chat_image_generation.should_take_direct_image_path",
            return_value=True,
        ),
        patch(
            "app.services.chat_image_generation.run_chat_image_generation",
            return_value={
                "ok": True,
                "url": "https://example.com/generated.png",
                "reply": "Listo. Aquí está tu imagen generada.",
                "caption": "Imagen generada",
                "quality": "standard",
            },
        ),
        patch("app.services.text_chat.supabase_db.get_profile", return_value={}),
        patch("app.services.text_chat._stream_is_blocked", return_value=False),
        patch("app.services.chat_rate_limit.check_chat_rate_limit", return_value=(True, 0)),
        patch("app.deps.plan_access.chat_message_limit", return_value=100),
        patch("app.services.text_chat.get_settings") as settings,
        patch(
            "app.services.text_chat._load_stream_conversation",
            return_value=(CONV, []),
        ),
        patch(
            "app.services.text_chat.supabase_db.append_message",
            side_effect=RuntimeError("db down"),
        ),
        patch("app.services.text_chat._plan_id_for_user", return_value="pro"),
        patch("app.services.text_chat._stream_usage_snapshot", return_value={"blocked": False}),
        patch("app.services.text_chat._bump_stream_usage_cache"),
        patch("app.services.text_chat._publish_flow_requires_blocking", return_value=False),
        patch(
            "app.services.chat_intents.resolve_pdf_detail_for_turn",
            return_value=None,
        ),
        patch("app.services.llama_service.use_llama", return_value=False),
    ):
        settings.return_value = MagicMock(
            google_api_key="gk",
            anthropic_api_key="ak",
            gemini_voice_model="gemini-2.5-flash",
        )
        for chunk in text_chat.iter_send_message_stream(
            USER,
            content="hazme una foto de un gato",
        ):
            events.append(chunk)

    joined = "".join(events)
    assert "event: done" in joined
    assert "https://example.com/generated.png" in joined
    assert "event: token" in joined
