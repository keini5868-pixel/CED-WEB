"""Detección directa de intents en chat de texto (sin depender del LLM)."""

from __future__ import annotations

import re

# Incluye «Genérame» / «Créame» (acento en la raíz; típico de teclado móvil).
_CREATE_VERBS = (
    r"(?:gen[eé]r(?:a(?:r|me|mos|s|is|n|do)?|ame|áme)|"
    r"cr[eé](?:a(?:r|me|mos|s|is|n|do)?|ame|áme)|"
    r"cr[eé]ame|gener[aá]me|gen[eé]rame|"
    r"haz(?:me|nos|lo|la|es|emos|er|go)?|hacer(?:me|lo)?|"
    r"dise[nñ]a(?:r|me|mos|s|is|n|do)?|"
    r"dibuja(?:r|me|mos|s)?|pinta(?:r|me|mos|s)?|"
    r"dame|hazme|"
    r"generate|create|make|draw)"
)
_IMAGE_NOUN = (
    r"(?:imagen|foto|picture|illustration|ilustraci[oó]n|dise[nñ]o|arte|artwork|"
    r"gr[aá]fico|creativo|logo|banner|flyer|portada|image|photo|drawing)"
)

_NON_IMAGE_OBJECT = (
    r"(?:informaci[oó]n|an[aá]lisis|resumen|explicaci[oó]n|estrategia|"
    r"plan|lista|datos?|texto|copy|contenido|idea|concepto|prompt)"
)
_ARTICLE = r"(?:una?|un|la|el|las|los|an?)"

_IMAGE_PATTERNS = (
    re.compile(rf"\b{_CREATE_VERBS}\s+(?:{_ARTICLE}\s+)?{_IMAGE_NOUN}\b", re.I),
    re.compile(rf"\b{_CREATE_VERBS}\s+(?:me\s+)?(?:{_ARTICLE}\s+)?{_IMAGE_NOUN}\b", re.I),
    re.compile(rf"\bquiero\s+(?:que\s+)?{_CREATE_VERBS}\s+(?:{_ARTICLE}\s+)?{_IMAGE_NOUN}\b", re.I),
    re.compile(rf"\bquiero\s+(?:{_ARTICLE}\s+)?{_IMAGE_NOUN}\b", re.I),
    re.compile(rf"\bnecesito\s+(?:{_ARTICLE}\s+)?{_IMAGE_NOUN}\b", re.I),
    re.compile(rf"\bpuedes\s+{_CREATE_VERBS}\s+(?:{_ARTICLE}\s+)?{_IMAGE_NOUN}\b", re.I),
    re.compile(rf"\bcan\s+you\s+{_CREATE_VERBS}\s+(?:an?\s+)?{_IMAGE_NOUN}\b", re.I),
    # Verbo cerca del sustantivo, salvo «dame/haz la información del diseño».
    re.compile(
        rf"\b{_CREATE_VERBS}\b(?!.{{0,40}}\b{_NON_IMAGE_OBJECT}\b).{{0,48}}\b{_IMAGE_NOUN}\b",
        re.I,
    ),
    re.compile(rf"\b{_IMAGE_NOUN}\b.{{0,48}}\b{_CREATE_VERBS}\b", re.I),
)

# Pedido EXPLÍCITO de generar el activo visual (gana sobre ideación de texto).
_EXPLICIT_IMAGE_CREATE = re.compile(
    rf"\b{_CREATE_VERBS}\s+(?:una?\s+|un\s+|la\s+|el\s+|an?\s+)?"
    rf"{_IMAGE_NOUN}\b",
    re.I,
)

# «Necesito una foto, pero antes acordemos…» — no es generate_image.
_IMAGE_PREPRODUCTION = re.compile(
    r"(?is)"
    r"(?:"
    r"before\s+(?:we\s+)?(?:even\s+)?(?:creat|generat|mak|draw|design)|"
    r"antes\s+(?:de\s+)?(?:crear|generar|hacer|dise[nñ]ar|generarla|crearla)|"
    r"need\s+before\s+(?:creat|generat)|"
    r"necesit[oa]\s+(?:antes|primero)\s+(?:de\s+)?(?:crear|generar|acord)|"
    r"(?:let'?s|vamos\s+a)\s+(?:agree|acordar|ponernos\s+de\s+acuerdo)|"
    r"\bagree\s+(?:to|on|first)\b|"
    r"acord(?:emos|ar)\b|"
    r"pong(?:a|á)monos\s+de\s+acuerdo|"
    r"de\s+acuerdo\s+(?:en|para)\s+(?:hacer|crear)|"
    r"primero\s+(?:hay\s+que\s+)?(?:acord|decidir|hablar|ponernos)|"
    r"first\s+(?:we\s+)?(?:need\s+to\s+)?(?:agree|decide|discuss|align)|"
    r"don'?t\s+(?:creat|generat|make)\w*\s+(?:it\s+)?(?:yet|now)|"
    r"no\s+(?:la\s+|lo\s+)?(?:generes|crees|hagas|generar)\s+(?:todav[ií]a|a[uú]n)"
    r")"
)

_VISUAL_CONTEXT = re.compile(
    r"(?i)\b(?:imagen|foto|photo|picture|image|instagram|flyer|creativo|post)\b"
)

_SOFT_NEED_PHOTO = re.compile(
    r"(?i)\b(?:necesito|quiero|i\s+need|i\s+want)\s+"
    r"(?:(?:una?|an?|the|la|el)\s+)?(?:imagen|foto|photo|picture|image)\b"
)

_PHOTO_FOR_CHANNEL = re.compile(
    r"(?i)\b(?:imagen|foto|photo|picture|image)\b.{0,80}\b"
    r"(?:para|for|de)\s+(?:(?:el|la|mi|su|the|sek'?s?|ced'?s?)\s+)*"
    r"(?:instagram|insta|\big\b|facebook|\bfb\b|tiktok|perfil|profile|feed|"
    r"stories|story|redes)\b"
)

# Entregable pedido = idea/concepto/copy/prompt/texto (NO archivo de imagen).
_TEXT_DELIVERABLE = (
    r"(?:idea|ideas|concepto|conceptos|copy|copies|guion(?:es)?|gui[oó]n(?:es)?|"
    r"texto|textos|descripci[oó]n(?:es)?|caption|eslogan|slogan|"
    r"titular(?:es)?|headline|hook|gancho|prompt|prompts|script|scripts|"
    r"contenido|contenidos|pitch|gancho\s+de\s+venta)"
)

