"""Extrae solo el contenido publicable — sin instrucciones del usuario."""

from __future__ import annotations

import re
from typing import Any

_INSTRUCTION_PREFIX = re.compile(
    r"^(?:"
    r"(?:que\s+)?(?:diga|dice)\s+|"
    r"(?:con\s+el\s+)?texto\s*:?\s*|"
    r"(?:hazme\s+)?(?:una\s+)?publicaci[oó]n\s+(?:en\s+)?(?:facebook|fb|instagram|ig|meta|redes)\s+que\s+diga\s*|"
    r"(?:hazme\s+)?(?:una\s+)?publicaci[oó]n\s+que\s+diga\s*|"
    r"(?:un\s+)?post\s+que\s+diga\s+|"
    r"esto\s*:?\s*"
    r")",
    re.IGNORECASE,
)

_QUOTED = re.compile(r'^["\'](.+)["\']$')

_PUBLISH_VERB = re.compile(
    r"\b(publica(?:r|me|lo|mos|is|dan)?|postea(?:r|me|lo)?|sube(?:r|me|lo)?|"
    r"comparte(?:r|me|lo)?)\b",
    re.I,
)
_PUBLISH_STEM = re.compile(r"\b(?:public\w*|p[uúií]+blic\w*)\b", re.I)
_FACEBOOK_PLATFORM = re.compile(
    r"\b(?:facebook|facebo(?:ok|ok)?|face\s*book|face|fb)\b",
    re.I,
)
_INSTAGRAM_PLATFORM = re.compile(
    r"\b(?:instagram|insta|ig|imtagram|imstagram|intagran|instagran|intagram)\b",
    re.I,
)
_SOCIAL_PLATFORM = re.compile(
    r"\b(?:"
    r"instagram|insta|ig|imtagram|imstagram|intagran|instagran|intagram|"
    r"facebook|facebo(?:ok|ok)?|face\s*book|face|fb|meta|redes"
    r")\b",
    re.I,
)
_PUBLISH_CONFIRM = re.compile(
    r"\b(env[ií]a(?:la|lo|me|r)?|enviar|publica(?:la|lo|me|r)?|publ[ií]calo|dale|adelante|confirmo|"
    r"conf[ií]rma(?:lo|la)?|"
    r"s[ií]\s*(?:env[ií]a|publica)|m[aá]ndala|mandala|hazlo|procede|env[ií]a\s+la\s+imagen|"
    r"enviar\s+publicaci[oó]n|haz(?:me)?\s+la\s+publicaci[oó]n|haz(?:me)?\s+(?:el|la)\s+post)\b",
    re.I,
)
_CAPTION_IS = re.compile(
    r"\b(?:el\s+)?texto\s+(?:para\s+la\s+imagen\s+)?(?:es|ser[aá])\s+(.+)$",
    re.I,
)
_CAPTION_TITLE = re.compile(
    r"\b(?:el\s+)?t[uiíu]tulo\s+(?:ser[aá]|es|ser[eé])\s+(.+)$",
    re.I,
)
_CAPTION_NAMED = re.compile(
    r"\b(?:t[uiíu]tulo|caption|descripci[oó]n)\s*[:=]\s*(.+)$",
    re.I,
)
_CAPTION_MESSAGE_WILL = re.compile(
    r"\b(?:el\s+)?mensaje\s+ser[aá]\s+(.+)$",
    re.I,
)
_CAPTION_WITH_DESCRIPTION = re.compile(
    r"\b(?:con\s+(?:esta|este|la|el|mi)?\s*(?:descripci[oó]n|descricion|texto|mensaje)|"
    r"(?:descripci[oó]n|descricion|texto|mensaje)\s*(?:es|:))\s*(.+)$",
    re.I,
)
_DEICTIC_CAPTION_REF = re.compile(
    r"(?:"
    r"(?:pub|pob)lica(?:la|lo|me|r)?\s+con\s+(?:eso|lo)\s+que\s+(?:te\s+)?(?:di|dije|dec[ií]a|dice|mand[eé]|envi[eé]|ped[ií])|"
    r"usa(?:r|)\s+(?:ese|este|el\s+mismo)\s+(?:texto|caption|descripci[oó]n|descricion|mensaje)|"
    r"lo\s+que\s+(?:te\s+)?(?:di|dije|mand[eé]|ped[ií])|"
    r"(?:eso|lo)\s+que\s+(?:te\s+)?(?:di|dije)"
    r")",
    re.I,
)
_PUBLISH_TRAILING = re.compile(
    r"\s+(?:y\s+)?(?:public[a-záéíóú]*|env[ií]a[a-záéíóú]*|postea[a-záéíóú]*|sube[a-záéíóú]*)\b.*$",
    re.I,
)
_PUBLISH_TRAILING_EXTRA = re.compile(r"\s+con\s+ese\s+texto\s*$", re.I)
_PUBLISH_HELP = re.compile(
    r"\b(ay[uú]da|ay[uú]dame|suger|cr[eé]ame|cr[eé]a|prop[oó]n|propone|"
    r"t[ií]tulo|descripci[oó]n|escr[ií]belo|escribe)\b",
    re.I,
)
_INLINE_CAPTION = re.compile(
    r"\b(?:con\s+el\s+|el\s+)?t[ií]tulo\s+(.+)$|"
    r"\b(?:con\s+la\s+)?descripci[oó]n\s+(.+)$|"
    r"\bque\s+diga\s+(.+)$",
    re.I,
)
_PUBLISH_ONLY = re.compile(
    r"^(?:ced\s+)?public[a-záéíóú]*\s+"
    r"(?:esta\s+)?(?:imagen|foto|esto)?\s*"
    r"(?:en\s+)?(?:mi\s+)?"
    r"(?:instagram|insta|ig|imtagram|imstagram|intagran|instagran|intagram|facebook|fb)?\s*[.!?]*$",
    re.I,
)

