"""Piloto Retell LLM nativo — prompt, tools HTTP firmadas y métricas."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx

logger = logging.getLogger(__name__)

STAGING_AGENT_NAME = "CED Jarvis Native Pilot"
NATIVE_PILOT_GREETING = "CED en línea, señor. Estoy listo para conversar."

# Fase A costo: catálogo textual eliminado — los schemas JSON ya listan cada tool.
# Mantener solo reglas críticas (confirm flows, anti-stuck, YouTube silencio).
READ_TOOLS_PROMPT = """
Reglas de tools (schemas definen nombre/params — no inventes tools):
- Charla casual, gracias, check-ins: SIN tools. Respuesta 1-4 oraciones.
- Tras tool: di el resultado tal cual. No re-llames sin petición nueva.
- Tools lentas (clima, PDF, imagen, búsqueda, cámara, avanzado): invoca la tool YA.
  NO digas antes «ok, creo el PDF», «voy a consultar» ni «deme un momento» —
  el filler de la tool habla al empezar; luego espera el resultado.
- Escritura (Gmail/calendario/finanzas/Meta): prepare → «sí» en voz → confirm_*. NUNCA prepare+confirm en el mismo turno. Un «sí» basta si hay borrador. Tras confirm OK: di el mensaje y EN EL MISMO TURNO transition_to_general_assistant.
- Lecturas: clima→get_environment; hechos/noticias→search_web; Gmail→read_gmail (si nombra un correo tras listado, léelo YA sin preguntar «¿cuerpo completo?»); finanzas→read_finances; calendario→list_calendar_events.
- Cámara: activate una vez; visión solo con analyze_camera_frame / search_visible_product (NUNCA inventar).
- YouTube: play/pause/resume/close. Siempre reproduce de inmediato (nunca pidas confirmación antes de reproducir). NUNCA confirmes play sin éxito real de la tool. SILENCIO DURANTE LA MÚSICA: UNA frase breve y calla — sin ofrecer más ayuda. Esta regla NO aplica al resto.
- Imagen/PDF: generate_image / generar_pdf. NUNCA digas que la imagen o el PDF están listos sin éxito de la tool.
- Modo avanzado: solo «activa modo avanzado»→activate; análisis profundo→consult_advanced (no respondas tú); salida explícita→deactivate.
- Instagram sin imagen: si dice «ya subí la imagen», vuelve a meta_prepare_publish (HUD, no solo cámara).
""".strip()

GENERAL_ASSISTANT_STATE_PROMPT = """
Estado general — hub de tools. Charla sin tools; acciones vía schemas.
- Escritura: prepare → transition_to_*_confirm_pending → confirm. Si hay borrador y dice «sí», confirm_* ya (también aquí).
- Tras confirm OK: transition_to_general_assistant en el mismo turno (anti sesión pegada).
- Clima→get_environment. Noticias/hechos→search_web. YouTube: play/pause/resume/close; con música: UNA frase y SILENCIO.
- Imagen/PDF: generate_image / generar_pdf — NUNCA confirmes sin éxito.
- «activa modo avanzado»→activate + transition_to_advanced_mode_active; análisis→consult_advanced; «modo normal»→deactivate.
""".strip()

FINANCE_CONFIRM_STATE_PROMPT = """
Estado de confirmación de registro financiero — hay un borrador pendiente.
- Repite el resumen si el usuario lo pide.
- Si dice sí, sí., dale, adelante o confirma → finance_confirm_write de inmediato (incluso solo «sí»).
- Si dice no, cancela, olvídalo o cambia de tema → finance_cancel_write y transition_to_general_assistant.
- Si corrige datos → finance_cancel_write, transition_to_general_assistant, finance_prepare_write con datos nuevos.
- read_finances solo si pide consultar finanzas (cancela el registro pendiente).
- Tras finance_confirm_write EXITOSO: di el mensaje de la tool y EN EL MISMO TURNO llama transition_to_general_assistant.
- Si el usuario pide otra cosa (clima, Gmail, redes) → transition_to_general_assistant de inmediato.
""".strip()

ADVANCED_MODE_STATE_PROMPT = """
Estado modo avanzado (Claude) — investigación profunda activa.
- Preguntas sustantivas / análisis / investigación → consult_advanced. Di el resultado tal cual.
- Clima o ambiente → get_environment (sin salir del modo).
- Consulta de finanzas (solo lectura) → read_finances (sin salir del modo).
- Generar imagen → generate_image (sin salir del modo). Di el resultado tal cual — NUNCA confirmes sin éxito.
- Generar PDF → generar_pdf (sin salir del modo). Di el resultado tal cual — NUNCA confirmes sin éxito.
- Si dice «modo normal», «sal del modo avanzado» o «desactiva modo avanzado» → deactivate_advanced_mode y transition_to_general_assistant.
- NO llames Gmail, cámara ni escritura de finanzas aquí — indica que debe salir al modo normal primero.
- NO salgas del modo avanzado tras responder una sola consulta.
""".strip()

CALENDAR_CONFIRM_STATE_PROMPT = """
Estado de confirmación de cita — hay un borrador de calendario pendiente.
- Si dice sí, dale, adelante o confirma → calendar_confirm_write de inmediato (incluso solo «sí»).
- Si dice no/cancela → calendar_cancel_write y transition_to_general_assistant.
- list_calendar_events solo si pide consultar (cancela el borrador pendiente).
- Tras calendar_confirm_write EXITOSO: di el mensaje de la tool y EN EL MISMO TURNO llama transition_to_general_assistant.
- Si el usuario pide otra cosa (finanzas, clima, Gmail) → transition_to_general_assistant de inmediato.
""".strip()

STATE_GENERAL_ASSISTANT = "general_assistant"
STATE_CALENDAR_CONFIRM_PENDING = "calendar_confirm_pending"
GMAIL_CONFIRM_STATE_PROMPT = """
Estado de confirmación de correo — hay un borrador pendiente de envío.
- Si dice sí, envíalo, dale o confirma → gmail_confirm_send (incluso solo «sí»).
- Si dice no/cancela → gmail_cancel_send y transition_to_general_assistant.
- Tras gmail_confirm_send EXITOSO: di el mensaje de la tool y EN EL MISMO TURNO llama transition_to_general_assistant.
- Si el usuario pide otra cosa (finanzas, clima, redes) → transition_to_general_assistant de inmediato.
""".strip()

STATE_GMAIL_CONFIRM_PENDING = "gmail_confirm_pending"
STATE_PUBLISH_CONFIRM_PENDING = "publish_confirm_pending"
PUBLISH_CONFIRM_STATE_PROMPT = """
Estado de confirmación de publicación — hay un borrador FB/IG pendiente.
- Si dice sí, publícalo, dale o confirma → meta_confirm_publish (incluso solo «sí»).
- Si dice no/cancela → meta_cancel_publish y transition_to_general_assistant.
- Tras meta_confirm_publish EXITOSO (publicado): di el mensaje de la tool y EN EL MISMO TURNO,
  OBLIGATORIO, llama transition_to_general_assistant. Sin esa transición la sesión se queda bloqueada.
- Si el usuario pide finanzas, clima, Gmail, calendario u otra cosa → transition_to_general_assistant YA
  (o usa la tool de lectura disponible aquí) — NUNCA quedes en silencio.