_TEXT_IDEATION = re.compile(
    r"(?is)"
    r"(?:"
    # dame/sugiere/necesito + idea|concepto|copy|prompt|guion|descripción…
    r"\b(?:dame|danos|necesito|quiero|propon(?:me|e|ga)?|sugi[eé]r\w*|recomiend\w*|"
    r"ay[uú]dame\s+(?:con|a)|escribe(?:me)?|redact\w*|piensa(?:me)?|"
    r"busca(?:me)?|pide(?:me)?)\s+"
    r"(?:(?:una?|unas?|algunas?|varios?|el|la|los|las|mi|tu)\s+)?"
    rf"{_TEXT_DELIVERABLE}\b"
    r"|"
    # genera/crea/haz + idea|concepto|copy|prompt (objeto ≠ imagen)
    r"\b(?:gener(?:a|ar|ame|áme)|cre(?:a|ar|ame|áme)|cr[eé]ame|gener[aá]me|"
    r"haz(?:me)?|dise[nñ]a(?:r|me)?)\s+"
    r"(?:(?:una?|unas?|el|la)\s+)?"
    rf"{_TEXT_DELIVERABLE}\b"
    r"|"
    # «idea/concepto de imagen|creativo|flyer|contenido» = concepto, no PNG
    r"\b(?:idea|ideas|concepto|conceptos|prompt|prompts)\s+(?:de|para)\s+"
    r"(?:(?:una?|un|el|la|los|las|mi|tu)\s+)?"
    r"(?:imagen|foto|picture|dise[nñ]o|arte|gr[aá]fico|creativo|logo|banner|"
    r"flyer|portada|image|photo|drawing|copy|post|contenido|campa[nñ]a|"
    r"anuncio|reel|video|publicaci[oó]n|vender|venta|promoci[oó]n)\b"
    r"|"
    r"\bconcepto\s+creativo\b"
    r"|"
    r"\bqu[eé]\s+(?:idea|concepto|copy|prompt)\b"
    r"|"
    r"\bideas?\s+(?:de|para)\s+(?:copy|contenido|prompt)\b"
    r"|"
    r"\b(?:prompt|prompts)\s+(?:para|de)\s+(?:vender|venta|promocion\w*|midjourney|"
    r"chatgpt|gemini|otra\s+ia|ia|ai)\b"
    r"|"
    r"\bcopy\s+(?:del|de\s+el|para\s+(?:el|la|mi|un))\s+"
    r"(?:creativo|flyer|banner|post|anuncio)\b"
    r")",
)

_CREATE_IDEA_OBJECT = re.compile(
    rf"\b{_CREATE_VERBS}\s+(?:una?\s+|unas?\s+|el\s+|la\s+)?"
    rf"(?:idea|ideas|concepto|conceptos|copy|texto|guion|gui[oó]n|"
    rf"descripci[oó]n|caption|prompt|prompts|contenido|script)\b",
    re.I,
)

# Hablar DE una imagen (adjunta, screenshot, queja) ≠ pedir generar una.
_IMAGE_META_TALK = re.compile(
    r"(?is)\b(?:"
    r"esta\s+imagen|esa\s+imagen|la\s+imagen\s+adjunta|imagen\s+adjunta|"
    r"no\s+se\s+adjunt[oó]|adjunt(?:a|e|ó|o)\s+(?:la\s+)?imagen|"
    r"en\s+(?:esta|la|esa)\s+imagen|"
    r"se\s+nota\s+(?:en\s+)?(?:esta|la|esa)\s+imagen|"
    r"me\s+gener[oó]\s+(?:una\s+)?imagen|"
    r"gener[oó]\s+(?:una\s+)?imagen\s+(?:y|cuando|sin|aunque)"
    r")\b"
)


def is_image_preproduction_talk(text: str) -> bool:
    """True si habla de una foto/post pero aún quiere acordar el concepto.

    No es un pedido de generar PNG. Ej.: «necesito una foto para Instagram,
    pero antes acordemos algo impactante».
    """
    t = (text or "").strip()
    if not t:
        return False
    if _IMAGE_PREPRODUCTION.search(t) and _VISUAL_CONTEXT.search(t):
        return True
    if _EXPLICIT_IMAGE_CREATE.search(t):
        return False
    if _SOFT_NEED_PHOTO.search(t) and _PHOTO_FOR_CHANNEL.search(t):
        return True
    return False


def is_text_ideation_request(text: str) -> bool:
    """True si el usuario pide idea/concepto/copy/texto — NO generar imagen.

    Ej.: «dame una idea de creativo», «sugiéreme un concepto», «escribe un copy».
    Si también pide explícitamente generar la imagen («genera una imagen de…»),
    esto devuelve False para no bloquear el path visual.
    """
    t = (text or "").strip()
    if not t:
        return False
    if is_image_preproduction_talk(t):
        return True
    if not _TEXT_IDEATION.search(t):
        return False
    # «genera una imagen…» explícito gana, salvo que el objeto del verbo sea la idea.
    if _EXPLICIT_IMAGE_CREATE.search(t) and not _CREATE_IDEA_OBJECT.search(t):
        return False
    return True


def mentions_pdf(text: str) -> bool:
    return bool(re.search(r"\bpdf\b", (text or "").strip(), re.I))


def is_image_meta_talk(text: str) -> bool:
    """True si habla de una imagen existente/adjunta, no pide generar una."""
    t = (text or "").strip()
    if not t:
        return False
    if _EXPLICIT_IMAGE_CREATE.search(t):
        return False
    return bool(_IMAGE_META_TALK.search(t))


_VISUAL_DESIGN_EXPLORATION = re.compile(
    r"(?is)\b("
    r"dame\s+(?:\d+\s+)?(?:unos?\s+|algunos?\s+)?ejemplos?"
    r"|(?:mu[eé]strame|ens[eé][nñ]ame)\s+(?:unos?\s+)?(?:ejemplos?|opciones?|variantes?|alternativas?)"
    r"|qu[eé]\s+opciones?\s+hay"
    r"|(?:c[oó]mo\s+se\s+ver[ií]a|y\s+si\s+(?:le\s+)?(?:ponemos|usamos|cambiamos|le\s+ponemos))"
    r"|qu[eé]\s+tal\s+si\s+(?:le\s+)?(?:ponemos|cambiamos|usamos)"
    r"|alternativas?\s+(?:para|de)\s+(?:esa|esta|el|la|ese|ese)\s+"
    r"(?:imagen|dise[nñ]o|flyer|creativo|banner|logo|visual)"
    r"|variantes?\s+(?:para|de|del?)\s+(?:esa|esta|el|la|mismo|misma)?\s*"
    r"(?:imagen|dise[nñ]o|concepto|flyer|creativo|banner)?"
    r"|explora(?:r|mos)?\s+(?:opciones|variantes|ideas)\s+(?:visual|de\s+dise[nñ]o)"
    r"|sin\s+generar(?:la)?\s+(?:todav[ií]a|a[uú]n|la\s+imagen)?"
    r"|antes\s+de\s+(?:generar|renderizar|crear\s+la\s+imagen)"
    r"|(?:describe|descr[ií]beme)\s+(?:c[oó]mo\s+)?(?:se\s+ver[ií]a|quedar[ií]a)"
    r"|ejemplos?\s+(?:de|para|sobre)\s+(?:(?:esa|esta|la|el|misma)\s+)*"
    r"(?:imagen|dise[nñ]o|flyer|creativo|banner|logo|mismo\s+dise[nñ]o)"
    r")\b",
    re.I,
)


def is_visual_design_exploration(
    text: str,
    history: list[dict[str, str]] | None = None,
) -> bool:
    """Exploración visual en TEXTO (ejemplos/variantes) — estilo ChatGPT, sin render.

    El usuario sigue conectado al mismo diseño pero pide ideas u opciones antes
    de generar otra imagen.
    """
    t = (text or "").strip()
    if not t or is_pdf_intent(t):
        return False
    if _EXPLICIT_IMAGE_CREATE.search(t):
        return False
    if not _VISUAL_DESIGN_EXPLORATION.search(t):
        return False
    if history_has_active_image_thread(history):
        return True
    if user_requests_prior_reference(t):
        return True
    if re.search(
        r"(?i)\b(?:imagen|foto|flyer|creativo|dise[nñ]o|banner|logo|visual|creativo)\b",
        t,
    ):
        return True
    return False


def is_generate_image_intent(text: str) -> bool:
    t = text.strip()
    if len(t) < 8:
        return False
    # Pedido real de PDF gana; mención casual de "PDF" en una lista no bloquea imagen
    # ni la dispara (is_pdf_intent ya no es solo mentions_pdf).
    if is_pdf_intent(t):
        return False
    if is_image_preproduction_talk(t):
        return False
    # Ideas/copys/conceptos en texto — no alucinar una imagen.
    if is_text_ideation_request(t):
        return False
    if is_image_meta_talk(t):
        return False
    return any(p.search(t) for p in _IMAGE_PATTERNS)