_SUSPICIOUS_CAPTION_PATTERNS = (
    re.compile(r"^(sí|si|dale|ok|envía|envia|publica)\s+", re.I),
    re.compile(r"\s+(envía|envia|publica)\s+(la\s+)?publicaci[oó]n", re.I),
    re.compile(r"(envíalo|envialo|mándalo|mandalo|póstéalo|postealo)\s+ya", re.I),
)

_LITERAL_INSTRUCTION_PATTERNS = (
    re.compile(r"^publica\s+(tus?|mis?|el|la|los|las|un|una|esto|esta)\s+", re.I),
    re.compile(r"^postea\s+(tus?|mis?|el|la|los|las|un|una|esto|esta)\s+", re.I),
    re.compile(r"^haz\s+(una?\s+)?publicaci[oó]n", re.I),
    re.compile(r"^crea\s+(un\s+)?post", re.I),
    re.compile(r"^comparte\s+(en|tus?|mis?)\s+", re.I),
)

_UI_LABEL_PATTERNS = (
    re.compile(r"^subir\s+imagen(\s+a\s+ced)?\.?$", re.I),
    re.compile(r"^upload\s+image\.?$", re.I),
    re.compile(r"^enviar\.?$", re.I),
    re.compile(r"^send\.?$", re.I),
    re.compile(r"^cancelar\.?$", re.I),
    re.compile(r"^cancel\.?$", re.I),
    re.compile(r"^cerrar\.?$", re.I),
    re.compile(r"^close\.?$", re.I),
    re.compile(r"^imagen\s+lista\s+para\s+ced\.?$", re.I),
    re.compile(r"^publicar\.?$", re.I),
)

