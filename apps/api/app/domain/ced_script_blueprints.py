"""Plantillas oficiales de guion CED — estructuras exactas definidas por el usuario.

El playbook de marketing resume estas estructuras; este bloque es la versión
canónica y literal: cuando el turno pide uno de los 6 tipos de guion, el modelo
debe seguir estos pasos con su nombre y sin saltarse ninguno (el clásico olvido
era «Por qué decidí crear esta serie» en la mini serie).
"""

from __future__ import annotations

import re

CED_SCRIPT_BLUEPRINTS = """
# PLANTILLAS OFICIALES DE GUION (mandan sobre cualquier otra estructura)

Si el turno pide un guion —o LA ESTRUCTURA de un guion— de alguno de estos 6 tipos,
usa la plantilla correspondiente TAL CUAL. Es la metodología del usuario, no una sugerencia.

Reglas duras:
- Entrega TODAS las secciones, en orden y con su nombre literal. PROHIBIDO omitir,
  fusionar, renombrar o reordenar una sección.
- PROHIBIDO inventar una estructura alternativa (capítulos 1–7, fases, etc.) cuando el
  tipo pedido está en esta lista.
- Si piden «la estructura» en vez del guion: devuelve la plantilla completa con sus
  secciones y qué va en cada una, más los extras (hooks o títulos) del tipo.
- Extras: tipos 1 y 2 → 5 opciones de hook. Tipo 6 → 5 opciones de título de la serie.
  En los demás añade 5 hooks al final (estándar CED de video).
- Tono humano, cercano y natural; nada de sonar vendedor.
- Si falta la materia prima (historia, nicho, tema, audiencia, comentario): UNA sola
  pregunta puntual y en el siguiente turno el entregable completo.

## 1) Historia que vende (vender sin vender)
Materia prima: historia del usuario + nicho. Formato: Instagram Reels.
1. Gancho emocional
2. Problema inicial
3. Punto de quiebre
4. Solución encontrada
5. Lección o cambio profundo
6. CTA natural
Extra: 5 opciones de hook. Debe sonar humano y cercano, no demasiado vendedor.

## 2) Educativo
Materia prima: tema + audiencia.
1. Hook
2. Problema común
3. Explicación sencilla
4. Consejo práctico
5. CTA
Extra: 5 hooks distintos para elegir. Claro, fácil de entender, lenguaje natural.

## 3) Autoridad
Materia prima: experiencia o resultado real + nicho.
1. Gancho con una meta o resultado deseable
2. Prueba social o experiencia real
3. 1 a 3 tips accionables
4. Promesa de cambio
5. CTA
Profesional, pero cercano y humano.

## 4) Responder una duda o comentario
Materia prima: el comentario o duda + el punto de vista del usuario.
1. Reacción al comentario
2. Señalar el problema o error
3. Solución práctica
4. Invitación a dejar más dudas
Claro, útil y con tono cercano.

## 5) Problema invisible
Materia prima: nicho + el problema que la audiencia no está viendo.
1. Gancho que haga dudar
2. Problema invisible
3. Síntomas o señales
4. Solución
5. CTA
Tono educativo, claro y fácil de entender (no alarmista).

## 6) Mini serie — primer capítulo
Materia prima: tema de la mini serie. Este primer video presenta la serie y genera
ganas de ver los siguientes.
1. Hook fuerte
2. Contexto del problema
3. Por qué decidí crear esta serie
4. Qué van a aprender en los próximos videos
5. CTA para seguir la serie
Extra: 5 opciones de título para la mini serie.
La sección 3 («Por qué decidí crear esta serie») es la que más se olvida: es OBLIGATORIA,
va con ese nombre y cuenta el motivo personal del usuario para hacer la serie.
""".strip()

_SCRIPT_KINDS: tuple[tuple[str, str], ...] = (
    ("mini_serie", r"mini\s*-?\s*serie|miniserie"),
    ("historia", r"historia\s+que\s+vende|vender?\s+sin\s+vender|historia\s+personal"),
    ("problema_invisible", r"problema\s+invisible"),
    ("autoridad", r"autoridad"),
    ("comentario", r"comentario|duda\s+de\s+(?:mi\s+)?audiencia|responder\s+una\s+duda"),
    ("educativo", r"educativ[oa]"),
)

_SCRIPT_WORD = re.compile(r"(?is)\b(?:gui[oó]n(?:es)?|script|storytelling)\b")
_STRUCTURE_WORD = re.compile(r"(?is)\b(?:estructura|plantilla|formato|esqueleto)\b")
_VIDEO_WORD = re.compile(
    r"(?is)\b(?:reels?|v[ií]deo|tiktok|instagram|ig|serie|contenido|capitul\w*)\b"
)


def detect_script_blueprint(text: str) -> str | None:
    """Devuelve el tipo de plantilla pedido, si el turno menciona uno."""
    t = (text or "").strip()
    if not t:
        return None
    for kind, pattern in _SCRIPT_KINDS:
        if re.search(pattern, t, re.IGNORECASE):
            return kind
    return None


def wants_script_blueprints(text: str) -> bool:
    """True si el turno pide un guion o la estructura de un guion para redes."""
    t = (text or "").strip()
    if len(t) < 6:
        return False
    kind = detect_script_blueprint(t)
    asks_script = bool(_SCRIPT_WORD.search(t))
    asks_structure = bool(_STRUCTURE_WORD.search(t))
    if kind and (asks_script or asks_structure or _VIDEO_WORD.search(t)):
        return True
    if asks_script and _VIDEO_WORD.search(t):
        return True
    return asks_script and asks_structure


def with_script_blueprints_if_needed(system: str, user_text: str) -> str:
    """Antepone las plantillas oficiales cuando el turno pide un guion.

    Van al principio a propósito: el system se recorta por el final (`_trim_system`,
    14k), así que un bloque añadido al final se perdería en la ruta con tools.
    """
    if not wants_script_blueprints(user_text):
        return system
    base = (system or "").strip()
    if not base:
        return CED_SCRIPT_BLUEPRINTS
    if "PLANTILLAS OFICIALES DE GUION" in base:
        return base
    return f"{CED_SCRIPT_BLUEPRINTS}\n\n{base}"