_IMAGE_PROMPT_PATTERNS = (
    re.compile(
        rf"(?:\b(?:me\s+)?(?:puedes\s+)?{_CREATE_VERBS}\s+(?:una?\s+)?{_IMAGE_NOUN}\s+"
        rf"(?:de|con|para|que\s+)?\s*[:.]?\s*(.+))$",
        re.I,
    ),
    re.compile(rf"\b{_IMAGE_NOUN}\s+de\s+(.+)$", re.I),
    re.compile(
        rf"\bquiero\s+(?:que\s+)?{_CREATE_VERBS}\s+(?:una?\s+)?{_IMAGE_NOUN}\s+(?:de|con|para|que\s+)?\s*[:.]?\s*(.+)$",
        re.I,
    ),
    re.compile(
        rf"\bnecesito\s+(?:una?\s+)?{_IMAGE_NOUN}\s+(?:de|con|para|que\s+)?\s*[:.]?\s*(.+)$",
        re.I,
    ),
    re.compile(
        rf"\bpuedes\s+{_CREATE_VERBS}\s+(?:una?\s+)?{_IMAGE_NOUN}\s+(?:de|con|para|que\s+)?\s*[:.]?\s*(.+)$",
        re.I,
    ),
)

_PDF_PATTERNS = (
    re.compile(r"\bpdf\b", re.I),
    re.compile(
        r"\b(genera|generar|gener[aá]me|gen[eé]rame|crea|crear|cr[eé]ame|exporta|exportar|convierte|convertir|"
        r"guarda|guárdame|haz(me)?|dame|pon|pásalo|pasalo)\s+"
        r"(?:.{0,48}?\s+)?(?:en\s+)?(?:un(?:a)?\s+)?pdf\b",
        re.I,
    ),
    re.compile(
        r"\b(?:esto|lo|el\s+plan|la\s+estrategia|ese\s+plan)\s+(?:en\s+)?(?:un(?:a)?\s+)?pdf\b",
        re.I,
    ),
    re.compile(r"\bpdf\s+(?:de|con|sobre|que\s+diga)\b", re.I),
    re.compile(r"\b(?:en|como)\s+(?:un(?:a)?\s+)?pdf\b", re.I),
)

_PDF_THIS_REF = re.compile(
    r"\b("
    r"esto|eso|lo|la\s+informaci[oó]n|esa\s+informaci[oó]n|con\s+eso|"
    r"lo\s+anterior|el\s+plan|la\s+estrategia|ese\s+plan|el\s+documento|"
    r"aqu[ií]\s+(?:presentado|mostrado)"
    r")\b",
    re.I,
)

_PDF_NAMED_TOPIC = re.compile(
    r"\b(?:sobre|acerca\s+de|de(?:l)?|con)\s+([A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9][\wÁÉÍÓÚÜÑáéíóúüñ\- ]{1,60})",
    re.I,
)


def _pdf_has_named_topic(user_text: str, content: str) -> bool:
    """True si el usuario nombró un tema concreto (no solo «esto/eso»)."""
    t = (user_text or "").strip()
    c = (content or "").strip()

    def _is_anaphora_label(label: str) -> bool:
        s = (label or "").strip()
        if not s:
            return True
        if _PDF_THIS_REF.search(s):
            return True
        return bool(re.fullmatch(r"(?:esto|eso|lo|la)", s, re.I))

    if c and len(c) >= 3 and not _is_anaphora_label(c):
        return True
    m = _PDF_NAMED_TOPIC.search(t)
    if m and not _is_anaphora_label(m.group(1)):
        return True
    return False


_PRIOR_REFERENCE = re.compile(
    r"\b("
    r"igual\s+a\s+(?:la\s+)?(?:que\s+)?(?:te\s+)?(?:pas[eé]|sub[ií]|mand[eé]|envi[eé])"
    r"|igual\s+a\s+(?:la\s+)?(?:imagen|foto|flyer|creativo|referencia)"
    r"|(?:la|el)\s+(?:misma|mismo)\s+(?:imagen|foto|flyer|creativo|dise[nñ]o|referencia)"
    r"|(?:mism[oa]s?\s+)(?:precios?|nombre|dise[nñ]o|estilo|textos?)"
    r"|(?:imagen|foto|flyer|creativo)\s+(?:de\s+)?referencia"
    r"|(?:que|la\s+que)\s+(?:te\s+)?(?:pas[eé]|sub[ií]|mand[eé]|envi[eé]|compart[ií])"
    r"|(?:usa|utiliza)\w*\s+(?:esa|esta|la)\s+(?:imagen|foto|referencia)"
    r"|basad[oa]\s+en\s+(?:la\s+)?(?:imagen|foto|referencia)"
    r")\b",
    re.I,
)

# Pedidos explícitos de variación/edición sobre una imagen ya presente en el hilo.
_REFERENCE_EDIT_OR_VARIATION = re.compile(
    r"\b("
    r"variaci[oó]n(?:es)?"
    r"|variar"
    r"|edita(?:r|ci[oó]n)?"
    r"|modifica(?:r)?"
    r"|retoca(?:r)?"
    r"|inspirad[oa]\s+en"
    r"|basad[oa]\s+en\s+(?:esta|esa|la)"
    r"|haz(?:me)?\s+una\s+variaci[oó]n"
    r"|cambia\s+(?:esta|esa|la)\s+(?:imagen|foto|flyer|dise[nñ]o)"
    r"|(?:en|con)\s+(?:esta|esa)\s+(?:misma\s+)?(?:imagen|foto|flyer)"
    r"|as[ií]\s+como\s+(?:esta|esa)"
    r"|con\s+(?:esta|esa)\s+misma"
    r"|mism[oa]s?\s+caracter[ií]sticas?"
    r"|(?:pon|pone|ponga|agr[eé]g[aá]|a[nñ]ade|coloca|incluye)\w*"
    r"|mant[eé]n(?:me)?\s+(?:l[ao]s?\s+)?(?:precios?|textos?|lista|dise[nñ]o)"
    r"|conserva\s+(?:l[ao]s?\s+)?(?:precios?|textos?|lista)"
    r"|(?:en|sobre|en\s+la)\s+(?:imagen|foto|flyer|creativo|banner|dise[nñ]o)\b.*"
    r"(?:que\s+(?:diga|ponga|aparezca|lea|salga)|pon(?:le|ga|me)?\s+(?:un\s+)?texto)"
    r"|que\s+(?:diga|ponga|aparezca|lea|salga)\s+"
    r"(?:(?:en|sobre)\s+)?(?:la\s+)?(?:imagen|foto|flyer|banner|cartel|creativo|post)\b"
    r"|cambia\s+(?:el\s+)?(?:fondo|dise[nñ]o|estilo)"
    r")\b",
    re.I,
)

_REAL_PUBLISH_PLATFORM = re.compile(
    r"\b(?:facebook|instagram|face\b|fb\b|ig\b)\b",
    re.I,
)
_REAL_PUBLISH_VERB = re.compile(
    r"\b(?:publica(?:r|me|lo|mos|is|dan)?|postea(?:r|me|lo)?)\b",
    re.I,
)
# Solo comandos reales de publicar — no «publica contenido» dentro de una lista de features.
_EXPLICIT_PUBLISH_COMMAND = re.compile(
    r"(?is)"
    r"(?:"
    r"\b(?:publica(?:r|me|lo)?|postea(?:r|me|lo)?)\s+"
    r"(?:esto|esta|esa|la\s+imagen|la\s+foto)?\s*"
    r"(?:en\s+)?(?:facebook|instagram|face\b|fb\b|ig\b)\b"
    r"|"
    r"\b(?:publica(?:r|me|lo)?|postea(?:r|me|lo)?)\s+en\s+"
    r"(?:facebook|instagram|face\b|fb\b|ig\b)\b"
    r"|"
    r"^\s*(?:perfecto[,.]?\s+|ok[,.]?\s+|dale[,.]?\s+)?"
    r"(?:publica|postea|sube)\b.{0,80}\b(?:facebook|instagram|face\b|fb\b|ig\b)\b"
    r")"
)


