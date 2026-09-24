"""Plantilla maestra de guiones de video — 10 formatos fijos definidos por el usuario.

Config interna, no texto libre en el prompt general: cada formato es un dato
(`ScriptBlueprint`) con los datos que hay que pedir, la estructura literal, el
tono y los extras. El bloque de prompt se genera a partir de esa lista, así que
añadir el formato 11 es añadir una entrada.

Al armar el prompt solo viaja el formato detectado (o el índice de los 10 cuando
el usuario todavía no eligió), para no cargar los tres canales con 10 fichas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Ritmo de habla en Reels: ~150 palabras por minuto.
WORDS_PER_SECOND = 2.5
DEFAULT_DURATION_HINT = "30–45 s"


@dataclass(frozen=True)
class ScriptBlueprint:
    """Un formato de guion: qué pedir, qué estructura seguir y con qué tono."""

    key: str
    number: int
    name: str
    purpose: str
    ask_for: str
    structure: tuple[str, ...]
    tone: str
    extra: str = ""
    patterns: tuple[str, ...] = field(default_factory=tuple)


CED_VIDEO_SCRIPT_FORMATS: tuple[ScriptBlueprint, ...] = (
    ScriptBlueprint(
        key="historia",
        number=1,
        name="Historia",
        purpose="Storytelling que vende sin vender.",
        ask_for="La historia que quiere contar y su nicho.",
        structure=(
            "Gancho emocional",
            "Problema inicial",
            "Punto de quiebre",
            "Solución encontrada",
            "Lección o cambio profundo",
            "CTA natural",
        ),
        tone="Humano, cercano, nada vendedor.",
        extra="5 opciones de hook.",
        patterns=(
            r"historia\s+que\s+vende",
            r"vender?\s+sin\s+vender",
            r"historia\s+personal",
            r"storytelling",
            r"guion\s+(?:de|tipo)\s+historia",
            r"formato\s+historia",
        ),
    ),
    ScriptBlueprint(
        key="que_vendes",
        number=2,
        name="Qué vendes",
        purpose="Presentación directa de su producto o servicio.",
        ask_for=(
            "Qué producto o servicio vende, qué problema le resuelve al cliente y "
            "el precio u oferta si quiere mencionarlo."
        ),
        structure=(
            "Gancho con resultado o transformación",
            "Presentación directa del producto o servicio",
            "Cómo funciona o qué incluye",
            "Beneficio principal para el cliente",
            "CTA claro de compra o contacto",
        ),
        tone="Directo, seguro, enfocado en el beneficio.",
        patterns=(
            r"qu[eé]\s+vend[eo]",
            r"presentar\s+(?:mi|el|un)\s+(?:producto|servicio|oferta)",
            r"guion\s+(?:de|para)\s+vent(?:a|as)",
            r"formato\s+qu[eé]\s+vendes",
        ),
    ),
    ScriptBlueprint(
        key="educativo",
        number=3,
        name="Educativo",
        purpose="Enseña algo útil y práctico a su audiencia.",
        ask_for="El tema y la audiencia a la que le habla.",
        structure=(
            "Hook",
            "Problema común",
            "Explicación sencilla",
            "Consejo práctico",
            "CTA",
        ),
        tone="Claro y natural.",
        extra="5 hooks diferentes.",
        patterns=(r"educativ[oa]", r"ense[nñ]ar\s+algo", r"tutorial"),
    ),
    ScriptBlueprint(
        key="autoridad",
        number=4,
        name="Autoridad",
        purpose="Lo posiciona como referente en su nicho.",
        ask_for="Su experiencia o el resultado que logró, y su nicho.",
        structure=(
            "Gancho con una meta o resultado deseable",
            "Prueba social o experiencia real",
            "1 a 3 tips accionables",
            "Promesa de cambio",
            "CTA",
        ),
        tone="Profesional pero cercano y humano.",
        patterns=(r"autoridad", r"posicionar\w*\s+como\s+referente", r"referente\s+en\s+mi"),
    ),
    ScriptBlueprint(
        key="problema_invisible",
        number=5,
        name="Problema invisible",
        purpose="Muestra un problema que la audiencia no ve.",
        ask_for="Su nicho y el problema invisible que quiere mostrar.",
        structure=(
            "Gancho que haga dudar",
            "Problema invisible",
            "Síntomas o señales",
            "Solución",
            "CTA",
        ),
        tone="Educativo, claro, fácil de entender (no alarmista).",
        patterns=(r"problema\s+invisible", r"problema\s+que\s+no\s+ve"),
    ),
    ScriptBlueprint(
        key="comentario",
        number=6,
        name="Responde dudas o comentarios",
        purpose="Responde una pregunta real de su audiencia.",
        ask_for="El comentario o duda que recibió y su opinión o respuesta.",
        structure=(
            "Reacción al comentario",
            "Señalar el problema o error",
            "Solución práctica",
            "Invitación a dejar más dudas",
        ),
        tone="Claro, útil, cercano.",
        patterns=(
            r"comentario",
            r"duda\s+de\s+(?:mi\s+)?audiencia",
            r"responder\s+una\s+duda",
            r"responder\s+(?:una\s+)?pregunta",
        ),
    ),
    ScriptBlueprint(
        key="mini_serie",
        number=7,
        name="Miniserie",
        purpose="Primer video de una serie que engancha a seguir viendo.",
        ask_for="El tema de la miniserie.",
        structure=(
            "Hook fuerte",
            "Contexto del problema",
            "Por qué decidí crear esta serie",
            "Qué van a aprender en los próximos videos",
            "CTA para seguir la serie",
        ),
        tone="Enganchador, con promesa clara de continuidad.",
        extra="5 opciones de título para la miniserie.",
        patterns=(r"mini\s*-?\s*serie", r"miniserie", r"serie\s+de\s+(?:videos|reels)"),
    ),
    ScriptBlueprint(
        key="entretenimiento",
        number=8,
        name="Entretenimiento",
        purpose="Contenido ligero que conecta y da a conocer su marca.",
        ask_for=(
            "El tema o anécdota graciosa o curiosa de su nicho y el formato deseado "
            "(sketch, reacción, tendencia…)."
        ),
        structure=(
            "Gancho sorpresivo o cómico",
            "Desarrollo con ritmo y giro inesperado",
            "Remate o punchline",
            "Conexión sutil con su marca o nicho",
            "CTA ligero (like, comentario, compartir)",
        ),
        tone="Divertido, con ritmo, sin forzar la venta.",
        patterns=(
            r"entretenimiento",
            r"entretenid[oa]",
            r"gracios[oa]",
            r"c[oó]mic[oa]",
            r"humor",
            r"sketch",
            r"divertid[oa]",
        ),
    ),
    ScriptBlueprint(
        key="demostrativo",
        number=9,
        name="Demostrativo",
        purpose="Muestra un proceso o resultado en acción.",
        ask_for=(
            "Qué producto, servicio o proceso quiere mostrar y el resultado final "
            "que se ve al terminar."
        ),
        structure=(
            "Gancho mostrando el resultado final primero",
            "Planteamiento de qué se va a demostrar",
            "Proceso paso a paso acelerado o resumido",
            "Resultado final confirmado",
            "CTA (cotización, DM, guardar el video)",
        ),
        tone="Visual, dinámico, orientado a resultados.",
        patterns=(
            r"demostrativ[oa]",
            r"demostraci[oó]n",
            r"mostrar\s+(?:el\s+)?proceso",
            r"paso\s+a\s+paso",
            r"antes\s+y\s+despu[eé]s",
        ),
    ),
    ScriptBlueprint(
        key="reflexivo",
        number=10,
        name="Reflexivo",
        purpose="Comparte un aprendizaje o una reflexión personal.",
        ask_for="El tema o aprendizaje que quiere compartir y la experiencia personal detrás.",
        structure=(
            "Gancho con una pregunta o frase que invite a pensar",
            "Contexto breve de la experiencia",
            "La reflexión o aprendizaje central",
            "Cómo esto le puede servir a quien mira",
            "CTA suave (comentar su opinión, guardar, compartir)",
        ),
        tone="Íntimo, honesto, sin apuro.",
        patterns=(r"reflexi(?:v[oa]|[oó]n)", r"aprendizaje\s+personal", r"introspectiv[oa]"),
    ),
)

_BY_KEY = {bp.key: bp for bp in CED_VIDEO_SCRIPT_FORMATS}

BLUEPRINTS_HEADER = "# PLANTILLAS OFICIALES DE GUION"

_HARD_RULES = """
Si el turno pide un guion de video —o LA ESTRUCTURA de uno— manda esta plantilla.
Es la metodología del usuario, no una sugerencia.

