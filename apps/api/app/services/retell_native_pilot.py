"""Piloto Retell LLM nativo — prompt, tools HTTP firmadas y métricas."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.services.voice_test_mode import GEMINI_STANDALONE_SYSTEM

logger = logging.getLogger(__name__)

STAGING_AGENT_NAME = "CED Jarvis Native Pilot"
NATIVE_PILOT_GREETING = "CED en línea, señor. Estoy listo para conversar."

READ_TOOLS_PROMPT = """
Herramientas (usar solo cuando el usuario lo pida explícitamente):
- get_environment: clima, temperatura, pronóstico, calidad del aire, polen o ambiente.
- list_calendar_events: consultar eventos, citas o recordatorios en Google Calendar (lectura).
- calendar_prepare_write: preparar borrador de cita/recordatorio (NUNCA agenda — solo borrador).
- calendar_confirm_write: agendar en Google Calendar SOLO tras confirmación explícita en voz.
- calendar_cancel_write: descartar borrador de cita pendiente.
- read_gmail: leer bandeja, categorías o correos de un remitente (lectura — incluye cuerpo completo).
- gmail_prepare_send: preparar borrador de correo (NUNCA envía — solo borrador).
- gmail_confirm_send: enviar correo SOLO tras confirmación explícita en voz.
- gmail_cancel_send: descartar borrador de correo pendiente.
- read_finances: resumen financiero, desglose de gastos o pagos pendientes (solo lectura).
- finance_prepare_write: preparar registro de gasto, ingreso o pago pendiente (NUNCA guarda — solo borrador).
- finance_confirm_write: ejecutar registro real SOLO tras confirmación explícita del usuario en voz.
- finance_cancel_write: descartar borrador financiero pendiente sin guardar.
- activate_camera: encender la cámara del dispositivo (una sola vez).
- deactivate_camera: apagar la cámara.
- analyze_camera_frame: describir qué hay frente a la cámara (visión).
- search_visible_product: identificar el objeto visible y buscar datos reales (precio, specs, dónde comprarlo).
- meta_prepare_publish: preparar borrador de publicación FB/IG (NUNCA publica).
- meta_confirm_publish: publicar SOLO tras confirmación explícita en voz.
- meta_cancel_publish: descartar borrador de publicación.
- check_meta_networks: comprobar si Facebook/Instagram están conectados.
- enable_prospection: activar detección de leads en comentarios.
- disable_prospection: desactivar prospección.
- prospection_report: reporte de leads de hoy.
- read_social_comments: leer comentarios recientes FB/IG.
- open_drive_map: abrir mapa / modo conducir.
- search_nearby_places: buscar destino («llévame a …»).
- show_route: mostrar ruta calculada («muéstrame la ruta»).
- start_drive_navigation: iniciar navegación en vivo («inicia la ruta»).
- stop_drive_navigation: detener navegación.
- navigation_status: estado/ETA de la ruta.
- search_web: búsqueda web general (noticias, hechos actuales, datos externos). NO para clima (use get_environment) ni para lo visible en cámara (use search_visible_product).
- activate_advanced_mode: activar modo avanzado con Claude (solo frase «activa modo avanzado»).
- consult_advanced: consulta profunda vía Claude — solo en modo avanzado.
- deactivate_advanced_mode: salir a modo conversacional normal.

Reglas generales:
- NO uses herramientas para charla casual, agradecimientos ("ok gracias"), check-ins ("¿me escuchas?"),
  desahogo personal ni menciones pasajeras sin petición de datos.
- Tras recibir el resultado, responde en 1-4 oraciones. No repitas la consulta ni vuelvas a llamar
  la herramienta sin una petición nueva del usuario.