_SCRIPT_NARRATIVE = re.compile(
    r"(?is)\b(?:"
    r"gui[oó]n(?:es)?|guion(?:es)?|escena|acto|plano|narraci[oó]n|rodaje|"
    r"contin[uú]a(?:r)?\s+(?:el\s+)?gui|despu[eé]s\s+de\s+ese\s+punto|"
    r"en\s+esa\s+parte|en\s+este\s+punto\s+del\s+gui|"
    r"le\s+digo\s+a\s+(?:ced|el\s+personaje|el\s+asistente|la\s+c[aá]mara)|"
    r"aparece\s+(?:ced|el\s+personaje)|"
    r"que\s+(?:ced\s+)?aparezca\b"
    r")\b"
)


def is_script_narrative_request(text: str) -> bool:
    """True si el usuario describe escena/guion — no pedir generar imagen."""
    t = (text or "").strip()
    if not t:
        return False
    if _EXPLICIT_IMAGE_CREATE.search(t) or _VISUAL_CONTEXT.search(t):
        return False
    if _SCRIPT_NARRATIVE.search(t):
        return True
    from app.services.deliverable_replies import is_deliverable_request

    if is_deliverable_request(t) and not _EXPLICIT_IMAGE_CREATE.search(t):
        return bool(re.search(rf"\b{_TEXT_DELIVERABLE}\b", t, re.I))
    return False


def user_requests_prior_reference(text: str) -> bool:
    return bool(_PRIOR_REFERENCE.search((text or "").strip()))


def wants_image_reference_edit(text: str) -> bool:
    """True si el usuario pide variar/editar/inspirarse en una imagen de referencia."""
    t = (text or "").strip()
    if not t or is_script_narrative_request(t):
        return False
    if user_requests_prior_reference(t):
        return True
    return bool(_REFERENCE_EDIT_OR_VARIATION.search(t))


def is_explicit_publish_to_social(text: str) -> bool:
    """True solo ante «publica en Facebook/Instagram» real.

    No dispara por viñetas tipo «publicar_instagram — publica contenido en redes»
    dentro de un brief de imagen o lista de capacidades.
    """
    t = (text or "").strip()
    if not t:
        return False
    if not _EXPLICIT_PUBLISH_COMMAND.search(t):
        return False
    # Si el mensaje es generar imagen, el comando de publicar debe ir al inicio.
    if is_generate_image_intent(t):
        head = t[:160]
        return bool(_EXPLICIT_PUBLISH_COMMAND.search(head))
    return True


def is_attachment_image_edit_request(text: str) -> bool:
    """Pedido de editar/variar la imagen adjunta (no publicar ni solo analizar)."""
    t = (text or "").strip()
    if not t or len(t) < 6:
        return False
    if is_explicit_publish_to_social(t):
        return False
    if wants_image_reference_edit(t):
        return True
    # «hazme una imagen…» + deíctico / cambio visual sobre el adjunto.
    # NO usar `\btexto\b` solo: dispara en «Chat de texto» / listas de capacidades.
    if is_generate_image_intent(t) and (
        re.search(r"\b(?:esta|esa|la)\s+(?:imagen|foto|flyer)\b", t, re.I)
        or re.search(r"\b(?:misma|mismo|as[ií]|igual)\b", t, re.I)
        or re.search(
            r"\b(?:pon|agrega|cambia|que\s+diga|lobo|cuadro|"
            r"(?:con\s+el\s+)?texto\s+(?:que|de|en)|agrega(?:r)?\s+texto)\b",
            t,
            re.I,
        )
    ):
        return True
    return False


def is_creative_artifact_intent(text: str) -> bool:
    """Pedido claro de generar imagen o PDF — gana sobre módulos con palabras trampa.

    Evita colisiones del tipo: «genera una imagen con la frase 'el tiempo va a
    pasar'» (disparaba clima por «tiempo»), o «hazme un PDF que diga … cita /
    correo …» (calendario/Gmail). Usar en chat y voz antes de enrutar a
    environment/finance.
    """
    t = (text or "").strip()
    if len(t) < 8:
        return False
    return is_pdf_intent(t) or is_generate_image_intent(t)


def parse_generate_image_prompt(text: str) -> str | None:
    t = text.strip()
    if not is_generate_image_intent(t):
        return None
    for pattern in _IMAGE_PROMPT_PATTERNS:
        match = pattern.search(t)
        body = (match.group(1) if match else "") or ""
        body = body.strip().strip("\"'")
        if len(body) >= 3:
            return body
    if len(t) >= 12:
        return t
    return None


def is_anaphoric_image_subject(subject: str) -> bool:
    """True si el sujeto del pedido es «esa idea / esa visión» sin escena concreta."""
    t = (subject or "").strip()
    if not t:
        return True
    return bool(_ANAPHORIC_IMAGE_SUBJECT.match(t))


def is_vague_image_subject(subject: str) -> bool:
    """True si el sujeto no describe una escena concreta (deícticos, meta, «ese ejemplo»)."""
    t = (subject or "").strip()
    if not t:
        return True
    if is_anaphoric_image_subject(t):
        return True
    if _VAGUE_IMAGE_META_TAIL.search(t):
        core = _VAGUE_IMAGE_META_TAIL.sub("", t).strip()
        if len(core) < 45 or is_anaphoric_image_subject(core):
            return True
    if len(t) < 55 and re.search(
        r"\b(?:ese|esa|este|esta|eso|lo\s+mismo|ejemplo|as[ií])\b",
        t,
        re.I,
    ):
        return True
    return False


def last_user_visual_context(
    history: list[dict[str, str]] | None,
) -> str | None:
    """Último mensaje del usuario sobre el tema visual (no comando de generar imagen)."""
    for row in reversed(history or []):
        role = str(row.get("role") or "").lower()
        if role not in {"user", "customer"}:
            continue
        content = (row.get("content") or "").strip()
        if not content or is_generate_image_intent(content):
            continue
        if len(content) >= 12:
            return content[:900]
    return None


def last_assistant_visual_description(
    history: list[dict[str, str]] | None,
) -> str | None:
    """Última respuesta del asistente que describe una escena visual concreta."""
    for row in reversed(history or []):
        role = str(row.get("role") or "").lower()
        if role not in {"assistant", "model", "agent"}:
            continue
        content = (row.get("content") or "").strip()
        if not content or len(content) < 40:
            continue
        if _ASSISTANT_VISUAL_SKIP.search(content[:160]):
            continue
        if re.search(
            r"(?is)\baqu[ií]\s+est[aá]\s+(?:tu|su|la)\s+imagen",
            content,
        ) and len(content) < 220:
            continue
        if _ASSISTANT_VISUAL_MARKERS.search(content) or len(content) >= 100:
            return content[:2000]
    return None