_INSTRUCTION_TO_CED_PATTERNS = (
    re.compile(
        r"^(solo\s+)?(pon|coloca|escribe|describe|explica|expl[ií]came|cuenta|cu[eé]ntame|"
        r"dime|muestra|mu[eé]strame|comparte|comparteme|hazme|haz|dame|env[ií]ame)\b",
        re.I,
    ),
    re.compile(
        r"^(cu[aá]les?|qu[eé]|c[oó]mo|cu[aá]ndo|d[oó]nde|por\s+qu[eé]|para\s+qu[eé])\s+"
        r"(son|es|son\s+las|es\s+el)",
        re.I,
    ),
    re.compile(
        r"\b(t[uú]|tu|tus|tuyas?|tuyos?)\s+"
        r"(caracter[ií]sticas|capacidades|funciones|servicios)\b",
        re.I,
    ),
    re.compile(r"\b(dime|dime\s+tu|dime\s+tus)\b", re.I),
    re.compile(r"^(crea|genera|escribe|redacta|inventa)\s+(un|una|el|la|los|las)\b", re.I),
)

PUBLISH_CONFIRMATION_RULES = """
FLUJO OBLIGATORIO DE PUBLICACIÓN:

NUNCA invoques publicar_facebook ni publicar_instagram sin ANTES haber:
1. Acordado con el usuario el texto EXACTO a publicar.
2. Mostrado al usuario el texto propuesto: "Voy a publicar: [texto]. ¿Confirmo?"
3. Recibido confirmación explícita: "sí", "envía", "publica", "dale", "confirmo", "enviar publicación".

SI EL USUARIO NO CONFIRMÓ EXPLÍCITAMENTE, NO INVOQUES LA TOOL.

NUNCA uses como caption strings genéricos como "Subir imagen", "Enviar", "Publicar" o labels de UI.
"""

PUBLISH_INSTRUCTION_ABSOLUTE_RULES = """
INTERPRETACIÓN DE INSTRUCCIONES DE PUBLICACIÓN — REGLA ABSOLUTA:

Cuando el usuario diga frases tipo:
- "pon las características", "escribe sobre X", "solo pon Y"
- "dime cuáles son tus características", "describe esto", "explica X"

NUNCA tomes esa frase literal como caption. Son INSTRUCCIONES PARA TI.

PROCESO CORRECTO:
1. IDENTIFICAR que es una instrucción dirigida a ti (o una pregunta).
2. GENERAR el contenido apropiado basado en la instrucción.
3. PROPONER: "Voy a publicar lo siguiente: [contenido generado]. ¿Lo confirmo o desea ajustar?"
4. ESPERAR confirmación explícita: "sí", "envía", "dale", "publica".
5. Solo después invocar la tool con el contenido GENERADO como caption.

Si el usuario hace una PREGUNTA ("¿cuáles son tus características?"):
- RESPONDE la pregunta normalmente.
- NO interpretes como caption ni ofrezcas publicar salvo que lo pida explícitamente.

DISTINCIÓN CRÍTICA:
- "publica esto: [texto]" → caption = [texto]
- "publica X" o "pon X" → GENERA contenido sobre X primero
- "¿cuáles son X?" → RESPONDE, NO publiques

EJEMPLO INCORRECTO: Usuario "pon las características del sistema CED" → caption="pon las características..."
EJEMPLO CORRECTO: Genera texto sobre CED → propone → confirma → publica ese texto generado.
"""


def _is_instruction_to_ced(caption: str) -> bool:
    text = (caption or "").strip().lower()
    if not text:
        return False
    for pattern in _INSTRUCTION_TO_CED_PATTERNS:
        if pattern.search(text):
            return True
    return False


def is_instruction_to_ced(text: str) -> bool:
    """True si el texto es una instrucción o pregunta al asistente, no un caption."""
    return _is_instruction_to_ced(text)


def _is_ui_label(caption: str) -> bool:
    text = (caption or "").strip()
    text = re.sub(r"^[^\wáéíóúñ]+", "", text, flags=re.I).strip().lower()
    if not text:
        return True
    for pattern in _UI_LABEL_PATTERNS:
        if pattern.match(text):
            return True
    if len(text) < 10:
        return True
    return False


def requires_publish_confirmation(user_text: str) -> bool:
    return is_publish_confirm(user_text, allow_short_yes=True)