- EXCEPCIÓN Gmail: tras read_gmail, lee al usuario el texto devuelto por la herramienta tal cual, sin modificarlo ni añadir nada.
- EXCEPCIÓN Finanzas confirmación: tras finance_confirm_write exitoso, di el mensaje de confirmación sin parafrasear.
- EXCEPCIÓN Cámara: tras activate/deactivate/analyze/search, di el resultado de la herramienta tal cual.
- EXCEPCIÓN search_web: tras search_web, di el resultado de la herramienta tal cual (1-4 oraciones).
- EXCEPCIÓN Modo avanzado: tras activate/consult/deactivate avanzado, di el resultado de la herramienta tal cual.
- Calendario escritura: prepare → confirmación → confirm_write. NUNCA inventes que ya se agendó.
- PROHIBIDO llamar calendar_confirm_write en el mismo turno que calendar_prepare_write.
- Gmail envío: prepare → confirmación → confirm_send. NUNCA inventes que ya se envió.
- PROHIBIDO llamar gmail_confirm_send en el mismo turno que gmail_prepare_send.
- Meta publicación: prepare → confirmación → confirm_publish. NUNCA inventes que ya se publicó.
- PROHIBIDO llamar meta_confirm_publish en el mismo turno que meta_prepare_publish.

Gmail — lectura y envío con confirmación:
- read_gmail: repite el resultado tal cual; sin inventar.
- PROHIBIDO prometer «voy a extraer el cuerpo».
1. «envía un correo a … asunto … diciendo …» → gmail_prepare_send.
2. Tras prepare: lee el resumen y pregunta confirmación; transition_to_gmail_confirm_pending.
3. «sí» / «envíalo» → gmail_confirm_send (también en general si no transicionó).
4. «no / cancela» → gmail_cancel_send.

Cámara / visión:
1. «activa/enciende/abre la cámara» → activate_camera UNA sola vez. NO vuelvas a confirmar la activación.
2. PROHIBIDO describir nada visual sin llamar analyze_camera_frame o search_visible_product.
3. «qué ves / qué es esto / analiza» → analyze_camera_frame (si la cámara está apagada, la tool la activa internamente).
4. «dónde lo compro / precio / especificaciones / marca» → search_visible_product.
5. «apaga/cierra la cámara» → deactivate_camera.
6. Si falla captura o permisos, comunica el error UNA vez — sin bucles de «activando, activando».

Calendario — escritura con confirmación:
1. «agéndame / programa / recuérdame …» → calendar_prepare_write con la frase completa.
2. Tras prepare (awaiting_confirmation): lee el resumen y pregunta si confirma; transition_to_calendar_confirm_pending.
3. «sí» / «dale» / «agenda» → calendar_confirm_write (también disponible en general si no transicionó).
4. «no / cancela» → calendar_cancel_write.
5. Si falta permiso de escritura, comunica el mensaje de la tool tal cual (reconectar Calendar).

Meta / redes (publicación):
1. «publica en Facebook/Instagram que diga …» → meta_prepare_publish.
2. Tras prepare (awaiting_confirmation): lee el resumen y pregunta; transition_to_publish_confirm_pending.
3. «sí» / «publícalo» → meta_confirm_publish (también en general si no transicionó).
4. «no / cancela» → meta_cancel_publish.
5. Si falta Meta/OAuth, comunica el mensaje de la tool tal cual (Conectar Redes).
6. Instagram sin imagen: comunica needs_image; no inventes la publicación.
7. check_meta_networks si pregunta si están conectadas las redes.

Prospección (leads en comentarios):
1. «activa prospección» → enable_prospection.
2. «desactiva prospección» → disable_prospection.
3. «reporte de leads / prospección» → prospection_report.
4. «lee los comentarios de Instagram/Facebook» → read_social_comments.
5. Requiere Meta conectado y plan con prospección; si falla, di el mensaje de la tool.

Mapa / navegación:
1. «llévame a [lugar]» → search_nearby_places (abre mapa si hace falta).
2. «muéstrame la ruta» → show_route (traza la ruta; aún no inicia guía).
3. «inicia la ruta / inicia la navegación» → start_drive_navigation.
4. «abre el mapa / modo conducir» → open_drive_map.
5. «detén la navegación / cancela ruta» → stop_drive_navigation.

Búsqueda web (search_web):
1. «busca / investiga / qué pasó / noticias de / cuánto cuesta [sin cámara] / quién es …» con datos actuales → search_web.
2. NO uses search_web para clima/aire (get_environment), calendario, Gmail, finanzas ni objetos en cámara.
3. NO inventes resultados: si falla, di el mensaje de la tool.

