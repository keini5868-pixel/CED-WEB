"""Chat de texto con Claude — límites por plan + herramientas Meta."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import date, datetime, timezone
from typing import Any

import httpx

from app.config import get_settings
from app.services import supabase_db
from app.services.cognitive_router import build_chat_system_extras, route_message
from app.services.chat_intents import (
    is_generate_image_intent,
    is_pdf_intent,
    parse_followup_image_prompt,
    parse_generate_image_prompt,
    parse_pdf_request,
    resolve_pdf_request,
)
from app.domain.ced_identity import (
    CED_CORE_IDENTITY,
    CED_CREATOR_IDENTITY,
    CED_HUMAN_VOICE_STYLE,
    CED_UNIVERSAL_CONVERSATION,
)
from app.domain.ced_memory_prompt import CED_MEMORY_USAGE_RULES
from app.domain.ced_strategy_consultant import CED_STRATEGY_CONSULTATION_CORE
from app.domain.ced_sales_mentor import CED_SALES_MENTOR_CORE
from app.domain.ced_viral_knowledge import CED_VIRAL_KNOWLEDGE_2026
from app.services.meta_social import MetaSocialError, publish_facebook, publish_instagram
from app.services.pdf_report import (
    assistant_fallback_texts_from_messages,
    normalize_pdf_fields,
    store_pdf_with_timeout,
    user_texts_from_messages,
)
from app.services.internal_kb_guard import (
    contains_internal_kb_leak as _contains_internal_kb_leak,
    strip_internal_kb_from_reply as _strip_internal_kb_from_reply,
)
from app.services.deliverable_replies import (
    CHAT_DELIVERABLE_RULES,
    DELIVERABLE_CONTINUATION_MESSAGE,
    is_deliverable_request as _is_deliverable_request,
    has_deliverable_structure as _has_deliverable_structure,
    is_incomplete_deliverable as _is_incomplete_deliverable,
    merge_deliverable_continuation,
)
from app.services.voice_spoken import strip_voice_filler_prefix
from app.services.publish_text import PUBLISH_INSTRUCTION_ABSOLUTE_RULES

logger = logging.getLogger(__name__)

CHAT_MODEL = "claude-sonnet-4-6"
CHAT_MODEL_FAST = "claude-3-5-haiku-20241022"
CHAT_GEMINI_MODEL = "gemini-2.5-flash"
CHAT_SYSTEM_MAX_CHARS = 14_000


def _gemini_chat_model() -> str:
    settings = get_settings()
    return settings.gemini_voice_model.strip() or CHAT_GEMINI_MODEL


CHAT_HISTORY_LIMIT = 30
CHAT_STREAM_HISTORY_LIMIT = 12
_STREAM_USAGE_CACHE: dict[str, tuple[float, int]] = {}
_STREAM_USAGE_CACHE_TTL = 45.0
CHAT_SIMPLE_MAX_TOKENS = 1400
CHAT_DELIVERABLE_MAX_TOKENS = 3200
CHAT_TOOLS_MAX_TOKENS = 1600
DIRECT_IMAGE_MAX_CHARS = 500

_VIRAL_KEYWORDS = re.compile(
    r"\b(instagram|tiktok|reels?|viral|horario|publicar|contenido|linkedin|facebook|"
    r"hooks?|stories|algoritmo|engagement|redes\s+sociales)\b",
    re.I,
)

_GREETING_ONLY = re.compile(
    r"^(?:hola|buenos?\s+d[ií]as|buenas?\s+tardes|buenas?\s+noches|hey|hi|hello|"
    r"qué\s+tal|que\s+tal|como\s+estas?|cómo\s+estas?|saludos)[\s!.?]*$",
    re.I,
)
_TOOLS_KEYWORDS = re.compile(
    r"\b(publica|publicar|instagram|facebook|meta|recuerdas|guarda|memoria|"
    r"lead|cliente|pdf|imagen|conectad|busca|buscar|búsqueda|noticias|clima|"
    r"informaci[oó]n|investiga|terremoto|actual|reciente|dame datos)\b",
    re.I,
)

HALLUCINATED_TOOL_PATTERNS = (
    r"\*\*generate_image\*\*",
    r"\*\*generar_pdf\*\*",
    r"\*\*publicar_facebook\*\*",
    r"\*\*publicar_instagram\*\*",
    r"\*\*search_web\*\*",
    r"```\s*generate_image",
    r"```\s*generar_pdf",
    r"```\s*search_web",
)

HALLUCINATED_TOOL_CODE_PATTERNS = (
    r"\*\*tool_code\*\*",
    r"```\s*tool_code",
    r"print\(search_web\(",
    r"print\(generate_image\(",
    r"print\s*\(\s*generar_pdf\s*\(",
    r"print\(generar_pdf\(",
    r"tool_code\s*\n\s*print\(",
    r"search_web\(query=",
    r"generate_image\(prompt=",
    r"generar_pdf\s*\(\s*content\s*=",
)

TOOL_CODE_HALLUCINATION_RETRY_MESSAGE = (
    "ERROR: Escribiste código Python en lugar de invocar la herramienta con function calling. "
    "USA function calling real. NO escribas print(), tool_code, ni código Python."
)

SEARCH_HALLUCINATION_RETRY_MESSAGE = (
    "Dijiste que ibas a buscar pero no invocaste search_web. "
    "Invoca search_web AHORA con function calling real, o responde con conocimiento "
    "integrado y avisa honestamente si no hay datos actuales."
)

INTERNAL_KB_LEAK_RETRY_MESSAGE = (
    "Tu respuesta anterior incluyó el bloque interno 'Conocimiento interno CED'. "
    "Ese texto es SOLO contexto del sistema — NUNCA debe aparecer en tu respuesta al usuario. "
    "Reescribe de forma natural y útil, usando la información sin citar ni copiar el bloque interno."
)

HALLUCINATION_RETRY_USER_MESSAGE = (
    "ERROR: Escribiste el nombre de la herramienta como texto. "
    "Invócala mediante function calling real, o avisa honestamente que no puedes."
)

HALLUCINATION_FALLBACK_REPLY = (
    "Tuve un problema procesando tu solicitud. ¿Puedes intentar con un prompt más simple? "
    "Por ejemplo: 'genera una imagen de un atardecer'."
)

EMPTY_RESPONSE_RETRY_USER_MESSAGE = (
    "Tu respuesta anterior fue vacía o incompleta. Da una respuesta completa y útil."
)

CHAT_TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_web",
        "description": (
            "Busca en internet datos actuales: noticias, clima, eventos recientes, "
            "cifras o cualquier información que cambie en el tiempo. "
            "OBLIGATORIO invocar cuando el usuario pida buscar o información actual. "
            "NUNCA digas 'voy a buscar' sin invocar esta herramienta en el mismo turno."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Consulta de búsqueda en lenguaje natural",
                },
                "kind": {
                    "type": "string",
                    "enum": ["news", "weather", "general"],
                    "description": "Tipo: news (noticias), weather (clima), general (otros)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "consultar_redes_conectadas",
        "description": "Consulta si Facebook/Instagram están conectados a CED para este usuario.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "publicar_facebook",
        "description": (
            "Publica un post en la página de Facebook conectada. La imagen DEBE venir "
            "de una que el usuario ya subió al chat o sesión. NUNCA pidas URL al usuario. "
            "Si subió imagen recientemente, usa use_last_uploaded_image=true automáticamente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Texto del post"},
                "use_last_uploaded_image": {
                    "type": "boolean",
                    "description": (
                        "Si true, usa la última imagen subida por el usuario en esta "
                        "conversación. Default true cuando hay imagen en el chat."
                    ),
                    "default": True,
                },
            },
            "required": ["message"],
        },
    },
    {
        "name": "publicar_instagram",
        "description": (
            "Publica una imagen en Instagram Business conectado. La imagen DEBE venir "
            "de una que el usuario ya subió al chat o sesión. NUNCA pidas URL al usuario. "
            "Si subió imagen recientemente, usa use_last_uploaded_image=true automáticamente. "
            "Si no hay imagen subida, avisa que primero suba una imagen al chat."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "caption": {
                    "type": "string",
                    "description": "Texto/caption de la publicación",
                },
                "use_last_uploaded_image": {
                    "type": "boolean",
                    "description": (
                        "Si true, usa la última imagen subida por el usuario en esta "
                        "conversación. Default true."
                    ),
                    "default": True,
                },
            },
            "required": ["caption"],
        },
    },
    {
        "name": "generar_pdf",
        "description": (
            "Genera un PDF descargable. OBLIGATORIO: el campo content debe contener "
            "TODO el texto del documento (resumen, lista, informe completo). "
            "Nunca dejes content vacío ni solo con el título."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Título del documento PDF"},
                "content": {
                    "type": "string",
                    "description": "Cuerpo COMPLETO del PDF — todo el texto que el usuario quiere guardar",
                },
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "generate_image",
        "description": (
            "Genera una imagen con IA. INVÓCALA directamente mediante "
            "function calling; nunca escribas su nombre como texto. "
            "Usar cuando el usuario pida crear, diseñar, generar o "
            "hacer una imagen. Tras invocar exitosamente, confirma "
            "brevemente al usuario; la app muestra la imagen "
            "automáticamente. Si falla, avisa honestamente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": (
                        "Descripción visual concisa (sujeto, estilo, colores, composición). "
                        "Si el usuario da un brief largo, resume los elementos visuales clave "
                        "en máximo 1500 caracteres."
                    ),
                    "maxLength": 2000,
                },
                "quality": {
                    "type": "string",
                    "enum": ["auto", "standard", "hd"],
                    "description": "Calidad opcional",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "recall_previous_conversations",
        "description": (
            "Busca en conversaciones previas. Usar cuando referencien el pasado "
            "o pregunten '¿recuerdas cuando…?'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "days_back": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "save_to_long_term_memory",
        "description": (
            "Guarda datos importantes para futuras sesiones (leads, metas, proyectos). "
            "Silencioso — no anunciar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": [
                        "business",
                        "personal",
                        "goal",
                        "preference",
                        "fact",
                        "project",
                        "lead",
                    ],
                },
                "key": {"type": "string"},
                "value": {"type": "string"},
                "importance": {"type": "integer"},
            },
            "required": ["category", "key", "value"],
        },
    },
]

CHAT_SYSTEM_BASE = f"""Eres CED (Castillo de la Evolución Digital), asistente dentro de la plataforma CED Web.
Español latinoamericano natural, cálido y directo.
Responde con markdown cuando ayude. Sé útil y conciso. Nunca menciones Claude, Gemini ni APIs internas.
ORTOGRAFÍA: escribe siempre en español correcto (tildes, sin anglicismos innecesarios, sin typos).

{CED_CORE_IDENTITY}

{CED_CREATOR_IDENTITY}

{CED_HUMAN_VOICE_STYLE}

{CED_SALES_MENTOR_CORE}

{CED_STRATEGY_CONSULTATION_CORE}

{CED_UNIVERSAL_CONVERSATION}

IMPORTANTE — tratamiento del usuario:
- Usa el nombre y título del bloque "USUARIO ACTUAL — TRATAMIENTO" inyectado abajo.
- Si piden "llámame señor/señora/jefe/etc.", confirma y recuerda con save_memory key "tratamiento".
- NO uses tono de mayordomo exagerado; Señor/Señora solo si el usuario lo prefiere.

IMPORTANTE — cerebro híbrido CED:
- Primero usa conocimiento interno estable (conceptos, negocio, ciencia, cultura) cuando viene en el contexto.
- Solo afirma datos de hoy (clima, precios, noticias) si hay contexto web inyectado abajo.
- Sistema avanzado: si el contexto indica confirmación pendiente, pregunta antes de profundizar.
- NUNCA incluyas en tu respuesta al usuario el texto del bloque "Conocimiento interno CED" ni líneas tipo "- [Marketing digital] ...".
  Úsalo SOLO como contexto interno para generar respuestas naturales, útiles y en tus propias palabras.
