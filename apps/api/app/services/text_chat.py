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
from app.services.cognitive_intents import has_advanced_confirmation
from app.services.cognitive_router import build_chat_system_extras, route_message
from app.services.chat_intents import (
    is_generate_image_intent,
    is_pdf_intent,
    parse_generate_image_prompt,
    parse_pdf_request,
)
from app.services.claude_deep_analysis import consultar_sistema_avanzado
from app.domain.ced_identity import (
    CED_CORE_IDENTITY,
    CED_CREATOR_IDENTITY,
    CED_HUMAN_VOICE_STYLE,
)
from app.domain.ced_memory_prompt import CED_MEMORY_USAGE_RULES
from app.domain.ced_sales_mentor import CED_SALES_MENTOR_CORE
from app.domain.ced_viral_knowledge import CED_VIRAL_KNOWLEDGE_2026
from app.services.meta_social import MetaSocialError, publish_facebook, publish_instagram
from app.services.pdf_report import store_pdf

logger = logging.getLogger(__name__)

CHAT_MODEL = "claude-sonnet-4-6"
CHAT_MODEL_FAST = "claude-3-5-haiku-20241022"
CHAT_GEMINI_MODEL = "gemini-2.5-flash"
CHAT_SYSTEM_MAX_CHARS = 14_000


def _gemini_chat_model() -> str:
    settings = get_settings()
    return settings.gemini_voice_model.strip() or CHAT_GEMINI_MODEL


CHAT_HISTORY_LIMIT = 30
CHAT_SIMPLE_MAX_TOKENS = 700
CHAT_TOOLS_MAX_TOKENS = 1000
DIRECT_IMAGE_MAX_CHARS = 500

_VIRAL_KEYWORDS = re.compile(
    r"\b(instagram|tiktok|reels?|viral|horario|publicar|contenido|linkedin|facebook|"
    r"hooks?|stories|algoritmo|engagement|redes\s+sociales)\b",
    re.I,
)
_TOOLS_KEYWORDS = re.compile(
    r"\b(publica|publicar|instagram|facebook|meta|recuerdas|guarda|memoria|"
    r"lead|cliente|pdf|imagen|conectad)\b",
    re.I,
)

