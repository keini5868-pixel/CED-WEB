"""Tests — lista de capacidades CED vs falsos positivos de publicar/PDF."""

from __future__ import annotations

from app.domain.ced_product_capabilities import (
    CED_CAPABILITY_CATALOG_REPLY,
    is_capability_catalog_request,
    try_capability_catalog_reply,
)
from app.services.cognitive_intents import is_meta_publish_intent
from app.services.publish_text import is_social_publish_intent
from app.services.chat_intents import is_pdf_intent


CAPABILITY_LIST_MSG = (
    "Dame una lista donde especifique así por número, por ejemplo número uno "
    "publicación en redes número dos sistema avanzado de análisis profundo, "
    "número tres generación de imágenes y PDF y así sucesivamente todas las "
    "habilidades y las herramientas que tiene el sistema ced"
)


def test_capability_list_is_catalog_not_publish_or_pdf():
    assert is_capability_catalog_request(CAPABILITY_LIST_MSG)
    assert not is_social_publish_intent(CAPABILITY_LIST_MSG)
    assert not is_social_publish_intent(CAPABILITY_LIST_MSG, with_image=True)
    assert not is_meta_publish_intent(CAPABILITY_LIST_MSG)
    assert not is_pdf_intent(CAPABILITY_LIST_MSG)
    reply = try_capability_catalog_reply(CAPABILITY_LIST_MSG)
    assert reply is not None
    assert "WhatsApp" not in reply
    assert "YouTube" in reply
    assert "Publicación en Facebook" in reply or "Facebook" in reply


def test_real_publish_still_detected():
    assert is_social_publish_intent("publica esto en Instagram")
    assert is_social_publish_intent("publica en Facebook que diga hola")
    assert not is_capability_catalog_request("publica esto en Instagram")


def test_catalog_reply_is_factual():
    assert "WhatsApp" not in CED_CAPABILITY_CATALOG_REPLY
    assert "Modo avanzado" in CED_CAPABILITY_CATALOG_REPLY
    assert "PDF" in CED_CAPABILITY_CATALOG_REPLY
    assert "YouTube" in CED_CAPABILITY_CATALOG_REPLY
    assert "Finanzas" in CED_CAPABILITY_CATALOG_REPLY
    assert "Recordatorios" in CED_CAPABILITY_CATALOG_REPLY
    assert "viabilidad" in CED_CAPABILITY_CATALOG_REPLY.lower()
    assert "Variaciones de imagen" in CED_CAPABILITY_CATALOG_REPLY
    assert "Ads Manager" not in CED_CAPABILITY_CATALOG_REPLY or "no es Ads Manager" in CED_CAPABILITY_CATALOG_REPLY


def test_voice_capabilities_cover_product_gaps():
    from app.domain.ced_voice_capabilities import CED_VOICE_CAPABILITIES

    low = CED_VOICE_CAPABILITIES.lower()
    for needle in (
        "youtube",
        "finanzas",
        "modo avanzado",
        "get_environment",
        "viabilidad",
        "recordatorios",
        "variaciones",
    ):
        assert needle in low, needle
    assert "whatsapp" not in low


def test_retell_native_prompt_includes_capability_oral_summary():
    from app.services.retell_native_pilot import RETELL_NATIVE_PILOT_PROMPT

    low = RETELL_NATIVE_PILOT_PROMPT.lower()
    assert "qué puedes hacer" in low or "habilidades" in low
    assert "youtube" in low
    assert "finanzas" in low
    assert "mensajería de terceros" in low or "mensajeria de terceros" in low
    assert "prohibido inventar" in low