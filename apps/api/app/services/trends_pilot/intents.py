"""Intent estricto de tendencias de industria — evita colisiones con VIABLE y otras tools."""

from __future__ import annotations

import re
import unicodedata

_TRENDS_VERB = re.compile(
    r"(?:"
    r"tendencias?\s+(?:de|del|en|para|sobre)"
    r"|qu[eé]\s+est[aá]\s+trending"
    r"|trending\s+(?:en|de|para)"
    r"|outlook\s+(?:a|de|para|del)?"
    r"|predicci[oó]n(?:es)?\s+a\s+\d+\s+meses"
    r"|hacia\s+d[oó]nde\s+va\s+(?:el\s+)?mercado"
    r"|necesidades\s+emergentes"
    r"|oportunidades\s+(?:en|de|del)\s+(?:mi\s+)?(?:rubro|industria|nicho)"
    r"|industry\s+trends?"
    r"|market\s+trends?"
    r")",
    re.IGNORECASE,
)

_HARD_EXCLUDE = re.compile(
    r"(?:"
    r"analiza(?:r)?\s+(?:la\s+)?viabilidad"
    r"|viabilidad\s+(?:de|del)"
    r"|probabilidad\s+de\s+[eé]xito"
    r"|genera(?:r|me)?\s+(?:una?\s+)?(?:imagen|foto|flyer)"
    r"|publica(?:r)?\s+(?:en|esto)"
    r"|prospect(?:ar|os?|ci[oó]n)"
    r"|activa(?:r)?\s+(?:el\s+)?modo\s+avanzado"
    r"|busca(?:r)?\s+(?:en\s+)?(?:internet|la\s+web)"
    r")",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    raw = (text or "").strip().lower()
    raw = unicodedata.normalize("NFKD", raw)
    return "".join(ch for ch in raw if not unicodedata.combining(ch))


def is_trends_module_intent(text: str) -> bool:
    if not (text or "").strip():
        return False
    norm = _normalize(text)
    if _HARD_EXCLUDE.search(norm):
        return False
    return bool(_TRENDS_VERB.search(norm))