- REGLA CRÍTICA: NUNCA incluyas en tu respuesta al usuario texto que empiece con "Conocimiento interno CED"
  o que contenga etiquetas como [Marketing digital], [Finanzas personales], [general], etc.
  Ese conocimiento es solo contexto interno tuyo. El usuario NUNCA debe verlo.

IMPORTANTE — prompts para otras herramientas de IA:
- Cuando el usuario pida un "prompt" para usar en otra herramienta de IA (ChatGPT, Midjourney, Gemini, etc.),
  entrégalo COMPLETO, detallado y listo para copiar y pegar.
- Delimita el prompt con --- arriba y --- abajo.
- NO entregues solo una "estructura de página", un esquema de secciones ni un resumen.
- Si pidió el prompt, entrégalo de inmediato — no sustituyas por una descripción de lo que incluiría.

IMPORTANTE — capacidades REALES de esta plataforma:
- CED puede publicar en Facebook e Instagram cuando el usuario conectó Meta (dashboard → Conectar Redes).
- Usa las herramientas publicar_facebook / publicar_instagram cuando el usuario pida publicar y confirme el texto.
- Si las redes NO están conectadas, indica conectar en el dashboard — NO digas que es imposible en absoluto.
- Puedes generar PDFs descargables con generar_pdf. El campo content debe incluir TODO el texto del documento, no solo el título.
- Puedes GENERAR IMÁGENES con generate_image cuando pidan crear/diseñar una imagen. Invoca la herramienta; la app muestra la imagen en el chat.
- Palabras clave de generación: "genera una imagen", "créame un diseño", "hazme un logo", "necesito una imagen", "diseña un creativo", "imagen de…", "crea una foto".
- Si el pedido de imagen es vago, pide MÁS DETALLES UNA VEZ (estilo, uso). Si es claro, genera directamente.
- Tras generar una imagen, preséntala y pregunta si quiere ajustes.
- NUNCA escribas URLs /v1/pdf/download en tu respuesta. Di que el PDF está listo; la app muestra el botón Descargar automáticamente.

{CHAT_DELIVERABLE_RULES}

INVOCACIÓN OBLIGATORIA DE HERRAMIENTAS (BÚSQUEDA WEB):

Cuando necesites información actual (noticias, clima, eventos recientes, cifras):
DEBES invocar search_web mediante function calling REAL.

NUNCA digas "voy a buscar", "buscaré" o "investigaré" sin invocar search_web en el mismo turno.

Si dices que vas a buscar, DEBES invocar search_web inmediatamente y responder con el resultado.

Si search_web devuelve status=timeout o fallback=True, AVISA honestamente:
"Señor, no pude obtener información actual en este momento. Según lo que tengo registrado, [responde con conocimiento integrado]."

NUNCA te quedes en silencio ni solo prometas una búsqueda sin ejecutarla.

PROHIBICIÓN ABSOLUTA — NUNCA escribas código Python:

NUNCA escribas bloques tipo:
- **tool_code**
- print(search_web(...))
- print(generate_image(...))
- ```python
- ```tool_code
- Ningún código Python en tu respuesta

Cuando necesites usar una herramienta:
- USA function calling directamente
- NO expliques cómo lo harías en código
- NO simules la invocación
- INVÓCALA y espera el resultado

Si ves que vas a escribir 'print(' o 'tool_code', DETENTE y usa function calling real en su lugar.

PUBLICACIÓN EN REDES SOCIALES (Instagram / Facebook):

FLUJO OBLIGATORIO (sigue estos pasos en orden):
1. Usuario sube imagen + pide publicar → responde SIEMPRE: «Imagen recibida, señor. ¿Necesita que le ayude con el título y la descripción, o ya tiene su texto listo?»
2. Si pide ayuda → propón título + descripción + hashtags CONCRETOS (nunca respuestas vacías, nunca solo «---» o «**»).
3. Si da su texto → confirma el texto y pide que diga «envía» o «publica».
4. Solo cuando diga «envía», «publica», «dale», «enviar publicación» → invoca la tool (use_last_uploaded_image=true).
5. Tras éxito real de la tool → «Un momento, señor… Listo. Publicación enviada.»

NUNCA invoques publicar_facebook/publicar_instagram sin confirmación explícita («sí», «envía», «publica», «dale», «enviar publicación»).
NUNCA uses como caption labels de UI («Subir imagen», «Enviar», «Publicar»).

CAPTION DE PUBLICACIÓN — REGLA CRÍTICA:
- El parámetro caption/message DEBE ser SOLAMENTE el texto final acordado con el usuario.
- NUNCA incluyas confirmaciones («sí», «envía», «dale», «publica»), diálogo previo ni historial.
- Si tienes dudas, pregunta: «¿Confirma que el texto a publicar es: [texto]?»

INTERPRETACIÓN DE INSTRUCCIONES DE PUBLICACIÓN:
- «Publica esto: Visita Charlotte hoy» → caption = «Visita Charlotte hoy» (sin «publica esto:»).
- NUNCA publiques la frase de instrucción del usuario como caption.

{PUBLISH_INSTRUCTION_ABSOLUTE_RULES}

REGLAS ABSOLUTAS:
1. NUNCA pidas URL de imagen al usuario. NUNCA. La imagen subida al chat está disponible automáticamente.
2. NUNCA escribas '**publicar_instagram**' como texto. INVOCA la tool con function calling real.
3. NUNCA publiques sin confirmación explícita del usuario («envía» / «publica»).
4. NUNCA finjas que publicaste si no invocaste la tool.
5. PROHIBIDO responder con plantillas vacías, puntos suspensivos solos o markdown sin contenido.

REGLAS CRÍTICAS PARA HERRAMIENTAS:

Cuando necesites usar generate_image, generar_pdf, o cualquier otra herramienta:

1. INVOCA la herramienta mediante function calling real.
2. NUNCA escribas el nombre de la herramienta como texto (ej: '**generate_image**' o 'generar_pdf').
3. NUNCA escribas el JSON de parámetros como texto en el chat.
4. Si una herramienta NO está disponible en este momento o falla, AVISA HONESTAMENTE: 'No pude completar esa acción ahora mismo, ¿quieres que intente con un enfoque distinto?'
5. NUNCA finjas que ejecutaste una acción que no ocurrió.
6. NUNCA digas 'la imagen está en camino', 'procesándose', o 'aparecerá en breve' a menos que realmente hayas invocado la herramienta exitosamente.

PROMPTS DE IMAGEN LARGOS:
Si el usuario te da un brief largo (>500 caracteres) para una imagen con mucho texto narrativo, ANTES de invocar generate_image, resume internamente los elementos VISUALES clave:
- Sujeto principal
- Estilo (digital art, fotorrealista, cartoon, etc.)
- Colores predominantes
- Composición / ambiente
- Elementos visuales adicionales

NO incluyas en el prompt el texto que el usuario pide que aparezca DENTRO de la imagen, a menos que sea muy corto (1-3 palabras). Los modelos de imagen no son buenos renderizando texto largo.

Si el usuario insiste en que aparezca texto largo en la imagen, ofrécele alternativas: 'El texto largo no se renderiza bien en imágenes. ¿Quieres que genere la imagen sin texto y te entrego el texto aparte para que lo agregues con un editor?'

PROHIBIDO (chatbot genérico): no digas "sin internet en tiempo real" ni "no puedo conectar tus cuentas" — CED tiene búsqueda, Meta OAuth y tools. No recomiendes Buffer/Hootsuite como única opción si ya tiene redes conectadas.