Reglas duras:
- Entrega TODAS las secciones, en orden y con su nombre literal. PROHIBIDO omitir,
  fusionar, renombrar o reordenar una sección.
- PROHIBIDO inventar una estructura alternativa (capítulos 1–7, fases, etc.) cuando el
  formato pedido está en esta lista.
- Si el usuario NO dijo qué formato quiere: pregunta cuál de los 10 antes de pedir
  cualquier otro dato, listando el índice (una línea por formato). No pidas los datos
  de un formato que no eligió.
- Con el formato elegido: pide SOLO los datos de ese formato, en un único mensaje
  corto. En el turno siguiente entrega el guion completo.
- Si piden «la estructura» en vez del guion: devuelve la plantilla completa con sus
  secciones y qué va en cada una, más los extras del formato.
- Los extras van SIEMPRE, incluso si piden solo la estructura o aún no dieron el tema:
  en ese caso entrégalos como plantilla con [corchetes] (ej. «Lo que nadie te dice sobre
  [tema]»). PROHIBIDO prometer los títulos o los hooks «cuando me compartas el tema».
- Cuando un formato no tenga extra propio, cierra con 5 hooks (estándar CED de video).
- Tono humano, cercano y natural; nada de sonar vendedor.
- Si pide un CALENDARIO / estructura del mes / N videos por semana usando estos
  formatos: NO es un solo guion ni una publicación. Entrega la grilla del mes.
