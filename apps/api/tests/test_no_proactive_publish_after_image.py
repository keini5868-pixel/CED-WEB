"""CED no debe ofrecer publicar en redes de forma proactiva tras generar imagen."""

from __future__ import annotations

from app.domain.ced_voice_capabilities import CED_VOICE_CAPABILITIES
from app.services.text_chat import CHAT_SYSTEM_BASE


def test_chat_system_forbids_proactive_publish_after_image():
    low = CHAT_SYSTEM_BASE.lower()
    assert "proactiva" in low or "prohibido ofrecer publicar" in low
    assert "instagram/facebook" in low or "instagram" in low
    # La oferta antigua sin condición ya no debe existir.
    assert "ofrece publicarlo con ced si aplica" not in low


def test_voice_capabilities_do_not_frame_images_as_ready_to_publish():
    assert "quedan listas para publicar" not in CED_VOICE_CAPABILITIES.lower()
    assert "pedido explícito" in CED_VOICE_CAPABILITIES.lower() or "explícito" in CED_VOICE_CAPABILITIES.lower()


def test_voice_image_tool_skips_follow_up_like_pdf():
    import inspect

    from app.services import openai_voice_llm as ovl

    # Clase concreta del LLM de voz (nombre puede variar).
    llm_cls = next(
        getattr(ovl, name)
        for name in dir(ovl)
        if "VoiceLl" in name and inspect.isclass(getattr(ovl, name))
    )
    src = inspect.getsource(llm_cls.draft_response)
    assert "only_image" in src
    assert "generate_image" in src
    assert "skip follow-up" in src.lower() or "direct spoken" in src.lower()