HALLUCINATED_TOOL_PATTERNS = (
    r"\*\*generate_image\*\*",
    r"\*\*generar_pdf\*\*",
    r"\*\*publicar_facebook\*\*",
    r"\*\*publicar_instagram\*\*",
    r"```\s*generate_image",
    r"```\s*generar_pdf",
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

{CED_CORE_IDENTITY}

{CED_CREATOR_IDENTITY}

{CED_HUMAN_VOICE_STYLE}

{CED_SALES_MENTOR_CORE}

IMPORTANTE — tratamiento del usuario:
- Usa el nombre y título del bloque "USUARIO ACTUAL — TRATAMIENTO" inyectado abajo.
- Si piden "llámame señor/señora/jefe/etc.", confirma y recuerda con save_memory key "tratamiento".
- NO uses tono de mayordomo exagerado; Señor/Señora solo si el usuario lo prefiere.

IMPORTANTE — cerebro híbrido CED:
- Primero usa conocimiento interno estable (conceptos, negocio, ciencia, cultura) cuando viene en el contexto.
- Solo afirma datos de hoy (clima, precios, noticias) si hay contexto web inyectado abajo.
- Sistema avanzado: si el contexto indica confirmación pendiente, pregunta antes de profundizar.

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

PUBLICACIÓN EN REDES SOCIALES (Instagram / Facebook):

FLUJO OBLIGATORIO (sigue estos pasos en orden):
1. Usuario sube imagen + pide publicar → responde SIEMPRE: «Imagen recibida, señor. ¿Necesita que le ayude con el título y la descripción, o ya tiene su texto listo?»
2. Si pide ayuda → propón título + descripción + hashtags CONCRETOS (nunca respuestas vacías, nunca solo «---» o «**»).
3. Si da su texto → confirma el texto y pide que diga «envía» o «publica».
4. Solo cuando diga «envía», «publica», «dale», «enviar publicación» → invoca la tool (use_last_uploaded_image=true).
5. Tras éxito real de la tool → «Un momento, señor… Listo. Publicación enviada.»

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

PROHIBIDO (respuestas de chatbot genérico):
- "No tengo acceso a internet en tiempo real" — CED tiene búsqueda y herramientas en voz; en chat puedes preparar contenido y publicar vía Meta.
- "No me puedo conectar a tus cuentas" — sí puedes vía Meta OAuth cuando está conectado.
- Recomendar Buffer/Hootsuite como única opción si el usuario ya tiene CED con redes conectadas.

Cuando prepares contenido para redes, entrégalo listo y ofrece publicarlo con CED si aplica."""


def _wants_viral_knowledge(text: str) -> bool:
    return bool(_VIRAL_KEYWORDS.search(text or ""))


def _has_hallucinated_tool(text: str) -> bool:
    for pattern in HALLUCINATED_TOOL_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


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
    if re.search(r"sugerencia.*(?:instagram|facebook)", stripped, re.I) and len(stripped) < 80:
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


def _needs_chat_tools(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if is_generate_image_intent(t):
        img_prompt = parse_generate_image_prompt(t)
        if not img_prompt or len(t) > DIRECT_IMAGE_MAX_CHARS:
            return True
        return False
    if is_pdf_intent(t):
        return False
    return bool(_TOOLS_KEYWORDS.search(t))


def _build_chat_system(
    user_id: str,
    user_text: str,
    route: Any | None = None,
    conversation_id: str | None = None,
) -> str:
    parts = [_chat_system_for_user(user_id)]
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


def chat_status(user_id: str) -> dict[str, Any]:
    from app.services.admin_users import get_user_access

    allowed, reason, _ = get_user_access(user_id)
    trial_expired = not allowed and reason == "trial_expired"
    limit = _message_limit_for_user(user_id)
    used = count_user_messages_today(user_id)
    unlimited = limit < 0
    remaining = -1 if unlimited else max(0, limit - used)
    blocked = not unlimited and limit > 0 and used >= limit
    return {
        "messages_used_today": used,
        "messages_limit_daily": limit if limit >= 0 else None,
        "unlimited": unlimited,
        "remaining_today": remaining if remaining >= 0 else None,
        "blocked": blocked,
        "trial_expired": trial_expired,
    }


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
) -> str:
    try:
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
            from app.services.publish_image_context import (
                clear_session_image,
                resolve_image_for_publishing,
            )

            use_last = tool_input.get("use_last_uploaded_image", True)
            resolved_url: str | None = None
            resolved_data: str | None = None
            if tool_input.get("image_url") or tool_input.get("image_data"):
                resolved = resolve_image_for_publishing(
                    user_id,
                    conversation_id,
                    use_last_uploaded_image=False,
                    image_url=tool_input.get("image_url"),
                    image_data=tool_input.get("image_data"),
                )
                if resolved.get("ok"):
                    resolved_url = resolved.get("url")
                    resolved_data = resolved.get("data")
            elif use_last is not False:
                resolved = resolve_image_for_publishing(
                    user_id,
                    conversation_id,
                    use_last_uploaded_image=True,
                )
                if resolved.get("ok"):
                    resolved_url = resolved.get("url")
                    resolved_data = resolved.get("data")
            result = publish_facebook(
                user_id,
                str(tool_input.get("message") or ""),
                image_url=resolved_url,
                image_data=resolved_data,
            )
            if result.get("ok") and (resolved_url or resolved_data):
                clear_session_image(user_id, conversation_id)
            return json.dumps(result)
        if name == "publicar_instagram":
            from app.services.publish_image_context import (
                clear_session_image,
                resolve_image_for_publishing,
            )

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
                str(tool_input.get("caption") or ""),
                image_url=resolved.get("url"),
                image_data=resolved.get("data"),
            )
            if result.get("ok"):
                clear_session_image(user_id, conversation_id)
                try:
                    from app.services import voice_client_session as vcs

                    vcs.clear_last_publishable_image(user_id)
                except Exception:  # noqa: BLE001
                    pass
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
            title = str(tool_input.get("title") or "Documento CED").strip()
            content = str(tool_input.get("content") or "").strip()
            if not content or len(content) < 3:
                content = title
            artifact = store_pdf(user_id=user_id, title=title, content=content)
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
            from app.services.openai_images import generate_image

            plan_id = None
            try:
                sub = supabase_db.get_subscription(user_id)
                plan_id = sub.get("plan_id") if sub else None
            except Exception:  # noqa: BLE001
                pass
            prompt = str(tool_input.get("prompt") or "").strip()
            quality = str(tool_input.get("quality") or "auto")
            result = generate_image(
                user_id=user_id,
                plan_id=plan_id,
                prompt=prompt,
                quality=quality,
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
) -> str:
    data = _anthropic_request(
        api_key=api_key,
        system=system,
        messages=messages,
        model=CHAT_MODEL_FAST,
        max_tokens=CHAT_SIMPLE_MAX_TOKENS,
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
) -> str:
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
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=_trim_system(system),
                    temperature=0.4,
                    max_output_tokens=CHAT_SIMPLE_MAX_TOKENS,
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
) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None]:
    """Gemini primero; Claude como respaldo."""
    last_exc: Exception | None = None

    if google_key:
        try:
            reply = _gemini_simple_reply(
                api_key=google_key,
                model=gemini_model,
                system=system,
                messages=messages,
            )
            return reply, None, None
        except Exception as exc:  # noqa: BLE001
            logger.warning("[CHAT] Gemini simple failed: %s", exc)
            last_exc = exc

    if anthropic_key:
        try:
            reply = _anthropic_simple_reply(api_key=anthropic_key, system=system, messages=messages)
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
        return {
            "url": str(data["url"]),
            "prompt": data.get("prompt"),
            "quality": data.get("quality"),
        }
    return None


def _advanced_confirm_followup(history: list[dict[str, str]], user_reply: str) -> str | None:
    """Si el usuario confirmó sistema avanzado, devuelve la pregunta original."""
    if not has_advanced_confirmation(user_reply):
        return None
    last_model: str | None = None
    for row in reversed(history):
        if row.get("role") == "model":
            last_model = (row.get("content") or "").strip()
            break
    if not last_model or not re.search(r"sistema avanzado|confirma", last_model, re.I):
        return None
    seen_model = False
    for row in reversed(history):
        role = row.get("role")
        content = (row.get("content") or "").strip()
        if not content:
            continue
        if role == "model" and content == last_model:
            seen_model = True
            continue
        if seen_model and role == "user":
            return content
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
    for _ in range(4):
        data = _anthropic_request(api_key=api_key, system=system, messages=messages)
        blocks = data.get("content") or []
        tool_uses = [b for b in blocks if isinstance(b, dict) and b.get("type") == "tool_use"]
        if not tool_uses:
            reply = _final_text_from_response(data)
            if reply:
                if pdf_attachment:
                    reply = _strip_pdf_markdown_links(reply)
                if (
                    allow_hallucination_retry
                    and _has_hallucinated_tool(reply)
                    and not image_attachment
                    and not pdf_attachment
                ):
                    logger.warning("[CHAT] Hallucinated tool detected, retrying")
                    retry_messages = [
                        *messages,
                        {"role": "assistant", "content": reply},
                        {"role": "user", "content": HALLUCINATION_RETRY_USER_MESSAGE},
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
        )
        if _has_hallucinated_tool(reply) and anthropic_key:
            logger.warning("[CHAT] Hallucinated tool in simple path — escalating to tools")
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

    if image_bytes:
        from app.services.chat_multimedia import analyze_chat_image
        from app.services.publish_image_context import register_text_chat_image
        from app.services.publish_text import is_social_publish_intent
        from app.services.text_publish_flow import (
            handle_publish_flow_turn,
            start_publish_flow_from_image,
        )

        register_text_chat_image(
            user_id,
            conversation_id,
            image_bytes,
            image_media_type or "image/jpeg",
        )

        if is_social_publish_intent(text):
            reply = start_publish_flow_from_image(user_id, conversation_id, text)
            return _finish(
                reply,
                route_meta={"intent": "publish_flow", "source": "image_upload"},
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

    img_prompt = parse_generate_image_prompt(text)
    if (
        img_prompt
        and is_generate_image_intent(text)
        and len(text.strip()) <= DIRECT_IMAGE_MAX_CHARS
    ):
        from app.services.openai_images import generate_image

        plan_id = None
        try:
            sub = supabase_db.get_subscription(user_id)
            plan_id = sub.get("plan_id") if sub else None
        except Exception:  # noqa: BLE001
            pass
        img_result = generate_image(
            user_id=user_id,
            plan_id=plan_id,
            prompt=img_prompt,
            quality="auto",
        )
        if img_result.get("ok") and img_result.get("url"):
            from app.services.publish_image_context import register_text_chat_image_url

            register_text_chat_image_url(
                user_id,
                conversation_id,
                str(img_result["url"]),
            )
            return _finish(
                "Listo. Aquí está tu imagen generada.",
                route_meta={"intent": "generate_image", "source": "direct"},
                image={
                    "url": str(img_result["url"]),
                    "prompt": img_prompt,
                    "quality": img_result.get("quality"),
                },
            )
        err = str(img_result.get("error") or "No pude generar la imagen.")
        return _finish(
            f"No pude generar la imagen: {err}",
            route_meta={"intent": "generate_image", "source": "direct_error"},
        )

    pdf_req = parse_pdf_request(text)
    if pdf_req and is_pdf_intent(text):
        from app.deps.plan_access import effective_plan_limits

        limits, reason, _trial = effective_plan_limits(user_id)
        if reason == "trial_expired":
            return _finish(
                "Tu prueba terminó. Elige un plan en Precios o continúa con el plan Básico gratis.",
            )
        if not limits.pdf_reports:
            return _finish(
                "Los PDFs requieren plan Élite o Founding. Mejora tu plan en /pricing.",
            )
        pdf_title, pdf_body = pdf_req
        if pdf_title == "Documento CED" and pdf_body:
            pdf_title = pdf_body[:60].strip()
        artifact = store_pdf(
            user_id=user_id,
            title=pdf_title,
            content=pdf_body,
            conversation_id=conversation_id,
        )
        return _finish(
            f'Listo. PDF "{artifact.title}" generado. Usa el botón Descargar abajo.',
            route_meta={"intent": "generar_pdf", "source": "direct"},
            pdf=_pdf_attachment_from_artifact(artifact),
        )

    followup_prompt = _advanced_confirm_followup(history, text)
    if followup_prompt:
        deep = consultar_sistema_avanzado(followup_prompt)
        if deep.get("ok"):
            reply = str(deep.get("result") or "").strip() or "Listo."
        else:
            reply = str(deep.get("error") or "El sistema avanzado no respondió.")
        return _finish(
            reply,
            route_meta={"intent": "advanced_analysis", "source": "confirm_followup"},
        )

    route = route_message(user_id, text, channel="text")

    if route.intent == "memory_save" and route.speakable:
        return _finish(route.speakable, route_meta=route.to_dict())

    if route.needs_advanced_confirm and route.speakable:
        return _finish(route.speakable, route_meta=route.to_dict())

    if route.intent == "advanced_analysis" and route.speakable:
        return _finish(route.speakable, route_meta=route.to_dict())

    if route.intent == "web_search" and route.speakable and route.web_kind in ("news", "weather"):
        return _finish(route.speakable, route_meta=route.to_dict())

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
            publish_reply,
            route_meta={"intent": "publish_flow", "source": "conversation"},
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

    return _finish(
        reply,
        route_meta=route.to_dict(),
        pdf=pdf_attachment,
        image=image_attachment,
    )
