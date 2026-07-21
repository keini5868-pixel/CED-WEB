"""Long from-scratch image briefs must take direct path (no silent stall)."""

from __future__ import annotations

from app.services.chat_image_generation import (
    reply_is_image_wait_filler,
    should_take_direct_image_path,
)


DETAILED = (
    "Genera una imagen profesional con fondo degradado azul oscuro a negro, "
    "elemento visual de un cerebro iluminado en el centro, tipografía sans-serif "
    "bold blanca en la parte superior que diga 'Tu mundo interior', subtítulo "
    "en tipografía light que diga 'luchas y pensamientos', estilo cinematic, "
    "alto contraste, composición centrada, calidad 4k, sin texto inventado extra "
    "y con márgenes limpios alrededor del sujeto principal para redes sociales. "
    "Añade partículas de luz suaves, profundidad de campo, y un marco sutil "
    "con acentos cian. Incluye una franja inferior con tipografía monoespaciada "
    "pequeña que diga 'asistente virtual sofisticado' alineada a la izquierda."
)


def test_long_detailed_brief_takes_direct_path():
    assert len(DETAILED) > 500
    assert should_take_direct_image_path(DETAILED, []) is True


def test_wait_filler_detected():
    assert reply_is_image_wait_filler("Un momento, señor, estoy generando la imagen.")
    assert reply_is_image_wait_filler("Dame un segundo")
    assert not reply_is_image_wait_filler("Listo. Aquí está tu imagen generada.")