def extract_confirmed_publish_caption(
    transcript: list[Any],
    platform: str = "facebook",
) -> str:
    """Busca el caption acordado en turnos previos del usuario (no el de confirmación)."""
    for row in reversed(transcript or []):
        role = str(getattr(row, "role", None) or (row.get("role") if isinstance(row, dict) else "") or "")
        if role != "user":
            continue
        text = str(getattr(row, "content", None) or (row.get("content") if isinstance(row, dict) else "") or "").strip()
        if not text:
            continue
        explicit_cap = extract_user_caption_for_publish(text)
        if explicit_cap:
            cap = sanitize_publish_caption(explicit_cap)
            is_valid, _ = validate_caption(cap)
            if is_valid:
                return cap
        if is_publish_confirm(text, allow_short_yes=True):
            cap_hint = extract_user_caption_for_publish(text) or extract_publish_body(
                text,
                platform=platform,
            )
            if not cap_hint:
                continue
        body = extract_publish_body(text, platform=platform)
        if body:
            cap = sanitize_publish_caption(body)
            is_valid, _ = validate_caption(cap)
            if is_valid:
                return cap
        if is_publish_help_request(text):
            continue
        if is_vague_publish_instruction(text):
            continue
        cap = extract_caption_from_turn(text, platform)
        cap = sanitize_publish_caption(cap)
        is_valid, _ = validate_caption(cap)
        if is_valid:
            return cap

    for row in reversed(transcript or []):
        role = str(getattr(row, "role", None) or (row.get("role") if isinstance(row, dict) else "") or "")
        if role != "agent":
            continue
        text = str(getattr(row, "content", None) or (row.get("content") if isinstance(row, dict) else "") or "").strip()
        if not text:
            continue
        cap = _extract_agent_proposed_caption(text)
        if cap:
            return cap
    return ""


_AGENT_PROPOSED_CAPTION_PATTERNS = (
    re.compile(
        r'\bel\s+texto\s+(?:ser[aá]|será|es)\s*:?\s*["«“](.+?)["»”]',
        re.I | re.DOTALL,
    ),
    re.compile(
        r'\bel\s+texto\s+(?:ser[aá]|será|es)\s*:?\s*(.+?)(?:\.\s*(?:¿confirma|confirme)|\?\s*$|\.\s*$)',
        re.I | re.DOTALL,
    ),
    re.compile(
        r'\bvoy a publicar(?:\s+lo siguiente)?\s*:?\s*["«“](.+?)["»”]',
        re.I | re.DOTALL,
    ),
    re.compile(
        r'\btexto\s+(?:propuesto|ser[aá])\s*:?\s*["«“](.+?)["»”]',
        re.I | re.DOTALL,
    ),
)