""".strip()

_CALENDAR_RULES = """
# CALENDARIO DE VIDEOS (no publicar, no pedir imagen)
El usuario quiere la ESTRUCTURA del mes con ESTOS 10 formatos, no un Reel/Story/Carrusel
y no un post en Instagram ahora.

OBLIGATORIO:
- Entrega YA el calendario semana por semana hasta la fecha que dio (si dijo
  «de aquí al 24» y no hay mes, usa el próximo 24).
- Respeta la cadencia (ej. 3 videos/semana). Rota los 10 formatos: no repitas el
  mismo dos veces seguidas; cubre todos al menos una vez si el mes lo permite.
- Cada pieza: día o fecha, formato (número + nombre), tema del nicho que dio,
  gancho de 1 línea, y qué dato haría falta para escribir el guion de ese día.
- El nicho (salón, coach, etc.) basta: no preguntes objetivo ni Reel vs Story.
- PROHIBIDO abrir publicación, pedir imagen o decir «Publicaré en Instagram».
- Un guion completo solo si piden el de UN día concreto.
""".strip()

_CALENDAR_RE = re.compile(
    r"(?is)(?:"
    r"\d+\s+videos?\s+por\s+semana|"
    r"videos?\s+por\s+semana|"
    r"calendario\s+de\s+(?:contenido|videos?)|"
    r"estrut?ura\s+(?:de\s+)?(?:este\s+)?mes|"
    r"de\s+aqu[ií]\s+al\s+\d{1,2}|"
    r"hasta\s+el\s+\d{1,2}"
    r")"
)
_CATALOG_RE = re.compile(
    r"(?is)(?:[ií]ndice\s+de\s+formatos|los\s+10\s+formatos|"
    r"quiero\s+usar\s+esta\s+estrut?ura)"
)


def _duration_rule(seconds: int | None) -> str:
    if seconds:
        words = int(seconds * WORDS_PER_SECOND)
        return (
            f"Duración pedida: {seconds} s → unas {words} palabras habladas en TOTAL.\n"
            "Reparte ese presupuesto entre las secciones proporcionalmente (gancho y "
            "remate cortos, desarrollo un poco más largo) y no te pases: si no cabe, "
            "recorta el desarrollo, nunca elimines una sección."
        )
    return (
        f"Si no indican duración, apunta a {DEFAULT_DURATION_HINT} "
        f"(unas {int(30 * WORDS_PER_SECOND)}–{int(45 * WORDS_PER_SECOND)} palabras) y dilo "
        "en una línea al final. Si piden otra duración (30 s, 40 s, 1 min…), ajusta la "
        "extensión de cada sección proporcionalmente sin quitar secciones."
    )


def format_blueprint(blueprint: ScriptBlueprint) -> str:
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(blueprint.structure, start=1))
    lines = [
        f"## {blueprint.number:02d} — {blueprint.name}: {blueprint.purpose}",
        f"Datos a pedir: {blueprint.ask_for}",
        steps,
        f"Tono: {blueprint.tone}",
    ]
    if blueprint.extra:
        lines.append(f"Extra obligatorio: {blueprint.extra}")
    return "\n".join(lines)


def blueprints_index() -> str:
    rows = "\n".join(
        f"{bp.number:02d} — {bp.name}: {bp.purpose}" for bp in CED_VIDEO_SCRIPT_FORMATS
    )
    return f"## Los 10 formatos\n{rows}"


def listed_script_formats(text: str) -> list[str]:
    """Claves de formato que aparecen en el texto (el índice pega varios)."""
    t = (text or "").strip()
    if not t:
        return []
    found: list[str] = []
    for blueprint in CED_VIDEO_SCRIPT_FORMATS:
        if any(re.search(pattern, t, re.IGNORECASE) for pattern in blueprint.patterns):
            found.append(blueprint.key)
    return found


def is_script_format_catalog(text: str) -> bool:
    """True si pega el índice o nombra 3+ formatos: quiere usarlos todos."""
    t = (text or "").strip()
    if len(t) < 12:
        return False
    if _CATALOG_RE.search(t):
        return True
    return len(listed_script_formats(t)) >= 3


def is_video_content_calendar(text: str) -> bool:
    """Plan del mes / N videos por semana — no un guion suelto ni una publicación."""
    t = (text or "").strip()
    if len(t) < 8:
        return False
    if is_script_format_catalog(t):
        return True
    if not _CALENDAR_RE.search(t):
        return False
    return bool(_VIDEO_WORD.search(t) or _STRUCTURE_WORD.search(t) or _SCRIPT_WORD.search(t))


def compact_format_rows() -> str:
    lines: list[str] = []
    for bp in CED_VIDEO_SCRIPT_FORMATS:
        steps = " → ".join(bp.structure)
        lines.append(f"{bp.number:02d} — {bp.name}: {steps}")
    return "\n".join(lines)


def script_blueprints_block(
    kind: str | None = None,
    *,
    seconds: int | None = None,
    calendar: bool = False,
) -> str:
    """Bloque de prompt: reglas + el formato pedido (o el índice / calendario)."""
    parts = [BLUEPRINTS_HEADER, _HARD_RULES, _duration_rule(seconds)]
    if calendar:
        parts.append(_CALENDAR_RULES)
        parts.append("## Los 10 formatos (rota estos, no inventes otros)\n" + compact_format_rows())
        return "\n\n".join(parts)
    blueprint = _BY_KEY.get(kind or "")
    if blueprint:
        parts.append(format_blueprint(blueprint))
        parts.append(
            "Si el usuario cambia de formato, usa el que pida de la lista de 10 "
            "(pídele el número o el nombre)."
        )
    else:
        parts.append(blueprints_index())
        parts.append(
            "Pregunta cuál de los 10 quiere y, con esa respuesta, pide solo los datos "
            "de ese formato. Si pide el calendario del mes o pega el índice completo, "
            "NO preguntes: entrega la grilla con los 10."
        )
    return "\n\n".join(parts)


# Plantilla completa (los 10 formatos detallados) — referencia y pruebas.
CED_SCRIPT_BLUEPRINTS = "\n\n".join(
    [
        BLUEPRINTS_HEADER,
        _HARD_RULES,
        _duration_rule(None),
        blueprints_index(),
        *(format_blueprint(bp) for bp in CED_VIDEO_SCRIPT_FORMATS),
    ]
)

_SCRIPT_WORD = re.compile(r"(?is)\b(?:gui[oó]n(?:es)?|script|storytelling)\b")
_STRUCTURE_WORD = re.compile(
    r"(?is)\b(?:estrutura|estructura|plantilla|formato|esqueleto)\b"
)
_VIDEO_WORD = re.compile(
    r"(?is)\b(?:reels?|v[ií]deo|tiktok|instagram|ig|serie|contenido|capitul\w*)\b"
)
_DURATION_RE = re.compile(
    r"(?is)(?:(\d{1,3})\s*(?:s|seg|segs|segundos?)\b"
    r"|(\d{1,2})\s*(?:m|min|mins|minutos?)\b"
    r"|\b(un|medio)\s+minuto\b"
    r"|\bminuto\s+y\s+medio\b)"
)


def detect_script_blueprint(text: str) -> str | None:
    """Devuelve la clave del formato pedido, si el turno menciona uno.

    Si pega el índice o nombra varios, no elige el primero: es calendario.
    """
    t = (text or "").strip()
    if not t:
        return None
    if is_script_format_catalog(t) or is_video_content_calendar(t):
        return None
    for blueprint in CED_VIDEO_SCRIPT_FORMATS:
        for pattern in blueprint.patterns:
            if re.search(pattern, t, re.IGNORECASE):
                return blueprint.key
    return None


def detect_script_duration(text: str) -> int | None:
    """Duración pedida, en segundos (30s, 40 segundos, 1 min, minuto y medio…)."""
    match = _DURATION_RE.search(text or "")
    if not match:
        return None
    raw = match.group(0).lower()
    if "minuto y medio" in raw:
        return 90
    secs, mins, word = match.group(1), match.group(2), match.group(3)
    if secs:
        value = int(secs)
        return value if 5 <= value <= 600 else None
    if mins:
        value = int(mins)
        return value * 60 if 1 <= value <= 10 else None
    if word:
        return 30 if word.lower() == "medio" else 60
    return None


def wants_script_blueprints(text: str) -> bool:
    """True si el turno pide un guion, la estructura o el calendario del mes."""
    t = (text or "").strip()
    if len(t) < 6:
        return False
    if is_video_content_calendar(t) or is_script_format_catalog(t):
        return True
    kind = detect_script_blueprint(t)
    asks_script = bool(_SCRIPT_WORD.search(t))
    asks_structure = bool(_STRUCTURE_WORD.search(t))
    if kind and (asks_script or asks_structure or _VIDEO_WORD.search(t)):
        return True
    if asks_script and _VIDEO_WORD.search(t):
        return True
    return asks_script and asks_structure


def with_script_blueprints_if_needed(system: str, user_text: str) -> str:
    """Antepone la plantilla del formato pedido cuando el turno pide un guion.

    Va al principio a propósito: el system se recorta por el final (`_trim_system`,
    14k), así que un bloque añadido al final se perdería en la ruta con tools.
    """
    if not wants_script_blueprints(user_text):
        return system
    base = (system or "").strip()
    if BLUEPRINTS_HEADER in base:
        return base
    calendar = is_video_content_calendar(user_text) or is_script_format_catalog(user_text)
    block = script_blueprints_block(
        None if calendar else detect_script_blueprint(user_text),
        seconds=detect_script_duration(user_text),
        calendar=calendar,
    )
    if not base:
        return block
    return f"{block}\n\n{base}"
