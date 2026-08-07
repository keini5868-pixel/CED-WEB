"""Ideación de texto (idea/concepto/copy) NO debe disparar generación de imagen."""

from __future__ import annotations

from app.services.chat_image_generation import should_take_direct_image_path
from app.services.chat_intents import (
    is_generate_image_intent,
    is_text_ideation_request,
)
from app.services.marketing_creative import (
    is_image_creation_request,
    is_marketing_creative_intent,
)


_IDEA_ONLY = [
    "dame una idea de copy para Instagram",
    "dame una idea para un post",
    "necesito una idea de contenido",
    "quiero un concepto para un video",
    "dame ideas de copy",
    "sugiéreme un concepto creativo",
    "escribe un copy para mi producto",
    "dame una descripción de producto",
    "genera una idea de campaña",
    "hazme una idea de creativo",
    "dame una idea de creativo para instagram",
    "dame una idea de imagen para el feed",
    "quiero ideas para un flyer",
    "proponme un concepto de banner",
    "ayúdame con el copy del creativo",
    "dame el concepto de la imagen",
    "qué idea de imagen me recomiendas",
    "crea un concepto visual",
    "hazme un prompt para vender Activise",
    "dame una idea de contenido sobre Restorate",
    "necesito un prompt para Midjourney de FitLine",
    "escribe un prompt para ChatGPT sobre el producto",
]


_EXPLICIT_IMAGE = [
    "genera una imagen de un atardecer",
    "hazme una foto de un gato",
    "créame una imagen del producto",
    "Diseña un creativo para Meta Ads",
    "Necesito una imagen para mi perfil",
    "generame un flyer con los beneficios",
]


def test_idea_requests_are_text_ideation():
    for msg in _IDEA_ONLY:
        assert is_text_ideation_request(msg) is True, msg


def test_idea_requests_do_not_trigger_image_intent():
    for msg in _IDEA_ONLY:
        assert is_generate_image_intent(msg) is False, msg
        assert should_take_direct_image_path(msg, []) is False, msg
        assert is_image_creation_request(msg, []) is False, msg
        assert is_marketing_creative_intent(msg) is False, msg


def test_explicit_image_requests_still_work():
    for msg in _EXPLICIT_IMAGE:
        assert is_text_ideation_request(msg) is False, msg
        assert is_generate_image_intent(msg) is True, msg
        assert should_take_direct_image_path(msg, []) is True, msg


def test_generate_image_with_idea_in_scene_still_images():
    """«genera una imagen de una idea abstracta» sigue siendo pedido visual."""
    msg = "genera una imagen de una idea abstracta flotando en el cielo"
    assert is_text_ideation_request(msg) is False
    assert is_generate_image_intent(msg) is True