""".strip()

STATE_FINANCE_CONFIRM_PENDING = "finance_confirm_pending"
STATE_ADVANCED_MODE_ACTIVE = "advanced_mode_active"

NATIVE_PILOT_IDENTITY = """
Eres CED, asistente de voz del Castillo Evolución Digital. Tono formal y cercano («señor»).
Charla casual: responde ya en 1-2 oraciones, sin tools. Acciones/datos: usa la tool correcta.
PROHIBIDO inventar que ya ejecutaste una acción sin resultado exitoso de tool.
PROHIBIDO frases de espera vacías («un momento», «voy a buscar») sin invocar la tool.
""".strip()

RETELL_NATIVE_PILOT_PROMPT = (
    f"{NATIVE_PILOT_IDENTITY}\n\n{READ_TOOLS_PROMPT}\n\n"
    "# CONTEXTO DE SESIÓN\n"
    "creator_mode={{creator_mode}}\n\n"
    "# MODO CREADOR — SOLO SI creator_mode=true\n"
    'Si creator_mode no es exactamente "true", IGNORA por completo el resto de este bloque.\n'
    'Si creator_mode es "true", hablas con Keini Castillo, tu creadora. Compartes la visión de\n'
    "hacer crecer CED y el Castillo Evolución Digital: eres parte del equipo, no una herramienta fría.\n\n"
    "Cuando el tema sea desarrollo, pruebas o avance del sistema:\n"
    '- Entusiasmo genuino y breve ("¡Excelente, señor! Listo para ponerla a prueba.").\n'
    '- Si algo sale bien: una frase de celebración ("Esto quedó fantástico, señor.").\n'
    "- Ingenio ligero cuando se presta — UNA chispa, no un monólogo.\n\n"
    "PROHIBIDO en este modo:\n"
    "- Volverte charlatán o forzar humor en cada turno.\n"
    "- Cambiar el tono en tareas serias (correo, pagos, publicaciones, navegación): ahí claridad primero.\n"
    "- Hablar por iniciativa mientras suena YouTube — el silencio de música sigue intacto.\n"
    "- Adulación excesiva o melodrama."
)

GET_ENVIRONMENT_DESCRIPTION = (
    "Clima, temperatura, pronóstico, aire o polen. Solo si lo pide en tiempo real."
)
LIST_CALENDAR_DESCRIPTION = (
    "Lee citas/eventos de Google Calendar. Para agendar: calendar_prepare_write."
)
CALENDAR_PREPARE_DESCRIPTION = (
    "Borrador de cita/recordatorio (qué, día, hora). NO agenda — pide confirmación."
)
CALENDAR_CONFIRM_DESCRIPTION = (
    "Agenda el borrador tras «sí/dale». Un «sí» basta si hay borrador."
)
CALENDAR_CANCEL_DESCRIPTION = "Cancela el borrador de cita sin agendar."

READ_GMAIL_DESCRIPTION = (
    "Lee Gmail (bandeja/categoría/remitente, cuerpo completo). Enviar: gmail_prepare_send."
)
GMAIL_PREPARE_DESCRIPTION = "Borrador de correo (para/asunto/cuerpo). NO envía — pide confirmación."
GMAIL_CONFIRM_DESCRIPTION = "Envía el borrador tras «sí/envíalo». Un «sí» basta."
GMAIL_CANCEL_DESCRIPTION = "Cancela el borrador de correo sin enviar."

META_PREPARE_DESCRIPTION = (
    "Borrador FB/IG (plataforma + texto). NO publica. IG necesita imagen (HUD/cámara/generada). "
    "Si ya subió imagen, vuelve a llamar esta tool."
)
META_CONFIRM_DESCRIPTION = "Publica el borrador tras «sí/publícalo». Un «sí» basta."
META_CANCEL_DESCRIPTION = "Cancela el borrador de publicación."
CHECK_META_DESCRIPTION = "¿Facebook/Instagram conectados?"

ENABLE_PROSPECTION_DESCRIPTION = "Activa prospección de leads en comentarios de Instagram."
DISABLE_PROSPECTION_DESCRIPTION = "Desactiva prospección."
PROSPECTION_REPORT_DESCRIPTION = "Reporte de leads de hoy."
READ_SOCIAL_COMMENTS_DESCRIPTION = "Lee comentarios recientes FB/IG y destaca prospectos."

OPEN_DRIVE_MAP_DESCRIPTION = "Abre el mapa / modo conducir."
SEARCH_NEARBY_PLACES_DESCRIPTION = "Busca destino («llévame a …»)."
SHOW_ROUTE_DESCRIPTION = "Muestra la ruta sin iniciar guía («muéstrame la ruta»)."
START_DRIVE_NAVIGATION_DESCRIPTION = "Inicia navegación en vivo («inicia la ruta»)."
STOP_DRIVE_NAVIGATION_DESCRIPTION = "Detiene la navegación."
NAVIGATION_STATUS_DESCRIPTION = "Estado/ETA de la navegación."

SEARCH_WEB_DESCRIPTION = (
    "Noticias/hechos/datos actuales. NO clima (get_environment) ni objeto en cámara "
    "(search_visible_product)."
)

PLAY_YOUTUBE_DESCRIPTION = (
    "Reproduce video de YouTube («pon/reproduce X en YouTube»). Reproduce YA, "
    "nunca preguntes confirmación antes de reproducir. Di 'spoken' tal cual tras "
    "éxito real: SILENCIO — no ofrezcas más ayuda."
)
PAUSE_YOUTUBE_DESCRIPTION = "Pausa el video de YouTube."
RESUME_YOUTUBE_DESCRIPTION = (
    "Reanuda YouTube. Una frase y silencio mientras suena."
)
CLOSE_YOUTUBE_DESCRIPTION = "Cierra el reproductor de YouTube."

GENERATE_IMAGE_DESCRIPTION = (
    "Genera imagen por descripción hablada. Di el resultado tal cual — NUNCA confirmes sin éxito."
)
GENERAR_PDF_DESCRIPTION = (
    "Genera PDF (título/contenido). Di el resultado tal cual — NUNCA confirmes sin éxito."
)

READ_FINANCES_DESCRIPTION = "Lee finanzas (resumen/gastos/pendientes). No registra."
FINANCE_PREPARE_DESCRIPTION = (
    "Borrador gasto/ingreso/pendiente (monto+concepto). NO guarda — pide confirmación."
)
FINANCE_CONFIRM_DESCRIPTION = (
    "Guarda el borrador financiero tras «sí/dale». Un «sí» basta."
)
FINANCE_CANCEL_DESCRIPTION = "Descarta el borrador financiero sin guardar."

ACTIVATE_CAMERA_DESCRIPTION = (
    "Enciende la cámara una vez. Solo confirma activación — no describe lo visible."
)
DEACTIVATE_CAMERA_DESCRIPTION = "Apaga la cámara."
ANALYZE_CAMERA_FRAME_DESCRIPTION = (
    "Describe lo que hay frente a la cámara. PROHIBIDO inventar sin llamar esta tool."
)
SEARCH_VISIBLE_PRODUCT_DESCRIPTION = (
    "Identifica el objeto en cámara y busca precio/specs/dónde comprarlo."
)

ACTIVATE_ADVANCED_DESCRIPTION = (
    "Activa modo avanzado (Claude). SOLO con la frase «activa modo avanzado»."
)
CONSULT_ADVANCED_DESCRIPTION = (
    "Análisis/investigación profunda vía Claude (modo avanzado). "
    "NUNCA respondas esas preguntas sin esta tool. Di el resultado tal cual."
)
DEACTIVATE_ADVANCED_DESCRIPTION = (
    "Sale del modo avanzado («modo normal» / «desactiva modo avanzado»)."
)

GET_ENVIRONMENT_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Petición completa sobre clima o ambiente, con ubicación si la mencionó."
            ),
        },
    },
    "required": ["query"],
}

LIST_CALENDAR_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Petición del usuario sobre su calendario "
                "(ej. 'qué tengo hoy', 'eventos de mañana', 'esta semana')."
            ),
        },
    },
    "required": ["query"],
}

CALENDAR_PREPARE_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Frase del usuario para agendar "
                "(ej. 'agéndame reunión con Ana mañana a las 3 pm', 'recuérdame pagar el lunes a las 9')."
            ),
        },
    },
    "required": ["query"],
}

CALENDAR_CONFIRM_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "draft_id": {
            "type": "string",
            "description": "ID del borrador de calendar_prepare_write (opcional si hay uno activo).",
        },
    },
}

CALENDAR_CANCEL_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "draft_id": {
            "type": "string",
            "description": "ID del borrador a cancelar (opcional si hay uno activo).",
        },
    },
}

READ_GMAIL_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Petición de lectura de correo tal cual "
                "(ej. 'léeme mis correos', 'correos importantes', 'léeme el correo de Juan')."
            ),
        },
    },
    "required": ["query"],
}

GMAIL_PREPARE_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "to": {"type": "string", "description": "Correo destinatario."},
        "subject": {"type": "string", "description": "Asunto del correo."},
        "body": {"type": "string", "description": "Cuerpo del mensaje."},
        "query": {
            "type": "string",
            "description": (
                "Frase completa del usuario si no se separaron to/subject/body "
                "(ej. 'envía un correo a ana@x.com asunto Reunión diciendo confirmo')."
            ),
        },
    },
}

GMAIL_CONFIRM_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "draft_id": {
            "type": "string",
            "description": "ID del borrador de gmail_prepare_send (opcional).",
        },
    },
}

GMAIL_CANCEL_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "draft_id": {
            "type": "string",
            "description": "ID del borrador a cancelar (opcional).",
        },
    },
}

META_PREPARE_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "platform": {
            "type": "string",
            "description": "facebook o instagram",
        },
        "caption": {
            "type": "string",
            "description": "Texto a publicar.",
        },
        "query": {
            "type": "string",
            "description": "Frase completa del usuario si no se separaron platform/caption.",
        },
    },
}

META_CONFIRM_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "draft_id": {
            "type": "string",
            "description": "ID del borrador de meta_prepare_publish (opcional).",
        },
    },
}

META_CANCEL_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "draft_id": {"type": "string", "description": "ID del borrador (opcional)."},
    },
}

CHECK_META_PARAMETERS: dict[str, Any] = {"type": "object", "properties": {}}

ENABLE_PROSPECTION_PARAMETERS: dict[str, Any] = {"type": "object", "properties": {}}
DISABLE_PROSPECTION_PARAMETERS: dict[str, Any] = {"type": "object", "properties": {}}
PROSPECTION_REPORT_PARAMETERS: dict[str, Any] = {"type": "object", "properties": {}}
READ_SOCIAL_COMMENTS_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "platform": {
            "type": "string",
            "description": "both, instagram o facebook. Por defecto both.",
        },
    },
}

OPEN_DRIVE_MAP_PARAMETERS: dict[str, Any] = {"type": "object", "properties": {}}
SEARCH_NEARBY_PLACES_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Lugar o destino."},
    },
    "required": ["query"],
}
SHOW_ROUTE_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Destino opcional si aún no hay ruta."},
        "option_index": {"type": "integer", "description": "Índice 0-based de la opción en pantalla."},
    },
}
START_DRIVE_NAVIGATION_PARAMETERS: dict[str, Any] = {"type": "object", "properties": {}}
STOP_DRIVE_NAVIGATION_PARAMETERS: dict[str, Any] = {"type": "object", "properties": {}}
NAVIGATION_STATUS_PARAMETERS: dict[str, Any] = {"type": "object", "properties": {}}

SEARCH_WEB_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Consulta de búsqueda (ej. 'quién ganó el Super Bowl 2026', "
                "'noticias de OpenAI hoy', 'precio del dólar en RD')."
            ),
        },
        "kind": {
            "type": "string",
            "description": "Tipo opcional: general, news u other. Por defecto general.",
        },
    },
    "required": ["query"],
}

PLAY_YOUTUBE_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Qué video buscar en YouTube (canción, artista, tema). "
                "Ej: 'música de Juan Luis Guerra', 'cómo cambiar un neumático'."
            ),
        },
    },
    "required": ["query"],
}
PAUSE_YOUTUBE_PARAMETERS: dict[str, Any] = {"type": "object", "properties": {}}
RESUME_YOUTUBE_PARAMETERS: dict[str, Any] = {"type": "object", "properties": {}}
CLOSE_YOUTUBE_PARAMETERS: dict[str, Any] = {"type": "object", "properties": {}}

GENERATE_IMAGE_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "prompt": {
            "type": "string",
            "description": (
                "Descripción detallada de la imagen a generar "
                "(ej. 'un café al atardecer con luz cálida')."
            ),
        },
        "quality": {
            "type": "string",
            "description": "Calidad opcional: auto, standard o hd. Por defecto auto.",
        },
    },
    "required": ["prompt"],
}

GENERAR_PDF_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "titulo": {
            "type": "string",
            "description": "Título del documento PDF.",
        },
        "contenido": {
            "type": "string",
            "description": "Texto completo del PDF (redacta si el usuario no lo dictó entero).",
        },
    },
    "required": ["titulo", "contenido"],
}

READ_FINANCES_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Petición de consulta financiera "
                "(ej. 'cómo voy este mes', 'desglose de gastos', 'pagos pendientes')."
            ),
        },
    },
    "required": ["query"],
}

FINANCE_PREPARE_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Frase del usuario sobre el movimiento a registrar "
                "(ej. 'gasté 50 en materiales', 'el lunes tengo que pagar 850')."
            ),
        },
    },
    "required": ["query"],
}

FINANCE_CONFIRM_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "draft_id": {
            "type": "string",
            "description": "ID del borrador devuelto por finance_prepare_write (opcional si hay uno activo).",
        },
    },
}

FINANCE_CANCEL_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "draft_id": {
            "type": "string",
            "description": "ID del borrador a cancelar (opcional si hay uno activo).",
        },
    },
}

ACTIVATE_CAMERA_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {},
}

DEACTIVATE_CAMERA_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {},
}

ANALYZE_CAMERA_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {
            "type": "string",
            "description": (
                "Pregunta opcional sobre lo visible "
                "(ej. 'qué marca es', 'qué producto muestro')."
            ),
        },
    },
}

SEARCH_VISIBLE_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {
            "type": "string",
            "description": (
                "Pregunta del usuario sobre el producto visible "
                "(ej. 'dónde lo compro', 'especificaciones', 'precio')."
            ),
        },
    },
}

ACTIVATE_ADVANCED_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {},
}

CONSULT_ADVANCED_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Consulta profunda del usuario "
                "(ej. 'explica cómo funciona el interés compuesto', "
                "'compara opciones de financing para un auto')."
            ),
        },
    },
    "required": ["query"],
}

DEACTIVATE_ADVANCED_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {},
}

_lock = threading.Lock()
_tool_metrics: list[dict[str, Any]] = []
_call_metrics: dict[str, dict[str, Any]] = {}


def _build_custom_tool(
    *,
    api_public_url: str,
    name: str,
    description: str,
    parameters: dict[str, Any],
    filler: str,
    timeout_ms: int,
) -> dict[str, Any]:
    """Custom Function Retell.

    Retell solo dice el filler UNA vez al inicio de la tool (docs). Se probó
    `enable_typing_sound` para esperas largas (PDF/clima/imagen) pero el "taca,
    taca" de fondo interfería con la voz de CED al hablar/confirmar — se retiró
    por completo. La espera silenciosa tras el filler es preferible.
    """
    base = api_public_url.rstrip("/")
    return {
        "type": "custom",
        "name": name,
        "description": description,
        "url": f"{base}/v1/retell/tools/{name}",
        "method": "POST",
        "parameters": parameters,
        "speak_during_execution": True,
        "speak_after_execution": True,
        "execution_message_type": "static_text",
        "execution_message_description": filler,
        "timeout_ms": timeout_ms,
    }


def build_get_environment_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="get_environment",
        description=GET_ENVIRONMENT_DESCRIPTION,
        parameters=GET_ENVIRONMENT_PARAMETERS,
        filler=(
            "Un momento, consultando el clima, señor. "
            "Puede tardar unos segundos."
        ),
        timeout_ms=22_000,
    )


def build_list_calendar_events_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="list_calendar_events",
        description=LIST_CALENDAR_DESCRIPTION,
        parameters=LIST_CALENDAR_PARAMETERS,
        filler="Un momento, revisando su calendario, señor.",
        timeout_ms=18_000,
    )


def build_calendar_prepare_write_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="calendar_prepare_write",
        description=CALENDAR_PREPARE_DESCRIPTION,
        parameters=CALENDAR_PREPARE_PARAMETERS,
        filler="Un momento, preparando la cita, señor.",
        timeout_ms=12_000,
    )


def build_calendar_confirm_write_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="calendar_confirm_write",
        description=CALENDAR_CONFIRM_DESCRIPTION,
        parameters=CALENDAR_CONFIRM_PARAMETERS,
        filler="Agendando en su calendario, señor.",
        timeout_ms=20_000,
    )


def build_calendar_cancel_write_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="calendar_cancel_write",
        description=CALENDAR_CANCEL_DESCRIPTION,
        parameters=CALENDAR_CANCEL_PARAMETERS,
        filler="Un momento, señor.",
        timeout_ms=8_000,
    )


def build_read_gmail_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="read_gmail",
        description=READ_GMAIL_DESCRIPTION,
        parameters=READ_GMAIL_PARAMETERS,
        filler="Un momento, revisando su correo, señor.",
        timeout_ms=24_000,
    )


def build_gmail_prepare_send_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="gmail_prepare_send",
        description=GMAIL_PREPARE_DESCRIPTION,
        parameters=GMAIL_PREPARE_PARAMETERS,
        filler="Un momento, preparando el correo, señor.",
        timeout_ms=12_000,
    )


def build_gmail_confirm_send_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="gmail_confirm_send",
        description=GMAIL_CONFIRM_DESCRIPTION,
        parameters=GMAIL_CONFIRM_PARAMETERS,
        filler="Enviando el correo, señor.",
        timeout_ms=20_000,
    )


def build_gmail_cancel_send_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="gmail_cancel_send",
        description=GMAIL_CANCEL_DESCRIPTION,
        parameters=GMAIL_CANCEL_PARAMETERS,
        filler="Un momento, señor.",
        timeout_ms=8_000,
    )


def build_search_web_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="search_web",
        description=SEARCH_WEB_DESCRIPTION,
        parameters=SEARCH_WEB_PARAMETERS,
        filler="Investigando, señor.",
        timeout_ms=25_000,
    )


def build_play_youtube_video_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="play_youtube_video",
        description=PLAY_YOUTUBE_DESCRIPTION,
        parameters=PLAY_YOUTUBE_PARAMETERS,
        filler="Buscando en YouTube, señor.",
        timeout_ms=15_000,
    )


def build_pause_youtube_video_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="pause_youtube_video",
        description=PAUSE_YOUTUBE_DESCRIPTION,
        parameters=PAUSE_YOUTUBE_PARAMETERS,
        filler="Un momento, señor.",
        timeout_ms=8_000,
    )


def build_resume_youtube_video_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="resume_youtube_video",
        description=RESUME_YOUTUBE_DESCRIPTION,
        parameters=RESUME_YOUTUBE_PARAMETERS,
        filler="Un momento, señor.",
        timeout_ms=8_000,
    )


def build_close_youtube_player_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="close_youtube_player",
        description=CLOSE_YOUTUBE_DESCRIPTION,
        parameters=CLOSE_YOUTUBE_PARAMETERS,
        filler="Un momento, señor.",
        timeout_ms=8_000,
    )


def build_generate_image_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="generate_image",
        description=GENERATE_IMAGE_DESCRIPTION,
        parameters=GENERATE_IMAGE_PARAMETERS,
        filler="Un momento, generando su imagen, señor.",
        timeout_ms=60_000,
    )


def build_generar_pdf_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="generar_pdf",
        description=GENERAR_PDF_DESCRIPTION,
        parameters=GENERAR_PDF_PARAMETERS,
        filler=(
            "Un momento, preparando su PDF, señor. "
            "Puede tardar unos segundos mientras lo redacto."
        ),
        timeout_ms=45_000,
    )


def build_meta_prepare_publish_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="meta_prepare_publish",
        description=META_PREPARE_DESCRIPTION,
        parameters=META_PREPARE_PARAMETERS,
        filler="Preparando la publicación, señor.",
        timeout_ms=12_000,
    )


def build_meta_confirm_publish_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="meta_confirm_publish",
        description=META_CONFIRM_DESCRIPTION,
        parameters=META_CONFIRM_PARAMETERS,
        filler="Publicando, señor.",
        timeout_ms=35_000,
    )


def build_meta_cancel_publish_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="meta_cancel_publish",
        description=META_CANCEL_DESCRIPTION,
        parameters=META_CANCEL_PARAMETERS,
        filler="Un momento, señor.",
        timeout_ms=8_000,
    )


def build_check_meta_networks_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="check_meta_networks",
        description=CHECK_META_DESCRIPTION,
        parameters=CHECK_META_PARAMETERS,
        filler="Revisando sus redes, señor.",
        timeout_ms=10_000,
    )


def build_enable_prospection_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="enable_prospection",
        description=ENABLE_PROSPECTION_DESCRIPTION,
        parameters=ENABLE_PROSPECTION_PARAMETERS,
        filler="Activando prospección, señor.",
        timeout_ms=12_000,
    )


def build_disable_prospection_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="disable_prospection",
        description=DISABLE_PROSPECTION_DESCRIPTION,
        parameters=DISABLE_PROSPECTION_PARAMETERS,
        filler="Un momento, señor.",
        timeout_ms=8_000,
    )


def build_prospection_report_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="prospection_report",
        description=PROSPECTION_REPORT_DESCRIPTION,
        parameters=PROSPECTION_REPORT_PARAMETERS,
        filler="Revisando leads, señor.",
        timeout_ms=12_000,
    )


def build_read_social_comments_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="read_social_comments",
        description=READ_SOCIAL_COMMENTS_DESCRIPTION,
        parameters=READ_SOCIAL_COMMENTS_PARAMETERS,
        filler="Leyendo comentarios, señor.",
        timeout_ms=25_000,
    )


def build_open_drive_map_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="open_drive_map",
        description=OPEN_DRIVE_MAP_DESCRIPTION,
        parameters=OPEN_DRIVE_MAP_PARAMETERS,
        filler="Abriendo el mapa, señor.",
        timeout_ms=8_000,
    )


def build_search_nearby_places_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="search_nearby_places",
        description=SEARCH_NEARBY_PLACES_DESCRIPTION,
        parameters=SEARCH_NEARBY_PLACES_PARAMETERS,
        filler="Buscando el destino, señor.",
        timeout_ms=20_000,
    )


def build_show_route_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="show_route",
        description=SHOW_ROUTE_DESCRIPTION,
        parameters=SHOW_ROUTE_PARAMETERS,
        filler="Calculando la ruta, señor.",
        timeout_ms=25_000,
    )


def build_start_drive_navigation_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="start_drive_navigation",
        description=START_DRIVE_NAVIGATION_DESCRIPTION,
        parameters=START_DRIVE_NAVIGATION_PARAMETERS,
        filler="Iniciando navegación, señor.",
        timeout_ms=15_000,
    )


def build_stop_drive_navigation_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="stop_drive_navigation",
        description=STOP_DRIVE_NAVIGATION_DESCRIPTION,
        parameters=STOP_DRIVE_NAVIGATION_PARAMETERS,
        filler="Un momento, señor.",
        timeout_ms=8_000,
    )


def build_navigation_status_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="navigation_status",
        description=NAVIGATION_STATUS_DESCRIPTION,
        parameters=NAVIGATION_STATUS_PARAMETERS,
        filler="Revisando la ruta, señor.",
        timeout_ms=8_000,
    )


def build_read_finances_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="read_finances",
        description=READ_FINANCES_DESCRIPTION,
        parameters=READ_FINANCES_PARAMETERS,
        filler="Un momento, revisando sus finanzas, señor.",
        timeout_ms=18_000,
    )


def build_finance_prepare_write_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="finance_prepare_write",
        description=FINANCE_PREPARE_DESCRIPTION,
        parameters=FINANCE_PREPARE_PARAMETERS,
        filler="Un momento, preparando el registro, señor.",
        timeout_ms=12_000,
    )


def build_finance_confirm_write_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="finance_confirm_write",
        description=FINANCE_CONFIRM_DESCRIPTION,
        parameters=FINANCE_CONFIRM_PARAMETERS,
        filler="Registrando su movimiento, señor.",
        timeout_ms=20_000,
    )


def build_finance_cancel_write_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="finance_cancel_write",
        description=FINANCE_CANCEL_DESCRIPTION,
        parameters=FINANCE_CANCEL_PARAMETERS,
        filler="Un momento, señor.",
        timeout_ms=8_000,
    )


def build_activate_camera_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="activate_camera",
        description=ACTIVATE_CAMERA_DESCRIPTION,
        parameters=ACTIVATE_CAMERA_PARAMETERS,
        filler="Activando la cámara, señor.",
        timeout_ms=12_000,
    )


def build_deactivate_camera_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="deactivate_camera",
        description=DEACTIVATE_CAMERA_DESCRIPTION,
        parameters=DEACTIVATE_CAMERA_PARAMETERS,
        filler="Un momento, señor.",
        timeout_ms=8_000,
    )


def build_analyze_camera_frame_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="analyze_camera_frame",
        description=ANALYZE_CAMERA_FRAME_DESCRIPTION,
        parameters=ANALYZE_CAMERA_PARAMETERS,
        filler="Un momento, analizando lo que me muestra, señor.",
        timeout_ms=45_000,
    )


def build_search_visible_product_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="search_visible_product",
        description=SEARCH_VISIBLE_PRODUCT_DESCRIPTION,
        parameters=SEARCH_VISIBLE_PARAMETERS,
        filler="Un momento, buscando información sobre lo que veo, señor.",
        timeout_ms=45_000,
    )


def build_activate_advanced_mode_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="activate_advanced_mode",
        description=ACTIVATE_ADVANCED_DESCRIPTION,
        parameters=ACTIVATE_ADVANCED_PARAMETERS,
        filler="Activando modo avanzado, señor.",
        timeout_ms=8_000,
    )


def build_consult_advanced_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="consult_advanced",
        description=CONSULT_ADVANCED_DESCRIPTION,
        parameters=CONSULT_ADVANCED_PARAMETERS,
        filler="Un momento, consultando el sistema avanzado, señor.",
        timeout_ms=45_000,
    )


def build_deactivate_advanced_mode_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="deactivate_advanced_mode",
        description=DEACTIVATE_ADVANCED_DESCRIPTION,
        parameters=DEACTIVATE_ADVANCED_PARAMETERS,
        filler="Un momento, señor.",
        timeout_ms=8_000,
    )


def build_native_pilot_states(*, api_public_url: str) -> tuple[list[dict[str, Any]], str]:
    """Retell States — tools restringidas por estado (general_tools vacío)."""
    return [
        {
            "name": STATE_GENERAL_ASSISTANT,
            "state_prompt": GENERAL_ASSISTANT_STATE_PROMPT,
            "tools": [
                build_get_environment_tool(api_public_url=api_public_url),
                build_list_calendar_events_tool(api_public_url=api_public_url),
                build_calendar_prepare_write_tool(api_public_url=api_public_url),
                build_calendar_confirm_write_tool(api_public_url=api_public_url),
                build_calendar_cancel_write_tool(api_public_url=api_public_url),
                build_read_gmail_tool(api_public_url=api_public_url),
                build_gmail_prepare_send_tool(api_public_url=api_public_url),
                build_gmail_confirm_send_tool(api_public_url=api_public_url),
                build_gmail_cancel_send_tool(api_public_url=api_public_url),
                build_search_web_tool(api_public_url=api_public_url),
                build_play_youtube_video_tool(api_public_url=api_public_url),
                build_pause_youtube_video_tool(api_public_url=api_public_url),
                build_resume_youtube_video_tool(api_public_url=api_public_url),
                build_close_youtube_player_tool(api_public_url=api_public_url),
                build_generate_image_tool(api_public_url=api_public_url),
                build_generar_pdf_tool(api_public_url=api_public_url),
                build_check_meta_networks_tool(api_public_url=api_public_url),
                build_meta_prepare_publish_tool(api_public_url=api_public_url),
                build_meta_confirm_publish_tool(api_public_url=api_public_url),
                build_meta_cancel_publish_tool(api_public_url=api_public_url),
                build_enable_prospection_tool(api_public_url=api_public_url),
                build_disable_prospection_tool(api_public_url=api_public_url),
                build_prospection_report_tool(api_public_url=api_public_url),
                build_read_social_comments_tool(api_public_url=api_public_url),
                build_open_drive_map_tool(api_public_url=api_public_url),
                build_search_nearby_places_tool(api_public_url=api_public_url),
                build_show_route_tool(api_public_url=api_public_url),
                build_start_drive_navigation_tool(api_public_url=api_public_url),
                build_stop_drive_navigation_tool(api_public_url=api_public_url),
                build_navigation_status_tool(api_public_url=api_public_url),
                build_read_finances_tool(api_public_url=api_public_url),
                build_finance_prepare_write_tool(api_public_url=api_public_url),
                build_finance_confirm_write_tool(api_public_url=api_public_url),
                build_finance_cancel_write_tool(api_public_url=api_public_url),
                build_activate_camera_tool(api_public_url=api_public_url),
                build_deactivate_camera_tool(api_public_url=api_public_url),
                build_analyze_camera_frame_tool(api_public_url=api_public_url),
                build_search_visible_product_tool(api_public_url=api_public_url),
                build_activate_advanced_mode_tool(api_public_url=api_public_url),
                # Mismo patrón que finance_confirm_write: disponibles en general
                # por si Retell no transiciona a advanced_mode_active.
                build_consult_advanced_tool(api_public_url=api_public_url),
                build_deactivate_advanced_mode_tool(api_public_url=api_public_url),
            ],
            "edges": [
                {
                    "destination_state_name": STATE_FINANCE_CONFIRM_PENDING,
                    "description": (
                        "Transición cuando finance_prepare_write devuelve awaiting_confirmation: "
                        "hay borrador listo y debe pedirse confirmación de registro al usuario."
                    ),
                },
                {
                    "destination_state_name": STATE_GMAIL_CONFIRM_PENDING,
                    "description": (
                        "Transición cuando gmail_prepare_send devuelve awaiting_confirmation."
                    ),
                },
                {
                    "destination_state_name": STATE_PUBLISH_CONFIRM_PENDING,
                    "description": (
                        "Transición cuando meta_prepare_publish devuelve awaiting_confirmation."
                    ),
                },
                {
                    "destination_state_name": STATE_CALENDAR_CONFIRM_PENDING,
                    "description": (
                        "Transición cuando calendar_prepare_write devuelve awaiting_confirmation: "
                        "hay borrador de cita listo y debe pedirse confirmación al usuario."
                    ),
                },
                {
                    "destination_state_name": STATE_ADVANCED_MODE_ACTIVE,
                    "description": (
                        "Transición cuando activate_advanced_mode confirma modo avanzado activo "
                        "(usuario dijo «activa modo avanzado»)."
                    ),
                },
            ],
        },
        {
            "name": STATE_FINANCE_CONFIRM_PENDING,
            "state_prompt": FINANCE_CONFIRM_STATE_PROMPT,
            "tools": [
                build_read_finances_tool(api_public_url=api_public_url),
                build_finance_confirm_write_tool(api_public_url=api_public_url),
                build_finance_cancel_write_tool(api_public_url=api_public_url),
                build_get_environment_tool(api_public_url=api_public_url),
            ],
            "edges": [
                {
                    "destination_state_name": STATE_GENERAL_ASSISTANT,
                    "description": (
                        "OBLIGATORIO tras finance_confirm_write / finance_cancel_write exitoso. "
                        "También si el usuario pide clima, Gmail, redes u otro tema no financiero."
                    ),
                },
            ],
        },
        {
            "name": STATE_GMAIL_CONFIRM_PENDING,
            "state_prompt": GMAIL_CONFIRM_STATE_PROMPT,
            "tools": [
                build_read_gmail_tool(api_public_url=api_public_url),
                build_gmail_confirm_send_tool(api_public_url=api_public_url),
                build_gmail_cancel_send_tool(api_public_url=api_public_url),
                build_get_environment_tool(api_public_url=api_public_url),
                build_read_finances_tool(api_public_url=api_public_url),
            ],
            "edges": [
                {
                    "destination_state_name": STATE_GENERAL_ASSISTANT,
                    "description": (
                        "OBLIGATORIO tras gmail_confirm_send / gmail_cancel_send exitoso. "
                        "También si pide finanzas, clima, redes u otro tema."
                    ),
                },
            ],
        },
        {
            "name": STATE_PUBLISH_CONFIRM_PENDING,
            "state_prompt": PUBLISH_CONFIRM_STATE_PROMPT,
            "tools": [
                build_check_meta_networks_tool(api_public_url=api_public_url),
                build_meta_confirm_publish_tool(api_public_url=api_public_url),
                build_meta_cancel_publish_tool(api_public_url=api_public_url),
                # Escape hatch: si Retell no transiciona tras publicar, el usuario
                # no debe quedar en silencio al pedir finanzas/clima/Gmail.
                build_get_environment_tool(api_public_url=api_public_url),
                build_read_finances_tool(api_public_url=api_public_url),
                build_read_gmail_tool(api_public_url=api_public_url),
                build_list_calendar_events_tool(api_public_url=api_public_url),
                build_search_web_tool(api_public_url=api_public_url),
            ],
            "edges": [
                {
                    "destination_state_name": STATE_GENERAL_ASSISTANT,
                    "description": (
                        "OBLIGATORIO en el mismo turno tras meta_confirm_publish exitoso "
                        "(status published) o meta_cancel_publish. "
                        "También si el usuario pide finanzas, clima, Gmail, calendario "
                        "o cualquier tema que no sea confirmar/cancelar la publicación."
                    ),
                },
            ],
        },
        {
            "name": STATE_CALENDAR_CONFIRM_PENDING,
            "state_prompt": CALENDAR_CONFIRM_STATE_PROMPT,
            "tools": [
                build_list_calendar_events_tool(api_public_url=api_public_url),
                build_calendar_confirm_write_tool(api_public_url=api_public_url),
                build_calendar_cancel_write_tool(api_public_url=api_public_url),
                build_get_environment_tool(api_public_url=api_public_url),
                build_read_finances_tool(api_public_url=api_public_url),
            ],
            "edges": [
                {
                    "destination_state_name": STATE_GENERAL_ASSISTANT,
                    "description": (
                        "OBLIGATORIO tras calendar_confirm_write / calendar_cancel_write exitoso. "
                        "También si pide finanzas, clima, Gmail u otro tema."
                    ),
                },
            ],
        },
        {
            "name": STATE_ADVANCED_MODE_ACTIVE,
            "state_prompt": ADVANCED_MODE_STATE_PROMPT,
            "tools": [
                build_consult_advanced_tool(api_public_url=api_public_url),
                build_deactivate_advanced_mode_tool(api_public_url=api_public_url),
                build_get_environment_tool(api_public_url=api_public_url),
                build_read_finances_tool(api_public_url=api_public_url),
                build_generate_image_tool(api_public_url=api_public_url),
                build_generar_pdf_tool(api_public_url=api_public_url),
            ],
            "edges": [
                {
                    "destination_state_name": STATE_GENERAL_ASSISTANT,
                    "description": (
                        "Volver al modo conversacional normal tras deactivate_advanced_mode "
                        "(salida explícita del usuario)."
                    ),
                },
            ],
        },
    ], STATE_GENERAL_ASSISTANT


def build_native_pilot_llm_config(*, api_public_url: str) -> dict[str, Any]:
    """Config LLM completa: states + starting_state, sin general_tools globales."""
    states, starting = build_native_pilot_states(api_public_url=api_public_url)
    return {
        "general_tools": [],
        "states": states,
        "starting_state": starting,
    }


def _estimate_tokens(text: str) -> int:
    """Aprox. tokens LLM (chars/4). Suficiente para umbral Retell ~4k."""
    return max(0, (len(text) + 3) // 4)


def estimate_general_assistant_token_floor(*, api_public_url: str = "https://api.example.com") -> dict[str, Any]:
    """
    Piso de tokens del estado general_assistant (sin historial de conversación).

    Aproxima lo que Retell cuenta hacia el umbral de surcharge (~4 000 tok):
    general_prompt + state_prompt + schemas de tools + edges (transitions).
    """
    import json

    states, _ = build_native_pilot_states(api_public_url=api_public_url)
    general = next(s for s in states if s["name"] == STATE_GENERAL_ASSISTANT)
    tools = general.get("tools") or []
    edges = general.get("edges") or []

    # Schemas model-facing: name + description + parameters (sin url/fillers)
    slim_tools = [
        {
            "name": t.get("name"),
            "description": t.get("description"),
            "parameters": t.get("parameters"),
        }
        for t in tools
    ]
    tools_json = json.dumps(slim_tools, ensure_ascii=False, separators=(",", ":"))
    edges_text = json.dumps(edges, ensure_ascii=False, separators=(",", ":"))

    general_prompt_tok = _estimate_tokens(RETELL_NATIVE_PILOT_PROMPT)
    state_prompt_tok = _estimate_tokens(str(general.get("state_prompt") or ""))
    tools_tok = _estimate_tokens(tools_json)
    # Retell sintetiza transition_to_* — ~55 tok por edge (nombre+desc)
    transitions_tok = max(0, len(edges) * 55)
    edges_tok = _estimate_tokens(edges_text)

    floor = general_prompt_tok + state_prompt_tok + tools_tok + transitions_tok
    return {
        "state": STATE_GENERAL_ASSISTANT,
        "tool_count": len(tools),
        "edge_count": len(edges),
        "general_prompt_tokens": general_prompt_tok,
        "state_prompt_tokens": state_prompt_tok,
        "tool_schemas_tokens": tools_tok,
        "edges_json_tokens": edges_tok,
        "transition_tools_tokens_est": transitions_tok,
        "floor_tokens_no_history": floor,
        "retell_surcharge_threshold": 4000,
        "under_threshold": floor < 4000,
        "target_tokens": 3800,
        "under_target": floor <= 3800,
        "estimated_llm_scale_factor": round(max(1.0, floor / 4000), 3),
        "notes": (
            "Sin historial de turno. Historial real suma tokens y puede reactivar surcharge. "
            "Estimación chars/4; Retell puede diferir ±10–15%."
        ),
    }


def build_native_pilot_tools(*, api_public_url: str) -> list[dict[str, Any]]:
    """Lista plana de tools (tests / compat) — incluye todas las del piloto."""
    states, _ = build_native_pilot_states(api_public_url=api_public_url)
    tools: list[dict[str, Any]] = []
    for state in states:
        tools.extend(state.get("tools") or [])
    return tools


def _extract_call_id(payload: dict[str, Any]) -> str:
    call = payload.get("call") or {}
    return str(call.get("call_id") or call.get("callId") or "").strip()


def _latest_user_utterance(payload: dict[str, Any]) -> str:
    call = payload.get("call") or {}
    transcript_obj = call.get("transcript_object") or call.get("transcriptObject") or []
    if isinstance(transcript_obj, list):
        for entry in reversed(transcript_obj):
            if not isinstance(entry, dict):
                continue
            role = str(entry.get("role") or "").lower()
            if role in {"user", "customer"}:
                content = str(entry.get("content") or entry.get("text") or "").strip()
                if content:
                    return content
    transcript = str(call.get("transcript") or "").strip()
    if transcript:
        lines = [ln.strip() for ln in transcript.splitlines() if ln.strip()]
        for line in reversed(lines):
            lower = line.lower()
            if lower.startswith("user:") or lower.startswith("agent:"):
                prefix = "user:" if lower.startswith("user:") else "agent:"
                text = line.split(":", 1)[-1].strip()
                if prefix == "user:" and text:
                    return text
            elif not lower.startswith("agent:"):
                return line
    return ""


def resolve_tool_query(payload: dict[str, Any], args: dict[str, Any]) -> str:
    query = str(
        args.get("query")
        or args.get("consulta")
        or args.get("transcript")
        or ""
    ).strip()
    if query:
        return query
    from_transcript = _latest_user_utterance(payload)
    if from_transcript:
        return from_transcript
    return ""


def record_tool_metric(
    *,
    call_id: str,
    tool_name: str,
    latency_ms: int,
    ok: bool,
    query: str = "",
) -> None:
    entry = {
        "call_id": call_id or "unknown",
        "tool": tool_name,
        "latency_ms": latency_ms,
        "ok": ok,
        "query_preview": (query or "")[:120],
        "ts": time.time(),
    }
    with _lock:
        _tool_metrics.append(entry)
        if len(_tool_metrics) > 400:
            del _tool_metrics[: len(_tool_metrics) - 400]
        if call_id:
            bucket = _call_metrics.setdefault(
                call_id,
                {"call_id": call_id, "tools": [], "started_at": time.time()},
            )
            bucket["tools"].append(entry)


def get_pilot_metrics_snapshot() -> dict[str, Any]:
    with _lock:
        tools = list(_tool_metrics)
        calls = {cid: dict(data) for cid, data in _call_metrics.items()}

    def _stats(name: str) -> dict[str, Any]:
        rows = [t for t in tools if t.get("tool") == name]
        latencies = [int(t["latency_ms"]) for t in rows if t.get("latency_ms") is not None]
        avg = round(sum(latencies) / len(latencies)) if latencies else None
        return {
            "invocations": len(rows),
            "avg_latency_ms": avg,
            "latencies_ms": latencies[-20:],
        }

    return {
        "tool_invocations": len(tools),
        "calls_tracked": len(calls),
        "get_environment": _stats("get_environment"),
        "list_calendar_events": _stats("list_calendar_events"),
        "calendar_prepare_write": _stats("calendar_prepare_write"),
        "calendar_confirm_write": _stats("calendar_confirm_write"),
        "calendar_cancel_write": _stats("calendar_cancel_write"),
        "read_gmail": _stats("read_gmail"),
        "gmail_prepare_send": _stats("gmail_prepare_send"),
        "gmail_confirm_send": _stats("gmail_confirm_send"),
        "gmail_cancel_send": _stats("gmail_cancel_send"),
        "search_web": _stats("search_web"),
        "play_youtube_video": _stats("play_youtube_video"),
        "pause_youtube_video": _stats("pause_youtube_video"),
        "resume_youtube_video": _stats("resume_youtube_video"),
        "close_youtube_player": _stats("close_youtube_player"),
        "meta_prepare_publish": _stats("meta_prepare_publish"),
        "meta_confirm_publish": _stats("meta_confirm_publish"),
        "meta_cancel_publish": _stats("meta_cancel_publish"),
        "check_meta_networks": _stats("check_meta_networks"),
        "enable_prospection": _stats("enable_prospection"),
        "disable_prospection": _stats("disable_prospection"),
        "prospection_report": _stats("prospection_report"),
        "read_social_comments": _stats("read_social_comments"),
        "open_drive_map": _stats("open_drive_map"),
        "search_nearby_places": _stats("search_nearby_places"),
        "show_route": _stats("show_route"),
        "start_drive_navigation": _stats("start_drive_navigation"),
        "stop_drive_navigation": _stats("stop_drive_navigation"),
        "navigation_status": _stats("navigation_status"),
        "read_finances": _stats("read_finances"),
        "finance_prepare_write": _stats("finance_prepare_write"),
        "finance_confirm_write": _stats("finance_confirm_write"),
        "finance_cancel_write": _stats("finance_cancel_write"),
        "activate_camera": _stats("activate_camera"),
        "deactivate_camera": _stats("deactivate_camera"),
        "analyze_camera_frame": _stats("analyze_camera_frame"),
        "search_visible_product": _stats("search_visible_product"),
        "activate_advanced_mode": _stats("activate_advanced_mode"),
        "consult_advanced": _stats("consult_advanced"),
        "deactivate_advanced_mode": _stats("deactivate_advanced_mode"),
        "environment_invocations": _stats("get_environment")["invocations"],
        "environment_avg_latency_ms": _stats("get_environment")["avg_latency_ms"],
        "environment_latencies_ms": _stats("get_environment")["latencies_ms"],
        "recent_tools": tools[-30:],
    }


def get_call_pilot_metrics(call_id: str) -> dict[str, Any] | None:
    with _lock:
        data = _call_metrics.get(call_id.strip())
        return dict(data) if data else None


_FAILURE_SPOKEN_MARKERS = (
    "no pude",
    "no identifiqu",
    "aún no tiene",
    "reconect",
    "no está disponible",
    "permisos",
)


def _spoken_indicates_failure(spoken: str) -> bool:
    low = (spoken or "").lower()
    return any(marker in low for marker in _FAILURE_SPOKEN_MARKERS)


async def _execute_native_read_tool(
    *,
    tool_name: str,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
    handler: Callable[[str, str], dict[str, str]],
    empty_query_message: str,
    failure_prefix: str = "No pude completar",
) -> dict[str, Any]:
    import asyncio

    started = time.perf_counter()
    call_id = _extract_call_id(payload)
    query = resolve_tool_query(payload, args)

    if not user_id:
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_tool_metric(
            call_id=call_id,
            tool_name=tool_name,
            latency_ms=latency_ms,
            ok=False,
            query=query,
        )
        return {
            "result": "No identifiqué al usuario, señor.",
            "latency_ms": latency_ms,
            "ok": False,
        }

    from app.services.finance_write_flow import maybe_clear_finance_pending_on_topic_change

    maybe_clear_finance_pending_on_topic_change(user_id, tool_name)

    if not query:
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_tool_metric(
            call_id=call_id,
            tool_name=tool_name,
            latency_ms=latency_ms,
            ok=False,
        )
        return {
            "result": empty_query_message,
            "latency_ms": latency_ms,
            "ok": False,
        }

    try:
        result = await asyncio.to_thread(handler, user_id, query)
        spoken = str(result.get("spoken") or "Completado, señor.").strip()
        ok = not _spoken_indicates_failure(spoken)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "[NATIVE-PILOT] %s HTTP %s user=%s",
            tool_name,
            exc.response.status_code,
            user_id[:8],
        )
        spoken = f"{failure_prefix} en este momento, señor. Revise la conexión de Google."
        ok = False
    except ValueError as exc:
        if str(exc) == "not_connected":
            spoken = (
                "Señor, aún no tiene esa integración conectada. "
                "Use el botón correspondiente en configuración de voz."
            )
        else:
            spoken = f"{failure_prefix} en este momento, señor."
        ok = False
    except Exception:  # noqa: BLE001
        logger.exception("[NATIVE-PILOT] %s failed user=%s", tool_name, user_id[:8])
        spoken = f"{failure_prefix} en este momento, señor. Intente de nuevo en unos minutos."
        ok = False

    latency_ms = int((time.perf_counter() - started) * 1000)
    record_tool_metric(
        call_id=call_id,
        tool_name=tool_name,
        latency_ms=latency_ms,
        ok=ok,
        query=query,
    )
    logger.info(
        "[NATIVE-PILOT] %s call=%s user=%s latency=%sms ok=%s",
        tool_name,
        call_id[:12] if call_id else "?",
        user_id[:8],
        latency_ms,
        ok,
    )
    return {"result": spoken, "latency_ms": latency_ms, "ok": ok}


async def execute_get_environment_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    from app.modules.environment_module import handle_environment_query_sync

    return await _execute_native_read_tool(
        tool_name="get_environment",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=handle_environment_query_sync,
        empty_query_message="Señor, ¿de qué ciudad o zona desea el clima o la calidad del aire?",
        failure_prefix="No pude obtener datos ambientales",
    )


async def execute_list_calendar_events_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    from app.modules.calendar_module import handle_calendar_read_sync

    return await _execute_native_read_tool(
        tool_name="list_calendar_events",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=handle_calendar_read_sync,
        empty_query_message="Señor, ¿qué día o periodo de su calendario desea consultar?",
        failure_prefix="No pude consultar su calendario",
    )


async def execute_read_gmail_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    from app.modules.gmail_module import handle_gmail_read_sync

    return await _execute_native_read_tool(
        tool_name="read_gmail",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=handle_gmail_read_sync,
        empty_query_message="Señor, ¿qué correos desea que revise?",
        failure_prefix="No pude consultar su correo",
    )


async def execute_read_finances_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    from app.modules.finance_module import handle_finance_read_sync
    from app.services.finance_write_flow import maybe_clear_finance_pending_on_topic_change

    maybe_clear_finance_pending_on_topic_change(user_id, "read_finances")

    return await _execute_native_read_tool(
        tool_name="read_finances",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=handle_finance_read_sync,
        empty_query_message="Señor, ¿qué desea consultar de sus finanzas?",
        failure_prefix="No pude consultar sus finanzas",
    )


def _format_finance_action_result(action: dict[str, Any]) -> str:
    """Resultado hablado + metadata JSON para el LLM (transiciones Retell)."""
    return _format_action_result_with_meta(action)


def _format_action_result_with_meta(action: dict[str, Any]) -> str:
    import json

    spoken = str(action.get("spoken") or "Completado, señor.").strip()
    transition = action.get("transition")
    # Refuerzo anti-silencio: tras éxito en estados confirm, Retell debe salir al general.
    if transition == "transition_to_general_assistant":
        spoken = (
            f"{spoken} "
            f"[REQUERIDO: llama ahora transition_to_general_assistant]"
        )
    meta = {
        "status": action.get("status"),
        "draft_id": action.get("draft_id"),
        "transition": transition,
        "ok": action.get("ok"),
    }
    meta = {k: v for k, v in meta.items() if v is not None}
    if meta:
        return f"{spoken}\n\n[meta:{json.dumps(meta, ensure_ascii=False)}]"
    return spoken


async def _execute_native_finance_action_tool(
    *,
    tool_name: str,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
    handler: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    import asyncio

    started = time.perf_counter()
    call_id = _extract_call_id(payload)

    if not user_id:
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_tool_metric(
            call_id=call_id,
            tool_name=tool_name,
            latency_ms=latency_ms,
            ok=False,
        )
        return {
            "result": "No identifiqué al usuario, señor.",
            "latency_ms": latency_ms,
            "ok": False,
        }

    try:
        action = await asyncio.to_thread(
            handler,
            user_id,
            call_id=call_id,
            payload=payload,
            args=args,
        )
        spoken = _format_finance_action_result(action)
        ok = bool(action.get("ok"))
    except Exception:  # noqa: BLE001
        logger.exception("[NATIVE-PILOT] %s failed user=%s", tool_name, user_id[:8])
        spoken = "Señor, no pude completar la operación de finanzas en este momento."
        ok = False

    latency_ms = int((time.perf_counter() - started) * 1000)
    record_tool_metric(
        call_id=call_id,
        tool_name=tool_name,
        latency_ms=latency_ms,
        ok=ok,
        query=str(args.get("draft_id") or args.get("query") or "")[:120],
    )
    return {"result": spoken, "latency_ms": latency_ms, "ok": ok}


def _run_finance_prepare(user_id: str, *, call_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from app.services.finance_write_flow import prepare_finance_write

    query = resolve_tool_query(payload, args)
    return prepare_finance_write(user_id, call_id=call_id, query=query)


def _run_finance_confirm(user_id: str, *, call_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from app.services.finance_write_flow import confirm_finance_write

    return confirm_finance_write(
        user_id,
        call_id=call_id,
        payload=payload,
        draft_id=str(args.get("draft_id") or ""),
    )


def _run_finance_cancel(user_id: str, *, call_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from app.services.finance_write_flow import cancel_finance_write

    return cancel_finance_write(
        user_id,
        draft_id=str(args.get("draft_id") or ""),
        reason="user_cancel",
    )


async def execute_finance_prepare_write_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_finance_action_tool(
        tool_name="finance_prepare_write",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=_run_finance_prepare,
    )


async def execute_finance_confirm_write_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_finance_action_tool(
        tool_name="finance_confirm_write",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=_run_finance_confirm,
    )


async def execute_finance_cancel_write_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_finance_action_tool(
        tool_name="finance_cancel_write",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=_run_finance_cancel,
    )


_PRODUCT_FOLLOWUP_RE = (
    r"\b("
    r"marca|brand|precio|cuesta|cuesta|comprar|consig|d[oó]nde\s+(?:lo\s+)?(?:compro|vendo|encuentro)|"
    r"especificaci|specs?|caracter[ií]stic|modelo|cu[aá]nto\s+(?:cuesta|vale)|"
    r"informaci[oó]n(?:\s+adicional)?|datos\s+(?:del\s+)?producto"
    r")\b"
)


def _camera_question_from_args(payload: dict[str, Any], args: dict[str, Any]) -> str:
    for key in ("question", "pregunta", "query"):
        value = str(args.get(key) or "").strip()
        if value:
            return value
    return resolve_tool_query(payload, args)


async def _execute_native_camera_tool(
    *,
    tool_name: str,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    """Wrappers sobre voice_tool_executor — misma lógica que Custom LLM / Live."""
    import re

    from app.services import voice_client_session as vcs
    from app.services.voice_tool_executor import execute_voice_tool

    started = time.perf_counter()
    call_id = _extract_call_id(payload)
    question = _camera_question_from_args(payload, args)

    if not user_id:
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_tool_metric(
            call_id=call_id,
            tool_name=tool_name,
            latency_ms=latency_ms,
            ok=False,
            query=question,
        )
        return {
            "result": "No identifiqué al usuario, señor.",
            "latency_ms": latency_ms,
            "ok": False,
        }

    try:
        if tool_name == "activate_camera":
            # Idempotente: is_camera_active → respuesta corta sin re-push.
            result = await execute_voice_tool(
                "request_camera_activation",
                user_id,
                {},
            )
        elif tool_name == "deactivate_camera":
            result = await execute_voice_tool(
                "request_camera_deactivation",
                user_id,
                {},
            )
        elif tool_name == "analyze_camera_frame":
            result = await execute_voice_tool(
                "analyze_camera_frame",
                user_id,
                {"pregunta": question or "¿Qué ves en la imagen?"},
            )
        elif tool_name == "search_visible_product":
            last_vision = vcs.get_last_vision_summary(user_id)
            # Solo reutilizar cache si el subject es suficientemente específico.
            subject_ok = bool(
                last_vision
                and len(last_vision) >= 28
                and not re.search(
                    r"\b(no pude|no pudo|fall[oó]|procesar la imagen)\b",
                    last_vision,
                    re.I,
                )
            )
            followup = bool(
                subject_ok
                and question
                and re.search(_PRODUCT_FOLLOWUP_RE, question, re.I)
            )
            if followup:
                # Reutiliza el último objeto identificado + búsqueda web (sin recapturar).
                obj = re.sub(
                    r"(?i)^(es|se ve|parece)\s+(un|una)\s+",
                    "",
                    last_vision,
                ).strip()
                obj = re.sub(r"\s+", " ", obj)[:120]
                search_q = f"{obj} {question}".strip()[:200]
                result = await execute_voice_tool(
                    "search_web",
                    user_id,
                    {"query": search_q, "kind": "general"},
                )
                spoken_web = str(result.get("spoken") or "").strip()
                if spoken_web and result.get("ok", True):
                    result = {
                        "ok": True,
                        "spoken": (
                            f"Sobre lo que identificamos ({obj}): {spoken_web}"
                        ),
                    }
                else:
                    result = await execute_voice_tool(
                        "buscar_lo_visible",
                        user_id,
                        {
                            "pregunta": question
                            or "Identifica lo visible y busca información",
                        },
                    )
            else:
                result = await execute_voice_tool(
                    "buscar_lo_visible",
                    user_id,
                    {
                        "pregunta": question
                        or "Identifica lo visible y busca información",
                    },
                )
        else:
            result = {"ok": False, "spoken": "Herramienta de cámara no reconocida, señor."}

        spoken = str(result.get("spoken") or "Completado, señor.").strip()
        ok = bool(result.get("ok", True)) and not _spoken_indicates_failure(spoken)
    except Exception:  # noqa: BLE001
        logger.exception("[NATIVE-PILOT] %s failed user=%s", tool_name, user_id[:8])
        spoken = "Señor, no pude completar la operación de cámara en este momento."
        ok = False

    latency_ms = int((time.perf_counter() - started) * 1000)
    record_tool_metric(
        call_id=call_id,
        tool_name=tool_name,
        latency_ms=latency_ms,
        ok=ok,
        query=question[:120],
    )
    return {"result": spoken, "latency_ms": latency_ms, "ok": ok}


async def execute_activate_camera_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_camera_tool(
        tool_name="activate_camera",
        user_id=user_id,
        payload=payload,
        args=args,
    )


async def execute_deactivate_camera_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_camera_tool(
        tool_name="deactivate_camera",
        user_id=user_id,
        payload=payload,
        args=args,
    )


async def execute_analyze_camera_frame_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_camera_tool(
        tool_name="analyze_camera_frame",
        user_id=user_id,
        payload=payload,
        args=args,
    )


async def execute_search_visible_product_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_camera_tool(
        tool_name="search_visible_product",
        user_id=user_id,
        payload=payload,
        args=args,
    )


async def _execute_native_advanced_tool(
    *,
    tool_name: str,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    import asyncio

    from app.services.advanced_mode_flow import (
        activate_advanced_mode,
        consult_advanced,
        deactivate_advanced_mode,
    )

    started = time.perf_counter()
    call_id = _extract_call_id(payload)
    query = resolve_tool_query(payload, args)

    if not user_id:
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_tool_metric(
            call_id=call_id,
            tool_name=tool_name,
            latency_ms=latency_ms,
            ok=False,
            query=query,
        )
        return {
            "result": "No identifiqué al usuario, señor.",
            "latency_ms": latency_ms,
            "ok": False,
        }

    try:
        if tool_name == "activate_advanced_mode":
            action = await asyncio.to_thread(activate_advanced_mode, user_id)
        elif tool_name == "deactivate_advanced_mode":
            action = await asyncio.to_thread(deactivate_advanced_mode, user_id)
        elif tool_name == "consult_advanced":
            action = await asyncio.to_thread(consult_advanced, user_id, query)
        else:
            action = {
                "ok": False,
                "spoken": "Herramienta de modo avanzado no reconocida, señor.",
            }
        spoken = _format_action_result_with_meta(action)
        # Respuestas de consult sin transición: solo texto limpio para voz
        # (evita que Retell lea [meta:...] o se confunda tras speak_after_execution).
        if tool_name == "consult_advanced" and action.get("status") == "answered":
            spoken = str(action.get("spoken") or spoken).strip()
        ok = bool(action.get("ok"))
    except Exception:  # noqa: BLE001
        logger.exception("[NATIVE-PILOT] %s failed user=%s", tool_name, user_id[:8])
        spoken = "Señor, no pude completar la operación de modo avanzado."
        ok = False

    latency_ms = int((time.perf_counter() - started) * 1000)
    record_tool_metric(
        call_id=call_id,
        tool_name=tool_name,
        latency_ms=latency_ms,
        ok=ok,
        query=query[:120],
    )
    return {"result": spoken, "latency_ms": latency_ms, "ok": ok}


async def execute_activate_advanced_mode_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_advanced_tool(
        tool_name="activate_advanced_mode",
        user_id=user_id,
        payload=payload,
        args=args,
    )


async def execute_consult_advanced_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_advanced_tool(
        tool_name="consult_advanced",
        user_id=user_id,
        payload=payload,
        args=args,
    )


async def execute_deactivate_advanced_mode_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_advanced_tool(
        tool_name="deactivate_advanced_mode",
        user_id=user_id,
        payload=payload,
        args=args,
    )



def _run_calendar_prepare(user_id: str, *, call_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from app.services.calendar_write_flow import prepare_calendar_write

    query = resolve_tool_query(payload, args)
    return prepare_calendar_write(user_id, call_id=call_id, query=query)


def _run_calendar_confirm(user_id: str, *, call_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from app.services.calendar_write_flow import confirm_calendar_write

    return confirm_calendar_write(
        user_id,
        call_id=call_id,
        payload=payload,
        draft_id=str(args.get("draft_id") or ""),
    )


def _run_calendar_cancel(user_id: str, *, call_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from app.services.calendar_write_flow import cancel_calendar_write

    return cancel_calendar_write(
        user_id,
        draft_id=str(args.get("draft_id") or ""),
        reason="user_cancel",
    )


async def execute_calendar_prepare_write_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_finance_action_tool(
        tool_name="calendar_prepare_write",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=_run_calendar_prepare,
    )


async def execute_calendar_confirm_write_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_finance_action_tool(
        tool_name="calendar_confirm_write",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=_run_calendar_confirm,
    )


async def execute_calendar_cancel_write_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_finance_action_tool(
        tool_name="calendar_cancel_write",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=_run_calendar_cancel,
    )



def _run_gmail_prepare(user_id: str, *, call_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from app.services.gmail_send_flow import prepare_gmail_send

    query = resolve_tool_query(payload, args)
    return prepare_gmail_send(
        user_id,
        call_id=call_id,
        to=str(args.get("to") or ""),
        subject=str(args.get("subject") or ""),
        body=str(args.get("body") or ""),
        query=query,
    )


def _run_gmail_confirm(user_id: str, *, call_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from app.services.gmail_send_flow import confirm_gmail_send

    return confirm_gmail_send(
        user_id,
        call_id=call_id,
        payload=payload,
        draft_id=str(args.get("draft_id") or ""),
    )


def _run_gmail_cancel(user_id: str, *, call_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from app.services.gmail_send_flow import cancel_gmail_send

    return cancel_gmail_send(
        user_id,
        draft_id=str(args.get("draft_id") or ""),
        reason="user_cancel",
    )


async def execute_gmail_prepare_send_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_finance_action_tool(
        tool_name="gmail_prepare_send",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=_run_gmail_prepare,
    )


async def execute_gmail_confirm_send_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_finance_action_tool(
        tool_name="gmail_confirm_send",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=_run_gmail_confirm,
    )


async def execute_gmail_cancel_send_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_finance_action_tool(
        tool_name="gmail_cancel_send",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=_run_gmail_cancel,
    )


async def execute_search_web_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    """Búsqueda web general — reutiliza voice_tool_executor.search_web."""
    from app.services.calendar_write_flow import maybe_clear_calendar_pending_on_topic_change
    from app.services.finance_write_flow import maybe_clear_finance_pending_on_topic_change
    from app.services.gmail_send_flow import maybe_clear_gmail_pending_on_topic_change
    from app.services.voice_tool_executor import execute_voice_tool

    started = time.perf_counter()
    call_id = _extract_call_id(payload)
    query = resolve_tool_query(payload, args)
    kind = str(args.get("kind") or "general").strip() or "general"

    if user_id:
        maybe_clear_finance_pending_on_topic_change(user_id, "search_web")
        maybe_clear_calendar_pending_on_topic_change(user_id, "search_web")
        maybe_clear_gmail_pending_on_topic_change(user_id, "search_web")

    if not user_id:
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_tool_metric(
            call_id=call_id,
            tool_name="search_web",
            latency_ms=latency_ms,
            ok=False,
            query=query,
        )
        return {
            "result": "No identifiqué al usuario, señor.",
            "latency_ms": latency_ms,
            "ok": False,
        }

    if not query:
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_tool_metric(
            call_id=call_id,
            tool_name="search_web",
            latency_ms=latency_ms,
            ok=False,
        )
        return {
            "result": "Señor, ¿qué desea que busque?",
            "latency_ms": latency_ms,
            "ok": False,
        }

    try:
        result = await execute_voice_tool(
            "search_web",
            user_id,
            {"query": query, "kind": kind},
        )
        spoken = str(result.get("spoken") or "").strip()
        ok = bool(result.get("ok", True)) and bool(spoken) and not _spoken_indicates_failure(
            spoken
        )
        if not spoken:
            spoken = "Señor, no pude completar la búsqueda en este momento."
            ok = False
    except Exception:  # noqa: BLE001
        logger.exception("[NATIVE-PILOT] search_web failed user=%s", user_id[:8])
        spoken = "Señor, no pude completar la búsqueda en este momento."
        ok = False

    latency_ms = int((time.perf_counter() - started) * 1000)
    record_tool_metric(
        call_id=call_id,
        tool_name="search_web",
        latency_ms=latency_ms,
        ok=ok,
        query=query,
    )
    logger.info(
        "[NATIVE-PILOT] search_web call=%s user=%s latency=%sms ok=%s",
        call_id[:12] if call_id else "?",
        user_id[:8],
        latency_ms,
        ok,
    )
    return {"result": spoken, "latency_ms": latency_ms, "ok": ok}



def _run_meta_prepare(user_id: str, *, call_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from app.services.meta_publish_flow import prepare_meta_publish

    query = resolve_tool_query(payload, args)
    return prepare_meta_publish(
        user_id,
        call_id=call_id,
        platform=str(args.get("platform") or ""),
        caption=str(args.get("caption") or ""),
        query=query,
    )


def _run_meta_confirm(user_id: str, *, call_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from app.services.meta_publish_flow import confirm_meta_publish

    return confirm_meta_publish(
        user_id,
        call_id=call_id,
        payload=payload,
        draft_id=str(args.get("draft_id") or ""),
    )


def _run_meta_cancel(user_id: str, *, call_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from app.services.meta_publish_flow import cancel_meta_publish

    return cancel_meta_publish(
        user_id,
        draft_id=str(args.get("draft_id") or ""),
        reason="user_cancel",
    )


async def execute_meta_prepare_publish_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_finance_action_tool(
        tool_name="meta_prepare_publish",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=_run_meta_prepare,
    )


async def execute_meta_confirm_publish_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_finance_action_tool(
        tool_name="meta_confirm_publish",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=_run_meta_confirm,
    )


async def execute_meta_cancel_publish_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_finance_action_tool(
        tool_name="meta_cancel_publish",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=_run_meta_cancel,
    )


async def execute_check_meta_networks_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    from app.services.voice_tool_executor import execute_voice_tool

    started = time.perf_counter()
    call_id = _extract_call_id(payload)
    if not user_id:
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_tool_metric(call_id=call_id, tool_name="check_meta_networks", latency_ms=latency_ms, ok=False)
        return {"result": "No identifiqué al usuario, señor.", "latency_ms": latency_ms, "ok": False}
    result = await execute_voice_tool("consultar_redes_conectadas", user_id, {})
    spoken = str(result.get("spoken") or "").strip() or "No pude consultar sus redes, señor."
    ok = bool(result.get("ok", True))
    latency_ms = int((time.perf_counter() - started) * 1000)
    record_tool_metric(call_id=call_id, tool_name="check_meta_networks", latency_ms=latency_ms, ok=ok)
    return {"result": spoken, "latency_ms": latency_ms, "ok": ok}


async def _execute_native_voice_alias_tool(
    *,
    tool_name: str,
    voice_tool_name: str,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.services.voice_tool_executor import execute_voice_tool

    started = time.perf_counter()
    call_id = _extract_call_id(payload)
    if not user_id:
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_tool_metric(call_id=call_id, tool_name=tool_name, latency_ms=latency_ms, ok=False)
        return {"result": "No identifiqué al usuario, señor.", "latency_ms": latency_ms, "ok": False}
    result = await execute_voice_tool(voice_tool_name, user_id, args or {})
    spoken = str(result.get("spoken") or "").strip() or "Completado, señor."
    ok = bool(result.get("ok", True)) and not _spoken_indicates_failure(spoken)
    latency_ms = int((time.perf_counter() - started) * 1000)
    record_tool_metric(call_id=call_id, tool_name=tool_name, latency_ms=latency_ms, ok=ok)
    return {"result": spoken, "latency_ms": latency_ms, "ok": ok}


async def execute_enable_prospection_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_voice_alias_tool(
        tool_name="enable_prospection",
        voice_tool_name="activar_prospeccion",
        user_id=user_id,
        payload=payload,
    )


async def execute_disable_prospection_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_voice_alias_tool(
        tool_name="disable_prospection",
        voice_tool_name="desactivar_prospeccion",
        user_id=user_id,
        payload=payload,
    )


async def execute_prospection_report_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_voice_alias_tool(
        tool_name="prospection_report",
        voice_tool_name="reporte_prospeccion",
        user_id=user_id,
        payload=payload,
    )


async def execute_read_social_comments_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    platform = str(args.get("platform") or "both").strip() or "both"
    return await _execute_native_voice_alias_tool(
        tool_name="read_social_comments",
        voice_tool_name="leer_comentarios_redes",
        user_id=user_id,
        payload=payload,
        args={"platform": platform},
    )



async def execute_open_drive_map_tool(*, user_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    return await _execute_native_voice_alias_tool(
        tool_name="open_drive_map",
        voice_tool_name="activar_modo_conducir",
        user_id=user_id,
        payload=payload,
    )


async def execute_search_nearby_places_tool(*, user_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip() or resolve_tool_query(payload, args)
    return await _execute_native_voice_alias_tool(
        tool_name="search_nearby_places",
        voice_tool_name="search_nearby_places",
        user_id=user_id,
        payload=payload,
        args={"query": query, "_user_request": query},
    )


async def execute_show_route_tool(*, user_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    """Muestra ruta: usa opción pendiente/índice o destino en query; no inicia guía."""
    from app.services.navigation_session import get_place_options, get_route

    params: dict[str, Any] = {}
    if args.get("option_index") is not None:
        params["option_index"] = int(args["option_index"])
    query = str(args.get("query") or "").strip() or resolve_tool_query(payload, args)
    if query and query.lower() not in {
        "muestrame la ruta",
        "muéstrame la ruta",
        "mostrar la ruta",
        "muestra la ruta",
        "traza la ruta",
        "calcula la ruta",
        "la ruta",
    }:
        params["destino"] = query
    # «muéstrame la ruta» tras búsqueda → primera opción si aún no hay ruta.
    if "option_index" not in params and "destino" not in params:
        if get_place_options(user_id) and not get_route(user_id):
            params["option_index"] = 0
    # Sin confirm: preview (apply_route); no begin_navigation.
    return await _execute_native_voice_alias_tool(
        tool_name="show_route",
        voice_tool_name="start_navigation",
        user_id=user_id,
        payload=payload,
        args=params,
    )


async def execute_start_drive_navigation_tool(*, user_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    return await _execute_native_voice_alias_tool(
        tool_name="start_drive_navigation",
        voice_tool_name="start_navigation",
        user_id=user_id,
        payload=payload,
        args={"confirm": True, "destino": "iniciar"},
    )


async def execute_stop_drive_navigation_tool(*, user_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    return await _execute_native_voice_alias_tool(
        tool_name="stop_drive_navigation",
        voice_tool_name="stop_navigation",
        user_id=user_id,
        payload=payload,
    )


async def execute_navigation_status_tool(*, user_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    return await _execute_native_voice_alias_tool(
        tool_name="navigation_status",
        voice_tool_name="navigation_status",
        user_id=user_id,
        payload=payload,
    )


async def execute_play_youtube_video_tool(*, user_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip() or resolve_tool_query(payload, args)
    return await _execute_native_voice_alias_tool(
        tool_name="play_youtube_video",
        voice_tool_name="play_youtube_video",
        user_id=user_id,
        payload=payload,
        args={"query": query},
    )


async def execute_pause_youtube_video_tool(*, user_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    return await _execute_native_voice_alias_tool(
        tool_name="pause_youtube_video",
        voice_tool_name="pause_youtube_video",
        user_id=user_id,
        payload=payload,
    )


async def execute_resume_youtube_video_tool(*, user_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    return await _execute_native_voice_alias_tool(
        tool_name="resume_youtube_video",
        voice_tool_name="resume_youtube_video",
        user_id=user_id,
        payload=payload,
    )


async def execute_close_youtube_player_tool(*, user_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    return await _execute_native_voice_alias_tool(
        tool_name="close_youtube_player",
        voice_tool_name="close_youtube_player",
        user_id=user_id,
        payload=payload,
    )


async def execute_generate_image_tool(*, user_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    prompt = str(args.get("prompt") or "").strip() or resolve_tool_query(payload, args)
    quality = str(args.get("quality") or "auto").strip() or "auto"
    call_id = _extract_call_id(payload)
    return await _execute_native_voice_alias_tool(
        tool_name="generate_image",
        voice_tool_name="generate_image",
        user_id=user_id,
        payload=payload,
        args={"prompt": prompt, "quality": quality, "call_id": call_id},
    )


async def execute_generar_pdf_tool(*, user_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    titulo = str(args.get("titulo") or args.get("title") or "").strip()
    contenido = str(args.get("contenido") or args.get("content") or "").strip()
    query = resolve_tool_query(payload, args)
    call_id = _extract_call_id(payload)
    return await _execute_native_voice_alias_tool(
        tool_name="generar_pdf",
        voice_tool_name="generar_pdf",
        user_id=user_id,
        payload=payload,
        args={
            "titulo": titulo,
            "contenido": contenido,
            "_user_request": query or f"{titulo} {contenido}".strip(),
            "call_id": call_id,
        },
    )


# Compat tests / imports previos
resolve_environment_tool_query = resolve_tool_query