def resolve_anaphoric_image_prompt(
    text: str,
    history: list[dict[str, str]] | None,
) -> str | None:
    """Resuelve «ese ejemplo / esa idea» desde el hilo reciente de conversación."""
    t = (text or "").strip()
    parsed = parse_generate_image_prompt(t) or t
    if not is_vague_image_subject(parsed):
        return None

    prior = last_concrete_image_user_prompt(history)
    if prior:
        from app.services.gemini_images import strip_image_generation_instruction

        stripped = strip_image_generation_instruction(prior).strip()
        return stripped or prior

    concept = last_assistant_image_concept(history)
    user_ctx = last_user_visual_context(history)
    assistant_desc = last_assistant_visual_description(history)

    parts: list[str] = []
    if user_ctx:
        parts.append(f"Escena pedida por el usuario: {user_ctx}")
    if assistant_desc:
        parts.append(f"Descripción visual a plasmar: {assistant_desc}")
    elif concept:
        parts.append(concept)

    if parts:
        return "\n\n".join(parts)[:3800]

    blob = " ".join(
        (row.get("content") or "").strip()
        for row in (history or [])[-6:]
        if (row.get("content") or "").strip()
    ).strip()
    if len(blob) >= 40:
        return (
            "Genera una imagen fotorrealista basada en esta conversación reciente: "
            f"{blob[:2500]}"
        )
    return None


def last_concrete_image_user_prompt(
    history: list[dict[str, str]] | None,
) -> str | None:
    """Último pedido de imagen del usuario con escena usable (no anáfora)."""
    for row in reversed(history or []):
        role = str(row.get("role") or "").lower()
        if role not in {"user", "customer"}:
            continue
        content = (row.get("content") or "").strip()
        if not content or not is_generate_image_intent(content):
            continue
        parsed = parse_generate_image_prompt(content)
        if parsed and not is_anaphoric_image_subject(parsed):
            return content
        if not is_anaphoric_image_subject(content) and len(content) >= 20:
            return content
    return None


def last_assistant_image_concept(
    history: list[dict[str, str]] | None,
) -> str | None:
    """Concepto visual propuesto por el asistente (sin haber generado aún)."""
    for row in reversed(history or []):
        role = str(row.get("role") or "").lower()
        if role not in {"assistant", "model", "agent"}:
            continue
        content = (row.get("content") or "").strip()
        if not content:
            continue
        if not _PENDING_IMAGE_ASSISTANT.search(content):
            continue
        # Preferir bloque tras «Concepto» / descripción sustancial.
        m = re.search(
            r"(?is)(?:Concepto\s*:\s*|visi[oó]n[^:\n]*:\s*)(.+?)(?:\n\s*\n|¿|$)",
            content,
        )
        if m and len(m.group(1).strip()) >= 40:
            return m.group(1).strip()[:2000]
        if len(content) >= 80:
            return content[:2000]
    return None


_FOLLOWUP_IMAGE_CONTEXT = re.compile(
    r"\b(genera(?:r|me|nos|do)?|crea(?:r|me|nos|do)?|imagen|foto|dise[nñ]o|"
    r"creativo|ilustraci[oó]n|face(?:book)?|instagram|publicar|banner|flyer|"
    r"referencia|precio|dise[nñ]o|igual|mismo|otra\s+vez|de\s+nuevo)\b",
    re.I,
)
_FOLLOWUP_SKIP = re.compile(
    r"^(?:ok|gracias|s[ií]|no|vale|perfecto|listo|env[ií]a|publica|dale|hola|buenas)\b",
    re.I,
)
# El mensaje ACTUAL (no el historial) debe traer una señal real de edición/continuación
# visual — de lo contrario cualquier mensaje casual dentro de las 8 líneas siguientes a
# una imagen ya generada se interpretaba como "seguir con la imagen" (bug: chat normal
# generaba imagen con cualquier mensaje tras el primer pedido de imagen en la conversación).
_FOLLOWUP_EDIT_SIGNAL = re.compile(
    r"\b("
    r"hazl[oa]s?|c[aá]mbial[oa]|ajust[aá]l[oa]|ponle|qu[ií]tale|agr[eé]gale|mejor[aá]l[oa]|"
    r"otra\s+versi[oó]n|otra\s+variaci[oó]n|otra\s+vez|de\s+nuevo|una\s+m[aá]s|"
    r"m[aá]s\s+(?:grande|peque[nñ]|oscur|clar|colorid|realist|simple|detall)|"
    r"en\s+otro\s+color|otro\s+color|diferente\s+color|otro\s+estilo|otro\s+fondo|"
    r"con\s+(?:otro|un)\s+(?:fondo|estilo)|as[ií]\s+pero|en\s+vez\s+de|"
    r"cambia(?:le)?\s+(?:el|la|los|las)|quita(?:le)?\s+(?:el|la|los|las)|"
    r"agrega(?:le)?\s+(?:el|la|los|las|un|una)|"
    r"ahora\s+(?:con|sin)|pero\s+(?:con|sin)|"
    r"mant[eé]n(?:me|iendo|gas|ga)?\s+(?:l[ao]s?\s+)?textos?|"
    r"conserv(?:a|ando)\s+(?:l[ao]s?\s+)?textos?|"
    r"quiero\s+que\s+mantengas|"
    r"con\s+(?:l[ao]s?\s+)?textos?|"
    r"integr(?:a|ados?)\s+(?:l[ao]s?\s+)?textos?"
    r")\b",
    re.I,
)
_IMAGE_THREAD_USER = re.compile(
    r"(?:"
    r"\b(?:gen[eé]ra(?:r|me|nos|do)?|cr[eé]a(?:r|me|nos|do)?|haz(?:me|nos|lo|la)?|dise[nñ]a(?:r|me|mos|s|is|n|do)?)"
    r"\s+(?:una?\s+)?(?:imagen|foto|creativo|flyer|logo|banner|portada|dise[nñ]o)\b"
    r"|"
    r"\b(?:una?\s+)?imagen\s+que\s+(?:tenga|muestre|diga|lleve|con)\b"
    r"|"
    r"\blogo\s+oficial\b"
    r"|"
    r"\bel\s+meta\s+de\s+(?:una?\s+)?imagen\b"
    r")",
    re.I,
)
_IMAGE_THREAD_ASSISTANT = re.compile(
    r"(?:Descargar imagen|Creativo\s+[—\-]|imagen generada|"
    r"aqu[ií]\s+est[aá]\s+(?:tu|su|la)?\s*(?:imagen|creativo)|"
    r"imagen\s+editada|"
    r"plasmada\s+en\s+la\s+imagen|junto\s+a\s+los\s+logos|"
    r"generando\s+su\s+imagen|"
    r"\*\*Qu[eé]\s+es\*\*|Detalle visible|Observaciones\s+[—\-]|"
    r"antes\s+de\s+generarlo|quieres\s+ajustar|Concepto:)",
    re.I,
)
_PENDING_IMAGE_USER = re.compile(
    r"(?is)\b(?:imagen|foto|flyer|creativo|banner|logo|portada)\b"
)
_PENDING_IMAGE_ASSISTANT = re.compile(
    r"(?is)(?:plasmada\s+en\s+la\s+imagen|junto\s+a\s+los\s+logos|"
    r"frase\s+debe|generando\s+su\s+imagen|"
    r"antes\s+de\s+generarlo|quieres\s+ajustar|"
    r"visi[oó]n\s+del|Concepto:|"
    r"\b1\.\s*.{8,}\b2\.\s*)"
)
_IMAGE_CHOICE_CONFIRM = re.compile(
    r"(?is)"
    r"(?:"
    r"que\s+sea\s+la\s+(?P<ord1>primera|segunda|tercera|1|2|3|uno|dos|tres)"
    r"|opci[oó]n\s*(?P<ord3>1|2|3|uno|dos|tres|primera|segunda|tercera)"
    r"|n[uú]mero\s*(?P<ord4>1|2|3|uno|dos|tres)"
    r"|esa\s+(?:frase|opci[oó]n|idea|visi[oó]n|concepto|descripci[oó]n)"
    r"|con\s+esa\s+(?:idea|visi[oó]n|concepto|descripci[oó]n|propuesta)"
    r"|usa\s+la\s+primera"
    r"|adelante\s+con\s+(?:esa|la\s+primera)"
    r"|cr[eé]ala"
    r"|gen[eé]ra(?:la|lo|me)?(?:\s+(?:ya|as[ií]|con\s+esa(?:\s+\w+)?))?"
    r")"
)
_ANAPHORIC_IMAGE_SUBJECT = re.compile(
    r"(?is)^\s*(?:con\s+)?(?:esa|este|esta|ese|aquell[oa])\s+"
    r"(?:idea|visi[oó]n|concepto|descripci[oó]n|propuesta|brief|dise[nñ]o|"
    r"ejemplo|escena|variante|versi[oó]n|opci[oó]n|habitaci[oó]n|espacio|"
    r"ba[nñ]o|cuarto|propuesta)\s*[.!]?\s*"
    r"(?:para\s+ver\s+(?:c[oó]mo\s+)?(?:se\s+ver[ií]a|el\s+resultado))?\s*[.!]?\s*$"
    r"|^\s*(?:eso|lo\s+mismo|lo\s+anterior|con\s+eso|as[ií]|de\s+eso)\s*[.!]?\s*$"
)
_VAGUE_IMAGE_META_TAIL = re.compile(
    r"(?is)\b(?:para\s+ver\s+(?:c[oó]mo\s+)?(?:se\s+ver[ií]a|el\s+resultado)|"
    r"c[oó]mo\s+se\s+ver[ií]a|a\s+ver\s+c[oó]mo\s+queda)\s*[.!]?\s*$"
)
_ASSISTANT_VISUAL_SKIP = re.compile(
    r"(?is)^(bienvenido|hola|buenos|retomemos|"
    r"aqu[ií]\s+est[aá]\s+(?:tu|su|la)\s+imagen|listo\.?\s+aqu[ií])"
)
_ASSISTANT_VISUAL_MARKERS = re.compile(
    r"(?is)\b(se\s+ver[ií]a|colocar|espejo|luz|led|dise[nñ]o|espacio|"
    r"habitaci|ba[nñ]o|color|estilo|fondo|perspectiva|fotorrealist|"
    r"vertical|horizontal|encimera|mueble|decor|vanity|l[aá]mpara)\b"
)
_SHORT_IMAGE_CHOICE = re.compile(
    r"(?is)^\s*(?:(?:ok|okay|vale|dale|perfecto|listo|te\s+sigo)[\s.,!]*)*"
    r"(?:que\s+sea\s+)?la\s+(?P<ord2>primera|segunda|tercera|1|2|3)\s*[.!]?\s*$"
)
_ORDINAL_INDEX = {
    "primera": 0,
    "1": 0,
    "uno": 0,
    "segunda": 1,
    "2": 1,
    "dos": 1,
    "tercera": 2,
    "3": 2,
    "tres": 2,
}
_NUMBERED_QUOTED_OPTION = re.compile(
    r'(?:^|[.\s])(\d+)[\).:\-]\s*[«"“]([^"»”]{8,240})[»"”]',
    re.M,
)
_NUMBERED_LINE_OPTION = re.compile(
    r"(?m)^\s*(\d+)[\).:\-]\s+(.{8,240}?)$",
)
_CASUAL_CHAT_BLOCK = re.compile(
    r"\b("
    r"cambiando\s+(?:de\s+|el\s+)?tema|otro\s+tema|hablemos\s+de\s+otra|"
    r"dolor\s+de\s+cabeza|mal\s+de\s+cabeza|me\s+duele\s+la\s+cabeza|"
    r"solo\s+quiero\s+charlar|charlar\s+un\s+rato|conversar|platique|platicar|"
    r"estoy\s+(?:mal|enferm|cansad|triste)|me\s+siento|"
    r"por\s+cierto|a\s+prop[oó]sito|"
    r"olvida(?:lo|mos)?|dejemos\s+(?:eso|lo)|"
    r"no\s+(?:sobre|de)\s+(?:eso|marketing|estrategia)"
    r")\b",
    re.I,
)