Modo avanzado (Claude):
1. Solo la frase «activa modo avanzado» → activate_advanced_mode. Luego transition_to_advanced_mode_active.
2. Tras activar (aunque no hayas cambiado de estado), preguntas sustantivas / análisis / comparación → consult_advanced SIEMPRE. consult_advanced también está disponible en este estado general.
3. PROHIBIDO responder tú mismo análisis profundo, filosófico o literario — debe ser consult_advanced.
4. Clima (get_environment) y lectura de finanzas (read_finances) SÍ disponibles en modo avanzado sin salir.
5. Gmail, escritura de finanzas y cámara: si el usuario las pide en modo avanzado, usa la tool correspondiente o pide salir — no inventes.
6. Salida solo explícita: «modo normal», «sal del modo avanzado», «desactiva modo avanzado» → deactivate_advanced_mode.
7. NO salgas solo tras una respuesta — el modo permanece activo hasta salida explícita.
8. Tras consult_advanced, di el resultado tal cual (sin inventar ni cortar).

Finanzas — escritura con confirmación obligatoria:
1. finance_prepare_write requiere monto y concepto claros (gasto, ingreso o pago pendiente con fecha).
2. Tras prepare exitoso (awaiting_confirmation), lee el resumen en voz y pregunta si confirma el registro.
3. Llama transition_to_finance_confirm_pending cuando prepare devuelva awaiting_confirmation.
4. finance_confirm_write cuando el usuario dice sí, sí., dale, adelante o confirma — incluso solo «sí».
5. NUNCA llames finance_confirm_write en el mismo turno que finance_prepare_write.
6. Si el usuario dice no/cancela → finance_cancel_write y transition_to_general_assistant.
7. Si hay borrador pendiente y el usuario dice «sí», llama finance_confirm_write aunque no hayas cambiado de estado.

