"""Routing: edit/variation on upload beats publish and marketing creativo swallow."""

from __future__ import annotations

from app.services.chat_intents import (
    is_attachment_image_edit_request,
    is_explicit_publish_to_social,
    wants_image_reference_edit,
)
from app.services.marketing_creative import is_marketing_creative_intent
from app.services.publish_text import is_social_publish_intent


WOLF = (
    "hazme una imagen con esta misma característica del dogo y "
    "Pon un lobo con dos cabezas"
)
BRAIN = (
    "hazme una imagen así como esta que te acabo de compartir pero el cerebro "
    "con lo fragmentado en partes y pon tu mundo interior y tus luchas están "
    "aquí dentro de tu cerebro o dentro de tu mente"
)
CUADROS = (
    "Okay en esa imagen que te compro a ti un cuadro También aparte de los días "
    "tan que diga asistente virtual sofisticado con otro padre que diga "
    "publicaciones en redes y otro cuadro que diga asesor en finanzas"
)
FLYER_KEEP_PRICES = (
    "cambia el fondo del flyer pero mantén la lista de precios igual"
)
PUBLISH_FB = "publica esta imagen en facebook"


def test_wolf_is_edit_not_publish_not_marketing():
    assert is_attachment_image_edit_request(WOLF)
    assert wants_image_reference_edit(WOLF) or is_attachment_image_edit_request(WOLF)
    assert not is_social_publish_intent(WOLF, with_image=True)
    assert not is_marketing_creative_intent(WOLF)


def test_brain_fragment_is_edit_not_publish():
    assert is_attachment_image_edit_request(BRAIN)
    assert not is_social_publish_intent(BRAIN, with_image=True)


def test_cuadros_publicaciones_en_redes_is_edit_not_publish():
    """«que diga publicaciones en redes» = texto en la imagen, no publicar."""
    assert is_attachment_image_edit_request(CUADROS)
    assert not is_explicit_publish_to_social(CUADROS)
    assert not is_social_publish_intent(CUADROS, with_image=True)


def test_flyer_keep_prices_is_edit():
    assert is_attachment_image_edit_request(FLYER_KEEP_PRICES)
    assert not is_social_publish_intent(FLYER_KEEP_PRICES, with_image=True)


def test_explicit_publish_still_works():
    assert is_explicit_publish_to_social(PUBLISH_FB)
    assert is_social_publish_intent(PUBLISH_FB, with_image=True)
    assert not is_attachment_image_edit_request(PUBLISH_FB)


def test_short_esa_imagen_still_publish_signal():
    assert is_social_publish_intent("esa imagen", with_image=True)
