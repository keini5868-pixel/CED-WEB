"""Utilidades compartidas — capa LLM de voz Retell (OpenAI GPT-4.1 / legacy Gemini)."""

from __future__ import annotations

from app.domain.openai_voice_prompt import build_ced_voice_system_prompt, voice_prompt_diagnostics
from app.services.retell_custom_llm import is_generic_agent_line, is_unwanted_voice_reply
from app.services.retell_llm_types import Utterance
from app.services.voice_spoken import is_advisory_voice_query

MAX_HISTORY_TURNS = 10
SESSION_MAX_MINUTES = 30.0
FALLBACK_REPLY = "Disculpe, señor. Tuve un inconveniente técnico. ¿Puede repetir?"

CONVERSATIONAL_TURN_OVERLAY = """
# TURNO CONVERSACIONAL — PRIORIDAD ABSOLUTA
El usuario está en charla personal, saludo casual o comparte algo emocional/cotidiano.
NO invoques herramientas. Responde como Seth: empático, natural, 1-3 oraciones completas.
PROHIBIDO responder solo "¿En qué puedo ayudarle?" o variantes transaccionales.
Valida lo que dice antes de ofrecer ayuda. No fuerces tareas ni prospección.
""".strip()

GREETING_OVERLAY = """
# SALUDO INICIAL DE VOZ — UNA SOLA FRASE
Acabas de conectar una llamada de voz. El usuario aún no ha hablado.
Di UNA sola frase breve, cálida y natural estilo Seth (como en chat empático).
Válido: "Hola, señor." / "Buenos días, señor." / "Seth en línea, señor."
PROHIBIDO: monólogo, listar capacidades, "¿En qué puedo ayudarle?", "A su servicio", "operativo".
""".strip()

REMINDER_OVERLAY = """
# SILENCIO PROLONGADO
El usuario lleva un momento en silencio. Usa el transcript para contexto.
Responde con UNA frase natural y empática — pregunta si sigue ahí, ofrece paciencia,
o retoma el tema anterior si aplica.
PROHIBIDO: "Sigo atento", "¿Continuamos?", tono de chatbot de soporte.
""".strip()

DELAY_ACK_OVERLAY = """
# DEMORA EN PROCESAR
La generación tardó. Responde con UNA frase breve que reconozca la demora con calidez.
Ejemplo: "Permítame un momento, señor." / "Un segundo, señor, ya le respondo."
NO listes capacidades ni uses "¿En qué puedo ayudarle?"
""".strip()

REFORMULATE_EMPATHY_OVERLAY = """
# REFORMULAR CON MÁS EMPATÍA
Tu respuesta anterior fue demasiado genérica, transaccional o vacía.
Reescribe con empatía genuina estilo Seth — la misma calidez que el chat de texto CED.
1-3 oraciones naturales. Valida lo que compartió el usuario antes de ofrecer ayuda.
PROHIBIDO: "¿En qué puedo ayudarle?", "operativo", "a su servicio", relleno de chatbot.
""".strip()


def voice_generation_limits(user_text: str) -> tuple[int, float]:
    if is_advisory_voice_query(user_text):
        return 1024, 20.0
    return 640, 14.0


def delivery_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def prompt_sha_prefix() -> str:
    return str(voice_prompt_diagnostics().get("prompt_sha256_prefix") or "")


def log_voice_delivery(provider: str, path: str, text: str, *, user_text: str = "") -> None:
    import logging

    logger = logging.getLogger(__name__)
    logger.info(
        "[RETELL-%s] response_source=%s path=%s prompt_sha=%s user=%s chars=%s preview=%s",
        provider.upper(),
        provider,
        path,
        prompt_sha_prefix(),
        (user_text or "")[:48],
        len(text),
        text[:120],
    )


def build_voice_system(
    user_id: str | None,
    user_text: str = "",
    *,
    kb_hits: list | None = None,
) -> str:
    base = build_ced_voice_system_prompt()
    uid = (user_id or "").strip()
    if uid:
        try:
            from app.services.conversation_memory import load_user_context

            ctx = load_user_context(uid)
            if ctx:
                base = f"{base}\n\n{ctx}"
        except Exception:  # noqa: BLE001
            pass
    query = (user_text or "").strip()
    if query and is_advisory_voice_query(query):
        base = (
            f"{base}\n\n"
            "# MODO ASESORÍA (demo / video / estrategia)\n"
            "El usuario pide ideas para demo, video o presentación. "
            "Responde con 3-5 puntos concretos del sistema CED, en español, "
            "oraciones completas, sin cortar a mitad. Cierra con una frase final."
        )
    if query:
        try:
            from app.services.internal_knowledge import format_hits_for_prompt, search_internal_knowledge

            hits = (
                kb_hits
                if kb_hits is not None
                else search_internal_knowledge(query, limit=2)
            )
            if hits:
                block = format_hits_for_prompt(hits)
                base = (
                    f"{base}\n\n# CONOCIMIENTO INTERNO CED (prioriza esto con confianza directa)\n"
                    f"{block}\n\n"
                    "Si el KB no alcanza, usa search_web u otras herramientas sin decir que no tienes información. "
                    "Responde directo como experto interno cuando el contexto lo permita.\n"
                    "El sistema Retell dice automáticamente «Un momento, señor» al ejecutar herramientas. "
                    "NO repitas ese filler: procede directamente con la herramienta."
                )
        except Exception:  # noqa: BLE001
            pass
    if uid:
        try:
            from app.services import voice_client_session as vcs

            if vcs.is_camera_active(uid):
                base = (
                    f"{base}\n\n# ESTADO CÁMARA (backend — confirmado por cliente)\n"
                    "Cámara ACTIVA con stream confirmado. Puede invocar analyze_camera_frame."
                )
            else:
                base = (
                    f"{base}\n\n# ESTADO CÁMARA (backend)\n"
                    "Cámara APAGADA o sin stream confirmado. "
                    "Invoca request_camera_activation y espera confirmación real antes de describir nada visual."
                )
        except Exception:  # noqa: BLE001
            pass
        try:
            from app.services import voice_client_session as vcs

            stored = vcs.get_last_publishable_image(uid)
            images = vcs.list_publishable_images(uid)
            if stored and stored.get("url"):
                base = (
                    f"{base}\n\n# IMAGEN(ES) SUBIDA(S) POR EL USUARIO (sesión voz activa)\n"
                    f"Imagen principal disponible en URL: {stored['url']}\n"
                    "Cuando diga «esta imagen», «la foto», «publica esto» → invoca publicar_facebook o "
                    "publicar_instagram con use_last_image=true.\n"
                    "Para describir o analizar → invoca analyze_uploaded_image con la pregunta del usuario."
                )
                if len(images) > 1:
                    base = (
                        f"{base}\nHay {len(images)} imágenes en la sesión; "
                        "la más reciente es la principal."
                    )
        except Exception:  # noqa: BLE001
            pass
    return base


def needs_empathy_reformulation(text: str, *, user_text: str = "") -> bool:
    if not text or not text.strip():
        return True
    if is_unwanted_voice_reply(text, user_text=user_text):
        return True
    if is_generic_agent_line(text) and len(text) < 72:
        return True
    return False


def transcript_to_openai_messages(transcript: list[Utterance]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for utterance in transcript:
        role = "user" if utterance.role == "user" else "assistant"
        text = (utterance.content or "").strip()
        if not text:
            continue
        messages.append({"role": role, "content": text})
    return messages


def truncate_messages(messages: list[dict], *, max_turns: int = MAX_HISTORY_TURNS) -> list[dict]:
    if len(messages) <= max_turns:
        return messages
    return messages[-max_turns:]
