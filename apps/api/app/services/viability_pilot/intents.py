"""Intent estricto de viabilidad — evita colisiones con imagen, prospección, search, avanzado.

Triggers requieren verbo de análisis de mercado/viabilidad + objeto producto/servicio/negocio.
NO matchea: generar flyer/imagen, publicar, prospectar, «busca en internet», modo avanzado.
"""

from __future__ import annotations

import re
import unicodedata

# Verbos / pedidos de análisis de mercado (requieren uno).
_VIABILITY_VERB = re.compile(
    r"(?:"
    r"analiza(?:r)?\s+(?:la\s+)?viabilidad"
    r"|viabilidad\s+(?:de|del|de\s+mi|de\s+este|de\s+esta|del\s+producto|del\s+servicio|del\s+negocio)"
    r"|an[aá]lisis\s+de\s+viabilidad"
    r"|(?:qu[eé]\s+tan|qu[eé]\s+tan\s+)viable"
    r"|es\s+viable\s+(?:mi|este|esta|el|la)"
    r"|probabilidad\s+de\s+[eé]xito"
    r"|estudio\s+de\s+mercado\s+(?:de|para|del)"
    r"|an[aá]lisis\s+de\s+mercado\s+(?:de|para|del|mi)"
    r"|competitive\s+landscape"
    r"|market\s+viability"
    r"|product\s+viability"
    r")",
    re.IGNORECASE,
)

# Objeto / contexto de oferta (refuerzo; el verbo ya acota bastante).
_OFFERING_HINT = re.compile(
    r"(?:"
    r"producto|servicio|negocio|emprendimiento|startup|flyer|folleto|"
    r"oferta|idea\s+de\s+negocio|tienda|marca|app|restaurante|cafeter[ií]a|"
    r"consultor[ií]a|curso|membres[ií]a"
    r")",
    re.IGNORECASE,
)

# Exclusiones duras — si matchean, NO es viabilidad (otras tools).
_HARD_EXCLUDE = re.compile(
    r"(?:"
    r"genera(?:r|me)?\s+(?:una?\s+)?(?:imagen|foto|flyer|dise[nñ]o|logo|banner)"
    r"|crea(?:r|me)?\s+(?:una?\s+)?(?:imagen|foto|flyer|dise[nñ]o)"
    r"|edita(?:r)?\s+(?:la\s+)?(?:imagen|foto|flyer)"
    r"|publica(?:r)?\s+(?:en|esto|eso|a)"
    r"|prospect(?:ar|os?|ci[oó]n)"
    r"|activa(?:r)?\s+(?:el\s+)?modo\s+avanzado"
    r"|modo\s+avanzado"
    r"|busca(?:r)?\s+(?:en\s+)?(?:internet|la\s+web|google)"
    r"|noticias\s+(?:de|hoy|sobre)"
    r"|reproduce|pon(?:me)?\s+(?:un\s+)?(?:video|canci[oó]n)"
    r")",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    raw = (text or "").strip().lower()
    raw = unicodedata.normalize("NFKD", raw)
    return "".join(ch for ch in raw if not unicodedata.combining(ch))


def is_viability_module_intent(text: str) -> bool:
    """True solo con pedido explícito de viabilidad/mercado — no genérico «analiza»."""
    if not (text or "").strip():
        return False
    norm = _normalize(text)
    if _HARD_EXCLUDE.search(norm):
        return False
    if not _VIABILITY_VERB.search(norm):
        return False
    # Si el verbo ya incluye «viabilidad» / «estudio de mercado», basta.
    if re.search(
        r"viabilidad|estudio\s+de\s+mercado|analisis\s+de\s+mercado|"
        r"probabilidad\s+de\s+exito|market\s+viability|product\s+viability|"
        r"competitive\s+landscape",
        norm,
    ):
        return True
    # «es viable mi…» / «qué tan viable» necesitan hint de oferta.
    return bool(_OFFERING_HINT.search(norm))