def is_casual_chat_interrupt(text: str) -> bool:
    """Charla personal o cambio de tema — no enrutar a creativos ni herramientas."""
    t = (text or "").strip()
    if not t:
        return False
    if _CASUAL_CHAT_BLOCK.search(t):
        return True
    from app.services.cognitive_intents import is_personal_vent_intent, is_topic_change

    return is_personal_vent_intent(t) or is_topic_change(t)


def history_has_active_image_thread(history: list[dict[str, str]] | None) -> bool:
    """True solo si hubo un pedido o entrega real de imagen/creativo en el hilo reciente."""
    for row in (history or [])[-8:]:
        content = (row.get("content") or "").strip()
        if not content:
            continue
        role = str(row.get("role") or "").lower()
        if role == "user" and _IMAGE_THREAD_USER.search(content):
            return True
        if role in ("assistant", "model", "agent") and _IMAGE_THREAD_ASSISTANT.search(content):
            return True
    return False


def is_image_choice_confirmation(text: str) -> bool:
    """True si elige una frase/opción ya propuesta para generar la imagen."""
    t = (text or "").strip()
    if not t or len(t) > 180:
        return False
    if is_generate_image_intent(t) or is_text_ideation_request(t):
        return False
    if re.search(r"(?i)\b(pregunta|preguntas|despu[eé]s\s+de)\b", t):
        return False
    return bool(_SHORT_IMAGE_CHOICE.match(t) or _IMAGE_CHOICE_CONFIRM.search(t))


def history_has_pending_image_brief(history: list[dict[str, str]] | None) -> bool:
    """True si el hilo reciente ya describió o propuso la imagen a generar."""
    if history_has_active_image_thread(history):
        return True
    for row in (history or [])[-10:]:
        content = (row.get("content") or "").strip()
        if not content:
            continue
        role = str(row.get("role") or "").lower()
        if role in {"user", "customer"} and _PENDING_IMAGE_USER.search(content):
            return True
        if role in {"assistant", "model", "agent"} and _PENDING_IMAGE_ASSISTANT.search(
            content
        ):
            return True
    return False


def _choice_index_from_text(text: str) -> int:
    match = _SHORT_IMAGE_CHOICE.match(text or "") or _IMAGE_CHOICE_CONFIRM.search(text or "")
    if not match:
        return 0
    groups = match.groupdict()
    for key in ("ord1", "ord2", "ord3", "ord4"):
        val = groups.get(key)
        if val:
            return _ORDINAL_INDEX.get(val.lower(), 0)
    return 0


def _extract_numbered_options(content: str) -> list[str]:
    quoted = [m.group(2).strip() for m in _NUMBERED_QUOTED_OPTION.finditer(content or "")]
    if len(quoted) >= 2:
        return quoted[:5]
    lines: list[str] = []
    for match in _NUMBERED_LINE_OPTION.finditer(content or ""):
        body = match.group(2).strip().strip('"«»“”')
        body = re.sub(r"\s*\([^)]{0,40}\)\s*$", "", body).strip()
        if body:
            lines.append(body)
    return lines[:5]