def _extract_agent_proposed_caption(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    for pattern in _AGENT_PROPOSED_CAPTION_PATTERNS:
        match = pattern.search(raw)
        if not match or not match.group(1):
            continue
        cap = sanitize_publish_caption(match.group(1))
        is_valid, _ = validate_caption(cap)
        if is_valid:
            return cap
    return ""



PUBLISH_INTERPRETATION_RULES = """
INTERPRETACIÓN DE INSTRUCCIONES DE PUBLICACIÓN:

Cuando el usuario dice "publica X" o "publica sobre X", NUNCA publiques literalmente
la frase "publica X". En su lugar:

1. INTERPRETA X como el TEMA o TIPO de contenido a publicar.
2. GENERA el contenido apropiado sobre X.
3. PROPÓN al usuario: "Voy a publicar lo siguiente: [contenido generado]. ¿Lo confirmo?"
4. Solo invoca publicar_* tras confirmación explícita del usuario.

EJEMPLO INCORRECTO: caption="Publica tus características en Facebook"
EJEMPLO CORRECTO: genera texto sobre CED → pide confirmación → publica ese texto.

REGLA: el caption SIEMPRE es contenido sustantivo, NUNCA la instrucción de publicación.
"""


def _is_literal_instruction(caption: str) -> bool:
    text = (caption or "").strip().lower()
    if not text:
        return False
    for pattern in _LITERAL_INSTRUCTION_PATTERNS:
        if pattern.match(text):
            return True
    return False


def is_deictic_caption_reference(text: str) -> bool:
    """«publícala con eso que te di» — referencia al caption previo, no el caption."""
    return bool(_DEICTIC_CAPTION_REF.search((text or "").strip()))


def _sanitize_caption_candidate(raw: str) -> str:
    cap = sanitize_publish_caption(raw)
    if validate_caption(cap)[0]:
        return cap
    return ""


def extract_caption_from_history(
    history: list[dict[str, str]] | None,
    *,
    platform: str = "instagram",
) -> str:
    """Recupera el caption acordado desde turnos previos del chat."""
    for row in reversed(history or []):
        if str(row.get("role") or "") != "user":
            continue
        text = str(row.get("content") or "").strip()
        if not text or is_deictic_caption_reference(text):
            continue
        cap = extract_user_caption_for_publish(text)
        if cap:
            cleaned = _sanitize_caption_candidate(cap)
            if cleaned:
                return cleaned
        if is_publish_help_request(text):
            continue
        if is_publish_confirm(text, allow_short_yes=True):
            body = extract_publish_body(text, platform=platform)
            if body:
                cleaned = _sanitize_caption_candidate(body)
                if cleaned:
                    return cleaned
            continue
        body = extract_publish_body(text, platform=platform)
        if body:
            cleaned = _sanitize_caption_candidate(body)
            if cleaned:
                return cleaned
        cap = extract_caption_from_turn(text, platform=platform)
        cleaned = _sanitize_caption_candidate(cap)
        if cleaned:
            return cleaned
    for row in reversed(history or []):
        if str(row.get("role") or "") not in ("model", "assistant"):
            continue
        text = str(row.get("content") or "").strip()
        cap = _extract_agent_proposed_caption(text)
        if cap:
            return cap
    return ""


def extract_initial_publish_caption(text: str, *, platform: str = "instagram") -> str:
    """Caption explícito en el primer mensaje con imagen adjunta."""
    cap = extract_caption_from_turn(text, platform=platform)
    return _sanitize_caption_candidate(cap)


def is_vague_publish_instruction(user_text: str) -> bool:
    """True si el usuario pide publicar un tema, no un caption final."""
    t = (user_text or "").strip()
    if not t:
        return False
    platform = detect_publish_platform(t)
    body = extract_publish_body(t, platform=platform)
    if body:
        cap = sanitize_publish_caption(body)
        is_valid, _ = validate_caption(cap)
        if is_valid:
            return False
    if _is_instruction_to_ced(t):
        return True
    if _is_literal_instruction(t):
        return True
    if _PUBLISH_ONLY.match(t):
        return True
    if not body:
        return True
    is_valid, _ = validate_caption(sanitize_publish_caption(body))
    return not is_valid


def sanitize_publish_caption(raw: str) -> str:
    return strip_publish_instruction((raw or "").strip())


def validate_caption(caption: str) -> tuple[bool, str]:
    """Valida que el caption no parezca historial de conversación."""
    text = sanitize_publish_caption(caption)
    if not text:
        return False, "Caption vacío"
    if _is_instruction_to_ced(text):
        return False, "Caption parece ser una instrucción al asistente, no contenido a publicar"
    if is_deictic_caption_reference(text):
        return False, "Caption parece referirse a un texto previo, no contenido final"
    if _is_ui_label(text):
        return False, "Caption parece ser un label de UI, no contenido"
    if _is_literal_instruction(text):
        return False, "caption es la instrucción literal, no el contenido"
    if _is_instruction_garbage_caption(text):
        return False, "Caption parece instrucción conversacional"
    lowered = text.lower()
    for pattern in _SUSPICIOUS_CAPTION_PATTERNS:
        if pattern.search(lowered):
            return False, "Caption parece contener historial de conversación"
    words = lowered.split()
    if len(words) > 10:
        unique_ratio = len(set(words)) / len(words)
        if unique_ratio < 0.7:
            return False, "Caption tiene mucha repetición"
    return True, "ok"


def strip_publish_instruction(raw: str) -> str:
    """Quita prefijos como 'que diga', 'hazme una publicación que diga'."""
    text = (raw or "").strip(" .,:;-")
    if not text:
        return ""
    for _ in range(4):
        m = _INSTRUCTION_PREFIX.match(text)
        if not m:
            break
        text = text[m.end() :].strip(" .,:;-")
    q = _QUOTED.match(text)
    if q:
        text = q.group(1).strip(" .,:;-")
    return text


def extract_publish_body(user_text: str, platform: str = "facebook") -> str:
    """Extrae cuerpo publicable desde frases naturales de voz."""
    last = (user_text or "").strip()
    if not last:
        return ""
    patterns = (
        r"\bpublica(?:r|me|lo|ar)?\s+(?:esta\s+)?(?:imagen|foto)\s+con\s+(?:esta\s+)?"
        r"(?:descripci[oó]n|descricion|texto)\s+(.+)$",
        r"\b(?:hazme\s+)?(?:una\s+)?publicaci[oó]n\s+(?:en\s+)?"
        r"(?:facebook|fb|instagram|ig|meta|redes(?:\s+sociales)?)\s+que\s+diga\s*:?\s*(.+)$",
        r"\b(?:hazme\s+)?(?:una\s+)?publicaci[oó]n\s+que\s+diga\s*:?\s*(.+)$",
        rf"\bpublica(?:r|me|lo|que|ar)?\s+(?:en\s+)?(?:{platform}|ig|fb|instagram|facebook)\s*[:.]?\s*"
        r"(?:que\s+)?(?:diga|dice|con\s+el\s+texto|esto)?\s*[:.]?\s*(.+)$",
        r"\b(?:sube|postea)(?:r|me|lo)?\s+(?:en\s+)?(?:instagram|ig|facebook|fb)\s*[:.]?\s*"
        r"(?:que\s+)?(?:diga|dice|con\s+el\s+texto|esto)?\s*[:.]?\s*(.+)$",
        r"\b(?:publica|postea)\s*[:.]?\s*(.+)$",
        r"\bque\s+diga\s*:?\s*(.+)$",
    )
    for pat in patterns:
        m = re.search(pat, last, re.I)
        if m and m.group(1):
            body = strip_publish_instruction(m.group(1))
            if body:
                return body
    quoted = re.search(r'["\'](.+?)["\']', last)
    if quoted and quoted.group(1).strip():
        return strip_publish_instruction(quoted.group(1))
    return strip_publish_instruction(last)


def is_explicit_social_publish_request(text: str, *, with_image: bool = False) -> bool:
    """Publicar en red social — distinto de generar creativo o flyer."""
    t = (text or "").strip()
    if not t:
        return False
    from app.domain.ced_product_capabilities import is_capability_catalog_request

    if is_capability_catalog_request(t):
        return False
    has_verb = bool(_PUBLISH_VERB.search(t) or _PUBLISH_STEM.search(t))
    has_platform = bool(_SOCIAL_PLATFORM.search(t) or is_publish_platform_reply(t))
    has_image_ref = bool(re.search(r"\b(imagen|foto|esto|esta)\b", t, re.I))
    if has_verb and (has_platform or has_image_ref):
        return True
    if with_image and has_platform and has_verb:
        return True
    if with_image and has_platform:
        return True
    if with_image and has_verb and has_image_ref:
        return True
    return False


def is_publish_platform_reply(text: str) -> bool:
    """Respuestas cortas al elegir red: «en face», «facebook», «ig»."""
    t = re.sub(r"[^\w\sáéíóúñ]", "", (text or "").strip(), flags=re.I)
    if not t or len(t) > 40:
        return False
    if re.fullmatch(
        r"(?:en\s+)?(?:face(?:book)?|fb|instagram|insta|ig|meta)\.?",
        t,
        re.I,
    ):
        return True
    return bool(_FACEBOOK_PLATFORM.search(t) or _INSTAGRAM_PLATFORM.search(t))


_IMAGE_FOR_PUBLISH = re.compile(
    r"(?:"
    r"^(?:esa|esta)\s+(?:es\s+(?:la\s+)?)?imagen\b(?!\s+(?:de\s+)?(?:referencia|fondo))|"
    r"\b(?:usa|usar|utiliza)\w*\s+(?:esta|esa)\s+imagen\b(?!\s+(?:de\s+)?(?:referencia|fondo))|"
    r"\b(?:para\s+)?publicar\b.*\b(?:esta|esa)\s+imagen\b|"
    r"\b(?:esta|esa)\s+imagen\b.*\b(?:para\s+)?publicar\b|"
    r"\busar\s+para\s+publicar\b|"
    r"\bpublica\s+(?:con\s+)?(?:esta|esa)\s+imagen\b"
    r")",
    re.I,
)


def is_image_for_publish_signal(text: str) -> bool:
    """Usuario señala la imagen adjunta/recién subida como medio a publicar."""
    t = (text or "").strip()
    if not t:
        return False
    return bool(_IMAGE_FOR_PUBLISH.search(t))


def is_social_publish_intent(text: str, *, with_image: bool = False) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    from app.domain.ced_product_capabilities import is_capability_catalog_request

    if is_capability_catalog_request(t):
        return False
    if with_image and is_image_for_publish_signal(t):
        return True
    if is_explicit_social_publish_request(t, with_image=with_image):
        return True
    from app.services.marketing_creative import blocks_publish_intent

    if blocks_publish_intent(t):
        return False
    has_platform = bool(_SOCIAL_PLATFORM.search(t))
    has_image_ref = bool(re.search(r"\b(imagen|foto|esto|esta)\b", t, re.I))
    has_verb = bool(_PUBLISH_VERB.search(t) or _PUBLISH_STEM.search(t))
    if has_verb and (has_platform or has_image_ref):
        return True
    if with_image and has_platform:
        return True
    if with_image and has_verb and has_image_ref:
        return True
    return False


def history_awaits_publish_image(history: list[dict[str, str]] | None) -> bool:
    """True si el asistente pidió recientemente subir imagen para FB/IG."""
    recent = list(history or [])[-8:]
    blob_user = " ".join(
        str(r.get("content") or "")
        for r in recent
        if str(r.get("role") or "") == "user"
    )
    blob_asst = " ".join(
        str(r.get("content") or "")
        for r in recent
        if str(r.get("role") or "") in {"assistant", "model"}
    )
    if not (_SOCIAL_PLATFORM.search(blob_user) or _PUBLISH_VERB.search(blob_user) or _PUBLISH_STEM.search(blob_user)):
        if not (_SOCIAL_PLATFORM.search(blob_asst) and re.search(r"public", blob_asst, re.I)):
            return False
    return bool(
        re.search(
            r"(?:suba|sube|adjunt|env[ií]e|envie|cargue|pegue).{0,40}(?:imagen|foto)|"
            r"(?:imagen|foto).{0,40}(?:para\s+publicar|de\s+la\s+publicaci)|"
            r"cuando\s+(?:tenga|suba|adjunte)\s+la\s+imagen|"
            r"necesito\s+la\s+imagen|"
            r"facebook\s+est[aá]\s+conectado",
            blob_asst,
            re.I,
        )
    )


def detect_publish_platform_explicit(text: str) -> str | None:
    """Devuelve la red solo si el usuario la menciona explícitamente."""
    t = (text or "").strip()
    if not t:
        return None
    if is_publish_platform_reply(t):
        if _INSTAGRAM_PLATFORM.search(t) and not _FACEBOOK_PLATFORM.search(t):
            return "instagram"
        if _FACEBOOK_PLATFORM.search(t) or re.search(r"\bface\b|\bfb\b", t, re.I):
            return "facebook"
    if _FACEBOOK_PLATFORM.search(t):
        return "facebook"
    if _INSTAGRAM_PLATFORM.search(t):
        return "instagram"
    return None


def detect_publish_platform(text: str, *, default: str = "instagram") -> str:
    return detect_publish_platform_explicit(text) or default


def is_publish_confirm(text: str, *, allow_short_yes: bool = False) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if allow_short_yes and re.fullmatch(r"s[ií][\s!.]*", t, re.I):
        return True
    if re.fullmatch(r"s[ií]\s*(?:env[ií]a(?:la|lo)?|publica(?:la|lo)?)[\s!.]*", t, re.I):
        return True
    # «te confirmo» / «sí te confirmo» / «confirmo la publicación»
    if re.search(r"\b(?:te\s+)?confirmo\b", t, re.I):
        return True
    return bool(_PUBLISH_CONFIRM.search(t))


def wants_publish_now(text: str) -> bool:
    t = (text or "").strip()
    if is_publish_confirm(t):
        return True
    return bool(
        re.search(r"\bpublica(?:la|lo|me|r)?\b", t, re.I)
        or re.search(r"\bhaz(?:me)?\s+la\s+publicaci[oó]n\b", t, re.I)
    )


def _is_instruction_garbage_caption(text: str) -> bool:
    t = (text or "").strip()
    if not t or _PUBLISH_ONLY.match(t):
        return True
    if is_deictic_caption_reference(t):
        return True
    if _is_instruction_to_ced(t):
        return True
    if is_publish_confirm(t):
        return True
    if _PUBLISH_STEM.search(t) and (_SOCIAL_PLATFORM.search(t) or re.search(r"\b(imagen|foto)\b", t, re.I)):
        return True
    letters = re.sub(r"[^a-záéíóúñA-ZÁÉÍÓÚÑ]", "", t)
    return len(letters) < 3


def extract_user_caption_for_publish(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    for pattern in (
        _CAPTION_IS,
        _CAPTION_TITLE,
        _CAPTION_NAMED,
        _CAPTION_MESSAGE_WILL,
        _CAPTION_WITH_DESCRIPTION,
    ):
        match = pattern.search(t)
        if not match:
            continue
        body = match.group(1).strip()
        body = _PUBLISH_TRAILING.sub("", body).strip(" .,:;-")
        body = _PUBLISH_TRAILING_EXTRA.sub("", body).strip(" .,:;-")
        if body and not _is_instruction_garbage_caption(body) and not _is_instruction_to_ced(body):
            return body
    return ""


_CAPTION_PLAIN_MAX_CHARS = 280


def _plain_caption_fallback(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    if is_deictic_caption_reference(t):
        return ""
    if is_publish_help_request(t) or wants_publish_now(t) or is_social_publish_intent(t):
        return ""
    if _is_instruction_to_ced(t):
        return ""
    if _is_instruction_garbage_caption(t):
        return ""
    if re.fullmatch(r"s[ií][\s!.]*", t, re.I):
        return ""
    if len(t) > _CAPTION_PLAIN_MAX_CHARS:
        return ""
    words = [w for w in t.split() if w]
    if len(words) < 2 and len(t) < 6:
        return ""
    return t


def extract_caption_from_turn(text: str, platform: str = "instagram") -> str:
    t = (text or "").strip()
    if not t:
        return ""
    cap = extract_user_caption_for_publish(t)
    if cap:
        return cap
    cap = extract_inline_publish_caption(t, platform=platform)
    if cap and not _is_instruction_garbage_caption(cap):
        return cap
    return _plain_caption_fallback(t)


def is_publish_help_request(text: str) -> bool:
    return bool(_PUBLISH_HELP.search((text or "").strip()))


def extract_inline_publish_caption(text: str, platform: str = "instagram") -> str:
    t = (text or "").strip()
    if not t or _PUBLISH_ONLY.match(t) or _is_instruction_garbage_caption(t):
        return ""
    match = _INLINE_CAPTION.search(t)
    if match:
        for group in match.groups():
            if group and group.strip():
                body = strip_publish_instruction(group.strip())
                if body and not _is_instruction_garbage_caption(body):
                    return body
    return ""