Cuando prepares contenido para redes, entrégalo listo y ofrece publicarlo con CED si aplica."""


def _wants_viral_knowledge(text: str) -> bool:
    return bool(_VIRAL_KEYWORDS.search(text or ""))


def _instant_chat_greeting_reply(text: str) -> str | None:
    cleaned = (text or "").strip()
    if _GREETING_ONLY.match(cleaned):
        if re.search(r"como\s+estas?|cómo\s+estas?", cleaned, re.I):
            return (
                "Muy bien, señor, gracias por preguntar. "
                "¿En qué le ayudo hoy?"
            )
        return (
            "Hola, señor. Soy CED — su asistente de negocios y marketing. "
            "¿En qué le ayudo hoy?"
        )
    return None

def _has_hallucinated_tool(text: str) -> bool:
    for pattern in HALLUCINATED_TOOL_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def _has_hallucinated_tool_code(text: str) -> bool:
    for pattern in HALLUCINATED_TOOL_CODE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def _extract_query_from_hallucination(text: str) -> str | None:
    """Extrae el query del código alucinado para ejecutar búsqueda directa."""
    t = text or ""
    match = re.search(r'query=["\']([^"\']+)["\']', t, re.I)
    if match:
        return match.group(1).strip()
    match = re.search(r'search_web\(["\']([^"\']+)["\']', t, re.I)
    if match:
        return match.group(1).strip()
    return None


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for row in reversed(messages):
        if row.get("role") != "user":
            continue
        content = row.get("content")
        if isinstance(content, str):
            stripped = content.strip()
            if stripped:
                return stripped
    return ""


def _hallucinated_generar_pdf_fields(text: str) -> tuple[str, str] | None:
    """Extrae título/contenido de un print(generar_pdf(...)) alucinado."""
    blob = text or ""
    if not re.search(r"generar_pdf", blob, re.I):
        return None
    title = "Documento CED"
    title_match = re.search(
        r'(?:title|titulo)\s*=\s*"((?:\\.|[^"\\])*)"',
        blob,
        re.I,
    )
    if title_match:
        title = title_match.group(1).replace("\\n", "\n").replace('\\"', '"').strip()
    content_match = re.search(
        r'(?:content|contenido)\s*=\s*"((?:\\.|[^"\\])*)"',
        blob,
        re.I | re.S,
    )
    if content_match:
        content = content_match.group(1).replace("\\n", "\n").replace('\\"', '"').strip()
        if len(content) >= 20:
            return title[:200], content[:12000]
    return None


def _execute_direct_pdf(
    user_id: str,
    *,
    title: str,
    content: str,
    history: list[dict[str, Any]],
    conversation_id: str | None,
    user_request: str,
) -> tuple[str, dict[str, Any]] | None:
    """Genera PDF real y devuelve mensaje + adjunto para el chat."""
    from app.deps.plan_access import effective_plan_limits

    limits, reason, _trial = effective_plan_limits(user_id)
    if reason == "trial_expired":
        return (
            "Tu prueba terminó. Elige un plan en Precios o continúa con el plan Básico gratis.",
            {},
        )
    if not limits.pdf_reports:
        return ("Los PDFs requieren plan Élite o Founding. Mejora tu plan en /pricing.", {})

    pdf_title = (title or "Documento CED").strip()[:200]
    pdf_body = (content or "").strip()
    fallbacks = assistant_fallback_texts_from_messages(_anthropic_messages(history))
    user_texts = user_texts_from_messages(_anthropic_messages(history))
    resolved_request = user_request or (user_texts[-1] if user_texts else pdf_title)
    try:
        artifact = store_pdf_with_timeout(
            user_id=user_id,
            title=pdf_title,
            content=pdf_body,
            conversation_id=conversation_id,
            fallback_texts=fallbacks,
            user_request=resolved_request,
        )
    except TimeoutError:
        return (
            "No pude generar el PDF a tiempo, señor. Intenta de nuevo en un momento.",
            {},
        )
    except ValueError:
        return (
            "No pude armar el contenido del PDF. ¿Puedes indicar qué quieres incluir?",
            {},
        )
    except RuntimeError:
        return (
            "No pude guardar el PDF en el servidor. Intenta de nuevo.",
            {},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("[CHAT] direct PDF failed: %s", exc)
        return ("No pude generar el PDF en este momento. Intenta de nuevo.", {})

    attachment = _pdf_attachment_from_artifact(artifact)
    return (
        f'Listo. PDF "{artifact.title}" generado. Usa el botón Descargar abajo.',
        attachment,
    )


def _try_direct_pdf_from_context(
    user_id: str,
    *,
    text: str,
    history: list[dict[str, Any]],
    conversation_id: str | None,
) -> tuple[str, dict[str, Any]] | None:
    req = resolve_pdf_request(text, history)
    if not req:
        return None
    title, body = req
    result = _execute_direct_pdf(
        user_id,
        title=title,
        content=body,
        history=history,
        conversation_id=conversation_id,
        user_request=text,
    )
    if not result:
        return None
    message, attachment = result
    if not attachment.get("file_id"):
        return message, {}
    return message, attachment


def _try_pdf_from_hallucinated_reply(
    user_id: str,
    *,
    reply: str,
    user_text: str,
    messages: list[dict[str, Any]],
    conversation_id: str | None,
) -> tuple[str, dict[str, Any] | None, None] | None:
    if not _has_hallucinated_tool_code(reply):
        return None
    extracted = _hallucinated_generar_pdf_fields(reply)
    if extracted:
        title, body = extracted
    else:
        req = resolve_pdf_request(user_text, messages)
        if not req:
            return None
        title, body = req
    result = _execute_direct_pdf(
        user_id,
        title=title,
        content=body,
        history=messages,
        conversation_id=conversation_id,
        user_request=user_text,
    )
    if not result:
        return None
    message, attachment = result
    if not attachment.get("file_id"):
        return message, None, None
    return message, attachment, None


def _reply_from_direct_search(query: str, *, kind: str = "news") -> str:
    """Ejecuta búsqueda directamente si Claude alucinó tool_code."""
    q = (query or "").strip()
    if not q:
        return "Señor, no pude obtener la información. ¿Puede reformular?"
    from app.services.gemini_grounded import execute_search_web_sync

    result = execute_search_web_sync(q, kind=kind)
    summary = str(result.get("summary") or result.get("message") or "").strip()
    if result.get("ok") and summary:
        return summary
    return str(
        result.get("message")
        or "Señor, no pude obtener información actual en este momento."
    )


def _resolve_hallucinated_tool_code_reply(
    reply: str,
    messages: list[dict[str, Any]],
    *,
    user_id: str = "",
    user_text: str = "",
) -> str | None:
    if not _has_hallucinated_tool_code(reply):
        return None
    if re.search(r"generar_pdf", reply or "", re.I):
        return None
    if re.search(r"recall_memory|recall_previous_conversations", reply or "", re.I):
        from app.services.cognitive_intents import is_conversation_recall_intent
        from app.services.session_memory import build_conversation_recall_reply

        prompt = user_text or _last_user_text(messages)
        if is_conversation_recall_intent(prompt) or re.search(
            r"recall_memory|recall_previous",
            reply or "",
            re.I,
        ):
            return build_conversation_recall_reply(user_id, prompt, channel="text")
    query = _extract_query_from_hallucination(reply) or _last_user_text(messages)
    return _reply_from_direct_search(query)


def _tool_hallucination_kind(reply: str) -> str | None:
    if _has_hallucinated_tool_code(reply):
        return "tool_code"
    if _promised_web_search_without_tool(reply):
        return "search_promise"
    if _has_hallucinated_tool(reply):
        return "tool_name"
    return None


def _hallucination_retry_message(kind: str) -> str:
    if kind == "tool_code":
        return TOOL_CODE_HALLUCINATION_RETRY_MESSAGE
    if kind == "search_promise":
        return SEARCH_HALLUCINATION_RETRY_MESSAGE
    return HALLUCINATION_RETRY_USER_MESSAGE


def _dedupe_chat_reply(text: str) -> str:
    """Elimina bloques idénticos consecutivos y muletillas duplicadas en la respuesta."""
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned
    cleaned = re.sub(
        r"(Un momento,?\s*se[nñ]or\.?\s*){2,}",
        r"\1",
        cleaned,
        flags=re.I,
    )
    parts = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
    if len(parts) >= 2:
        deduped: list[str] = [parts[0]]
        for part in parts[1:]:
            if part != deduped[-1]:
                deduped.append(part)
        cleaned = "\n\n".join(deduped)
    half = len(cleaned) // 2
    if half > 120:
        first = cleaned[:half].strip()
        second = cleaned[half:].strip()
        if first == second:
            return first
    return cleaned


def _chat_max_tokens(user_text: str, *, with_tools: bool = False) -> int:
    if with_tools:
        return CHAT_TOOLS_MAX_TOKENS
    if _is_deliverable_request(user_text):
        return CHAT_DELIVERABLE_MAX_TOKENS
    return CHAT_SIMPLE_MAX_TOKENS


def _strip_chat_filler_prefix(text: str) -> str:
    """Quita muletilla inicial sin colapsar saltos de línea del markdown."""
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned
    lines = cleaned.splitlines()
    if len(lines) == 1:
        return strip_voice_filler_prefix(cleaned)
    first = strip_voice_filler_prefix(lines[0].strip())
    if not first:
        return "\n".join(line for line in lines[1:] if line is not None).strip()
    return "\n".join([first, *lines[1:]]).strip()


def _finalize_chat_reply(text: str) -> str:
    """Post-proceso de chat de texto: dedupe y ortografía, sin recorte de voz."""
    from app.services.copy_quality import polish_spanish_for_user

    cleaned = _dedupe_chat_reply(text)
    cleaned = _strip_chat_filler_prefix(cleaned)
    cleaned = cleaned or (text or "").strip()
    return polish_spanish_for_user(cleaned)


def _ensure_chat_reply_quality(
    reply: str,
    *,
    user_text: str,
) -> str:
    """Evita respuestas KB/genéricas cuando el usuario pidió investigación web."""
    from app.services.cognitive_intents import is_web_research_intent, requires_live_web
    from app.services.retell_custom_llm import is_unwanted_voice_reply

    if not user_text or not reply:
        return reply
    if not (requires_live_web(user_text) or is_web_research_intent(user_text)):
        return reply
    if not is_unwanted_voice_reply(reply, user_text=user_text):
        return reply
    logger.warning("[CHAT] Unwanted reply for web query — direct search fallback")
    direct = _reply_from_direct_search(user_text)
    return direct or reply


def _ensure_chat_reply_no_kb_leak(
    reply: str,
    *,
    user_id: str,
    user_text: str,
    anthropic_key: str,
    google_key: str,
    gemini_model: str,
    system: str,
    messages: list[dict[str, Any]],
    conversation_id: str | None,
    pdf_attachment: dict[str, Any] | None,
    image_attachment: dict[str, Any] | None,
) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None]:
    if not _contains_internal_kb_leak(reply):
        return reply, pdf_attachment, image_attachment

    logger.warning("[CHAT] Internal KB leak detected — regenerating reply")
    retry_messages = [
        *messages,
        {"role": "assistant", "content": reply},
        {"role": "user", "content": INTERNAL_KB_LEAK_RETRY_MESSAGE},
    ]
    try:
        regen, pdf2, img2 = _complete_chat_resilient(
            user_id,
            user_text=user_text,
            anthropic_key=anthropic_key,
            google_key=google_key,
            gemini_model=gemini_model,
            system=system,
            messages=retry_messages,
            conversation_id=conversation_id,
        )
        if not pdf_attachment and pdf2:
            pdf_attachment = pdf2
        if not image_attachment and img2:
            image_attachment = img2
        if regen and not _contains_internal_kb_leak(regen):
            return regen, pdf_attachment, image_attachment
        if regen:
            stripped = _strip_internal_kb_from_reply(regen)
            if stripped and not _contains_internal_kb_leak(stripped):
                return stripped, pdf_attachment, image_attachment
    except Exception:  # noqa: BLE001
        logger.exception("[CHAT] KB leak regeneration failed")

    stripped = _strip_internal_kb_from_reply(reply)
    if stripped and not _contains_internal_kb_leak(stripped):
        return stripped, pdf_attachment, image_attachment
    return reply, pdf_attachment, image_attachment


def _promised_web_search_without_tool(text: str) -> bool:
    """True si promete buscar pero no entrega resultado sustantivo."""
    t = (text or "").strip()
    if not t:
        return False
    if _has_hallucinated_tool_code(t):
        return True
    promised = bool(
        re.search(
            r"\b(buscar[eé]|voy a buscar|investigar[eé]|consultar[eé] en internet|"
            r"d[eé]jame buscar|perm[ií]teme buscar)\b",
            t,
            re.I,
        )
    )
    if not promised:
        return False
    substantive = len(re.sub(r"[^a-záéíóúñA-ZÁÉÍÓÚÑ0-9]", "", t)) > 80
    return not substantive


def _is_empty_or_placeholder_response(text: str) -> bool:
    stripped = (text or "").strip()
    if len(stripped) < 10:
        return True
    if stripped in ("...", "…", "....", "**", "---", "----"):
        return True
    if stripped.endswith(("...", "…")) and all(c in ".… \t\n\r" for c in stripped):
        return True
    if re.fullmatch(r"[-*_`\s]+", stripped):
        return True
    if re.search(r"sugerencia.*(?:instagram|facebook)|opci[oó]n\s+1\s*:", stripped, re.I):
        if len(stripped) < 120 or re.search(r"\*\*[^*]{0,20}$", stripped):
            return True
    return False


def _suggest_social_caption(
    platform: str,
    user_text: str,
    history: list[dict[str, str]],
) -> str:
    settings = get_settings()
    google_key = settings.google_api_key.strip()
    if not google_key:
        return "Un momento especial compartido desde CED. #CED #EvoluciónDigital"
    messages: list[dict[str, str]] = []
    for row in history[-8:]:
        role = row.get("role")
        content = (row.get("content") or "").strip()
        if not content:
            continue
        if role == "model":
            messages.append({"role": "assistant", "content": content})
        elif role == "user":
            messages.append({"role": "user", "content": content})
    messages.append(
        {
            "role": "user",
            "content": (
                f"El usuario subió una imagen y quiere publicar en {platform}. "
                f"Escribe SOLO el caption del post: título breve, 1-2 frases y 3-5 hashtags. "
                f"Sin introducción, sin «aquí tienes», sin markdown vacío. "
                f"Contexto: {user_text}"
            ),
        }
    )
    system = (
        "Eres CED. Genera captions atractivos para redes en español latinoamericano. "
        "Responde solo con el texto del post."
    )
    try:
        return _gemini_simple_reply(
            api_key=google_key,
            model=_gemini_chat_model(),
            system=system,
            messages=messages,
        )
    except Exception:  # noqa: BLE001
        return "Un momento especial compartido desde CED. #CED #EvoluciónDigital"


def _recent_chat_context(history: list[dict[str, str]], *, limit: int = 6) -> str:
    chunks: list[str] = []
    for row in history[-limit:]:
        content = (row.get("content") or "").strip()
        if content:
            chunks.append(content)
    return " ".join(chunks)


def _format_image_generation_error(raw_error: str) -> str:
    err = (raw_error or "").strip() or "No pude generar la imagen."
    if err.lower().startswith("no pude generar la imagen"):
        return err
    return f"No pude generar la imagen: {err}"


def _chat_image_attachment(
    url: str,
    *,
    caption: str,
    quality: str | None = None,
) -> dict[str, Any]:
    label = (caption or "Imagen generada").strip()
    payload: dict[str, Any] = {
        "url": url,
        "caption": label,
        "prompt": label,
    }
    if quality:
        payload["quality"] = quality
    return payload


def _generate_chat_image_with_reference(
    user_id: str,
    *,
    prompt: str,
    reference_bytes: bytes,
    media_type: str,
    style_mode: str = "edit",
    quality: str = "auto",
) -> dict[str, Any]:
    from app.services.image_reference_generator import generate_image_with_reference

    return generate_image_with_reference(
        user_id=user_id,
        prompt=prompt,
        reference_image=reference_bytes,
        content_type=media_type,
        style_mode=style_mode,
        quality=quality,
    )


def _needs_chat_tools(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if is_pdf_intent(t):
        return False
    if is_generate_image_intent(t):
        img_prompt = parse_generate_image_prompt(t)
        if not img_prompt or len(t) > DIRECT_IMAGE_MAX_CHARS:
            return True
        return False
    return bool(_TOOLS_KEYWORDS.search(t))


def _build_chat_system(
    user_id: str,
    user_text: str,
    route: Any | None = None,
    conversation_id: str | None = None,
) -> str:
    from app.services.system_clock import clock_context_block

    parts = [_chat_system_for_user(user_id), clock_context_block()]
    if conversation_id:
        from app.services.publish_image_context import has_publishable_image

        if has_publishable_image(user_id, conversation_id):
            parts.append(
                "IMAGEN DISPONIBLE EN ESTA CONVERSACIÓN:\n"
                "El usuario ya subió una imagen al chat. Está lista para publicar en "
                "Instagram o Facebook.\n"
                "Al invocar publicar_instagram o publicar_facebook usa "
                "use_last_uploaded_image=true.\n"
                "PROHIBIDO pedir URL de imagen al usuario."
            )
    if _wants_viral_knowledge(user_text):
        parts.append(CED_VIRAL_KNOWLEDGE_2026)
        parts.append(CED_MEMORY_USAGE_RULES)
    extras = build_chat_system_extras(user_id, route)
    if extras:
        parts.append(extras)
    return "\n\n".join(parts)


def _build_chat_system_light(user_id: str, user_text: str) -> str:
    """System prompt mínimo para streaming — sin consultas DB (meta, dirección, KB)."""
    from app.services.system_clock import clock_context_block

    parts = [CHAT_SYSTEM_BASE, clock_context_block()]
    if _wants_viral_knowledge(user_text):
        parts.append(CED_VIRAL_KNOWLEDGE_2026)
        parts.append(CED_MEMORY_USAGE_RULES)
    return "\n\n".join(parts)


def _chat_system_for_user(user_id: str) -> str:
    conn = supabase_db.get_meta_connection(user_id)
    if conn and conn.get("access_token"):
        username = conn.get("ig_username") or "Instagram"
        return (
            f"{CHAT_SYSTEM_BASE}\n\n"
            f"Estado Meta del usuario: CONECTADO (@{username}). "
            "Puedes publicar con las herramientas cuando confirme el texto."
        )
    return (
        f"{CHAT_SYSTEM_BASE}\n\n"
        "Estado Meta del usuario: NO conectado. "
        "Para publicar directo, debe usar Conectar Redes en el dashboard."
    )


class TextChatError(ValueError):
    """Error de chat con código HTTP sugerido para la API."""

    def __init__(self, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.http_status = http_status
    pass


def _message_limit_for_user(user_id: str) -> int:
    from app.deps.plan_access import chat_message_limit

    return chat_message_limit(user_id)


def count_user_messages_today(user_id: str, *, channel: str = "text") -> int:
    try:
        client = supabase_db._client()
        today = date.today().isoformat()
        convs = (
            client.table("voice_conversations")
            .select("id")
            .eq("user_id", user_id)
            .eq("channel", channel)
            .execute()
        )
        conv_ids = [c["id"] for c in (convs.data or [])]
        if not conv_ids:
            return 0
        msgs = (
            client.table("voice_messages")
            .select("id, created_at")
            .in_("conversation_id", conv_ids)
            .eq("role", "user")
            .gte("created_at", f"{today}T00:00:00")
            .execute()
        )
        return len(msgs.data or [])
    except Exception:  # noqa: BLE001
        return 0


def chat_status(user_id: str, *, include_welcome: bool = False) -> dict[str, Any]:
    from app.services.admin_users import get_user_access

    allowed, reason, _ = get_user_access(user_id)
    trial_expired = not allowed and reason == "trial_expired"
    limit = _message_limit_for_user(user_id)
    used = _cached_messages_today(user_id)
    unlimited = limit < 0
    remaining = -1 if unlimited else max(0, limit - used)
    blocked = not unlimited and limit > 0 and used >= limit
    welcome_message = ""
    if include_welcome:
        try:
            from app.services.session_memory import build_text_chat_welcome

            welcome_message = build_text_chat_welcome(user_id)
        except Exception:  # noqa: BLE001
            pass
    return {
        "messages_used_today": used,
        "messages_limit_daily": limit if limit >= 0 else None,
        "unlimited": unlimited,
        "remaining_today": remaining if remaining >= 0 else None,
        "blocked": blocked,
        "trial_expired": trial_expired,
        "welcome_message": welcome_message,
    }


def end_text_conversation(user_id: str, conversation_id: str) -> dict[str, Any]:
    """Cierra conversación de chat y guarda memoria sesión a sesión."""
    from datetime import datetime, timezone

    cid = (conversation_id or "").strip()
    if not cid:
        raise TextChatError("conversation_id requerido.", http_status=400)

    conv = supabase_db.get_conversation(cid, user_id)
    if not conv or conv.get("channel") != "text":
        raise TextChatError("Conversación no encontrada.", http_status=404)

    msgs = supabase_db.get_conversation_messages(cid, user_id, limit=80)
    user_turns = sum(1 for m in msgs if str(m.get("role") or "") == "user")
    if user_turns < 1:
        return {"ok": True, "saved": False, "reason": "too_short"}

    started_epoch = __import__("time").time()
    created_raw = conv.get("created_at")
    if created_raw:
        try:
            created = datetime.fromisoformat(str(created_raw).replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            started_epoch = created.timestamp()
        except ValueError:
            pass

    from app.services.conversation_memory import finalize_session_async

    finalize_session_async(
        user_id=user_id,
        session_id=cid,
        conversation_id=cid,
        started_at_epoch=started_epoch,
        channel="text",
    )
    return {"ok": True, "saved": True, "conversation_id": cid}


def _anthropic_messages(history: list[dict[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in history:
        role = row.get("role")
        content = (row.get("content") or "").strip()
        if not content:
            continue
        if role == "model":
            out.append({"role": "assistant", "content": content})
        elif role == "user":
            out.append({"role": "user", "content": content})
    return out[-20:]


def _run_chat_tool(
    user_id: str,
    name: str,
    tool_input: dict[str, Any],
    *,
    conversation_id: str | None = None,
    chat_messages: list[dict[str, Any]] | None = None,
) -> str:
    try:
        if name == "search_web":
            from app.services.gemini_grounded import execute_search_web_sync

            query = str(tool_input.get("query") or "").strip()
            kind = str(tool_input.get("kind") or "general").strip() or "general"
            if not query:
                return json.dumps({"ok": False, "error": "query vacía", "status": "error"})
            logger.info("[CHAT] search_web query=%s kind=%s", query[:80], kind)
            result = execute_search_web_sync(query, kind=kind)
            return json.dumps(result)
        if name == "consultar_redes_conectadas":
            conn = supabase_db.get_meta_connection(user_id)
            if not conn or not conn.get("access_token"):
                return json.dumps({"connected": False})
            return json.dumps(
                {
                    "connected": True,
                    "instagram_username": conn.get("ig_username"),
                    "page_id": conn.get("page_id"),
                }
            )
        if name == "publicar_facebook":
            from app.services.publish_image_context import resolve_image_for_publishing
            from app.services.publish_text import sanitize_publish_caption

            use_last = tool_input.get("use_last_uploaded_image", True)
            resolved = resolve_image_for_publishing(
                user_id,
                conversation_id,
                use_last_uploaded_image=use_last is not False,
                image_url=tool_input.get("image_url"),
                image_data=tool_input.get("image_data"),
            )
            if not resolved.get("ok"):
                return json.dumps(
                    {
                        "ok": False,
                        "error": resolved.get("error"),
                        "message": resolved.get("message"),
                    }
                )
            result = publish_facebook(
                user_id,
                sanitize_publish_caption(str(tool_input.get("message") or "")),
                image_url=resolved.get("url"),
                image_data=resolved.get("data"),
            )
            return json.dumps(result)
        if name == "publicar_instagram":
            from app.services.publish_image_context import resolve_image_for_publishing
            from app.services.publish_text import sanitize_publish_caption

            use_last = tool_input.get("use_last_uploaded_image", True)
            resolved = resolve_image_for_publishing(
                user_id,
                conversation_id,
                use_last_uploaded_image=use_last is not False,
                image_url=tool_input.get("image_url"),
                image_data=tool_input.get("image_data"),
            )
            if not resolved.get("ok"):
                return json.dumps(
                    {
                        "ok": False,
                        "error": resolved.get("error"),
                        "message": resolved.get("message"),
                    }
                )
            result = publish_instagram(
                user_id,
                sanitize_publish_caption(str(tool_input.get("caption") or "")),
                image_url=resolved.get("url"),
                image_data=resolved.get("data"),
            )
            return json.dumps(result)
        if name == "generar_pdf":
            from app.deps.plan_access import effective_plan_limits

            limits, reason, _ = effective_plan_limits(user_id)
            if reason == "trial_expired":
                return json.dumps(
                    {"ok": False, "error": "Tu prueba terminó. Elige un plan en Precios."},
                )
            if not limits.pdf_reports:
                return json.dumps(
                    {
                        "ok": False,
                        "error": "Los PDFs requieren plan Élite o Founding. Mejora en /pricing.",
                    },
                )
            title, content = normalize_pdf_fields(tool_input)
            fallbacks = assistant_fallback_texts_from_messages(chat_messages or [])
            user_texts = user_texts_from_messages(chat_messages or [])
            user_request = user_texts[-1] if user_texts else title
            try:
                artifact = store_pdf_with_timeout(
                    user_id=user_id,
                    title=title,
                    content=content,
                    conversation_id=conversation_id,
                    fallback_texts=fallbacks,
                    user_request=user_request,
                )
            except TimeoutError:
                return json.dumps(
                    {
                        "ok": False,
                        "error": "No pude generar el PDF a tiempo. Intenta de nuevo.",
                    }
                )
            except (ValueError, RuntimeError) as exc:
                return json.dumps({"ok": False, "error": str(exc) or "PDF failed"})
            return json.dumps(
                {
                    "ok": True,
                    "file_id": artifact.file_id,
                    "filename": artifact.filename,
                    "title": artifact.title,
                    "download_path": f"/v1/pdf/download/{artifact.file_id}",
                }
            )
        if name == "generate_image":
            from app.services.gemini_images import generate_image
            from app.services.marketing_creative import resolve_image_creation_from_text

            plan_id = None
            try:
                sub = supabase_db.get_subscription(user_id)
                plan_id = sub.get("plan_id") if sub else None
            except Exception:  # noqa: BLE001
                pass
            prompt = str(tool_input.get("prompt") or "").strip()
            prior_rows: list[dict[str, str]] = []
            if chat_messages:
                prior_rows = [
                    {"content": str(m.get("content") or "")}
                    for m in chat_messages[:-1]
                    if isinstance(m, dict)
                ]
            prior = _recent_chat_context(prior_rows)
            creation = resolve_image_creation_from_text(prompt, prior_rows)
            quality = str(tool_input.get("quality") or "auto")
            if creation:
                result = generate_image(
                    user_id=user_id,
                    plan_id=plan_id,
                    prompt=creation["internal_prompt"],
                    quality=quality,
                    context="",
                    display_label=creation["display_label"],
                )
            else:
                result = generate_image(
                    user_id=user_id,
                    plan_id=plan_id,
                    prompt=prompt,
                    quality=quality,
                    context=prior,
                )
            if result.get("ok") and result.get("url"):
                result["prompt"] = prompt
                if conversation_id:
                    from app.services.publish_image_context import register_text_chat_image_url

                    register_text_chat_image_url(
                        user_id,
                        conversation_id,
                        str(result["url"]),
                    )
            return json.dumps(result)
        if name == "recall_previous_conversations":
            from app.services.conversation_memory import (
                format_recall_for_voice,
                recall_previous_conversations,
            )

            query = str(tool_input.get("query") or "").strip()
            days = int(tool_input.get("days_back") or 30)
            data = recall_previous_conversations(user_id, query, days_back=days)
            return json.dumps({**data, "spoken": format_recall_for_voice(data)})
        if name == "save_to_long_term_memory":
            from app.services.conversation_memory import save_long_term_memory

            return json.dumps(
                save_long_term_memory(
                    user_id,
                    category=str(tool_input.get("category") or "fact"),
                    key=str(tool_input.get("key") or ""),
                    value=str(tool_input.get("value") or ""),
                    importance=int(tool_input.get("importance") or 5),
                )
            )
        return json.dumps({"error": f"Herramienta desconocida: {name}"})
    except MetaSocialError as exc:
        return json.dumps({"ok": False, "error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        logger.exception("[CHAT] tool %s failed", name)
        return json.dumps({"ok": False, "error": str(exc)[:200]})


def _anthropic_fallback_statuses() -> tuple[int, ...]:
    return (401, 403, 429, 529)


def _should_fallback_anthropic_to_gemini(exc: httpx.HTTPStatusError, *, has_gemini: bool) -> bool:
    if not has_gemini:
        return False
    return exc.response.status_code in _anthropic_fallback_statuses()


def _trim_system(system: str) -> str:
    text = (system or "").strip()
    if len(text) <= CHAT_SYSTEM_MAX_CHARS:
        return text
    return text[: CHAT_SYSTEM_MAX_CHARS - 24] + "\n… [contexto truncado]"


def _anthropic_request(
    *,
    api_key: str,
    system: str,
    messages: list[dict[str, Any]],
    model: str = CHAT_MODEL,
    max_tokens: int = CHAT_TOOLS_MAX_TOKENS,
    with_tools: bool = True,
    timeout: float = 90.0,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    if with_tools:
        payload["tools"] = CHAT_TOOLS
    last_response: httpx.Response | None = None
    for attempt in range(3):
        with httpx.Client(timeout=timeout) as client:
            res = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
            )
            last_response = res
            if res.status_code == 429 and attempt < 2:
                retry_hdr = (res.headers.get("retry-after") or "").strip()
                try:
                    wait_s = min(float(retry_hdr), 8.0) if retry_hdr else 1.5 * (attempt + 1)
                except ValueError:
                    wait_s = 1.5 * (attempt + 1)
                logger.warning("[CHAT] Anthropic 429 — reintento %s en %.1fs", attempt + 1, wait_s)
                time.sleep(wait_s)
                continue
            res.raise_for_status()
            return res.json()
    if last_response is not None:
        last_response.raise_for_status()
    raise TextChatError("No hubo respuesta del proveedor de chat.")


def _anthropic_simple_reply(
    *,
    api_key: str,
    system: str,
    messages: list[dict[str, Any]],
    max_tokens: int = CHAT_SIMPLE_MAX_TOKENS,
) -> str:
    data = _anthropic_request(
        api_key=api_key,
        system=system,
        messages=messages,
        model=CHAT_MODEL_FAST,
        max_tokens=max_tokens,
        with_tools=False,
        timeout=45.0,
    )
    reply = _final_text_from_response(data)
    if not reply:
        raise TextChatError("Respuesta vacía del asistente.")
    return reply


def _gemini_simple_reply(
    *,
    api_key: str,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
    max_tokens: int = CHAT_SIMPLE_MAX_TOKENS,
    allow_llama: bool = True,
) -> str:
    from app.services.llama_service import (
        LlamaNotReadyError,
        call_llama_chat,
        should_route_to_llama,
        use_llama,
    )

    if allow_llama and use_llama():
        if should_route_to_llama():
            try:
                return call_llama_chat(
                    system=system,
                    messages=messages,
                    temperature=0.4,
                    max_tokens=max_tokens,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("[CHAT] Llama simple failed, fallback cloud: %s", exc)
        else:
            logger.warning("[CHAT] Ollama sin modelo listo — fallback cloud inmediato")

    from google import genai
    from google.genai import types

    contents: list[types.Content] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        if role == "user":
            contents.append(types.Content(role="user", parts=[types.Part(text=content)]))
        elif role == "assistant":
            contents.append(types.Content(role="model", parts=[types.Part(text=content)]))

    if not contents:
        raise TextChatError("Sin mensajes para el asistente.")

    model_name = (model or CHAT_GEMINI_MODEL).strip() or CHAT_GEMINI_MODEL
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            client = _gemini_client(api_key)
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=_trim_system(system),
                    temperature=0.4,
                    max_output_tokens=max_tokens,
                ),
            )
            text = (response.text or "").strip()
            if text:
                return text
            raise TextChatError("Respuesta vacía del asistente.", http_status=503)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < 2:
                wait_s = 1.5 * (attempt + 1)
                logger.warning("[CHAT] Gemini reintento %s en %.1fs: %s", attempt + 1, wait_s, exc)
                time.sleep(wait_s)
                continue
            break
    if isinstance(last_exc, TextChatError):
        raise last_exc
    raise TextChatError(
        "Gemini no respondió. Intenta de nuevo en un momento.",
        http_status=503,
    ) from last_exc


def _simple_chat_cascade(
    *,
    anthropic_key: str,
    google_key: str,
    gemini_model: str,
    system: str,
    messages: list[dict[str, Any]],
    user_text: str = "",
    max_tokens: int | None = None,
) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None]:
    """Gemini primero; Claude como respaldo. Con llm_provider=llama, solo Llama local."""
    from app.services.llama_service import should_route_to_llama, use_llama

    last_exc: Exception | None = None
    token_budget = max_tokens or _chat_max_tokens(user_text)

    if use_llama() and should_route_to_llama():
        try:
            reply = _gemini_simple_reply(
                api_key="",
                model="",
                system=system,
                messages=messages,
                max_tokens=token_budget,
            )
            return reply, None, None
        except Exception as exc:  # noqa: BLE001
            logger.warning("[CHAT] Llama cascade failed, fallback cloud: %s", exc)
            last_exc = exc
    elif use_llama():
        logger.warning("[CHAT] Llama configurado pero modelo no listo — cascade cloud")

    if google_key:
        try:
            reply = _gemini_simple_reply(
                api_key=google_key,
                model=gemini_model,
                system=system,
                messages=messages,
                max_tokens=token_budget,
            )
            return reply, None, None
        except Exception as exc:  # noqa: BLE001
            logger.warning("[CHAT] Gemini simple failed: %s", exc)
            last_exc = exc

    if anthropic_key:
        try:
            reply = _anthropic_simple_reply(
                api_key=anthropic_key,
                system=system,
                messages=messages,
                max_tokens=token_budget,
            )
            return reply, None, None
        except Exception as exc:  # noqa: BLE001
            logger.warning("[CHAT] Anthropic simple failed: %s", exc)
            last_exc = exc

    if isinstance(last_exc, httpx.HTTPStatusError):
        raise last_exc
    if isinstance(last_exc, TextChatError):
        raise last_exc
    raise TextChatError(
        "Servicio de chat temporalmente no disponible. Intenta de nuevo en unos minutos.",
        http_status=503,
    )


def _maybe_complete_deliverable_reply(
    reply: str,
    *,
    user_text: str,
    anthropic_key: str,
    google_key: str,
    gemini_model: str,
    system: str,
    messages: list[dict[str, Any]],
) -> str:
    if not _is_incomplete_deliverable(reply, user_text):
        return reply
    logger.warning("[CHAT] Incomplete deliverable — requesting continuation")
    continuation_messages = [
        *messages,
        {"role": "assistant", "content": reply},
        {"role": "user", "content": DELIVERABLE_CONTINUATION_MESSAGE},
    ]
    try:
        cont_reply, _, _ = _simple_chat_cascade(
            anthropic_key=anthropic_key,
            google_key=google_key,
            gemini_model=gemini_model,
            system=system,
            messages=continuation_messages,
            user_text=user_text,
            max_tokens=CHAT_DELIVERABLE_MAX_TOKENS,
        )
    except Exception:  # noqa: BLE001
        logger.exception("[CHAT] deliverable continuation failed")
        return reply
    if not cont_reply or len(cont_reply.strip()) <= len(reply.strip()):
        return reply
    return merge_deliverable_continuation(reply, cont_reply)


def _final_text_from_response(data: dict[str, Any]) -> str:
    blocks = data.get("content") or []
    return "".join(
        b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"
    ).strip()


def _pdf_attachment_from_artifact(artifact: Any) -> dict[str, Any]:
    return {
        "file_id": artifact.file_id,
        "filename": artifact.filename,
        "title": artifact.title,
        "download_path": f"/v1/pdf/download/{artifact.file_id}",
    }


def _strip_pdf_markdown_links(text: str) -> str:
    cleaned = re.sub(
        r"\[([^\]]*)\]\([^)]*\/pdf\/download\/[a-f0-9]+[^)]*\)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"https?://[^\s)]+(?:/v1/pdf|/api/ced/pdf)/download/[a-f0-9]+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"/(?:v1/pdf|api/ced/pdf)/download/[a-f0-9]+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _extract_pdf_from_tool_result(result: str) -> dict[str, Any] | None:
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and data.get("ok") and data.get("file_id"):
        return {
            "file_id": data["file_id"],
            "filename": data.get("filename") or "documento.pdf",
            "title": data.get("title") or "Documento CED",
            "download_path": data.get("download_path"),
        }
    return None


def _extract_image_from_tool_result(result: str) -> dict[str, Any] | None:
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and data.get("ok") and data.get("url"):
        caption = str(data.get("caption") or data.get("prompt") or "Imagen generada")
        return {
            "url": str(data["url"]),
            "caption": caption,
            "prompt": caption,
            "quality": data.get("quality"),
        }
    return None


def _complete_chat_with_tools(
    user_id: str,
    *,
    api_key: str,
    system: str,
    messages: list[dict[str, Any]],
    conversation_id: str | None = None,
    allow_hallucination_retry: bool = True,
    allow_empty_retry: bool = True,
) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None]:
    pdf_attachment: dict[str, Any] | None = None
    image_attachment: dict[str, Any] | None = None
    tool_max_tokens = _chat_max_tokens(_last_user_text(messages), with_tools=True)
    for _ in range(4):
        data = _anthropic_request(
            api_key=api_key,
            system=system,
            messages=messages,
            max_tokens=tool_max_tokens,
        )
        blocks = data.get("content") or []
        tool_uses = [b for b in blocks if isinstance(b, dict) and b.get("type") == "tool_use"]
        if not tool_uses:
            reply = _final_text_from_response(data)
            if reply:
                if pdf_attachment:
                    reply = _strip_pdf_markdown_links(reply)
                hallucination = _tool_hallucination_kind(reply)
                if (
                    allow_hallucination_retry
                    and hallucination
                    and not image_attachment
                    and not pdf_attachment
                ):
                    logger.warning("[CHAT] Hallucinated tool (%s), retrying", hallucination)
                    retry_messages = [
                        *messages,
                        {"role": "assistant", "content": reply},
                        {
                            "role": "user",
                            "content": _hallucination_retry_message(hallucination),
                        },
                    ]
                    return _complete_chat_with_tools(
                        user_id,
                        api_key=api_key,
                        system=system,
                        messages=retry_messages,
                        conversation_id=conversation_id,
                        allow_hallucination_retry=False,
                        allow_empty_retry=allow_empty_retry,
                    )
                if (
                    not allow_hallucination_retry
                    and _has_hallucinated_tool_code(reply)
                    and not image_attachment
                    and not pdf_attachment
                ):
                    pdf_fix = _try_pdf_from_hallucinated_reply(
                        user_id,
                        reply=reply,
                        user_text=_last_user_text(messages),
                        messages=messages,
                        conversation_id=conversation_id,
                    )
                    if pdf_fix:
                        return pdf_fix
                    logger.warning("[CHAT] tool_code alucinado tras retry — búsqueda directa")
                    direct = _resolve_hallucinated_tool_code_reply(
                        reply,
                        messages,
                        user_id=user_id,
                        user_text=_last_user_text(messages),
                    )
                    if direct:
                        return direct, pdf_attachment, image_attachment
                if (
                    allow_empty_retry
                    and _is_empty_or_placeholder_response(reply)
                    and not image_attachment
                    and not pdf_attachment
                ):
                    logger.warning("[CHAT] Empty or placeholder response, retrying")
                    retry_messages = [
                        *messages,
                        {"role": "assistant", "content": reply},
                        {"role": "user", "content": EMPTY_RESPONSE_RETRY_USER_MESSAGE},
                    ]
                    return _complete_chat_with_tools(
                        user_id,
                        api_key=api_key,
                        system=system,
                        messages=retry_messages,
                        conversation_id=conversation_id,
                        allow_hallucination_retry=False,
                        allow_empty_retry=False,
                    )
                if _has_hallucinated_tool(reply) and not image_attachment and not pdf_attachment:
                    return HALLUCINATION_FALLBACK_REPLY, None, None
                return reply, pdf_attachment, image_attachment
            raise TextChatError("Respuesta vacía del asistente.")

        messages.append({"role": "assistant", "content": blocks})
        tool_results: list[dict[str, Any]] = []
        for tool in tool_uses:
            tool_input = tool.get("input") if isinstance(tool.get("input"), dict) else {}
            result = _run_chat_tool(
                user_id,
                str(tool.get("name") or ""),
                tool_input,
                conversation_id=conversation_id,
                chat_messages=messages,
            )
            maybe_pdf = _extract_pdf_from_tool_result(result)
            if maybe_pdf:
                pdf_attachment = maybe_pdf
            maybe_img = _extract_image_from_tool_result(result)
            if maybe_img:
                image_attachment = maybe_img
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool.get("id"),
                    "content": result,
                }
            )
        messages.append({"role": "user", "content": tool_results})

    raise TextChatError("Demasiados pasos de herramientas. Intenta con un pedido más simple.")


def _complete_chat_resilient(
    user_id: str,
    *,
    user_text: str,
    anthropic_key: str,
    google_key: str,
    gemini_model: str,
    system: str,
    messages: list[dict[str, Any]],
    conversation_id: str | None = None,
) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None]:
    """Gemini para chat normal; Claude para herramientas / análisis."""
    trimmed_system = _trim_system(system)

    if not _needs_chat_tools(user_text):
        reply, pdf_attachment, image_attachment = _simple_chat_cascade(
            anthropic_key=anthropic_key,
            google_key=google_key,
            gemini_model=gemini_model,
            system=trimmed_system,
            messages=messages,
            user_text=user_text,
        )
        if _has_hallucinated_tool_code(reply):
            pdf_fix = _try_pdf_from_hallucinated_reply(
                user_id,
                reply=reply,
                user_text=user_text,
                messages=messages,
                conversation_id=conversation_id,
            )
            if pdf_fix:
                return pdf_fix
            logger.warning("[CHAT] tool_code alucinado en simple path — búsqueda directa")
            direct = _resolve_hallucinated_tool_code_reply(
                reply,
                messages,
                user_id=user_id,
                user_text=user_text,
            )
            if direct:
                return direct, pdf_attachment, image_attachment
        if anthropic_key and (
            _has_hallucinated_tool(reply) or _promised_web_search_without_tool(reply)
        ):
            logger.warning("[CHAT] Hallucinated tool/search in simple path — escalating to tools")
            return _complete_chat_with_tools(
                user_id,
                api_key=anthropic_key,
                system=trimmed_system,
                messages=messages,
                conversation_id=conversation_id,
            )
        if _is_empty_or_placeholder_response(reply) and anthropic_key:
            logger.warning("[CHAT] Empty response in simple path — escalating to tools")
            return _complete_chat_with_tools(
                user_id,
                api_key=anthropic_key,
                system=trimmed_system,
                messages=messages,
                conversation_id=conversation_id,
            )
        reply = _maybe_complete_deliverable_reply(
            reply,
            user_text=user_text,
            anthropic_key=anthropic_key,
            google_key=google_key,
            gemini_model=gemini_model,
            system=trimmed_system,
            messages=messages,
        )
        return reply, pdf_attachment, image_attachment

    if anthropic_key:
        try:
            return _complete_chat_with_tools(
                user_id,
                api_key=anthropic_key,
                system=trimmed_system,
                messages=messages,
                conversation_id=conversation_id,
            )
        except httpx.HTTPStatusError as exc:
            if google_key and _should_fallback_anthropic_to_gemini(exc, has_gemini=True):
                logger.warning(
                    "[CHAT] Claude tools %s — fallback Gemini",
                    exc.response.status_code,
                )
            else:
                raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("[CHAT] Claude tools failed: %s", exc)

    if google_key:
        reply = _gemini_simple_reply(
            api_key=google_key,
            model=gemini_model,
            system=trimmed_system,
            messages=messages,
            max_tokens=_chat_max_tokens(user_text),
        )
        reply = _maybe_complete_deliverable_reply(
            reply,
            user_text=user_text,
            anthropic_key=anthropic_key,
            google_key=google_key,
            gemini_model=gemini_model,
            system=trimmed_system,
            messages=messages,
        )
        return reply, None, None

    raise TextChatError(
        "Servicio de chat temporalmente no disponible. Configura GOOGLE_API_KEY.",
        http_status=503,
    )


def send_message(
    user_id: str,
    *,
    content: str,
    conversation_id: str | None = None,
    image_bytes: bytes | None = None,
    image_media_type: str | None = None,
) -> dict[str, Any]:
    text = content.strip()
    if not text and not image_bytes:
        raise TextChatError("Mensaje vacío.")
    if text and len(text) > 8000:
        raise TextChatError("Mensaje demasiado largo.")

    status = chat_status(user_id)
    if status["blocked"]:
        raise TextChatError(
            "Alcanzaste el límite de mensajes de hoy. Mejora tu plan o vuelve mañana.",
            http_status=429,
        )

    from app.deps.auth import is_super_admin
    from app.deps.plan_access import chat_message_limit
    from app.services.chat_rate_limit import check_chat_rate_limit

    profile = supabase_db.get_profile(user_id) or {}
    admin = is_super_admin(profile.get("email"), profile.get("role"))
    unlimited_plan = chat_message_limit(user_id) < 0
    if not admin and not unlimited_plan:
        allowed, retry_after = check_chat_rate_limit(
            user_id,
            is_admin=admin,
            unlimited_plan=unlimited_plan,
        )
        if not allowed:
            raise TextChatError(
                f"Has alcanzado el límite de mensajes. Espera {retry_after} segundos e intenta de nuevo.",
                http_status=429,
            )

    settings = get_settings()
    anthropic_key = settings.anthropic_api_key.strip()
    google_key = settings.google_api_key.strip()
    gemini_model = _gemini_chat_model()
    if not google_key:
        raise TextChatError(
            "Servicio de chat no disponible. Configura GOOGLE_API_KEY en Railway.",
            http_status=503,
        )

    if conversation_id:
        conv = supabase_db.get_conversation(conversation_id, user_id)
        if not conv or conv.get("channel") != "text":
            raise TextChatError("Conversación no encontrada.")
    else:
        title_source = text or "Imagen adjunta"
        title = title_source[:48] + ("…" if len(title_source) > 48 else "")
        conv = supabase_db.create_conversation(user_id, title=title, channel="text")
        conversation_id = str(conv["id"])

    history = supabase_db.get_conversation_messages(
        conversation_id, user_id, limit=CHAT_HISTORY_LIMIT,
    )
    user_display = text or "📷 Imagen adjunta"
    supabase_db.append_message(
        conversation_id,
        user_id,
        "user",
        user_display,
        session_id=conversation_id,
        channel="text",
    )

    def _finish(
        reply: str,
        *,
        route_meta: dict | None = None,
        pdf: dict[str, Any] | None = None,
        image: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        supabase_db.append_message(
            conversation_id,
            user_id,
            "model",
            reply,
            session_id=conversation_id,
            channel="text",
        )
        updated_status = chat_status(user_id)
        out: dict[str, Any] = {
            "conversation_id": conversation_id,
            "reply": reply,
            "usage": updated_status,
        }
        if route_meta:
            out["cognitive"] = route_meta
        if pdf:
            out["pdf"] = pdf
        if image:
            out["image"] = image
        return out

    from app.services.text_publish_flow import handle_publish_flow_turn

    publish_reply = handle_publish_flow_turn(
        user_id,
        conversation_id,
        text,
        history=history,
        run_tool=_run_chat_tool,
        suggest_caption=_suggest_social_caption,
    )
    if publish_reply:
        return _finish(
            _finalize_chat_reply(publish_reply),
            route_meta={"intent": "publish_flow", "source": "conversation"},
        )

    if not image_bytes:
        instant = _instant_chat_greeting_reply(text)
        if instant:
            return _finish(
                _finalize_chat_reply(instant),
                route_meta={"intent": "greeting", "source": "instant"},
            )
        from app.services.system_clock import try_instant_datetime_reply

        dt_instant = try_instant_datetime_reply(text, history=history)
        if dt_instant:
            return _finish(
                _finalize_chat_reply(dt_instant),
                route_meta={"intent": "datetime", "source": "instant"},
            )

    if image_bytes:
        try:
            from app.services.chat_multimedia import analyze_chat_image
            from app.services.marketing_creative import resolve_image_creation_from_attachment
            from app.services.publish_image_context import register_text_chat_image
            from app.services.publish_text import is_social_publish_intent
            from app.services.text_publish_flow import start_publish_flow_from_image

            register_text_chat_image(
                user_id,
                conversation_id,
                image_bytes,
                image_media_type or "image/jpeg",
            )

            if is_social_publish_intent(text, with_image=True):
                reply = start_publish_flow_from_image(
                    user_id,
                    conversation_id,
                    text,
                    history=history,
                )
                return _finish(
                    reply,
                    route_meta={"intent": "publish_flow", "source": "image_upload"},
                )

            creation = resolve_image_creation_from_attachment(text, history)
            if creation:
                ref_result = _generate_chat_image_with_reference(
                    user_id,
                    prompt=creation["internal_prompt"],
                    reference_bytes=image_bytes,
                    media_type=image_media_type or "image/jpeg",
                    style_mode=creation.get("style_mode") or "edit",
                )
                if ref_result.get("ok") and ref_result.get("url"):
                    from app.services.publish_image_context import register_text_chat_image_url

                    register_text_chat_image_url(
                        user_id,
                        conversation_id,
                        str(ref_result["url"]),
                    )
                    return _finish(
                        creation.get("reply") or "Listo. Aquí está su creativo.",
                        route_meta={"intent": "marketing_creative", "source": "attachment_reference"},
                        image=_chat_image_attachment(
                            str(ref_result["url"]),
                            caption=creation["display_label"],
                            quality=str(ref_result.get("quality") or ""),
                        ),
                    )
                err = str(ref_result.get("error") or "No pude generar el creativo.")
                return _finish(
                    _format_image_generation_error(err),
                    route_meta={"intent": "marketing_creative", "source": "attachment_error"},
                )

            reply = analyze_chat_image(
                user_id,
                image_bytes=image_bytes,
                media_type=image_media_type or "image/jpeg",
                user_text=text,
            )
            return _finish(
                reply,
                route_meta={"intent": "chat_vision", "source": "attachment"},
            )
        except TextChatError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("[CHAT] image attachment failed user=%s", user_id[:8])
            raise TextChatError(
                _format_image_generation_error(str(exc)),
                http_status=503,
            ) from exc

    from app.services.chat_intents import is_casual_chat_interrupt
    from app.services.cognitive_intents import is_conversation_recall_intent
    from app.modules.environment_module import is_environment_intent
    from app.services.session_memory import build_conversation_recall_reply

    if is_conversation_recall_intent(text):
        recall_reply = build_conversation_recall_reply(
            user_id,
            text,
            channel="text",
            history=history,
        )
        return _finish(
            _finalize_chat_reply(recall_reply),
            route_meta={"intent": "memory_recall", "source": "direct"},
        )

    if is_environment_intent(text):
        from app.modules.environment_module import handle_environment_query_sync

        env_result = handle_environment_query_sync(user_id, text)
        return _finish(
            _finalize_chat_reply(str(env_result.get("spoken") or "")),
            route_meta={"intent": "environment", "source": "direct"},
        )

    from app.services.hud_reminders import (
        handle_reminder_create_sync,
        handle_reminder_query_sync,
        is_reminder_intent,
    )
    from app.modules.calendar_module import handle_calendar_query_sync, is_calendar_intent
    from app.modules.finance_module import handle_finance_query_sync, is_finance_intent
    from app.modules.gmail_module import handle_gmail_query_sync, is_gmail_intent

    if is_reminder_intent(text) and re.search(r"recu[eé]rdame", text, re.I):
        reminder_result = handle_reminder_create_sync(user_id, text)
        return _finish(
            _finalize_chat_reply(str(reminder_result.get("spoken") or "")),
            route_meta={"intent": "reminder_create", "source": "direct"},
        )

    if is_reminder_intent(text):
        reminder_result = handle_reminder_query_sync(user_id, text)
        return _finish(
            _finalize_chat_reply(str(reminder_result.get("spoken") or "")),
            route_meta={"intent": "reminder_list", "source": "direct"},
        )

    if is_calendar_intent(text):
        calendar_result = handle_calendar_query_sync(user_id, text)
        return _finish(
            _finalize_chat_reply(str(calendar_result.get("spoken") or "")),
            route_meta={"intent": "calendar", "source": "direct"},
        )

    if is_gmail_intent(text):
        gmail_result = handle_gmail_query_sync(user_id, text)
        return _finish(
            _finalize_chat_reply(str(gmail_result.get("spoken") or "")),
            route_meta={"intent": "gmail", "source": "direct"},
        )

    if is_finance_intent(text):
        finance_result = handle_finance_query_sync(user_id, text)
        return _finish(
            _finalize_chat_reply(str(finance_result.get("spoken") or "")),
            route_meta={"intent": "finance", "source": "direct"},
        )

    pdf_req = resolve_pdf_request(text, history)
    if pdf_req and is_pdf_intent(text):
        pdf_title, pdf_body = pdf_req
        pdf_result = _execute_direct_pdf(
            user_id,
            title=pdf_title,
            content=pdf_body,
            history=history,
            conversation_id=conversation_id,
            user_request=text,
        )
        if pdf_result:
            reply, attachment = pdf_result
            return _finish(
                _finalize_chat_reply(reply),
                route_meta={"intent": "pdf", "source": "direct"},
                pdf=attachment if attachment.get("file_id") else None,
            )

    img_prompt = parse_generate_image_prompt(text)
    followup_prompt = (
        parse_followup_image_prompt(text, history)
        if not img_prompt and not is_casual_chat_interrupt(text)
        else None
    )
    effective_img_prompt = img_prompt or followup_prompt
    if (
        effective_img_prompt
        and not is_casual_chat_interrupt(text)
        and (is_generate_image_intent(text) or followup_prompt)
        and len(text.strip()) <= DIRECT_IMAGE_MAX_CHARS
    ):
        from app.services.gemini_images import generate_image
        from app.services.marketing_creative import (
            build_display_label,
            extract_product_subject,
            is_marketing_creative_intent,
            resolve_image_creation_from_text,
        )

        plan_id = None
        try:
            sub = supabase_db.get_subscription(user_id)
            plan_id = sub.get("plan_id") if sub else None
        except Exception:  # noqa: BLE001
            pass
        chat_context = _recent_chat_context(history)
        creation = resolve_image_creation_from_text(text, history)
        display_label = ""
        success_reply = "Listo. Aquí está tu imagen generada."
        if creation:
            prompt_for_model = creation["internal_prompt"]
            display_label = creation["display_label"]
            success_reply = creation.get("reply") or "Listo. Aquí está su creativo."
            img_result = generate_image(
                user_id=user_id,
                plan_id=plan_id,
                prompt=prompt_for_model,
                quality="auto",
                context="",
                display_label=display_label,
            )
        else:
            if is_marketing_creative_intent(text):
                display_label = build_display_label(extract_product_subject(chat_context))
                success_reply = "Listo, señor. Aquí está su creativo publicitario."
            img_result = generate_image(
                user_id=user_id,
                plan_id=plan_id,
                prompt=effective_img_prompt,
                quality="auto",
                context=chat_context,
                display_label=display_label or None,
            )
        if img_result.get("ok") and img_result.get("url"):
            from app.services.publish_image_context import register_text_chat_image_url

            register_text_chat_image_url(
                user_id,
                conversation_id,
                str(img_result["url"]),
            )
            caption = str(img_result.get("caption") or display_label or "Imagen generada")
            return _finish(
                success_reply,
                route_meta={
                    "intent": "marketing_creative" if creation or is_marketing_creative_intent(text) else "generate_image",
                    "source": "direct",
                },
                image=_chat_image_attachment(
                    str(img_result["url"]),
                    caption=caption,
                    quality=str(img_result.get("quality") or ""),
                ),
            )
        err = str(img_result.get("error") or "No pude generar la imagen.")
        return _finish(
            _format_image_generation_error(err),
            route_meta={"intent": "generate_image", "source": "direct_error"},
        )

    route = route_message(
        user_id,
        text,
        channel="text",
        defer_enrichment=bool(
            _instant_chat_greeting_reply(text)
            or is_casual_chat_interrupt(text)
        ),
    )

    if route.intent == "memory_save" and route.speakable:
        return _finish(route.speakable, route_meta=route.to_dict())

    if route.intent == "memory_recall" and route.speakable:
        return _finish(
            _finalize_chat_reply(route.speakable),
            route_meta=route.to_dict(),
        )

    if route.intent == "web_search" and route.speakable:
        return _finish(
            _finalize_chat_reply(route.speakable),
            route_meta=route.to_dict(),
        )

    messages = _anthropic_messages(history)
    messages.append({"role": "user", "content": text})
    try:
        system = _build_chat_system(user_id, text, route, conversation_id)
    except Exception:  # noqa: BLE001
        logger.exception("[CHAT] fallo armando system prompt — usando base")
        system = _chat_system_for_user(user_id)

    try:
        reply, pdf_attachment, image_attachment = _complete_chat_resilient(
            user_id,
            user_text=text,
            anthropic_key=anthropic_key,
            google_key=google_key,
            gemini_model=gemini_model,
            system=system,
            messages=messages,
            conversation_id=conversation_id,
        )
    except TextChatError:
        raise
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        body = exc.response.text[:300]
        logger.error("[CHAT] provider %s %s", status, body)
        if status in (401, 403):
            raise TextChatError(
                "Servicio de chat temporalmente no disponible. Intenta de nuevo en unos minutos.",
                http_status=503,
            ) from exc
        if status == 404:
            raise TextChatError(
                "Modelo de chat no disponible. Contacta soporte.",
                http_status=503,
            ) from exc
        if status == 429:
            raise TextChatError(
                "Los servidores de IA están ocupados. Reintentando en segundo plano — prueba de nuevo en unos segundos.",
                http_status=503,
            ) from exc
        raise TextChatError(
            "No pude obtener respuesta del asistente. Intenta de nuevo en un momento.",
            http_status=503,
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[CHAT] provider failed: %s", exc)
        raise TextChatError(
            "No pude conectar con el asistente. Intenta de nuevo en un momento.",
            http_status=503,
        ) from exc

    reply, pdf_attachment, image_attachment = _ensure_chat_reply_no_kb_leak(
        reply,
        user_id=user_id,
        user_text=text,
        anthropic_key=anthropic_key,
        google_key=google_key,
        gemini_model=gemini_model,
        system=system,
        messages=messages,
        conversation_id=conversation_id,
        pdf_attachment=pdf_attachment,
        image_attachment=image_attachment,
    )
    reply = _ensure_chat_reply_quality(reply, user_text=text)
    reply = _finalize_chat_reply(reply)

    return _finish(
        reply,
        route_meta=route.to_dict(),
        pdf=pdf_attachment,
        image=image_attachment,
    )


def _sse_event(name: str, payload: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _sse_flush() -> str:
    """Comentario SSE para forzar flush en proxies (Railway / Next.js)."""
    return ": flush\n\n"


def _invalidate_stream_usage_cache(user_id: str) -> None:
    _STREAM_USAGE_CACHE.pop(user_id, None)


def _cached_messages_today(user_id: str) -> int:
    now = time.monotonic()
    cached = _STREAM_USAGE_CACHE.get(user_id)
    if cached and now - cached[0] < _STREAM_USAGE_CACHE_TTL:
        return cached[1]
    used = count_user_messages_today(user_id)
    _STREAM_USAGE_CACHE[user_id] = (now, used)
    return used


def _bump_stream_usage_cache(user_id: str) -> None:
    now = time.monotonic()
    cached = _STREAM_USAGE_CACHE.get(user_id)
    if cached:
        _STREAM_USAGE_CACHE[user_id] = (now, cached[1] + 1)
    else:
        _STREAM_USAGE_CACHE[user_id] = (now, _cached_messages_today(user_id) + 1)


def _stream_usage_snapshot(
    user_id: str,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Uso diario ligero para evento done — sin welcome ni trial lookup pesado."""
    from app.deps.plan_access import chat_message_limit

    prof = profile if profile is not None else (supabase_db.get_profile(user_id) or {})
    limit = chat_message_limit(user_id, profile=prof)
    used = _cached_messages_today(user_id)
    unlimited = limit < 0
    remaining = -1 if unlimited else max(0, limit - used)
    blocked = not unlimited and limit > 0 and used >= limit
    return {
        "messages_used_today": used,
        "messages_limit_daily": limit if limit >= 0 else None,
        "unlimited": unlimited,
        "remaining_today": remaining if remaining >= 0 else None,
        "blocked": blocked,
        "trial_expired": False,
    }