def resolve_confirmed_image_prompt(
    text: str,
    history: list[dict[str, str]] | None = None,
) -> str | None:
    """Arma el prompt visual cuando el usuario elige «la primera» tras un brief de imagen."""
    if not is_image_choice_confirmation(text):
        return None
    if not history_has_pending_image_brief(history):
        return None
    idx = _choice_index_from_text(text)
    user_bits: list[str] = []
    options: list[str] = []
    for row in history or []:
        content = (row.get("content") or "").strip()
        role = str(row.get("role") or "").lower()
        if not content:
            continue
        if role in {"user", "customer"} and _PENDING_IMAGE_USER.search(content):
            user_bits.append(content)
        if role in {"assistant", "model", "agent"}:
            found = _extract_numbered_options(content)
            if len(found) >= 2:
                options = found
    headline = options[idx] if options and 0 <= idx < len(options) else ""
    brief = " ".join(user_bits[-3:]).strip()
    if not brief and not headline:
        return None
    parts = ["Generate this image:"]
    if brief:
        parts.append(brief)
    if headline:
        parts.append(f'Headline text on the image, exactly: "{headline}"')
    return " ".join(parts)[:4000]


def parse_followup_image_prompt(text: str, history: list[dict[str, str]] | None = None) -> str | None:
    """Detecta pedidos cortos de imagen que continúan un tema visual reciente."""
    t = (text or "").strip()
    # Revisiones de tipografía pueden ser más largas («mantén textos: A, B, C…»).
    max_len = 500 if re.search(r"(?i)\btextos?\b", t) else 120
    if not t or is_generate_image_intent(t) or len(t) > max_len or len(t) < 6:
        return None
    if is_casual_chat_interrupt(t):
        return None
    if _FOLLOWUP_SKIP.search(t):
        return None
    from app.services.publish_text import (
        is_explicit_social_publish_request,
        is_image_for_publish_signal,
        is_publish_help_request,
        is_publish_platform_reply,
    )

    # No llamar is_social_publish_intent aquí (recursión vía blocks_publish_intent).
    if (
        is_explicit_social_publish_request(t)
        or is_publish_platform_reply(t)
        or is_publish_help_request(t)
        or is_image_for_publish_signal(t)
    ):
        return None

    has_thread = history_has_active_image_thread(history)
    if not has_thread and not user_requests_prior_reference(t):
        return None

    # El historial reciente casi siempre menciona "imagen" tras generar una (p.ej. el
    # propio "aquí está tu imagen generada"), así que basarse solo en el blob de
    # historial no distingue un mensaje casual de un pedido real de continuar editando
    # la imagen. Exigimos que el mensaje ACTUAL traiga la señal, no el historial.
    if not _FOLLOWUP_EDIT_SIGNAL.search(t) and not user_requests_prior_reference(t):
        return None

    recent: list[str] = []
    for row in (history or [])[-8:]:
        content = (row.get("content") or "").strip()
        if content:
            recent.append(content)
    blob = " ".join(recent[-6:]).lower()
    if not _FOLLOWUP_IMAGE_CONTEXT.search(blob) and not user_requests_prior_reference(t):
        return None
    return t


def is_pdf_intent(text: str) -> bool:
    """True solo ante pedido real de crear/exportar un PDF — no por mencionar la palabra."""
    t = text.strip()
    if len(t) < 6:
        return False
    # Nunca basarse solo en mentions_pdf("… PDF …"): eso disparaba PDFs falsos en listas
    # de capacidades ("generación de imágenes y PDF", etc.).
    return any(p.search(t) for p in _PDF_PATTERNS[1:])


def parse_pdf_request(text: str) -> tuple[str, str] | None:
    t = text.strip()
    if not is_pdf_intent(t):
        return None

    title_match = re.search(
        r"(?:t[ií]tulo|titulo)\s*[:.]?\s*[\"']?([^\"'\n.]+?)[\"']?(?:\s+(?:contenido|sobre|de|con)\b|$)",
        t,
        re.I,
    )
    # \b evita que "de" haga match dentro de "del" y corte la primera letra
    # ("PDF del resumen" → "l resumen"); "del" se acepta completo.
    content_match = re.search(
        r"\b(?:contenido|sobre|de(?:l)?|con|que\s+diga|que\s+incluya)\b\s*[:.]?\s*(.+)$",
        t,
        re.I | re.S,
    )

    title = (title_match.group(1).strip() if title_match else "") or "Documento CED"
    content = (content_match.group(1).strip() if content_match else "") or ""

    dice_match = re.search(r"que\s+dice\s+(.+)$", t, re.I)
    if dice_match:
        content = dice_match.group(1).strip().strip("\"'")
        if not title_match:
            title = "Documento CED"

    if not content:
        content = re.sub(
            r"^(?:genera|generar|crea|crear|exporta|exportar|convierte|convertir|guarda|guárdame|haz(me)?|dame|pon|pásalo|pasalo)\s+"
            r"(?:.{0,48}?\s+)?(?:en\s+)?(?:un(?:a)?\s+)?pdf\s*(?:de|con|sobre|que\s+diga)?\s*",
            "",
            t,
            flags=re.I,
        ).strip()

    if not content:
        content = title if title != "Documento CED" else ""

    return title[:200], content[:12000]


_PDF_FILLER_ASSISTANT = re.compile(
    r"(?:"
    r"algo\s+m[aá]s\s+en\s+lo\s+que\s+(?:le\s+)?pueda\s+ayudar"
    r"|(?:en\s+)?qu[eé]\s+m[aá]s\s+puedo\s+ayud"
    r"|(?:puedo|le)\s+puedo\s+ayudar\s+en\s+algo"
    r")",
    re.I,
)


def _is_pdf_filler_assistant(text: str) -> bool:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return True
    if len(t) < 90 and _PDF_FILLER_ASSISTANT.search(t):
        return True
    if re.fullmatch(
        r"(?:¿?\s*)?(?:listo,?\s*señor|perfecto|de\s+nada|un\s+placer)[\s!.?]*",
        t,
        re.I,
    ):
        return True
    return False


def _assistant_texts_for_pdf(history: list[dict] | None, *, min_len: int = 80) -> list[str]:
    texts: list[str] = []
    for row in reversed(history or []):
        role = str(row.get("role") or "").lower()
        if role not in ("assistant", "model"):
            continue
        content = row.get("content")
        if not isinstance(content, str):
            continue
        text = content.strip()
        if len(text) < min_len or _is_pdf_filler_assistant(text):
            continue
        texts.append(text)
    return texts


def _last_assistant_text(history: list[dict] | None, *, min_len: int = 120) -> str:
    for text in _assistant_texts_for_pdf(history, min_len=min_len):
        return text
    return ""


def infer_pdf_title(user_text: str, content: str) -> str:
    """Título legible a partir del pedido y del cuerpo del documento."""
    blob = f"{user_text}\n{content[:900]}"
    if re.search(r"plan\s+semanal|estrategia\s+semanal", blob, re.I):
        return "Plan Semanal de Estrategia CED"
    if re.search(r"lanzamiento\s+(?:de\s+)?ced", blob, re.I):
        return "Plan de Lanzamiento CED"
    if re.search(r"\bestrategia\b", blob, re.I) and not re.search(r"tornado|noticia", blob, re.I):
        return "Estrategia CED"
    if re.search(r"\btornado\b", blob, re.I):
        if re.search(r"\bchina\b|\bhubei\b", blob, re.I):
            return "Tornado EF2 en Hubei, China"
        return "Informe sobre Tornado"
    if re.search(r"\bnoticia", blob, re.I):
        topic = re.search(
            r"noticia(?:s)?\s+(?:de|sobre|del?|la)?\s*([^.\n]{8,80})",
            user_text,
            re.I,
        )
        if topic:
            return topic.group(1).strip()[:120]
    if re.search(r"\bfinanz", blob, re.I):
        return "Reporte Financiero CED"
    body = (content or "").strip()
    for raw_line in re.split(r"[\n.!?]+", body):
        line = raw_line.strip()
        line = re.sub(r"^(?:señor,?\s*)?(?:sobre su consulta:?\s*)?", "", line, flags=re.I).strip()
        if _is_pdf_filler_assistant(line):
            continue
        if 18 <= len(line) <= 110 and not re.search(r"^(?:un momento|consulto|pdf)\b", line, re.I):
            return line[:120]
    for candidate in _assistant_texts_for_pdf(
        [{"role": "assistant", "content": body}],
        min_len=18,
    ):
        first_line = re.split(r"[\n.!?]+", candidate)[0].strip()
        if first_line and not _is_pdf_filler_assistant(first_line):
            return first_line[:120]
    return "Documento CED"


