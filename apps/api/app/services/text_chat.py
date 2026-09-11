"""Chat de texto con Claude — límites por plan + herramientas Meta."""

from __future__ import annotations

import contextvars
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
    PDF_DETAIL_CLARIFY_QUESTION,
    is_attachment_image_edit_request,
    is_generate_image_intent,
    is_pdf_intent,
    parse_followup_image_prompt,
    parse_generate_image_prompt,
    parse_pdf_request,
    prior_pdf_user_request,
    resolve_pdf_detail_for_turn,
    resolve_pdf_request,
)
from app.domain.ced_identity import (
    CED_CORE_IDENTITY,
    CED_CREATOR_IDENTITY,
    CED_HUMAN_VOICE_STYLE,
    CED_MARKETING_EXPERTISE,
    CED_UNIVERSAL_CONVERSATION,
    CED_CONFIDENTIALITY,
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


def _bridge_studio_to_voice(
    user_id: str,
    *,
    text: str,
    image: bool = False,
    pdf_filename: str | None = None,
) -> None:
    """Si hay llamada de voz activa, el cerebro de voz ve el chat escrito/adjuntos."""
    try:
        from app.services import voice_client_session as vcs

        kind = "document" if pdf_filename else ("image" if image else "text")
        vcs.push_studio_chat_event(
            user_id,
            kind=kind,
            text=text,
            filename=(pdf_filename or "").strip(),
        )
    except Exception:  # noqa: BLE001
        logger.debug("[CHAT] puente voz omitido", exc_info=True)


CHAT_MODEL = "claude-sonnet-4-6"
CHAT_MODEL_FAST = "claude-haiku-4-5-20251001"
CHAT_GEMINI_MODEL = "gemini-2.5-flash"
CHAT_SYSTEM_MAX_CHARS = 14_000

# Señal "recarga necesaria" desde una tool (imagen/PDF/búsqueda) hasta la
# respuesta HTTP final del turno — sin re-hilar el tipo de retorno por las
# ~15 funciones que ya encadenan (reply, pdf_attachment, image_attachment).
# Se fija dentro de _run_chat_tool y se lee/limpia una sola vez en _finish()
# o en el payload final del streaming, ambos dentro del mismo turno/contexto.
_pending_recharge_signal: contextvars.ContextVar[dict[str, Any] | None] = (
    contextvars.ContextVar("pending_recharge_signal", default=None)
)


def _mark_recharge_needed(resource: str, message: str) -> None:
    _pending_recharge_signal.set({"resource": resource, "message": message})


def _consume_recharge_needed() -> dict[str, Any] | None:
    signal = _pending_recharge_signal.get()
    if signal is not None:
        _pending_recharge_signal.set(None)
    return signal


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
DIRECT_IMAGE_MAX_CHARS = 8000
# Stream imagen: keepalives + deadline. Nunca shutdown(wait=True) tras timeout —
# eso bloqueaba el SSE y el cliente mostraba «No pude generar la imagen a tiempo».
# 90s cubre Ideogram/GPT + Gemini recortados; el job no debe vivir 3+ minutos.
IMAGE_STREAM_DEADLINE_SEC = 90.0
IMAGE_STREAM_KEEPALIVE_SEC = 5.0
BLOCKING_STREAM_DEADLINE_SEC = 90.0

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
    r"\b(publica|publicar|instagram|facebook|meta|face|fb|recuerdas|guarda|memoria|"
    r"lead|cliente|pdf|imagen|conectad|busca|buscar|búsqueda|noticias|clima|"
    r"informaci[oó]n|investiga|terremoto|actual|reciente|dame datos|"
    r"confirmo|confirm[oa]|env[ií]a|enviar|publ[ií]calo)\b",
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
    r"\bgenerate_image\s*\(",
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
    r"generate_image\s*\(\s*\{",
    r'generate_image\s*\(\s*["\']prompt["\']',
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

IMAGE_HALLUCINATION_RETRY_MESSAGE = (
    "Escribiste generate_image como texto o código. NO narres herramientas. "
    "Responde al usuario en lenguaje natural; el sistema generará la imagen por ti."
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
        "name": "activar_prospeccion",
        "description": (
            "Activa el modo prospección de CED (escanea comentarios de Instagram en busca de leads). "
            "SOLO si el usuario pide explícitamente activar/encender el modo prospección. "
            "PROHIBIDO si pide copy, ideas, un mensaje o un pitch de prospección — eso se responde en texto."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "desactivar_prospeccion",
        "description": "Desactiva el modo prospección de leads en Instagram.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "reporte_prospeccion",
        "description": "Reporte de leads detectados hoy por el modo prospección.",
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
Responde con markdown cuando ayude. Sé útil y conciso.
ORTOGRAFÍA: escribe siempre en español correcto (tildes, sin anglicismos innecesarios, sin typos).

{CED_CORE_IDENTITY}

{CED_CONFIDENTIALITY}

{CED_MARKETING_EXPERTISE}

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
- Si NO hay bloque interno inyectado sobre el tema: usa tu conocimiento general del modelo para ayudar igual.
- Solo afirma datos de hoy (clima, precios, noticias) si hay contexto web inyectado abajo o tras search_web.
- Si te falta dato actual o no estás seguro: invoca search_web — no te quedes corto ni hagas un cuestionario.
- Sistema avanzado: si el contexto indica confirmación pendiente, pregunta antes de profundizar.
- NUNCA incluyas en tu respuesta al usuario el texto del bloque "Conocimiento interno CED" ni líneas tipo "- [Marketing digital] ...".
  Úsalo SOLO como contexto interno para generar respuestas naturales, útiles y en tus propias palabras.
- REGLA CRÍTICA: NUNCA incluyas en tu respuesta al usuario texto que empiece con "Conocimiento interno CED"
  o que contenga etiquetas como [Marketing digital], [Finanzas personales], [general], etc.
  Ese conocimiento es solo contexto interno tuyo. El usuario NUNCA debe verlo.

IMPORTANTE — CONTENIDO / IDEAS / PROMPTS DE TEXTO vs IMAGEN (acciones distintas):
- Pedido de idea, concepto, copy, prompt, guion, caption, texto o contenido → responde en TEXTO.
  PROHIBIDO invocar generate_image por eso.
- Solo genera imagen cuando pidan EXPLÍCITAMENTE crear/diseñar una imagen, foto, flyer, logo o creativo visual
  («genera una imagen…», «diseña un flyer…»).
- «Dame una idea de imagen / creativo» o «hazme un prompt para…» = ideación de texto, NO PNG.
- ITERACIÓN DE DISEÑO (como ChatGPT): si ya hay imagen o diseño en el hilo y piden ejemplos, opciones,
  variantes o «cómo se vería» SIN decir genera/renderiza → responde en TEXTO anclado al MISMO diseño.
  Solo genera imagen cuando pidan explícitamente renderizar («genera», «hazlo», «créala», «genérala»).

IMPORTANTE — PM International / FitLine (módulo Oportunidades):
- Si el mensaje habla de FitLine, PM International o productos del catálogo (Activize/Activise, Restorate, Basics, etc.)
  y piden contenido/ideas/prompts de texto: usa el conocimiento Oportunidades inyectado y ENTREGA el contenido YA.
- NO preguntes qué es el producto, para qué sirve o a quién va (ya está en el contexto).
- NO digas que no tienes información del producto si el bloque Oportunidades está presente.
- NO confundas ese pedido con generación de imagen.
- PROHIBIDO search_web / Tavily / «investigando» / «déjeme consultar» si el bloque Oportunidades cubre el tema.
- PROHIBIDO pegar URLs de pm-international.com (ni la home ni /registration). Si piden el enlace de inscripción o de PM, NO escribas el link: el sistema abre Oportunidades (OPPS) con el botón del patrocinador. OBLIGATORIO: instruir a verificar que el nombre o ID del patrocinador en la página de registro coincida exactamente con quien le presentó la oportunidad.

IMPORTANTE — prompts para otras herramientas de IA:
- Cuando el usuario pida un "prompt" para usar en otra herramienta de IA (ChatGPT, Midjourney, Gemini, etc.),
  entrégalo COMPLETO, detallado y listo para copiar y pegar.
- Delimita el prompt con --- arriba y --- abajo.
- NO entregues solo una "estructura de página", un esquema de secciones ni un resumen.
- Si pidió el prompt, entrégalo de inmediato — no sustituyas por una descripción de lo que incluiría.

IMPORTANTE — capacidades REALES de esta plataforma:
- Si el usuario pide «qué puedes hacer» / lista de habilidades: usa SOLO el catálogo factual
  de capacidades CED (regla de sistema inyectada). PROHIBIDO inventar módulos inexistentes.
- CED puede publicar en Facebook e Instagram cuando el usuario conectó Meta (dashboard → Conectar Redes).
- Usa las herramientas publicar_facebook / publicar_instagram cuando el usuario pida publicar y confirme el texto.
- Modo prospección (leads en comentarios de Instagram): SOLO si piden activar, desactivar o un reporte. Invoca activar_prospeccion / desactivar_prospeccion / reporte_prospeccion. Si piden copy, ideas o un mensaje de prospección, responde en texto — NO actives el modo.
- Si las redes NO están conectadas, indica conectar en el dashboard — NO digas que es imposible en absoluto.
- Puedes generar PDFs descargables con generar_pdf. El campo content debe incluir TODO el texto del documento, no solo el título.
- Puedes GENERAR IMÁGENES con generate_image cuando pidan crear/diseñar una imagen. Invoca la herramienta; la app muestra la imagen en el chat.
- También puedes variar/editar a partir de una imagen de referencia cuando lo pidan.
- VIDEO (piloto / en desarrollo con Keini): generación con Veo 3 y edición de videos del usuario.
  Guía al módulo VIDEO del dashboard (?videoEditModule=pilot). Usa tokens de video (aparte del saldo de voz).
  Edición: subir MP4 + guion → cortes, transiciones, Text→SFX. Veo 3 en el pipeline cuando el producto lo habilite.
  NO inventes un MP4 ya renderizado desde el chat de texto; sé orgulloso del piloto y honesto con el estado.
- Palabras clave de generación (SOLO estas cuentan como «generar ahora»): "genera una imagen", "genérame una imagen", "créame un diseño", "hazme un logo", "diseña un creativo", "crea una foto", "genera la imagen".
- «Necesito una foto para Instagram» o «I need a photo for Sek» SIN «genera/genérame/hazme/créame» NO es generate_image: habla en texto, propone el concepto y espera confirmación.
- Si piden acordar algo impactante ANTES de crear, responde en texto. PROHIBIDO generate_image. PROHIBIDO decir que la generación falló, copyright o límites: no se pidió generar.
- Si el pedido es «genera/genérame/créame/hazme una imagen de X» (aunque X sea corto: robot, logo CED, etc.): GENERA YA. PROHIBIDO describir el concepto y preguntar «¿quieres ajustar?» / estilo / colores antes de generar.
- Si el pedido de imagen es vago SIN verbo de generación («necesito algo visual»), pide MÁS DETALLES UNA VEZ. Si es un «genera/hazme» claro, genera.
- Tras generar una imagen, preséntala (y opcionalmente pregunta si quiere ajustes visuales). NUNCA digas que la imagen está lista si no la generó el sistema en ese turno.
- PROHIBIDO ofrecer publicar en Instagram/Facebook, proponer copy/caption o sugerir redes
  de forma proactiva tras generar una imagen. Solo si el usuario lo pide explícitamente
  («publica esto», «hazme una propuesta para postear», «quiero subirla a Instagram»).
- Finanzas personales, clima/ambiente, recordatorios HUD, modo avanzado, guiones/copy y mentor de ventas
  también son capacidades reales — actívalas solo cuando el usuario las pida.
- Cámara, mapa/navegación y YouTube viven principalmente en el asistente de voz / HUD.
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

PROMPTS DE IMAGEN (SIN REESCRITURA):
Cuando invoques generate_image, el campo `prompt` DEBE ser el pedido del usuario TAL CUAL
(o casi intacto: puedes quitar solo «generame una imagen» / «okay»).
PROHIBIDO resumir, reinterpretar, inventar branding CED, mezclar historial o «mejorar» la escena.
El backend ya adapta el prompt mínimo hacia el motor de imagen del sistema.
Si el usuario pide texto largo DENTRO de la imagen («que diga», «EN TEXTO»), pásalo completo en `prompt`.

PROHIBIDO (chatbot genérico): no digas "sin internet en tiempo real" ni "no puedo conectar tus cuentas" — CED tiene búsqueda, Meta OAuth y tools. No recomiendes Buffer/Hootsuite como única opción si ya tiene redes conectadas.

Cuando el usuario pida EXPLÍCITAMENTE contenido para redes o publicar, entrégalo listo
y ofrece publicarlo con CED. NUNCA propongas publicar ni generes copy de redes por iniciativa
propia solo porque acabas de generar o analizar una imagen."""

# Versión reducida de CHAT_SYSTEM_BASE para el pipeline de streaming casual
# (Llama + su fallback Claude/Gemini en iter_unified_llm_stream). Esa ruta
# SOLO se usa cuando _can_stream_chat_text ya descartó que el turno necesite
# tools (imagen, PDF, publicar, búsqueda web, clima/entorno) — así que las ~10k
# chars de instrucciones de function-calling, publicación y generación de
# CHAT_SYSTEM_BASE son puro peso muerto ahí: en Llama (CPU, 13B) ese texto de
# más se traduce directo en varios segundos extra de prompt_eval antes del
# primer token, que es la principal causa de que el chat "se sienta lento".
CHAT_SYSTEM_LIGHT_BASE = f"""Eres CED (Castillo de la Evolución Digital), asistente dentro de la plataforma CED Web.
Español latinoamericano natural, cálido y directo.
Responde con markdown cuando ayude. Sé útil y conciso.
ORTOGRAFÍA: escribe siempre en español correcto (tildes, sin anglicismos innecesarios, sin typos).

{CED_CORE_IDENTITY}

{CED_CONFIDENTIALITY}

{CED_MARKETING_EXPERTISE}

{CED_CREATOR_IDENTITY}

{CED_HUMAN_VOICE_STYLE}

{CED_SALES_MENTOR_CORE}

{CED_STRATEGY_CONSULTATION_CORE}

{CED_UNIVERSAL_CONVERSATION}

IMPORTANTE — tratamiento del usuario:
- Usa el nombre y título del bloque "USUARIO ACTUAL — TRATAMIENTO" inyectado abajo si está presente.
- NO uses tono de mayordomo exagerado; Señor/Señora solo si el usuario lo prefiere.

IMPORTANTE — contenido de texto vs imagen:
- Idea, copy, prompt, guion o contenido pedido → responde en TEXTO completo. NO digas que generaste una imagen.
- FitLine/PM/productos del catálogo: usa el conocimiento Oportunidades si está inyectado; entrega ya; no preguntes lo básico.
- NUNCA pegues URLs de pm-international.com. Si piden el enlace de inscripción, di que abres Oportunidades; el botón está al final de la ficha. OBLIGATORIO: verificar que el nombre o ID del patrocinador en el registro coincida con quien le presentó la oportunidad.
- Otros temas sin bloque interno: usa tu conocimiento general; sé útil y concreto, no te quedes corto.

Esta es charla conversacional — no tienes tools disponibles en este turno. Si el usuario pide generar
una imagen, un PDF, publicar en redes o buscar algo en tiempo real, dilo de forma natural (ej. "Claro,
dame un segundo para eso") y NUNCA finjas que ya lo hiciste — esa acción se resuelve en el turno siguiente."""


def _wants_viral_knowledge(text: str) -> bool:
    return bool(_VIRAL_KEYWORDS.search(text or ""))


def _instant_chat_greeting_reply(text: str) -> str | None:
    cleaned = (text or "").strip()
    try:
        from app.services.opportunities_pilot.fitline_enroll import (
            wants_fitline_enroll_link,
        )

        if wants_fitline_enroll_link(cleaned):
            return None
    except Exception:  # noqa: BLE001
        pass
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

def _salvage_image_if_needed(
    user_id: str,
    conversation_id: str | None,
    user_text: str,
    history: list[dict[str, str]] | None,
    reply: str,
    image_attachment: dict[str, Any] | None,
    *,
    plan_id: str | None = None,
) -> tuple[str, dict[str, Any] | None]:
    from app.services.chat_image_generation import salvage_image_turn

    return salvage_image_turn(
        user_id,
        conversation_id,
        user_text,
        history,
        reply,
        image_attachment,
        plan_id=plan_id,
    )


def _plan_id_for_user(user_id: str) -> str | None:
    try:
        sub = supabase_db.get_subscription(user_id)
        return sub.get("plan_id") if sub else None
    except Exception:  # noqa: BLE001
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
    detail_level: str = "brief",
) -> tuple[str, dict[str, Any]] | None:
    """Genera PDF real y devuelve mensaje + adjunto para el chat."""
    from app.deps.plan_access import effective_plan_limits, pdf_included_in_plan_today

    limits, reason, _trial = effective_plan_limits(user_id)
    if reason == "trial_expired":
        return (
            "Tu prueba terminó. Elige un plan en Precios o continúa con el plan Básico gratis.",
            {},
        )
    included = pdf_included_in_plan_today(user_id, limits)
    pdf_wallet_charge_needed = False
    if not included:
        from app.services.wallet import can_afford

        if not can_afford(user_id, "pdf", units=1.0):
            msg = (
                f"Alcanzaste tu límite diario de {limits.pdf_reports_per_day} PDF gratis. "
                "Recarga desde $10 para seguir hoy."
                if limits.pdf_reports
                else (
                    "Los PDFs requieren plan Pro, Élite o Founding, "
                    "o recarga desde $10. Mejora tu plan en /pricing."
                )
            )
            _mark_recharge_needed("pdf", msg)
            return (msg, {})
        pdf_wallet_charge_needed = True

    pdf_title = (title or "Documento CED").strip()[:200]
    pdf_body = (content or "").strip()
    fallbacks = assistant_fallback_texts_from_messages(_anthropic_messages(history))
    user_texts = user_texts_from_messages(_anthropic_messages(history))
    resolved_request = user_request or (user_texts[-1] if user_texts else pdf_title)
    level = (detail_level or "brief").strip().lower() or "brief"
    try:
        artifact = store_pdf_with_timeout(
            user_id=user_id,
            title=pdf_title,
            content=pdf_body,
            conversation_id=conversation_id,
            fallback_texts=fallbacks,
            user_request=resolved_request,
            detail_level=level,
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

    if pdf_wallet_charge_needed:
        from app.services.wallet import try_spend

        spend = try_spend(user_id, "pdf", units=1.0)
        if not spend.get("ok"):
            msg = str(spend.get("error") or "Recarga desde $10 para generar PDF.")
            _mark_recharge_needed("pdf", msg)
            return (msg, {})

    attachment = _pdf_attachment_from_artifact(artifact)
    return _pdf_success_message(artifact.title), attachment


def _try_direct_pdf_from_context(
    user_id: str,
    *,
    text: str,
    history: list[dict[str, Any]],
    conversation_id: str | None,
) -> tuple[str, dict[str, Any]] | None:
    detail = resolve_pdf_detail_for_turn(text, history)
    if detail is None:
        return None
    if detail == "ask":
        return PDF_DETAIL_CLARIFY_QUESTION, {}

    level = detail if detail in ("brief", "full") else "brief"
    source_text = text
    if not is_pdf_intent(text):
        prior = prior_pdf_user_request(history)
        if not prior:
            return None
        source_text = prior

    req = resolve_pdf_request(source_text, history)
    if not req:
        return None
    title, body = req
    result = _execute_direct_pdf(
        user_id,
        title=title,
        content=body,
        history=history,
        conversation_id=conversation_id,
        user_request=source_text,
        detail_level=level,
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
    from app.services.chat_image_generation import looks_like_hallucinated_generate_image

    if looks_like_hallucinated_generate_image(reply):
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
    from app.services.chat_image_generation import looks_like_hallucinated_generate_image

    if looks_like_hallucinated_generate_image(reply):
        return "generate_image"
    if _has_hallucinated_tool_code(reply):
        return "tool_code"
    if _promised_web_search_without_tool(reply):
        return "search_promise"
    if _has_hallucinated_tool(reply):
        return "tool_name"
    return None


def _hallucination_retry_message(kind: str) -> str:
    if kind == "generate_image":
        return IMAGE_HALLUCINATION_RETRY_MESSAGE
    if kind == "tool_code":
        return TOOL_CODE_HALLUCINATION_RETRY_MESSAGE
    if kind == "search_promise":
        return SEARCH_HALLUCINATION_RETRY_MESSAGE
    return HALLUCINATION_RETRY_USER_MESSAGE


def _dedupe_chat_reply(text: str) -> str:
    """Elimina bloques idénticos consecutivos y muletillas duplicadas en la respuesta."""
    from app.services.deliverable_replies import collapse_repeated_deliverable_passages

    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned
    cleaned = re.sub(
        r"(Un momento,?\s*se[nñ]or\.?\s*){2,}",
        r"\1",
        cleaned,
        flags=re.I,
    )
    cleaned = collapse_repeated_deliverable_passages(cleaned)
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


def _chat_max_tokens(
    user_text: str,
    *,
    with_tools: bool = False,
    history: list | None = None,
) -> int:
    if with_tools:
        return CHAT_TOOLS_MAX_TOKENS
    from app.services.deliverable_replies import needs_deliverable_token_budget

    if needs_deliverable_token_budget(user_text, history):
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
    from app.services.voice_response_guard import strip_stack_leak

    cleaned = _dedupe_chat_reply(text)
    cleaned = _strip_chat_filler_prefix(cleaned)
    cleaned = cleaned or (text or "").strip()
    cleaned = strip_stack_leak(cleaned)
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
    from app.services.opportunities_pilot.fitline_knowledge import prefers_fitline_over_web

    if prefers_fitline_over_web(user_text):
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


def _vision_brief_for_publish_caption(
    user_id: str,
    conversation_id: str,
) -> str:
    """Análisis visual de la imagen a publicar — evita captions inventados (FitLine, etc.)."""
    import base64

    from app.services.publish_image_context import (
        get_last_uploaded_image_for_session,
        get_session_vision_analysis,
        set_session_vision_analysis,
    )

    uid = (user_id or "").strip()
    cid = (conversation_id or "").strip()
    if not uid:
        return ""
    cached = get_session_vision_analysis(uid, cid or None)
    if cached:
        return cached[:2500]

    row = get_last_uploaded_image_for_session(uid, cid or None)
    if not row:
        return ""

    image_b64 = ""
    data = row.get("data")
    if isinstance(data, (bytes, bytearray)) and len(data) > 0:
        image_b64 = base64.b64encode(bytes(data)).decode("ascii")
    else:
        url = str(row.get("url") or "").strip()
        if url.startswith(("http://", "https://")):
            try:
                with httpx.Client(timeout=25.0) as client:
                    res = client.get(url)
                    res.raise_for_status()
                    image_b64 = base64.b64encode(res.content).decode("ascii")
            except Exception:  # noqa: BLE001
                logger.warning(
                    "[CHAT:PUBLISH] no pude descargar imagen para caption user=%s",
                    uid[:8],
                    exc_info=True,
                )
                return ""
    if not image_b64:
        return ""

    question = (
        "Describe literalmente esta imagen en español latinoamericano (4-8 frases): "
        "escena, sujeto, estilo visual, colores e iluminación. "
        "Copia entre comillas TODO texto legible en la imagen. "
        "PROHIBIDO inventar marcas, productos, suplementos o claims de salud "
        "que no se vean claramente en la foto."
    )
    try:
        from app.services.vision_search import analyze_image

        result = analyze_image(image_b64, question=question)
    except Exception:  # noqa: BLE001
        logger.warning("[CHAT:PUBLISH] vision caption failed user=%s", uid[:8], exc_info=True)
        return ""
    summary = str(result.get("summary") or "").strip()
    if summary:
        set_session_vision_analysis(uid, cid or None, summary)
    return summary[:2500]


def _suggest_social_caption(
    platform: str,
    user_text: str,
    history: list[dict[str, str]],
    *,
    user_id: str = "",
    conversation_id: str = "",
) -> str:
    settings = get_settings()
    google_key = settings.google_api_key.strip()
    if not google_key:
        return "Un momento especial compartido desde CED. #CED #EvoluciónDigital"

    vision = ""
    if user_id:
        try:
            vision = _vision_brief_for_publish_caption(user_id, conversation_id)
        except Exception:  # noqa: BLE001
            logger.warning("[CHAT:PUBLISH] vision brief omitido", exc_info=True)
            vision = ""

    messages: list[dict[str, str]] = []
    # Solo el turno reciente: historial largo de FitLine contaminaba captions de otras fotos.
    for row in history[-4:]:
        role = row.get("role")
        content = (row.get("content") or "").strip()
        if not content:
            continue
        if role == "model":
            messages.append({"role": "assistant", "content": content[:500]})
        elif role == "user":
            messages.append({"role": "user", "content": content[:500]})

    vision_block = (
        f"ANÁLISIS VISUAL DE LA IMAGEN A PUBLICAR (fuente de verdad):\n{vision}\n\n"
        if vision
        else (
            "NO hay análisis visual disponible. Escribe un caption genérico de CED "
            "SIN inventar productos FitLine/PM/Activize ni claims de salud.\n\n"
        )
    )
    messages.append(
        {
            "role": "user",
            "content": (
                f"{vision_block}"
                f"El usuario quiere publicar esta imagen en {platform}. "
                f"Pedido: {user_text}\n\n"
                f"Escribe SOLO el caption del post: título breve, 1-2 frases y 3-5 hashtags. "
                f"Sin introducción, sin «aquí tienes», sin markdown vacío. "
                f"El caption DEBE reflejar la imagen (análisis visual). "
                f"Si el historial habla de otro producto o tema, IGNÓRALO."
            ),
        }
    )
    system = (
        "Eres CED. Genera captions atractivos para redes en español latinoamericano. "
        "Responde solo con el texto del post. "
        "OBLIGATORIO: basarte en la imagen / análisis visual. "
        "PROHIBIDO inventar FitLine, PM International, Activize, Restorate, PowerCocktail "
        "u otros productos si no aparecen en el análisis visual. "
        "PROHIBIDO reutilizar un copy de otro producto del historial."
    )
    try:
        return _gemini_simple_reply(
            api_key=google_key,
            model=_gemini_chat_model(),
            system=system,
            messages=messages,
        )
    except Exception:  # noqa: BLE001
        if vision:
            # Fallback honesto basado en visión truncada — mejor que alucinar Activize.
            first = vision.split(".")[0].strip()
            if first:
                return f"{first}. #CED #EvoluciónDigital"
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
    from app.services.prospection import is_prospection_mode_command

    if is_prospection_mode_command(t):
        return True
    return bool(_TOOLS_KEYWORDS.search(t))


def _build_chat_system(
    user_id: str,
    user_text: str,
    route: Any | None = None,
    conversation_id: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> str:
    from app.services.system_clock import clock_context_block

    parts = [_chat_system_for_user(user_id), clock_context_block()]
    if conversation_id:
        from app.services.publish_image_context import has_publishable_image

        if has_publishable_image(user_id, conversation_id):
            # Solo orientar a publicar si el usuario YA pidió publicar — no en
            # cada turno tras una imagen (provoca alucinaciones «Publicaré en IG»).
            from app.services.publish_text import is_social_publish_intent

            if is_social_publish_intent(user_text):
                parts.append(
                    "IMAGEN DISPONIBLE EN ESTA CONVERSACIÓN:\n"
                    "El usuario ya tiene una imagen lista para publicar en "
                    "Instagram o Facebook.\n"
                    "Al invocar publicar_instagram o publicar_facebook usa "
                    "use_last_uploaded_image=true.\n"
                    "PROHIBIDO pedir URL de imagen al usuario."
                )
            else:
                parts.append(
                    "HAY UNA IMAGEN RECIENTE EN ESTA CONVERSACIÓN.\n"
                    "Mantén el hilo visual: ejemplos y variantes en TEXTO salvo que pidan "
                    "generar/renderizar explícitamente.\n"
                    "Si piden GENERAR otra versión del mismo diseño, usa generate_image "
                    "(o referencia) conservando el concepto.\n"
                    "NO asumas que quiere publicar en redes salvo que lo pida "
                    "explícitamente («publica en Instagram/Facebook»)."
                )
    from app.services.chat_image_generation import build_active_image_thread_context

    thread_ctx = build_active_image_thread_context(
        history,
        user_id=user_id,
        conversation_id=conversation_id,
    )
    if thread_ctx:
        parts.append(thread_ctx)
    if _wants_viral_knowledge(user_text):
        parts.append(CED_VIRAL_KNOWLEDGE_2026)
        parts.append(CED_MEMORY_USAGE_RULES)
    from app.domain.ced_sales_marketing_playbook import (
        append_sales_marketing_playbook_if_needed,
    )
    from app.services.opportunities_pilot.fitline_knowledge import (
        append_fitline_knowledge_if_needed,
    )

    extras = build_chat_system_extras(user_id, route)
    if extras:
        parts.append(extras)
    system = append_sales_marketing_playbook_if_needed("\n\n".join(parts), user_text)
    system = append_fitline_knowledge_if_needed(
        system, user_text, user_id=user_id
    )
    try:
        from app.services.deliverable_replies import append_deliverable_finish_if_needed

        system = append_deliverable_finish_if_needed(system, user_text)
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.services.opportunities_pilot.fitline_close_trigger import (
            append_fitline_close_trigger_if_needed,
        )

        system = append_fitline_close_trigger_if_needed(system, user_id, user_text)
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.services.insight_questions import capture_insight_question

        capture_insight_question(user_id, user_text, channel="chat")
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.services.user_session_profile import touch_and_learn

        # El bloque corto ya viene en build_chat_system_extras; aquí solo aprendemos.
        touch_and_learn(user_id, user_text, channel="chat")
    except Exception:  # noqa: BLE001
        pass
    from app.services.opportunities_pilot.fitline_guide_mode import (
        append_fitline_guide_if_needed,
    )

    return append_fitline_guide_if_needed(system, user_id, user_text, channel="chat")


def _build_chat_system_light(user_id: str, user_text: str) -> str:
    """System prompt mínimo para streaming — sin consultas DB (meta, dirección, KB)
    y sin instrucciones de tools (esta ruta nunca las necesita, ver
    _can_stream_chat_text) para minimizar el prompt_eval de Llama."""
    from app.domain.ced_identity import creator_partnership_overlay_for_user
    from app.domain.ced_sales_marketing_playbook import (
        append_sales_marketing_playbook_if_needed,
    )
    from app.services.opportunities_pilot.fitline_knowledge import (
        append_fitline_knowledge_if_needed,
    )
    from app.services.opportunities_pilot.fitline_guide_mode import (
        append_fitline_guide_if_needed,
    )
    from app.services.system_clock import clock_context_block

    parts = [CHAT_SYSTEM_LIGHT_BASE, clock_context_block()]
    partnership = creator_partnership_overlay_for_user(user_id)
    if partnership:
        parts.append(partnership)
    if _wants_viral_knowledge(user_text):
        parts.append(CED_VIRAL_KNOWLEDGE_2026)
        parts.append(CED_MEMORY_USAGE_RULES)
    system = append_sales_marketing_playbook_if_needed("\n\n".join(parts), user_text)
    system = append_fitline_knowledge_if_needed(
        system, user_text, user_id=user_id
    )
    try:
        from app.services.deliverable_replies import append_deliverable_finish_if_needed

        system = append_deliverable_finish_if_needed(system, user_text)
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.services.opportunities_pilot.fitline_close_trigger import (
            append_fitline_close_trigger_if_needed,
        )

        system = append_fitline_close_trigger_if_needed(system, user_id, user_text)
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.services.insight_questions import capture_insight_question

        capture_insight_question(user_id, user_text, channel="chat")
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.services.user_session_profile import (
            append_client_memory_to_prompt,
            touch_and_learn,
        )

        touch_and_learn(user_id, user_text, channel="chat")
        system = append_client_memory_to_prompt(system, user_id)
    except Exception:  # noqa: BLE001
        pass
    return append_fitline_guide_if_needed(system, user_id, user_text, channel="chat")


def _chat_system_for_user(user_id: str) -> str:
    from app.domain.ced_identity import creator_partnership_overlay_for_user

    conn = supabase_db.get_meta_connection(user_id)
    partnership = creator_partnership_overlay_for_user(user_id)
    partnership_block = f"\n\n{partnership}" if partnership else ""
    if conn and conn.get("access_token"):
        username = conn.get("ig_username") or "Instagram"
        return (
            f"{CHAT_SYSTEM_BASE}{partnership_block}\n\n"
            f"Estado Meta del usuario: CONECTADO (@{username}). "
            "Puedes publicar con las herramientas cuando confirme el texto."
        )
    return (
        f"{CHAT_SYSTEM_BASE}{partnership_block}\n\n"
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
        if name == "activar_prospeccion":
            from app.services.prospection import enable_prospection_for_user

            return json.dumps(enable_prospection_for_user(user_id))
        if name == "desactivar_prospeccion":
            from app.services.prospection import set_prospection_enabled

            return json.dumps(set_prospection_enabled(user_id, False))
        if name == "reporte_prospeccion":
            from app.services.prospection import get_prospection_report

            return json.dumps(get_prospection_report(user_id))
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
            from app.deps.plan_access import effective_plan_limits, pdf_included_in_plan_today

            limits, reason, _ = effective_plan_limits(user_id)
            if reason == "trial_expired":
                return json.dumps(
                    {
                        "ok": False,
                        "error": "Tu prueba terminó. Elige un plan en Precios.",
                        "code": "trial_expired",
                    },
                )
            included = pdf_included_in_plan_today(user_id, limits)
            pdf_wallet_charge_needed = False
            if not included:
                from app.services.wallet import can_afford

                if not can_afford(user_id, "pdf", units=1.0):
                    msg = (
                        f"Alcanzaste tu límite diario de {limits.pdf_reports_per_day} PDF gratis. "
                        "Recarga desde $10 para seguir hoy."
                        if limits.pdf_reports
                        else (
                            "Los PDFs requieren plan Pro, Élite o Founding, "
                            "o recarga desde $10. Mejora en /pricing."
                        )
                    )
                    _mark_recharge_needed("pdf", msg)
                    return json.dumps(
                        {"ok": False, "error": msg, "code": "needs_recharge"},
                    )
                pdf_wallet_charge_needed = True
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
            if pdf_wallet_charge_needed:
                from app.services.wallet import try_spend

                spend = try_spend(user_id, "pdf", units=1.0)
                if not spend.get("ok"):
                    msg = str(spend.get("error") or "Recarga desde $10 para generar PDF.")
                    _mark_recharge_needed("pdf", msg)
                    return json.dumps(
                        {"ok": False, "error": msg, "code": "needs_recharge"},
                    )
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
            from app.services.chat_image_generation import (
                run_chat_image_generation,
                should_take_direct_image_path,
            )
            from app.services.chat_intents import is_generate_image_intent

            plan_id = None
            try:
                sub = supabase_db.get_subscription(user_id)
                plan_id = sub.get("plan_id") if sub else None
            except Exception:  # noqa: BLE001
                pass
            llm_prompt = str(tool_input.get("prompt") or "").strip()
            user_texts = user_texts_from_messages(chat_messages or [])
            raw_user = (user_texts[-1] if user_texts else "").strip()
            prior_rows: list[dict[str, str]] = []
            if chat_messages:
                prior_rows = [
                    {"role": str(m.get("role") or "user"), "content": str(m.get("content") or "")}
                    for m in chat_messages[:-1]
                    if isinstance(m, dict)
                ]

            if raw_user and not should_take_direct_image_path(raw_user, prior_rows):
                logger.info(
                    "[CHAT:IMG-TOOL] skip — user did not ask for an image user=%s",
                    user_id[:8],
                )
                return json.dumps(
                    {
                        "ok": False,
                        "skipped": True,
                        "error": (
                            "El usuario no pidió generar una imagen todavía. "
                            "Responda SOLO en texto: acuerde el concepto. "
                            "PROHIBIDO decir que la imagen falló, copyright o límites."
                        ),
                    }
                )
            # Preferir utterance del usuario: el LLM a menudo resume/reescribe el brief.
            if raw_user and is_generate_image_intent(raw_user):
                prompt = raw_user
            else:
                prompt = llm_prompt or raw_user
            quality = str(tool_input.get("quality") or "auto")
            logger.info(
                "[CHAT:IMG-TOOL] prompt_source=%s user=%s",
                "raw_user" if prompt == raw_user and raw_user else "llm",
                user_id[:8],
            )
            gen = run_chat_image_generation(
                user_id,
                conversation_id,
                prompt,
                prior_rows,
                plan_id=plan_id,
            )
            if gen.get("ok") and gen.get("url"):
                return json.dumps(
                    {
                        "ok": True,
                        "url": gen["url"],
                        "caption": gen.get("caption"),
                        "quality": gen.get("quality") or quality,
                        "prompt": prompt,
                        "used_reference": gen.get("used_reference"),
                    }
                )
            gen_code = str(gen.get("code") or "generation_failed")
            gen_err = str(gen.get("error") or gen.get("reply") or "No pude generar la imagen.")
            if gen_code == "needs_recharge":
                _mark_recharge_needed("image", gen_err)
            return json.dumps(
                {
                    "ok": False,
                    "error": gen_err,
                    "code": gen_code,
                }
            )
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
                logger.warning("[CHAT] Llama simple failed, fallback Claude: %s", exc)
        else:
            logger.warning("[CHAT] Ollama sin modelo listo — fallback Claude inmediato")

    settings = get_settings()
    anthropic_key = settings.anthropic_api_key.strip()
    if anthropic_key:
        return _anthropic_simple_reply(
            api_key=anthropic_key,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
        )

    if not (api_key or "").strip():
        raise TextChatError(
            "Sin ANTHROPIC_API_KEY para fallback cuando Llama no responde.",
            http_status=503,
        )

    logger.warning("[CHAT] Sin Claude — fallback Gemini degradado")
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
    """Claude como fallback cloud conversacional — sin Llama (ver iter_send_message_stream)."""
    last_exc: Exception | None = None
    token_budget = max_tokens or _chat_max_tokens(user_text)

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
            logger.warning("[CHAT] Anthropic cascade failed: %s", exc)
            last_exc = exc

    if google_key:
        try:
            reply = _gemini_simple_reply(
                api_key=google_key,
                model=gemini_model,
                system=system,
                messages=messages,
                max_tokens=token_budget,
                allow_llama=False,
            )
            return reply, None, None
        except Exception as exc:  # noqa: BLE001
            logger.warning("[CHAT] Gemini simple failed (degradado): %s", exc)
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


def _pdf_success_message(title: str) -> str:
    safe = (title or "Documento CED").strip()[:200]
    return f'Listo. PDF "{safe}" generado. Ya está en su historial.'


def _normalize_pdf_tool_reply(
    reply: str,
    pdf_attachment: dict[str, Any] | None,
) -> str:
    if not pdf_attachment or not pdf_attachment.get("file_id"):
        return reply
    standard = _pdf_success_message(str(pdf_attachment.get("title") or "Documento CED"))
    cleaned = _strip_pdf_markdown_links(reply or "").strip()
    if not cleaned:
        return standard
    if "historial" in cleaned.lower():
        return cleaned
    if "descargar abajo" in cleaned.lower():
        return standard
    if len(cleaned) < 30 or not re.search(r"\bpdf\b", cleaned, re.I):
        return standard
    return cleaned


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


def _history_rows_from_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in messages:
        if not isinstance(row, dict):
            continue
        content = row.get("content")
        if isinstance(content, str) and content.strip():
            rows.append({"role": str(row.get("role") or "user"), "content": content.strip()})
    return rows


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
                    hallucination == "generate_image"
                    and not image_attachment
                    and not pdf_attachment
                ):
                    from app.services.chat_image_generation import (
                        looks_like_hallucinated_generate_image,
                    )

                    salvaged, salvaged_img = _salvage_image_if_needed(
                        user_id,
                        conversation_id,
                        _last_user_text(messages),
                        _history_rows_from_messages(messages),
                        reply,
                        image_attachment,
                        plan_id=_plan_id_for_user(user_id),
                    )
                    if salvaged_img:
                        return salvaged, pdf_attachment, salvaged_img
                    if salvaged and not looks_like_hallucinated_generate_image(salvaged):
                        return salvaged, pdf_attachment, None
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
                if pdf_attachment:
                    reply = _normalize_pdf_tool_reply(reply, pdf_attachment)
                salvaged, salvaged_img = _salvage_image_if_needed(
                    user_id,
                    conversation_id,
                    _last_user_text(messages),
                    _history_rows_from_messages(messages),
                    reply,
                    image_attachment,
                    plan_id=_plan_id_for_user(user_id),
                )
                reply = salvaged
                if salvaged_img:
                    image_attachment = salvaged_img
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
        salvaged, salvaged_img = _salvage_image_if_needed(
            user_id,
            conversation_id,
            user_text,
            _history_rows_from_messages(messages),
            reply,
            image_attachment,
            plan_id=_plan_id_for_user(user_id),
        )
        reply = salvaged
        if salvaged_img:
            image_attachment = salvaged_img
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
    image_mode: str | None = None,
    pdf_bytes: bytes | None = None,
    pdf_filename: str | None = None,
) -> dict[str, Any]:
    text = content.strip()
    mode = (image_mode or "").strip().lower()
    inbound_pdf = None
    if pdf_bytes:
        from app.services.pdf_ingest import (
            PdfIngestError,
            extract_document_text,
            format_pdf_for_llm,
            user_display_for_pdf,
        )

        try:
            inbound_pdf = extract_document_text(pdf_bytes, filename=pdf_filename)
        except PdfIngestError as exc:
            raise TextChatError(str(exc), http_status=exc.http_status) from exc
        if not text:
            kind = (inbound_pdf.kind or "pdf").lower()
            label = "Word (.docx)" if kind == "docx" else "PDF"
            text = (
                f"Analiza este documento {label}: resume lo importante, "
                "destaca puntos clave y responde con claridad."
            )

    if not text and not image_bytes and not inbound_pdf:
        raise TextChatError("Mensaje vacío.")
    if not inbound_pdf:
        from app.domain.chat_limits import CHAT_MESSAGE_TOO_LONG_ES, CHAT_MESSAGE_MAX_CHARS

        if text and len(text) > CHAT_MESSAGE_MAX_CHARS:
            raise TextChatError(CHAT_MESSAGE_TOO_LONG_ES, http_status=400)
        if content.strip() and len(content.strip()) > CHAT_MESSAGE_MAX_CHARS:
            raise TextChatError(CHAT_MESSAGE_TOO_LONG_ES, http_status=400)

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

    try:
        from app.services.referrals import note_sales_chat_if_relevant

        note_sales_chat_if_relevant(user_id, text)
    except Exception:  # noqa: BLE001
        pass

    settings = get_settings()
    anthropic_key = settings.anthropic_api_key.strip()
    google_key = settings.google_api_key.strip()
    gemini_model = _gemini_chat_model()
    from app.services.llama_service import use_llama

    if not google_key and not anthropic_key and not use_llama():
        raise TextChatError(
            "Servicio de chat no disponible. Configura GOOGLE_API_KEY, ANTHROPIC_API_KEY o Llama en Railway.",
            http_status=503,
        )

    if conversation_id:
        conv = supabase_db.get_conversation(conversation_id, user_id)
        if not conv or conv.get("channel") != "text":
            raise TextChatError("Conversación no encontrada.")
    else:
        title_source = text or (
            f"PDF: {inbound_pdf.filename}" if inbound_pdf else "Imagen adjunta"
        )
        title = title_source[:48] + ("…" if len(title_source) > 48 else "")
        conv = supabase_db.create_conversation(user_id, title=title, channel="text")
        conversation_id = str(conv["id"])

    history = supabase_db.get_conversation_messages(
        conversation_id, user_id, limit=CHAT_HISTORY_LIMIT,
    )
    if inbound_pdf:
        user_display = user_display_for_pdf(inbound_pdf.filename, content.strip())
    else:
        user_display = text or "📷 Imagen adjunta"
    supabase_db.append_message(
        conversation_id,
        user_id,
        "user",
        user_display,
        session_id=conversation_id,
        channel="text",
    )
    _bridge_studio_to_voice(
        user_id,
        text=user_display,
        image=bool(image_bytes),
        pdf_filename=inbound_pdf.filename if inbound_pdf else None,
    )

    def _finish(
        reply: str,
        *,
        route_meta: dict | None = None,
        pdf: dict[str, Any] | None = None,
        image: dict[str, Any] | None = None,
        open_module: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from app.services.opportunities_pilot.fitline_enroll import (
            maybe_force_enroll_if_signup_leak,
        )

        forced = maybe_force_enroll_if_signup_leak(user_id, reply)
        if forced:
            reply = str(forced["spoken"])
            open_module = forced.get("open_module") or open_module
            route_meta = route_meta or {"intent": "fitline_enroll", "source": "signup_leak"}
        try:
            supabase_db.append_message(
                conversation_id,
                user_id,
                "model",
                reply,
                session_id=conversation_id,
                channel="text",
            )
        except Exception:  # noqa: BLE001
            logger.exception("[CHAT] persist in _finish failed user=%s", user_id[:8])
        try:
            updated_status = chat_status(user_id)
        except Exception:  # noqa: BLE001
            logger.exception("[CHAT] status in _finish failed user=%s", user_id[:8])
            updated_status = {"blocked": False}
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
        if open_module:
            out["open_module"] = open_module
        recharge_needed = _consume_recharge_needed()
        if recharge_needed:
            out["recharge_needed"] = recharge_needed
        return out

    from app.services.publish_image_context import (
        get_publish_flow,
        register_text_chat_image,
    )
    from app.services.publish_text import (
        history_awaits_publish_image,
        is_image_for_publish_signal,
        is_social_publish_intent,
    )
    from app.services.text_publish_flow import (
        continue_publish_after_image,
        handle_publish_flow_turn,
    )

    # Registrar imagen ANTES del flujo de publicación (awaiting_image → attach).
    if image_bytes:
        try:
            register_text_chat_image(
                user_id,
                conversation_id,
                image_bytes,
                image_media_type or "image/jpeg",
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[CHAT] register image failed user=%s", user_id[:8])
            raise TextChatError(
                _format_image_generation_error(str(exc)),
                http_status=503,
            ) from exc

    from app.domain.ced_product_capabilities import try_capability_catalog_reply

    catalog_reply = try_capability_catalog_reply(text)
    if catalog_reply:
        return _finish(
            _finalize_chat_reply(catalog_reply),
            route_meta={"intent": "capability_catalog", "source": "direct"},
        )

    # PDF entrante: ir directo al LLM con el texto extraído (sin intents de imagen/LIFE).
    if inbound_pdf:
        user_caption = content.strip() or text
        llm_text = format_pdf_for_llm(inbound_pdf, user_caption)
        route = route_message(
            user_id,
            user_caption,
            channel="text",
            defer_enrichment=True,
        )
        messages = _anthropic_messages(history)
        messages.append({"role": "user", "content": llm_text})
        try:
            system = _build_chat_system(
                user_id, user_caption, route, conversation_id, history
            )
        except Exception:  # noqa: BLE001
            logger.exception("[CHAT] fallo armando system prompt (pdf) — usando base")
            system = _chat_system_for_user(user_id)
        system = (
            f"{system}\n\n"
            "El usuario adjuntó un DOCUMENTO PDF. Usa el texto del documento "
            "como fuente principal. Cita páginas o secciones cuando ayude. "
            "No inventes contenido que no esté en el documento."
        )
        try:
            reply, pdf_attachment, image_attachment = _complete_chat_resilient(
                user_id,
                user_text=llm_text,
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
            logger.exception("[CHAT] pdf ingest reply failed: %s", exc)
            raise TextChatError(
                "No pude analizar el PDF. Intenta de nuevo en un momento.",
                http_status=503,
            ) from exc
        reply = _ensure_chat_reply_quality(reply, user_text=user_caption)
        reply = _finalize_chat_reply(reply)
        return _finish(
            reply,
            route_meta={
                "intent": "pdf_ingest",
                "source": "attachment",
                "filename": inbound_pdf.filename,
                "page_count": inbound_pdf.page_count,
                "truncated": inbound_pdf.truncated,
            },
            pdf=pdf_attachment,
            image=image_attachment,
        )

    publish_reply = handle_publish_flow_turn(
        user_id,
        conversation_id,
        text,
        history=history,
        run_tool=_run_chat_tool,
        suggest_caption=lambda platform, user_text, hist: _suggest_social_caption(
            platform,
            user_text,
            hist,
            user_id=user_id,
            conversation_id=conversation_id,
        ),
    )
    if publish_reply:
        return _finish(
            _finalize_chat_reply(publish_reply),
            route_meta={"intent": "publish_flow", "source": "conversation"},
        )

    if image_bytes:
        try:
            from app.services.chat_multimedia import analyze_chat_image
            from app.services.chat_image_generation import _merge_creative_user_request
            from app.services.marketing_creative import (
                is_marketing_creative_intent,
                resolve_image_creation_from_attachment,
            )

            flow = get_publish_flow(user_id, conversation_id)
            awaiting_pub = bool(flow and str(flow.get("stage") or "") == "awaiting_image")
            mode_l = (mode or "").strip().lower()
            edit_modes = {"edit", "variation", "inspired"}
            explicit_analyze = mode_l == "analyze" and bool(
                re.search(
                    r"\b(analiza|analizá|describe|expl[ií]came)\b|"
                    r"qu[eé]\s+piensas\s+de\s+esta\s+imagen",
                    text,
                    re.I,
                )
            )
            # Analyze-only UI default still allows free-form edits in the caption.
            wants_edit = mode_l in edit_modes or (
                mode_l != "publish"
                and is_attachment_image_edit_request(text)
                and not explicit_analyze
            )

            # Edit/variation beats publish: «que diga publicaciones en redes» ≠ publicar.
            wants_publish = mode_l == "publish" or (
                not wants_edit
                and not explicit_analyze
                and (
                    is_social_publish_intent(text, with_image=True)
                    or (
                        is_image_for_publish_signal(text)
                        and len((text or "").strip()) <= 72
                    )
                    or awaiting_pub
                    or history_awaits_publish_image(history)
                )
            )

            if wants_edit:
                style_mode = mode_l if mode_l in edit_modes else "edit"
                use_marketing = (
                    is_marketing_creative_intent(text)
                    and not re.search(
                        r"\b(?:lobo|cuadro|cerebro|fragment|pon\s+un|agrega|que\s+diga)\b",
                        text,
                        re.I,
                    )
                )
                creation = (
                    resolve_image_creation_from_attachment(text, history)
                    if use_marketing
                    else None
                )
                if creation:
                    ref_prompt = _merge_creative_user_request(
                        creation["internal_prompt"],
                        text,
                    )
                    success_reply = creation.get("reply") or "Listo. Aquí está su creativo."
                    caption = creation.get("display_label") or "Creativo"
                    style_mode = creation.get("style_mode") or style_mode
                    route_intent = "marketing_creative"
                else:
                    # Pedido libre: conservar instrucciones del usuario (lobo, textos, etc.).
                    ref_prompt = (text or "").strip() or "Edita esta imagen según lo pedido."
                    success_reply = "Listo. Aquí está la imagen con los cambios pedidos."
                    caption = ref_prompt[:72] if len(ref_prompt) <= 72 else "Imagen editada"
                    route_intent = "image_reference_edit"

                ref_result = _generate_chat_image_with_reference(
                    user_id,
                    prompt=ref_prompt,
                    reference_bytes=image_bytes,
                    media_type=image_media_type or "image/jpeg",
                    style_mode=style_mode,
                )
                if ref_result.get("ok") and ref_result.get("url"):
                    from app.services.publish_image_context import register_text_chat_image_url

                    register_text_chat_image_url(
                        user_id,
                        conversation_id,
                        str(ref_result["url"]),
                    )
                    return _finish(
                        success_reply,
                        route_meta={"intent": route_intent, "source": "attachment_reference"},
                        image=_chat_image_attachment(
                            str(ref_result["url"]),
                            caption=str(caption),
                            quality=str(ref_result.get("quality") or ""),
                        ),
                    )
                err = str(ref_result.get("error") or "No pude editar la imagen.")
                return _finish(
                    _format_image_generation_error(err),
                    route_meta={"intent": route_intent, "source": "attachment_error"},
                )

            if wants_publish:
                reply = continue_publish_after_image(
                    user_id,
                    conversation_id,
                    text if (text or "").strip() else "Usa esta imagen para publicar",
                    history=history,
                )
                return _finish(
                    reply,
                    route_meta={"intent": "publish_flow", "source": "image_upload"},
                )

            creation = resolve_image_creation_from_attachment(text, history)
            if creation:
                ref_prompt = _merge_creative_user_request(
                    creation["internal_prompt"],
                    text,
                )
                ref_result = _generate_chat_image_with_reference(
                    user_id,
                    prompt=ref_prompt,
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

            analyze_prompt = (text or "").strip()
            if not analyze_prompt or analyze_prompt in {
                "📷 Imagen adjunta",
                "¿Qué piensas de esta imagen?",
            }:
                analyze_prompt = (
                    "Describe brevemente qué se ve en esta imagen. "
                    "Si el usuario no pidió nada más, pregunta solo si desea "
                    "analizarla con más detalle o editarla/variarla. "
                    "NO ofrezcas publicarla en redes."
                )
            reply = analyze_chat_image(
                user_id,
                image_bytes=image_bytes,
                media_type=image_media_type or "image/jpeg",
                user_text=analyze_prompt,
            )
            from app.services.publish_image_context import set_session_vision_analysis

            set_session_vision_analysis(user_id, conversation_id, reply)
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

    from app.services.opportunities_pilot.fitline_enroll import try_fitline_enroll_turn

    enroll = try_fitline_enroll_turn(user_id, text, history=history)
    if enroll:
        return _finish(
            enroll["spoken"],
            route_meta={"intent": "fitline_enroll", "source": "direct"},
            open_module=enroll.get("open_module"),
        )

    from app.services.user_trash import try_trash_turn

    trash_turn = try_trash_turn(user_id, text)
    if trash_turn:
        return _finish(
            str(trash_turn["spoken"]),
            route_meta={"intent": "trash", "source": "direct"},
        )

    from app.services.chat_intents import (
        is_casual_chat_interrupt,
        is_creative_artifact_intent,
    )
    from app.services.cognitive_intents import is_conversation_recall_intent
    from app.modules.environment_module import is_environment_intent
    from app.services.session_memory import build_conversation_recall_reply
    from app.services.chat_image_generation import (
        should_take_direct_image_path,
        run_chat_image_generation,
    )

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

    # Imagen/PDF ANTES de clima/finanzas: palabras trampa dentro
    # del texto citado («tiempo», «cita», «correo») no deben secuestrar el pedido.
    detail = resolve_pdf_detail_for_turn(text, history)
    if detail == "ask" or (
        detail in ("brief", "full") and (
            resolve_pdf_request(text, history) or prior_pdf_user_request(history)
        )
    ):
        direct_pdf = _try_direct_pdf_from_context(
            user_id,
            text=text,
            history=history,
            conversation_id=conversation_id,
        )
        if direct_pdf:
            reply, attachment = direct_pdf
            return _finish(
                _finalize_chat_reply(reply),
                route_meta={
                    "intent": "pdf_clarify" if detail == "ask" else "pdf",
                    "source": "direct",
                    "pdf_detail": detail,
                },
                pdf=attachment if attachment.get("file_id") else None,
            )

    if should_take_direct_image_path(text, history):
        plan_id = None
        try:
            sub = supabase_db.get_subscription(user_id)
            plan_id = sub.get("plan_id") if sub else None
        except Exception:  # noqa: BLE001
            pass

        from app.services.marketing_creative import is_marketing_creative_intent

        gen = run_chat_image_generation(
            user_id,
            conversation_id,
            text,
            history,
            plan_id=plan_id,
        )
        if gen.get("ok") and gen.get("url"):
            return _finish(
                gen.get("reply") or "Listo. Aquí está tu imagen generada.",
                route_meta={
                    "intent": "marketing_creative"
                    if gen.get("used_reference") or is_marketing_creative_intent(text)
                    else "generate_image",
                    "source": "direct",
                    "used_reference": bool(gen.get("used_reference")),
                },
                image=_chat_image_attachment(
                    str(gen["url"]),
                    caption=str(gen.get("caption") or "Imagen generada"),
                    quality=str(gen.get("quality") or ""),
                ),
            )
        direct_err = str(gen.get("error") or gen.get("reply") or "")
        if gen.get("code") == "needs_recharge":
            _mark_recharge_needed("image", direct_err)
        return _finish(
            _format_image_generation_error(direct_err),
            route_meta={"intent": "generate_image", "source": "direct_error"},
        )

    # Tras imagen/PDF: módulos LIFE. Si el pedido era creativo, no competir.
    creative = is_creative_artifact_intent(text)

    if not creative and is_environment_intent(text):
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
    from app.modules.finance_module import handle_finance_query_sync, is_finance_intent

    if not creative and is_reminder_intent(text) and re.search(r"recu[eé]rdame", text, re.I):
        reminder_result = handle_reminder_create_sync(user_id, text)
        return _finish(
            _finalize_chat_reply(str(reminder_result.get("spoken") or "")),
            route_meta={"intent": "reminder_create", "source": "direct"},
        )

    if not creative and is_reminder_intent(text):
        reminder_result = handle_reminder_query_sync(user_id, text)
        return _finish(
            _finalize_chat_reply(str(reminder_result.get("spoken") or "")),
            route_meta={"intent": "reminder_list", "source": "direct"},
        )

    if not creative and is_finance_intent(text):
        finance_result = handle_finance_query_sync(user_id, text)
        return _finish(
            _finalize_chat_reply(str(finance_result.get("spoken") or "")),
            route_meta={"intent": "finance", "source": "direct"},
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
        from app.services.opportunities_pilot.fitline_knowledge import prefers_fitline_over_web

        if not prefers_fitline_over_web(text):
            return _finish(
                _finalize_chat_reply(route.speakable),
                route_meta=route.to_dict(),
            )

    messages = _anthropic_messages(history)
    from app.services.opportunities_pilot.fitline_knowledge import (
        with_fitline_user_prefix,
    )

    messages.append({"role": "user", "content": with_fitline_user_prefix(text)})
    try:
        system = _build_chat_system(user_id, text, route, conversation_id, history)
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

    reply, image_attachment = _salvage_image_if_needed(
        user_id,
        conversation_id,
        text,
        history,
        reply,
        image_attachment,
        plan_id=_plan_id_for_user(user_id),
    )
    if image_attachment:
        from app.services.chat_image_generation import (
            looks_like_hallucinated_generate_image,
            strip_hallucinated_generate_image_text,
        )

        if looks_like_hallucinated_generate_image(reply):
            reply = _finalize_chat_reply(
                strip_hallucinated_generate_image_text(reply)
                or str(image_attachment.get("caption") or "Imagen generada")
            )

    return _finish(
        reply,
        route_meta=route.to_dict(),
        pdf=pdf_attachment,
        image=image_attachment,
    )


def _sse_event(name: str, payload: dict[str, Any]) -> str:
    from app.services.sse_util import sse_event

    return sse_event(name, payload)


def _sse_flush() -> str:
    """Comentario SSE para forzar flush en proxies (Railway / Next.js)."""
    from app.services.sse_util import sse_flush

    return sse_flush()


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
    _bridge_studio_to_voice(user_id, text=text)
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


def _publish_flow_requires_blocking(
    user_id: str,
    conversation_id: str | None,
    text: str,
) -> bool:
    """Confirmaciones cortas («te confirmo», «sí», «envía») no deben ir por SSE sin tools."""
    from app.services.publish_image_context import get_publish_flow
    from app.services.publish_text import (
        is_publish_confirm,
        is_social_publish_intent,
        wants_publish_now,
    )

    t = (text or "").strip()
    if not t:
        return False
    if is_publish_confirm(t, allow_short_yes=False) or wants_publish_now(t):
        return True
    if is_social_publish_intent(t):
        return True
    if conversation_id and get_publish_flow(user_id, conversation_id):
        # Con borrador activo, incluso «sí» / ajustes deben pasar por handle_publish_flow_turn.
        return True
    return False


def _can_stream_chat_text(
    text: str,
    *,
    user_id: str | None = None,
    conversation_id: str | None = None,
) -> bool:
    from app.modules.environment_module import is_environment_intent
    from app.services.chat_module_context import requires_sync_module_handler
    from app.services.cognitive_intents import (
        is_conversation_recall_intent,
        is_news_intent,
        is_weather_intent,
        is_web_research_intent,
        requires_live_web,
    )

    if user_id and _publish_flow_requires_blocking(user_id, conversation_id, text):
        return False
    if requires_sync_module_handler(text):
        return False
    if is_weather_intent(text) or is_news_intent(text):
        return True
    if is_conversation_recall_intent(text):
        return False
    # Imagen: permitir SSE (status keepalives + path directo). PDF sigue bloqueante.
    if is_pdf_intent(text):
        return False
    if is_generate_image_intent(text):
        return True
    from app.services.opportunities_pilot.fitline_knowledge import prefers_fitline_over_web

    if is_web_research_intent(text) and not prefers_fitline_over_web(text):
        return False
    if is_environment_intent(text):
        return False
    if requires_live_web(text) and not prefers_fitline_over_web(text):
        return False
    if _needs_chat_tools(text) and not (is_weather_intent(text) or is_news_intent(text)):
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
    user_text: str = "",
):
    from app.services.chat_stream_pipeline import iter_unified_llm_stream

    for piece, _label in iter_unified_llm_stream(
        api_key=api_key,
        model=model,
        system=system,
        messages=messages,
        max_tokens=max_tokens,
        allow_llama=allow_llama,
        user_text=user_text,
    ):
        if piece:
            yield piece


def _iter_blocking_send(
    user_id: str,
    text: str,
    conversation_id: str | None,
):
    """Ejecuta send_message (ruta bloqueante: imagen/PDF/herramientas) dentro del SSE.

    Corre la llamada en un hilo y emite keep-alives cada 10 s: sin bytes el
    cliente aborta a los 45 s y la UI queda en silencio total. Cualquier
    excepción se convierte en un evento done con mensaje de error, nunca en
    un stream muerto.
    """
    from concurrent.futures import ThreadPoolExecutor
    from concurrent.futures import TimeoutError as _FutureTimeout

    from app.services.chat_image_generation import should_take_direct_image_path

    if should_take_direct_image_path(text, None):
        yield _sse_event("status", {"text": "Generando imagen con IA…"})
        yield _sse_flush()

    result: dict[str, Any] | None = None
    error_reply: str | None = None
    started = time.perf_counter()
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(
            send_message, user_id, content=text, conversation_id=conversation_id
        )
        while True:
            if time.perf_counter() - started > BLOCKING_STREAM_DEADLINE_SEC:
                error_reply = (
                    "La operación tardó demasiado. Intenta de nuevo en unos segundos."
                )
                break
            try:
                result = future.result(timeout=IMAGE_STREAM_KEEPALIVE_SEC)
                break
            except _FutureTimeout:
                if should_take_direct_image_path(text, None):
                    yield _sse_event("status", {"text": "Generando imagen con IA…"})
                yield _sse_flush()
            except TextChatError as exc:
                error_reply = str(exc) or "No pude completar esa acción."
                break
            except Exception:
                logger.exception(
                    "[CHAT] stream blocking-path failed user=%s", user_id[:8]
                )
                error_reply = (
                    "No pude completar esa acción. Intenta de nuevo en un momento."
                )
                break
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    if error_reply is not None or result is None:
        reply = error_reply or "No pude completar esa acción."
        yield _sse_event("token", {"text": reply})
        yield _sse_flush()
        yield _sse_event(
            "done", {"conversation_id": conversation_id, "reply": reply}
        )
        return

    reply = str(result.get("reply") or "").strip()
    if reply:
        yield _sse_event("token", {"text": reply})
        yield _sse_flush()
    yield _sse_event("done", result)


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

    from app.domain.chat_limits import CHAT_MESSAGE_MAX_CHARS, CHAT_MESSAGE_TOO_LONG_ES

    text = content.strip()
    if not text:
        raise TextChatError("Mensaje vacío.")
    if len(text) > CHAT_MESSAGE_MAX_CHARS:
        raise TextChatError(CHAT_MESSAGE_TOO_LONG_ES, http_status=400)

    try:
        from app.services.referrals import note_sales_chat_if_relevant

        note_sales_chat_if_relevant(user_id, text)
    except Exception:  # noqa: BLE001
        pass

    if not _can_stream_chat_text(
        text, user_id=user_id, conversation_id=conversation_id
    ):
        yield from _iter_blocking_send(user_id, text, conversation_id)
        return

    _perf("validated")

    # Doble red: por si el conversation_id llega tarde o el flujo se creó mid-stream setup.
    if conversation_id and _publish_flow_requires_blocking(user_id, conversation_id, text):
        yield from _iter_blocking_send(user_id, text, conversation_id)
        return

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

    from app.services.opportunities_pilot.fitline_enroll import try_fitline_enroll_turn

    stream_hist: list[dict[str, Any]] = []
    if conversation_id:
        try:
            stream_hist = supabase_db.get_conversation_messages(
                conversation_id, user_id, limit=8,
            )
        except Exception:  # noqa: BLE001
            stream_hist = []
    enroll = try_fitline_enroll_turn(user_id, text, history=stream_hist)
    if enroll:
        reply = str(enroll["spoken"])
        yield _sse_event("token", {"text": reply})
        yield _sse_flush()
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
                "cognitive": {"intent": "fitline_enroll", "source": "direct"},
                "open_module": enroll.get("open_module"),
            },
        )
        try:
            supabase_db.append_message(
                conv_id, user_id, "user", text, session_id=conv_id, channel="text",
            )
            _bump_stream_usage_cache(user_id)
            supabase_db.append_message(
                conv_id, user_id, "model", reply, session_id=conv_id, channel="text",
            )
        except Exception:  # noqa: BLE001
            logger.exception("[CHAT] enroll persist failed user=%s", user_id[:8])
        return

    from app.services.user_trash import try_trash_turn

    trash_turn = try_trash_turn(user_id, text)
    if trash_turn:
        reply = str(trash_turn["spoken"])
        yield _sse_event("token", {"text": reply})
        yield _sse_flush()
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
                "cognitive": {"intent": "trash", "source": "direct"},
            },
        )
        return

    yield _sse_event("status", {"text": "Preparando respuesta…"})
    yield _sse_flush()

    settings = get_settings()
    google_key = settings.google_api_key.strip()
    anthropic_key = settings.anthropic_api_key.strip()
    gemini_model = _gemini_chat_model()
    from app.services.llama_service import use_llama

    if not google_key and not anthropic_key and not use_llama():
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

    # Tras resolver conversation_id: si hay borrador Meta, publicar por vía bloqueante.
    if _publish_flow_requires_blocking(user_id, conversation_id, text):
        yield from _iter_blocking_send(user_id, text, conversation_id)
        return

    # PDF follow-up ("completo"/"breve") no pasa is_pdf_intent → sin este check
    # cae a Gemini stream y finge "Generando el PDF…" sin adjunto (repro prod).
    from app.services.chat_intents import resolve_pdf_detail_for_turn

    pdf_detail = resolve_pdf_detail_for_turn(text, history)
    if pdf_detail in ("ask", "brief", "full"):
        yield from _iter_blocking_send(user_id, text, conversation_id)
        return

    from app.services.chat_image_generation import (
        run_chat_image_generation,
        should_take_direct_image_path,
    )

    if should_take_direct_image_path(text, history):
        status = "Generando imagen con IA…"
        yield _sse_event("status", {"text": status})
        yield _sse_flush()

        def _run_image_job() -> dict[str, Any]:
            return run_chat_image_generation(
                user_id,
                conversation_id,
                text,
                history,
                plan_id=_plan_id_for_user(user_id),
            )

        gen: dict[str, Any] | None = None
        image_error: str | None = None
        image_attachment: dict[str, Any] | None = None
        reply = "No pude generar la imagen. Intenta de nuevo."
        from concurrent.futures import TimeoutError as _FutureTimeout

        # wait=False: si vence el deadline, seguir emitiendo done/error sin
        # esperar a Ideogram/Gemini (shutdown(wait=True) mataba los keepalives).
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            try:
                future = pool.submit(_run_image_job)
                hard_deadline = time.perf_counter() + IMAGE_STREAM_DEADLINE_SEC
                while True:
                    if time.perf_counter() > hard_deadline:
                        image_error = (
                            "La generación de imagen tardó demasiado. "
                            "Intenta de nuevo en unos segundos."
                        )
                        break
                    try:
                        gen = future.result(timeout=IMAGE_STREAM_KEEPALIVE_SEC)
                        break
                    except _FutureTimeout:
                        yield _sse_event("status", {"text": status})
                        yield _sse_flush()
                    except Exception:
                        logger.exception(
                            "[CHAT] stream image job failed user=%s", user_id[:8]
                        )
                        image_error = "No pude generar la imagen. Intenta de nuevo."
                        break
            finally:
                pool.shutdown(wait=False, cancel_futures=True)

            if image_error is not None or gen is None:
                reply = image_error or "No pude generar la imagen."
                image_attachment = None
                gen = {
                    "ok": False,
                    "code": "timeout" if image_error and "tardó" in image_error else "error",
                }
            elif gen.get("ok") and gen.get("url"):
                reply = str(gen.get("reply") or "Listo. Aquí está tu imagen generada.")
                image_attachment = _chat_image_attachment(
                    str(gen["url"]),
                    caption=str(gen.get("caption") or "Imagen generada"),
                    quality=str(gen.get("quality") or "") or None,
                )
            else:
                reply = _format_image_generation_error(
                    str(gen.get("error") or gen.get("reply") or "")
                )
                image_attachment = None
        except Exception:  # noqa: BLE001
            logger.exception("[CHAT] stream image path failed user=%s", user_id[:8])
            reply = "No pude generar la imagen. Intenta de nuevo."
            image_attachment = None
            gen = {"ok": False, "code": "error"}

        try:
            usage = _stream_usage_snapshot(user_id, profile)
        except Exception:  # noqa: BLE001
            logger.exception("[CHAT] image usage snapshot failed user=%s", user_id[:8])
            usage = {"blocked": False}

        payload: dict[str, Any] = {
            "conversation_id": conversation_id,
            "reply": reply,
            "usage": usage,
            "cognitive": {
                "intent": "generate_image",
                "source": "direct",
                "used_reference": bool((gen or {}).get("used_reference")),
            },
        }
        if image_attachment:
            payload["image"] = image_attachment
        elif (gen or {}).get("code") == "needs_recharge":
            payload["recharge_needed"] = {"resource": "image", "message": reply}
        # Cualquier usuario, cualquier pedido de imagen: emitir SSE antes de persistir
        # para que un fallo de DB no deje «Respuesta incompleta del chat».
        yield _sse_event("token", {"text": reply})
        yield _sse_flush()
        yield _sse_event("done", payload)
        try:
            supabase_db.append_message(
                conversation_id,
                user_id,
                "user",
                text,
                session_id=conversation_id,
                channel="text",
            )
            _bump_stream_usage_cache(user_id)
            supabase_db.append_message(
                conversation_id,
                user_id,
                "model",
                reply,
                session_id=conversation_id,
                channel="text",
            )
        except Exception:  # noqa: BLE001
            logger.exception("[CHAT] persist after image stream failed user=%s", user_id[:8])
        return

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

    user_message_persisted = False

    def _persist_user_message() -> None:
        nonlocal user_message_persisted
        if user_message_persisted:
            return
        supabase_db.append_message(
            conversation_id,
            user_id,
            "user",
            text,
            session_id=conversation_id,
            channel="text",
        )
        _bridge_studio_to_voice(user_id, text=text)
        _bump_stream_usage_cache(user_id)
        user_message_persisted = True

    from app.services.system_clock import try_instant_datetime_reply

    dt_instant = try_instant_datetime_reply(text, history=history)
    if dt_instant:
        _persist_user_message()
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
        _persist_user_message()
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
    from app.services.opportunities_pilot.fitline_knowledge import (
        with_fitline_user_prefix,
    )

    messages.append({"role": "user", "content": with_fitline_user_prefix(text)})
    try:
        system = _build_chat_system_light(user_id, text)
    except Exception:  # noqa: BLE001
        logger.exception("[CHAT] fallo armando system prompt — usando base")
        system = CHAT_SYSTEM_BASE

    module_route_meta: dict[str, Any] | None = None
    from app.services.chat_module_context import fetch_module_stream_context

    module_context, module_route_meta = fetch_module_stream_context(user_id, text)
    if module_context:
        system = f"{system}\n\n{module_context}"
        yield _sse_event("status", {"text": "Consultando datos del módulo…"})
        yield _sse_flush()

    token_budget = _chat_max_tokens(text)
    accumulated: list[str] = []
    stream_buf = ""
    _perf("pre_stream")
    try:
        from app.services.stream_delta import stream_piece_delta

        # Claude directo — sin Llama. Medido en producción: Llama (13B, CPU en
        # Railway) agota siempre su timeout sin producir un token y el pipeline
        # termina cayendo a Claude de todos modos (mismo techo que llevó a migrar
        # voz por completo a Gemini). Mantener el intento de Llama solo agregaba
        # varios segundos de espera muerta a cada turno sin ningún beneficio real.
        allow_llama = False
        for piece in _gemini_simple_reply_stream(
            api_key=google_key,
            model=gemini_model,
            system=system,
            messages=messages,
            max_tokens=token_budget,
            allow_llama=allow_llama,
        ):
            if not user_message_persisted:
                _persist_user_message()
                _perf("first_token")
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

    from app.services.opportunities_pilot.fitline_enroll import (
        maybe_force_enroll_if_signup_leak,
    )

    forced_enroll = maybe_force_enroll_if_signup_leak(user_id, reply)
    stream_open_module: dict[str, Any] | None = None
    if forced_enroll:
        reply = str(forced_enroll["spoken"])
        stream_open_module = forced_enroll.get("open_module")

    reply, image_attachment = _salvage_image_if_needed(
        user_id,
        conversation_id,
        text,
        history,
        reply,
        image_attachment,
        plan_id=_plan_id_for_user(user_id),
    )

    try:
        usage = _stream_usage_snapshot(user_id, profile)
    except Exception:  # noqa: BLE001
        logger.exception("[CHAT] text usage snapshot failed user=%s", user_id[:8])
        usage = {"blocked": False}

    payload: dict[str, Any] = {
        "conversation_id": conversation_id,
        "reply": reply,
        "usage": usage,
        "cognitive": module_route_meta if module_route_meta else route.to_dict(),
    }
    if stream_open_module:
        payload["open_module"] = stream_open_module
        payload["cognitive"] = {"intent": "fitline_enroll", "source": "signup_leak"}
    if pdf_attachment:
        payload["pdf"] = pdf_attachment
    if image_attachment:
        payload["image"] = image_attachment
    recharge_needed = _consume_recharge_needed()
    if recharge_needed:
        payload["recharge_needed"] = recharge_needed
    yield _sse_event("done", payload)
    try:
        _persist_user_message()
        supabase_db.append_message(
            conversation_id,
            user_id,
            "model",
            reply,
            session_id=conversation_id,
            channel="text",
        )
    except Exception:  # noqa: BLE001
        logger.exception("[CHAT] persist after text stream failed user=%s", user_id[:8])