def _stream_is_blocked(user_id: str, profile: dict[str, Any]) -> bool:
    from app.deps.plan_access import chat_message_limit

    limit = chat_message_limit(user_id, profile=profile)
    if limit < 0:
        return False
    if limit <= 0:
        return True
    return _cached_messages_today(user_id) >= limit


def _load_stream_conversation(
    user_id: str,
    text: str,
    conversation_id: str | None,
) -> tuple[str, list[dict[str, Any]]]:
    if conversation_id:
        conv = supabase_db.get_conversation(conversation_id, user_id)
        if not conv or conv.get("channel") != "text":
            raise TextChatError("Conversación no encontrada.")
        history = supabase_db.get_conversation_messages(
            conversation_id,
            user_id,
            limit=CHAT_STREAM_HISTORY_LIMIT,
        )
        return conversation_id, history
    title = text[:48] + ("…" if len(text) > 48 else "")
    conv = supabase_db.create_conversation(user_id, title=title, channel="text")
    return str(conv["id"]), []


def _stream_memory_route(user_id: str, text: str):
    from app.services.cognitive_intents import CognitiveIntent, analyze_intent
    from app.services.cognitive_router import CognitiveRouteResult
    from app.services.cognitive_memory import save_memory
    from app.services.session_memory import build_conversation_recall_reply

    analysis = analyze_intent(text)
    if analysis.primary == CognitiveIntent.MEMORY_SAVE and analysis.memory_save_text:
        save_memory(user_id, "nota_chat", analysis.memory_save_text)
        return CognitiveRouteResult(
            intent=analysis.primary.value,
            channel="text",
            confidence=1.0,
            speakable="Guardado en memoria cognitiva.",
            memory_saved=True,
        )
    if analysis.primary == CognitiveIntent.MEMORY_RECALL:
        reply = build_conversation_recall_reply(user_id, text, channel="text")
        return CognitiveRouteResult(
            intent=analysis.primary.value,
            channel="text",
            confidence=0.95 if reply else 0.3,
            speakable=reply,
        )
    return CognitiveRouteResult(
        intent=CognitiveIntent.DIRECT_REPLY.value,
        channel="text",
        confidence=0.85,
        source="stream_fast",
        meta={"defer_enrichment": True},
    )