def _infer_pdf_title(user_text: str, content: str) -> str:
    return infer_pdf_title(user_text, content)


def resolve_pdf_request(
    text: str,
    history: list[dict] | None = None,
) -> tuple[str, str] | None:
    """Título y cuerpo del PDF a partir del mensaje y del historial del chat."""
    t = (text or "").strip()
    if not is_pdf_intent(t):
        return None

    parsed = parse_pdf_request(t)
    title = parsed[0] if parsed else "Documento CED"
    content = parsed[1] if parsed else ""

    pasted = re.search(r"(?:en\s+)?(?:un(?:a)?\s+)?pdf\s*\n?\s*(.+)$", t, re.I | re.S)
    if pasted:
        body = pasted.group(1).strip()
        if len(body) >= 80:
            content = body

    if len(content) < 200 and _PDF_THIS_REF.search(t) and not _pdf_has_named_topic(t, content):
        previous = _last_assistant_text(history, min_len=80)
        if previous:
            content = previous

    # Solo anáfora vacía ("esto/eso en PDF") — NUNCA sustituir un tema corto
    # ("PDF sobre Restorate") por la respuesta anterior (p. ej. Activize).
    if (not content or len(content.strip()) < 8) and _PDF_THIS_REF.search(t):
        for previous in _assistant_texts_for_pdf(history, min_len=80):
            content = previous
            break
    elif not content or len(content.strip()) < 8:
        # Sin anáfora: dejar vacío para que compose redacte desde la petición/título.
        content = content.strip() if content else ""

    if title == "Documento CED" or len(title) < 8:
        title = infer_pdf_title(t, content)

    if not content:
        return title[:200], ""

    return title[:200], content[:12000]


PDF_DETAIL_CLARIFY_QUESTION = (
    "¿Prefiere un resumen breve o el contenido completo para el PDF, señor?"
)

_PDF_BRIEF = re.compile(
    r"\b("
    r"resumen(?:\s+breve)?|breve|corto|conciso|sint[eé]sis|resumid[oa]|"
    r"versi[oó]n\s+corta|poco\s+detalle|solo\s+lo\s+esencial|"
    r"executive\s+summary|tl;?dr"
    r")\b",
    re.I,
)
_PDF_FULL = re.compile(
    r"\b("
    r"completo|completa|extenso|extensa|detallad[oa]|a\s+fondo|"
    r"todo\s+el\s+detalle|con\s+(?:todo\s+)?detalle|versi[oó]n\s+larga|"
    r"exhaustiv[oa]|desarrollad[oa]|ampli[oa]|en\s+profundidad"
    r")\b",
    re.I,
)
_PDF_CLARIFY_ASSISTANT = re.compile(
    r"resumen\s+breve\s+o\s+el\s+contenido\s+completo",
    re.I,
)
_PDF_ANSWER_BRIEF = re.compile(
    r"\b(breve|corto|resumen|conciso|esencial|sint[eé]sis)\b",
    re.I,
)
_PDF_ANSWER_FULL = re.compile(
    r"\b(completo|completa|extenso|detallad[oa]|largo|todo|full)\b",
    re.I,
)


def pdf_detail_level(text: str) -> str | None:
    """'brief' | 'full' | None si la petición no especifica extensión."""
    t = (text or "").strip()
    if not t:
        return None
    brief = bool(_PDF_BRIEF.search(t))
    full = bool(_PDF_FULL.search(t))
    if brief and not full:
        return "brief"
    if full and not brief:
        return "full"
    if brief and full:
        # Ambos: prioriza lo más específico cerca de "pdf" o el último.
        if re.search(r"\b(completo|detallad[oa]|extenso).{0,40}\bpdf\b", t, re.I) or re.search(
            r"\bpdf\b.{0,40}\b(completo|detallad[oa]|extenso)\b", t, re.I
        ):
            return "full"
        if re.search(r"\b(resumen|breve|corto).{0,40}\bpdf\b", t, re.I) or re.search(
            r"\bpdf\b.{0,40}\b(resumen|breve|corto)\b", t, re.I
        ):
            return "brief"
        return None
    return None


def is_pdf_length_clarify_question(text: str) -> bool:
    return bool(_PDF_CLARIFY_ASSISTANT.search((text or "").strip()))


def parse_pdf_detail_answer(text: str) -> str | None:
    """Respuesta a la pregunta resumen vs completo."""
    t = (text or "").strip()
    if not t or len(t) > 160:
        return None
    brief = bool(_PDF_ANSWER_BRIEF.search(t))
    full = bool(_PDF_ANSWER_FULL.search(t))
    if brief and not full:
        return "brief"
    if full and not brief:
        return "full"
    if re.fullmatch(r"(?:el\s+)?(?:resumen(?:\s+breve)?|breve|corto)", t, re.I):
        return "brief"
    if re.fullmatch(r"(?:el\s+)?(?:completo|contenido\s+completo|detallado|extenso)", t, re.I):
        return "full"
    return None


def last_assistant_asked_pdf_detail(history: list[dict] | None) -> bool:
    for row in reversed(history or []):
        role = str(row.get("role") or "").lower()
        if role not in ("assistant", "model"):
            continue
        content = row.get("content")
        if isinstance(content, str) and is_pdf_length_clarify_question(content):
            return True
        break
    return False


def prior_pdf_user_request(history: list[dict] | None) -> str | None:
    """Último mensaje de usuario con intención real de PDF (antes de la pregunta de extensión)."""
    for row in reversed(history or []):
        role = str(row.get("role") or "").lower()
        content = row.get("content")
        if not isinstance(content, str):
            continue
        text = content.strip()
        if not text:
            continue
        if role in ("assistant", "model"):
            if is_pdf_length_clarify_question(text):
                continue
            continue
        if role == "user" and is_pdf_intent(text):
            return text
    return None


def resolve_pdf_detail_for_turn(
    text: str,
    history: list[dict] | None = None,
) -> str | None:
    """
    Devuelve:
      - 'brief' | 'full' → generar con ese nivel
      - 'ask' → preguntar antes de generar
      - None → no es un turno de PDF
    """
    t = (text or "").strip()
    if last_assistant_asked_pdf_detail(history):
        answered = parse_pdf_detail_answer(t)
        if answered:
            return answered
        level = pdf_detail_level(t)
        if level:
            return level
        if is_pdf_intent(t):
            return "ask"
        # Respuesta ambigua tras la pregunta → default breve.
        return "brief"

    if not is_pdf_intent(t):
        return None

    level = pdf_detail_level(t)
    if level:
        return level
    return "ask"


def is_viability_module_intent(text: str) -> bool:
    """Intent de viabilidad (piloto). NO se usa en text_chat de producción.

    El panel/API de viabilidad y el tool Retell native pilot son los únicos
    callers. Re-export para el router de intents de chat y tests de colisión.
    """
    from app.services.viability_pilot.intents import (
        is_viability_module_intent as _viability_intent,
    )

    return _viability_intent(text)
