"""Catálogo factual de capacidades de producto CED (chat / modo avanzado).

Fuente de verdad para cuando el usuario pide «qué puedes hacer» o una lista
numerada de habilidades. NO inventar módulos (p. ej. WhatsApp) que no existan.
"""

from __future__ import annotations

import re

_CAPABILITY_CATALOG = re.compile(
    r"\b("
    r"habilidades|herramientas|capacidades|funciones|"
    r"qu[eé]\s+(?:puedes|puede|sabe(?:s)?)\s+(?:hacer|hacer\s+ced)|"
    r"todas\s+las\s+(?:habilidades|herramientas|capacidades)|"
    r"lista\s+(?:donde|de)\s+(?:especifique|especificar|capacidades|habilidades|herramientas)|"
    r"sistema\s+ced"
    r")\b",
    re.I,
)
_ENUM_OR_LIST_HINT = re.compile(
    r"\b("
    r"lista|enumera|enumeraci[oó]n|n[uú]mero\s+(?:uno|dos|tres|\d+)|"
    r"por\s+ejemplo\s+n[uú]mero|as[ií]\s+sucesivamente|"
    r"y\s+as[ií]\s+sucesivamente|una\s+por\s+una"
    r")\b",
    re.I,
)

# Lista numerada — solo capacidades reales del producto.
CED_CAPABILITY_CATALOG_BODY = """1. Chat de texto conversacional
2. Modo avanzado (Claude) — análisis profundo de negocio, marketing y estrategia
3. Asistente de voz (piloto nativo Retell / Jarvis)
4. Publicación en Facebook e Instagram (Meta, con confirmación)
5. Prospección — detección de leads en comentarios de redes
6. Lectura de comentarios en Facebook/Instagram
7. Generación de imágenes con IA
8. Generación y descarga de PDF
9. Búsqueda web en tiempo real
10. Finanzas personales — consultar y registrar movimientos
11. Cámara y visión — describir o buscar lo visible
12. Mapa y navegación / modo conducir
13. YouTube — buscar y reproducir en el panel
14. Clima y ambiente (temperatura, aire, etc.)
15. Memoria de conversación y contexto de sesión
16. Modo Creador (solo administración del sistema, cuando aplica)"""

CED_CAPABILITY_CATALOG_REPLY = f"""Aquí tiene las habilidades y herramientas reales del sistema CED, señor:

{CED_CAPABILITY_CATALOG_BODY}

Si quiere, detallo alguna en concreto. Si prefiere exportar esta lista, diga si desea un PDF resumen breve o completo."""

CED_CAPABILITY_CATALOG_SYSTEM_RULE = f"""
LISTA DE CAPACIDADES DE CED (OBLIGATORIO):
Si el usuario pide una lista de habilidades, herramientas, capacidades o «qué puede hacer CED»:
- Responde SOLO con capacidades REALES del producto (usa esta lista o un subconjunto fiel).
- PROHIBIDO inventar módulos que no existan (p. ej. WhatsApp, soporte multiusuario genérico inventado, etc.).
- NO dispares publicación en redes, PDF ni imagen solo porque el usuario las mencione como ejemplo en la lista.

Capacidades reales:
{CED_CAPABILITY_CATALOG_BODY}
""".strip()


def is_capability_catalog_request(text: str) -> bool:
    """True si pide enumerar qué sabe hacer CED (no ejecutar una tool concreta)."""
    t = (text or "").strip()
    if len(t) < 24:
        return False
    catalog = bool(_CAPABILITY_CATALOG.search(t))
    enum_hint = bool(_ENUM_OR_LIST_HINT.search(t))
    if catalog and enum_hint:
        return True
    # «qué puedes hacer / habilidades del sistema» sin enumeración explícita
    if re.search(
        r"\b(qu[eé]\s+(?:puedes|puede|sabe(?:s)?)\s+hacer|"
        r"cu[aá]les\s+son\s+(?:tus|sus)\s+(?:habilidades|herramientas|capacidades)|"
        r"todas\s+las\s+(?:habilidades|herramientas)\b)",
        t,
        re.I,
    ):
        return True
    return False


def try_capability_catalog_reply(text: str) -> str | None:
    if not is_capability_catalog_request(text):
        return None
    return CED_CAPABILITY_CATALOG_REPLY