def _persist_stream_turn(
    user_id: str,
    *,
    conversation_id: str | None,
    text: str,
    reply: str,
) -> str:
    """Guarda turno tras primer token — no bloquea time-to-first-token."""
    conv_id, _history = _load_stream_conversation(user_id, text, conversation_id)
    supabase_db.append_message(
        conv_id,
        user_id,
        "user",
        text,
        session_id=conv_id,
        channel="text",
    )
    _bump_stream_usage_cache(user_id)
    supabase_db.append_message(
        conv_id,
        user_id,
        "model",
        reply,
        session_id=conv_id,
        channel="text",
    )
    return conv_id


def _can_stream_chat_text(text: str) -> bool:
    from app.modules.calendar_module import is_calendar_intent
    from app.modules.environment_module import is_environment_intent
    from app.modules.finance_module import is_finance_intent
    from app.modules.gmail_module import is_gmail_intent
    from app.services.cognitive_intents import (
        is_conversation_recall_intent,
        is_news_intent,
        is_weather_intent,
        is_web_research_intent,
        requires_live_web,
    )
    from app.services.hud_reminders import is_reminder_intent

    if is_gmail_intent(text) or is_calendar_intent(text):
        return False
    if is_finance_intent(text):
        return False
    if is_reminder_intent(text) or is_environment_intent(text):
        return False
    if is_conversation_recall_intent(text):
        return False
    if is_generate_image_intent(text) or is_pdf_intent(text):
        return False
    if requires_live_web(text) or is_web_research_intent(text):
        return False
    if is_news_intent(text) or is_weather_intent(text):
        return False
    if _needs_chat_tools(text):
        return False
    return True