read_finances / get_environment / list_calendar_events / read_gmail: reglas de lectura sin confirmación.
""".strip()

GENERAL_ASSISTANT_STATE_PROMPT = """
Estado general — clima, calendario, Gmail, finanzas, Meta/redes, búsqueda web, cámara, modo avanzado.
- search_web: hechos actuales / noticias / datos externos (no clima → get_environment; no cámara → search_visible_product).
- Meta: meta_prepare_publish → confirmar → meta_confirm_publish. check_meta_networks para estado de conexión.
- Prospección: enable_prospection / disable_prospection / prospection_report / read_social_comments.
- Mapa: open_drive_map, search_nearby_places, show_route, start_drive_navigation, stop_drive_navigation, navigation_status.
- Tras meta_prepare_publish con awaiting_confirmation: transition_to_publish_confirm_pending.
- Si hay borrador Meta y dice «sí», llama meta_confirm_publish de inmediato (también aquí).
- Gmail lectura: read_gmail. Envío: gmail_prepare_send → confirmar → gmail_confirm_send (sí / envíalo).
- Tras gmail_prepare_send con awaiting_confirmation: lee el resumen, pregunta confirmación y transition_to_gmail_confirm_pending.
- Si ya hay borrador de correo y el usuario dice «sí», llama gmail_confirm_send de inmediato (también disponible aquí).
- Para AGENDAR: calendar_prepare_write → confirmar → calendar_confirm_write (sí / dale).
- Cámara: activate_camera una sola vez; describe solo con analyze_camera_frame / search_visible_product.
- Si el usuario dice exactamente «activa modo avanzado» → activate_advanced_mode y transition_to_advanced_mode_active.
- Si el modo avanzado YA fue activado en esta sesión (activate_advanced_mode devolvió ok) y el usuario hace una pregunta de análisis/investigación/filosofía/comparación → consult_advanced de inmediato. NO respondas tú esa pregunta.
- Si dice «modo normal» / «sal del modo avanzado» → deactivate_advanced_mode.
- Para REGISTRAR finanzas: finance_prepare_write con la frase del usuario (monto + concepto).
- Tras prepare con awaiting_confirmation: lee el resumen, pregunta confirmación y usa transition_to_finance_confirm_pending.
- Si ya hay borrador pendiente y el usuario dice «sí» o «dale», llama finance_confirm_write de inmediato (también disponible aquí).
""".strip()

FINANCE_CONFIRM_STATE_PROMPT = """
Estado de confirmación de registro financiero — hay un borrador pendiente.
- Repite el resumen si el usuario lo pide.
- Si dice sí, sí., dale, adelante o confirma → finance_confirm_write de inmediato (incluso solo «sí»).
- Si dice no, cancela, olvídalo o cambia de tema → finance_cancel_write y transition_to_general_assistant.
- Si corrige datos → finance_cancel_write, transition_to_general_assistant, finance_prepare_write con datos nuevos.
- read_finances solo si pide consultar finanzas (cancela el registro pendiente).
- Tras finance_confirm_write exitoso, di al usuario exactamente el mensaje de confirmación devuelto.
""".strip()

ADVANCED_MODE_STATE_PROMPT = """
Estado modo avanzado (Claude) — investigación profunda activa.
- Preguntas sustantivas / análisis / investigación → consult_advanced. Di el resultado tal cual.
- Clima o ambiente → get_environment (sin salir del modo).
- Consulta de finanzas (solo lectura) → read_finances (sin salir del modo).
- Si dice «modo normal», «sal del modo avanzado» o «desactiva modo avanzado» → deactivate_advanced_mode y transition_to_general_assistant.
- NO llames Gmail, cámara ni escritura de finanzas aquí — indica que debe salir al modo normal primero.
- NO salgas del modo avanzado tras responder una sola consulta.
""".strip()

CALENDAR_CONFIRM_STATE_PROMPT = """
Estado de confirmación de cita — hay un borrador de calendario pendiente.
- Si dice sí, dale, adelante o confirma → calendar_confirm_write de inmediato (incluso solo «sí»).
- Si dice no/cancela → calendar_cancel_write y transition_to_general_assistant.
- list_calendar_events solo si pide consultar (cancela el borrador pendiente).
- Tras confirm exitoso, di exactamente el mensaje de la herramienta.
""".strip()

STATE_GENERAL_ASSISTANT = "general_assistant"
STATE_CALENDAR_CONFIRM_PENDING = "calendar_confirm_pending"
GMAIL_CONFIRM_STATE_PROMPT = """
Estado de confirmación de correo — hay un borrador pendiente de envío.
- Si dice sí, envíalo, dale o confirma → gmail_confirm_send (incluso solo «sí»).
- Si dice no/cancela → gmail_cancel_send y transition_to_general_assistant.
- Tras envío exitoso, di exactamente el mensaje de la herramienta.
""".strip()

STATE_GMAIL_CONFIRM_PENDING = "gmail_confirm_pending"
STATE_PUBLISH_CONFIRM_PENDING = "publish_confirm_pending"
PUBLISH_CONFIRM_STATE_PROMPT = """
Estado de confirmación de publicación — hay un borrador FB/IG pendiente.
- Si dice sí, publícalo, dale o confirma → meta_confirm_publish (incluso solo «sí»).
- Si dice no/cancela → meta_cancel_publish y transition_to_general_assistant.
- Tras publicar, di exactamente el mensaje de la herramienta.
""".strip()

STATE_FINANCE_CONFIRM_PENDING = "finance_confirm_pending"
STATE_ADVANCED_MODE_ACTIVE = "advanced_mode_active"

RETELL_NATIVE_PILOT_PROMPT = f"{GEMINI_STANDALONE_SYSTEM}\n\n{READ_TOOLS_PROMPT}"

GET_ENVIRONMENT_DESCRIPTION = (
    "Consulta clima, temperatura, pronóstico, calidad del aire o polen para una ubicación. "
    "Usar solo cuando el usuario pida activamente información ambiental en tiempo real."
)

LIST_CALENDAR_DESCRIPTION = (
    "Consulta eventos, citas o recordatorios del Google Calendar del usuario. "
    "Solo lectura — para agendar use calendar_prepare_write."
)

CALENDAR_PREPARE_DESCRIPTION = (
    "Prepara un borrador de cita o recordatorio en el calendario. "
    "Requiere qué, día y hora en la frase del usuario. NO agenda todavía — pide confirmación."
)

CALENDAR_CONFIRM_DESCRIPTION = (
    "Agenda en Google Calendar el borrador pendiente tras confirmación explícita: "
    "sí, dale, adelante. Un solo «sí» basta si hay borrador pendiente."
)

CALENDAR_CANCEL_DESCRIPTION = (
    "Cancela el borrador de cita pendiente sin agendarlo."
)

READ_GMAIL_DESCRIPTION = (
    "Lee correos de Gmail: bandeja, categoría o remitente, incluyendo el cuerpo completo del mensaje. "
    "Para enviar use gmail_prepare_send."
)

GMAIL_PREPARE_DESCRIPTION = (
    "Prepara un borrador de correo (para, asunto, cuerpo). NO envía — pide confirmación."
)

GMAIL_CONFIRM_DESCRIPTION = (
    "Envía el borrador de correo pendiente tras confirmación explícita: sí, envíalo, dale. Un solo «sí» basta."
)

GMAIL_CANCEL_DESCRIPTION = (
    "Cancela el borrador de correo pendiente sin enviarlo."
)

META_PREPARE_DESCRIPTION = (
    "Prepara un borrador de publicación en Facebook o Instagram. "
    "NO publica — pide confirmación. Requiere plataforma y texto (caption). "
    "Instagram requiere imagen previa (cámara o generada)."
)

META_CONFIRM_DESCRIPTION = (
    "Publica el borrador pendiente tras confirmación explícita: sí, publícalo, dale. "
    "Un solo «sí» basta."
)

META_CANCEL_DESCRIPTION = (
    "Cancela el borrador de publicación pendiente sin publicarlo."
)

CHECK_META_DESCRIPTION = (
    "Comprueba si Facebook e Instagram están conectados (Meta OAuth)."
)

ENABLE_PROSPECTION_DESCRIPTION = (
    "Activa el modo prospección: analiza comentarios de Instagram para detectar leads calientes."
)

DISABLE_PROSPECTION_DESCRIPTION = "Desactiva el modo prospección."

PROSPECTION_REPORT_DESCRIPTION = (
    "Informa cuántos leads y leads calientes se detectaron hoy."
)

READ_SOCIAL_COMMENTS_DESCRIPTION = (
    "Lee comentarios recientes de Instagram y/o Facebook y destaca prospectos calientes."
)

OPEN_DRIVE_MAP_DESCRIPTION = (
    "Abre el mapa / modo conducir en pantalla."
)
SEARCH_NEARBY_PLACES_DESCRIPTION = (
    "Busca lugares cercanos o un destino. Usar con «llévame a …»."
)
SHOW_ROUTE_DESCRIPTION = (
    "Calcula y muestra la ruta al destino (sin iniciar guía aún). Usar con «muéstrame la ruta»."
)
START_DRIVE_NAVIGATION_DESCRIPTION = (
    "Inicia la navegación en vivo con zoom, flecha y guía hablada. Usar con «inicia la ruta»."
)
STOP_DRIVE_NAVIGATION_DESCRIPTION = "Detiene la navegación y limpia la ruta activa."
NAVIGATION_STATUS_DESCRIPTION = "Informa el estado de la navegación (ETA, destino, si está guiando)."

SEARCH_WEB_DESCRIPTION = (
    "Búsqueda web general: noticias, hechos actuales, precios/datos externos o investigación breve. "
    "NO usar para clima (get_environment), calendario, Gmail, finanzas ni objetos visibles en cámara "
    "(search_visible_product)."
)

READ_FINANCES_DESCRIPTION = (
    "Consulta finanzas personales: resumen del mes, desglose de gastos o lista de pagos pendientes. "
    "Solo lectura — no registra movimientos."
)

FINANCE_PREPARE_DESCRIPTION = (
    "Prepara un borrador de registro financiero (gasto, ingreso o pago pendiente). "
    "Requiere monto y concepto en la frase del usuario. NO guarda — solo crea borrador "
    "y devuelve resumen para confirmación."
)

FINANCE_CONFIRM_DESCRIPTION = (
    "Ejecuta el registro real del borrador financiero pendiente. "
    "Llamar cuando el usuario acaba de confirmar en voz: sí, sí., dale, adelante, correcto. "
    "Un solo «sí» basta si hay borrador pendiente. draft_id opcional si hay uno activo."
)

FINANCE_CANCEL_DESCRIPTION = (
    "Cancela y descarta el borrador financiero pendiente sin guardar. "
    "Usar cuando el usuario dice no, cancela, olvídalo o desea corregir y rehacer."
)

ACTIVATE_CAMERA_DESCRIPTION = (
    "Enciende la cámara del dispositivo del usuario. "
    "Usar cuando diga activa/enciende/abre la cámara. "
    "Si ya está activa, responde sin reactivar. NO describe lo que ve — solo confirma activación."
)

DEACTIVATE_CAMERA_DESCRIPTION = (
    "Apaga la cámara del dispositivo. "
    "Usar cuando diga apaga/cierra/desactiva la cámara."
)

ANALYZE_CAMERA_FRAME_DESCRIPTION = (
    "Captura un frame de la cámara y describe qué hay frente a ella. "
    "Usar para 'qué ves', 'qué es esto', 'analiza lo que muestro'. "
    "Si la cámara está apagada, la activa internamente. "
    "PROHIBIDO inventar una descripción sin llamar esta herramienta."
)

SEARCH_VISIBLE_PRODUCT_DESCRIPTION = (
    "Identifica el objeto visible ante la cámara y busca información real "
    "(especificaciones, precio, dónde comprarlo, marca). "
    "Usar cuando el usuario pida datos adicionales sobre lo mostrado."
)

ACTIVATE_ADVANCED_DESCRIPTION = (
    "Activa el modo avanzado con Claude para investigación más profunda. "
    "Usar SOLO cuando el usuario diga «activa modo avanzado». "
    "No usar para charla casual ni para módulos rápidos (clima/Gmail/cámara)."
)

CONSULT_ADVANCED_DESCRIPTION = (
    "Consulta profunda vía Claude (modo avanzado). "
    "Usar para preguntas de análisis, investigación, filosofía, comparación de ideas o razonamiento complejo "
    "después de que activate_advanced_mode haya confirmado el modo (aunque no haya cambiado de estado). "
    "También disponible en el estado general por si Retell no transicionó. "
    "Repite el resultado tal cual al usuario. NUNCA respondas esas preguntas sin llamar esta herramienta."
)

DEACTIVATE_ADVANCED_DESCRIPTION = (
    "Sale del modo avanzado y vuelve al modo conversacional normal. "
    "Usar cuando diga «modo normal», «sal del modo avanzado» o «desactiva modo avanzado»."
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
        filler="Un momento, consultando el clima, señor.",
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
            ],
            "edges": [
                {
                    "destination_state_name": STATE_GENERAL_ASSISTANT,
                    "description": (
                        "Volver al flujo general tras registro exitoso, cancelación, borrador expirado "
                        "o cuando ya no hay movimiento pendiente."
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
            ],
            "edges": [
                {
                    "destination_state_name": STATE_GENERAL_ASSISTANT,
                    "description": (
                        "Volver al flujo general tras enviar, cancelar o borrador expirado."
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
            ],
            "edges": [
                {
                    "destination_state_name": STATE_GENERAL_ASSISTANT,
                    "description": (
                        "Volver al flujo general tras publicar, cancelar o borrador expirado."
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
            ],
            "edges": [
                {
                    "destination_state_name": STATE_GENERAL_ASSISTANT,
                    "description": (
                        "Volver al flujo general tras agendar, cancelar o borrador expirado."
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
    meta = {
        "status": action.get("status"),
        "draft_id": action.get("draft_id"),
        "transition": action.get("transition"),
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


# Compat tests / imports previos
resolve_environment_tool_query = resolve_tool_query
