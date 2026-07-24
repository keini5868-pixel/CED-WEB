"""Banco de frases de relleno (filler) para voz — tono formal CED."""

from __future__ import annotations

import random
from typing import Final

FILLER_MIN_HOLD_S: Final[float] = 1.6

_GENERAL_FILLERS: tuple[str, ...] = (
    "Déjeme pensar bien eso, señor.",
    "Un momento, señor, lo analizo.",
    "Permítame un instante, señor.",
    "Deme un segundo, señor, ya le respondo.",
    "Voy a reflexionar eso con cuidado, señor.",
)

_WEB_SEARCH_FILLERS: tuple[str, ...] = (
    "Un momento, voy a investigar eso para usted, señor.",
    "Consulto la información más reciente, señor.",
    "Déjeme buscar eso en internet, señor.",
    "Reviso fuentes actuales, señor, un instante.",
    "Investigo eso ahora mismo, señor.",
)

_MODULE_FILLERS: dict[str, tuple[str, ...]] = {
    "finance": (
        "Reviso sus finanzas, señor.",
        "Consulto sus registros financieros, señor.",
        "Un momento, analizo sus movimientos, señor.",
        "Permítame revisar sus finanzas, señor.",
        "Verifico su balance ahora, señor.",
    ),
    "camera": (
        "Active la cámara, señor, un instante.",
        "Analizo lo que veo, señor.",
        "Un momento, reviso con visión, señor.",
        "Permítame observar eso, señor.",
        "Consulto la imagen ahora, señor.",
    ),
    "map": (
        "Abro el mapa, señor.",
        "Preparo la ruta, señor, un momento.",
        "Consulto navegación, señor.",
        "Un instante, organizo el trayecto, señor.",
        "Verifico la ruta ahora, señor.",
    ),
    "publish": (
        "Preparo la publicación, señor.",
        "Un momento, organizo el post, señor.",
        "Reviso el contenido para publicar, señor.",
        "Permítame preparar la red social, señor.",
        "Armo la publicación ahora, señor.",
    ),
    "prospection": (
        "Activo prospección, señor.",
        "Reviso comentarios y oportunidades, señor.",
        "Un momento, analizo prospectos, señor.",
        "Consulto las interacciones, señor.",
        "Verifico clientes potenciales, señor.",
    ),
    "image_gen": (
        "Genero la imagen, señor.",
        "Un momento, creo el diseño, señor.",
        "Trabajo en su imagen ahora, señor.",
        "Permítame generar eso, señor.",
        "Preparo la imagen, señor.",
    ),
    "pdf": (
        "Preparo el documento, señor.",
        "Genero el PDF ahora, señor.",
        "Un momento, armo el reporte, señor.",
        "Permítame crear el documento, señor.",
        "Trabajo en su PDF, señor.",
    ),
    "environment": (
        "Consulto el clima, señor.",
        "Reviso condiciones ambientales, señor.",
        "Un momento, verifico el tiempo, señor.",
        "Consulto datos del ambiente, señor.",
        "Verifico el clima actual, señor.",
    ),
    "web_search": _WEB_SEARCH_FILLERS,
    "memory": (
        "Registro eso en memoria, señor.",
        "Un momento, guardo la información, señor.",
        "Permítame anotar eso, señor.",
        "Actualizo su memoria, señor.",
        "Guardo el dato ahora, señor.",
    ),
}

_last_phrase: dict[str, str] = {}
_rotate_idx: dict[str, int] = {}


def pick_voice_filler(
    category: str,
    *,
    call_id: str,
    module: str | None = None,
) -> str:
    """Elige filler rotando para no repetir la misma frase seguida."""
    if category == "module" and module:
        pool = _MODULE_FILLERS.get(module) or _GENERAL_FILLERS
        slot = f"{call_id}:module:{module}"
    elif category == "web_search":
        pool = _WEB_SEARCH_FILLERS
        slot = f"{call_id}:web_search"
    else:
        pool = _GENERAL_FILLERS
        slot = f"{call_id}:general"

    if not pool:
        return "Un momento, señor."

    idx = _rotate_idx.get(slot, 0)
    phrase = pool[idx % len(pool)]
    last = _last_phrase.get(slot)
    if phrase == last and len(pool) > 1:
        phrase = pool[(idx + 1) % len(pool)]
    _rotate_idx[slot] = idx + 1
    _last_phrase[slot] = phrase
    return phrase


def reset_filler_rotation(call_id: str) -> None:
    """Limpia estado de rotación al cerrar llamada (tests)."""
    prefix = f"{call_id}:"
    for store in (_last_phrase, _rotate_idx):
        for key in list(store):
            if key.startswith(prefix):
                del store[key]