# Timeout HTTP para Gemini: si la API se atasca, falla en vez de colgar para
# siempre. Es un timeout por lectura/conexión (ms); el streaming sano envía
# chunks con frecuencia, así que no corta respuestas saludables.
CHAT_GEMINI_HTTP_TIMEOUT_MS = 45_000


def _gemini_client(api_key: str):
    """Cliente Gemini con timeout HTTP para evitar cuelgues indefinidos."""
    from google import genai

    try:
        from google.genai import types

        return genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=CHAT_GEMINI_HTTP_TIMEOUT_MS),
        )
    except Exception:  # noqa: BLE001 — SDK sin soporte de http_options.timeout
        return genai.Client(api_key=api_key)


def _gemini_simple_reply_stream(
    *,
    api_key: str,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
    max_tokens: int = CHAT_SIMPLE_MAX_TOKENS,
    allow_llama: bool = True,
):
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

    from app.services.llama_service import (
        _CHAT_TIMEOUT_SEC,
        iter_llama_chat_stream,
        should_route_to_llama,
        use_llama,
    )

    if allow_llama and use_llama() and should_route_to_llama():
        def _collect_llama() -> list[str]:
            return list(
                iter_llama_chat_stream(
                    system=system,
                    messages=messages,
                    temperature=0.4,
                    max_tokens=max_tokens,
                )
            )

        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pieces = pool.submit(_collect_llama).result(timeout=_CHAT_TIMEOUT_SEC)
            if pieces:
                yield from pieces
                return
        except FuturesTimeout:
            logger.warning("[CHAT] Llama stream timeout %.0fs — fallback cloud", _CHAT_TIMEOUT_SEC)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[CHAT] Llama stream failed — fallback cloud: %s", exc)
    elif allow_llama and use_llama() and not should_route_to_llama():
        logger.warning("[CHAT] Ollama sin modelo listo — stream fallback cloud")

    settings = get_settings()
    anthropic_key = settings.anthropic_api_key.strip()
    if not (api_key or "").strip():
        if anthropic_key:
            from app.services.claude_advanced import _iter_anthropic_text_stream

            for piece, _label in _iter_anthropic_text_stream(
                api_key=anthropic_key,
                system=system,
                messages=messages,
                max_tokens=max_tokens,
                user_text="",
            ):
                if piece:
                    yield piece
            return
        raise TextChatError(
            "Sin proveedor cloud para fallback de chat.",
            http_status=503,
        )

    from google import genai
    from google.genai import types

    contents: list[types.Content] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        if role == "user":
            contents.append(types.Content(role="user", parts=[types.Part(text=content)]))
        elif role == "assistant":
            contents.append(types.Content(role="model", parts=[types.Part(text=content)]))

    if not contents:
        raise TextChatError("Sin mensajes para el asistente.")

    model_name = (model or CHAT_GEMINI_MODEL).strip() or CHAT_GEMINI_MODEL
    client = _gemini_client(api_key)
    stream = client.models.generate_content_stream(
        model=model_name,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=_trim_system(system),
            temperature=0.4,
            max_output_tokens=max_tokens,
        ),
    )
    for chunk in stream:
        piece = getattr(chunk, "text", None) or ""
        if piece:
            yield piece


def iter_send_message_stream(
    user_id: str,
    *,
    content: str,
    conversation_id: str | None = None,
):
    """Generador SSE — streaming Gemini para chat conversacional."""
    from concurrent.futures import ThreadPoolExecutor

    t0 = time.perf_counter()

    def _perf(step: str) -> None:
        logger.info("[PERF] chat/stream %s: %.2fs", step, time.perf_counter() - t0)

    text = content.strip()
    if not text:
        raise TextChatError("Mensaje vacío.")
    if len(text) > 8000:
        raise TextChatError("Mensaje demasiado largo.")

    if not _can_stream_chat_text(text):
        result = send_message(user_id, content=text, conversation_id=conversation_id)
        yield _sse_event("done", result)
        return

    _perf("validated")

    instant = _instant_chat_greeting_reply(text)
    if instant:
        reply = _finalize_chat_reply(instant)
        yield _sse_event("token", {"text": reply})
        yield _sse_flush()
        _perf("first_token")
        if conversation_id:
            conv_id = conversation_id
        else:
            conv_id, _ = _load_stream_conversation(user_id, text, conversation_id)
        yield _sse_event(
            "done",
            {
                "conversation_id": conv_id,
                "reply": reply,
                "usage": _stream_usage_snapshot(user_id),
                "cognitive": {"intent": "greeting", "source": "instant"},
            },
        )
        try:
            supabase_db.append_message(
                conv_id,
                user_id,
                "user",
                text,
                session_id=conv_id,
                channel="text",
            )
            _bump_stream_usage_cache(user_id)
            supabase_db.append_message(
                conv_id,
                user_id,
                "model",
                reply,
                session_id=conv_id,
                channel="text",
            )
        except Exception:  # noqa: BLE001
            logger.exception("[CHAT] instant greeting persist failed user=%s", user_id[:8])
        return

    yield _sse_event("status", {"text": "Preparando respuesta…"})
    yield _sse_flush()

    settings = get_settings()
    google_key = settings.google_api_key.strip()
    anthropic_key = settings.anthropic_api_key.strip()
    gemini_model = _gemini_chat_model()
    from app.services.llama_service import should_route_to_llama, use_llama

    if not google_key and not anthropic_key and not (use_llama() and should_route_to_llama()):
        raise TextChatError(
            "Servicio de chat no disponible. Configura GOOGLE_API_KEY o ANTHROPIC_API_KEY en Railway.",
            http_status=503,
        )

    from app.deps.auth import is_super_admin
    from app.deps.plan_access import chat_message_limit
    from app.services.chat_rate_limit import check_chat_rate_limit

    with ThreadPoolExecutor(max_workers=2) as pool:
        profile_future = pool.submit(supabase_db.get_profile, user_id)
        conv_future = pool.submit(
            _load_stream_conversation,
            user_id,
            text,
            conversation_id,
        )
        profile = profile_future.result() or {}
        conversation_id, history = conv_future.result()

    if _stream_is_blocked(user_id, profile):
        raise TextChatError(
            "Alcanzaste el límite de mensajes de hoy. Mejora tu plan o vuelve mañana.",
            http_status=429,
        )

    admin = is_super_admin(profile.get("email"), profile.get("role"))
    unlimited_plan = chat_message_limit(user_id, profile=profile) < 0
    if not admin and not unlimited_plan:
        allowed, retry_after = check_chat_rate_limit(
            user_id,
            is_admin=admin,
            unlimited_plan=unlimited_plan,
        )
        if not allowed:
            raise TextChatError(
                f"Has alcanzado el límite de mensajes. Espera {retry_after} segundos e intenta de nuevo.",
                http_status=429,
            )

    supabase_db.append_message(
        conversation_id,
        user_id,
        "user",
        text,
        session_id=conversation_id,
        channel="text",
    )
    _bump_stream_usage_cache(user_id)
    _perf("db_ready")

    from app.services.system_clock import try_instant_datetime_reply

    dt_instant = try_instant_datetime_reply(text, history=history)
    if dt_instant:
        reply = _finalize_chat_reply(dt_instant)
        yield _sse_event("token", {"text": reply})
        supabase_db.append_message(
            conversation_id,
            user_id,
            "model",
            reply,
            session_id=conversation_id,
            channel="text",
        )
        yield _sse_event(
            "done",
            {
                "conversation_id": conversation_id,
                "reply": reply,
                "usage": _stream_usage_snapshot(user_id, profile),
                "cognitive": {"intent": "datetime", "source": "instant"},
            },
        )
        return

    route = _stream_memory_route(user_id, text)
    if route.intent in ("memory_save", "memory_recall") and route.speakable:
        reply = _finalize_chat_reply(route.speakable)
        supabase_db.append_message(
            conversation_id,
            user_id,
            "model",
            reply,
            session_id=conversation_id,
            channel="text",
        )
        yield _sse_event("token", {"text": reply})
        yield _sse_event(
            "done",
            {
                "conversation_id": conversation_id,
                "reply": reply,
                "usage": _stream_usage_snapshot(user_id, profile),
                "cognitive": route.to_dict(),
            },
        )
        return

    messages = _anthropic_messages(history)
    messages.append({"role": "user", "content": text})
    try:
        system = _build_chat_system_light(user_id, text)
    except Exception:  # noqa: BLE001
        logger.exception("[CHAT] fallo armando system prompt — usando base")
        system = CHAT_SYSTEM_BASE

    token_budget = _chat_max_tokens(text)
    accumulated: list[str] = []
    stream_buf = ""
    _perf("pre_stream")
    try:
        from app.services.stream_delta import stream_piece_delta

        for piece in _gemini_simple_reply_stream(
            api_key=google_key,
            model=gemini_model,
            system=system,
            messages=messages,
            max_tokens=token_budget,
        ):
            delta = stream_piece_delta(stream_buf, piece)
            if not delta:
                continue
            stream_buf += delta
            accumulated.append(delta)
            yield _sse_event("token", {"text": delta})
        _perf("stream_done")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[CHAT] stream failed, fallback resilient: %s", exc)
        accumulated = []

    reply = "".join(accumulated).strip()
    pdf_attachment: dict[str, Any] | None = None
    image_attachment: dict[str, Any] | None = None
    if not reply:
        from app.services.cloud_llm_fallback import chat_cloud_reply

        cloud = chat_cloud_reply(
            system=system,
            messages=messages,
            user_text=text,
            max_tokens=token_budget,
        )
        if cloud:
            reply = cloud
    if not reply:
        try:
            reply, pdf_attachment, image_attachment = _complete_chat_resilient(
                user_id,
                user_text=text,
                anthropic_key=anthropic_key,
                google_key=google_key,
                gemini_model=gemini_model,
                system=system,
                messages=messages,
                conversation_id=conversation_id,
            )
        except TextChatError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("[CHAT] stream fallback failed")
            raise TextChatError(
                "No pude conectar con el asistente. Intenta de nuevo en un momento.",
                http_status=503,
            ) from exc

    if _contains_internal_kb_leak(reply):
        reply, pdf_attachment, image_attachment = _ensure_chat_reply_no_kb_leak(
            reply,
            user_id=user_id,
            user_text=text,
            anthropic_key=anthropic_key,
            google_key=google_key,
            gemini_model=gemini_model,
            system=system,
            messages=messages,
            conversation_id=conversation_id,
            pdf_attachment=pdf_attachment,
            image_attachment=image_attachment,
        )
    reply = _finalize_chat_reply(reply)

    supabase_db.append_message(
        conversation_id,
        user_id,
        "model",
        reply,
        session_id=conversation_id,
        channel="text",
    )
    payload: dict[str, Any] = {
        "conversation_id": conversation_id,
        "reply": reply,
        "usage": _stream_usage_snapshot(user_id, profile),
        "cognitive": route.to_dict(),
    }
    if pdf_attachment:
        payload["pdf"] = pdf_attachment
    if image_attachment:
        payload["image"] = image_attachment
    yield _sse_event("done", payload)
