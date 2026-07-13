"""Módulo Gmail — leer y enviar correos por voz."""

from __future__ import annotations

import asyncio
import logging
import re

import httpx

from app.modules.base_module import BaseModule
from app.modules.module_acks import MODULE_ACKS
from app.services import voice_client_session as vcs
from app.services.google_gmail_api import (
    detect_gmail_category,
    extract_recipient,
    extract_sender_query,
    fetch_message_body_detail,
    get_message_body,
    list_inbox_messages,
    list_messages,
    list_messages_by_category,
    send_message,
)
from app.services.google_oauth import force_refresh_access_token, get_valid_access_token
from app.services.orchestrator_types import ModuleResult
from app.services.retell_llm_types import Utterance

logger = logging.getLogger(__name__)

GMAIL_VOICE_TIMEOUT_SEC = 22.0
GMAIL_VOICE_BODY_LIMIT = 1400

_GMAIL_VOICE_UNAVAILABLE = (
    "No pude obtener el cuerpo completo de ese mensaje; "
    "puede estar en un adjunto, una invitación de calendario embebida o un formato no legible por la API."
)


def format_gmail_spoken_user(
    *,
    from_name: str,
    subject: str,
    body: str,
    body_ok: bool = True,
) -> str:
    """Texto listo para leer en voz — sin instrucciones internas para el LLM."""
    if body_ok and (body or "").strip():
        return f"Señor, de {from_name}, asunto «{subject}». {body.strip()}"
    return (
        f"Señor, de {from_name}, asunto «{subject}». "
        f"{_GMAIL_VOICE_UNAVAILABLE}"
    )


def format_gmail_literal_voice(
    *,
    from_name: str,
    subject: str,
    body: str,
    body_ok: bool = True,
) -> str:
    """Alias — salida limpia para voz (sin bloques CUERPO_LITERAL)."""
    return format_gmail_spoken_user(
        from_name=from_name,
        subject=subject,
        body=body,
        body_ok=body_ok,
    )

_READ_BODY_FOLLOWUP_RE = re.compile(
    r"\b(?:"
    r"contenido(?:\s+del\s+correo)?|cuerp[oa](?:\s+del\s+(?:correo|mensaje))?|"
    r"mensaje\s+completo|texto\s+del\s+correo|lo\s+que\s+dice\s+el\s+correo|"
    r"léeme\s+el\s+contenido|lee\s+el\s+contenido|qué\s+dice\s+el\s+correo"
    r")\b",
    re.I,
)


def is_gmail_read_body_followup(text: str) -> bool:
    return bool(_READ_BODY_FOLLOWUP_RE.search(text or ""))


GMAIL_PATTERNS: tuple[str, ...] = (
    r"\b(?:emails?|correos?|gmail)\b",
    r"\b(?:tengo|hay)\s+.*(?:emails?|correos?)\b",
    r"\b(?:tengo|hay)\s+.*(?:emails?|correos?)\s+importantes\b",
    r"\bl[eé]eme\s+(?:mis\s+)?(?:emails?|correos?)\b",
    r"\bl[eé]e\s+(?:los\s+)?(?:gmail|correos?|emails?)\b",
    r"\bl[eé]e(?:me)?\s+(?:el\s+|mi\s+)?(?:[úu]ltim[oa]s?\s+)?(?:correo|email|gmail|mensaje)\b",
    r"\b(?:me\s+puedes|puedes|pod[eí]as)\s+(?:leer|revisar|decir|contar).*(?:correo|email|gmail)\b",
    r"\b(?:[úu]ltim[oa]s?|reciente|nuev[oa])\s+(?:correo|email|gmail|mensaje)\b",
    r"\b(?:correo|email|gmail|mensaje)\s+(?:[úu]ltim[oa]|reciente|nuev[oa]|m[aá]s\s+reciente)\b",
    r"\b(?:qu[eé]|cu[aá]ntos)\s+.*(?:emails?|correos?)\b",
    r"\bl[eé]eme\s+(?:el\s+)?(?:email|correo)\b",
    r"\bl[eé]e(?:me)?\s+(?:el\s+)?(?:correo|email)\s+de\b",
    r"\benv[ií]a\s+(?:un\s+)?(?:email|correo)\b",
    r"\bmandar\s+(?:un\s+)?(?:email|correo)\b",
)

_READ_LATEST_RE = re.compile(
    r"\b(?:"
    r"(?:[úu]ltim[oa]s?|reciente|nuev[oa]|m[aá]s\s+reciente)\s+(?:correo|email|gmail|mensaje)|"
    r"(?:correo|email|gmail|mensaje)\s+(?:[úu]ltim[oa]|reciente|nuev[oa]|m[aá]s\s+reciente)|"
    r"(?:me\s+puedes|puedes|pod[eí]as)\s+(?:leer|revisar|decir|contar).*(?:correo|email|gmail)|"
    r"l[eé]e(?:me)?\s+(?:el\s+|mi\s+)?(?:[úu]ltim[oa]s?\s+)?(?:correo|email|gmail|mensaje)"
    r")\b",
    re.I,
)

_GMAIL_PICK_REJECT = re.compile(
    r"\b(?:clima|pdf|mapa|finanzas|imagen|c[áa]mara|ll[ée]vame|naveg|"
    r"escuchaste|me\s+oyes|me\s+o[ií]ste|repites|repite|me\s+escuchas)\b",
    re.I,
)

_GMAIL_COMMAND_RE = re.compile(
    r"\b(?:correo|email|gmail|mensaje|leer|l[eé]e|l[eé]eme|ultim|reciente)\b",
    re.I,
)


def is_gmail_intent(text: str) -> bool:
    t = (text or "").strip().lower()
    if len(t) < 6:
        return False
    return any(re.search(p, t) for p in GMAIL_PATTERNS)


def is_gmail_followup_pick(text: str, user_id: str = "") -> bool:
    """True si el usuario responde con el nombre del correo tras un listado."""
    t = (text or "").strip()
    if not t or not user_id or not vcs.is_gmail_awaiting_pick(user_id):
        return False
    if len(t) < 2 or len(t) > 100:
        return False
    if _GMAIL_PICK_REJECT.search(t):
        return False
    if _GMAIL_COMMAND_RE.search(t):
        return False
    if re.search(
        r"\bl[eé]eme\s+(?:el\s+)?(?:correo|email)\s+de\b",
        t,
        re.I,
    ):
        return False
    return True


def is_gmail_read_latest_intent(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 8:
        return False
    return bool(_READ_LATEST_RE.search(t))


def _not_connected_message() -> str:
    return (
        "Señor, aún no tiene Gmail conectado. "
        "Use el botón Conectar Gmail en configuración de voz."
    )


def _reconnect_message() -> str:
    return (
        "Señor, Gmail necesita reconexión. "
        "Use el botón Conectar Gmail en configuración de voz e intente de nuevo."
    )


def _format_gmail_error(exc: Exception) -> str:
    if isinstance(exc, ValueError):
        code = str(exc)
        if code == "not_connected":
            return _not_connected_message()
        if code == "reconnect_required":
            return _reconnect_message()
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in (401, 403):
            return _reconnect_message()
        if status == 429:
            return "Señor, Gmail está limitando las consultas. Intente en unos segundos."
    return "Señor, no pude consultar su correo en este momento."


def _gmail_api_call(user_id: str, fn):
    """Ejecuta fn(access) con refresh automático ante 401/403."""
    access = get_valid_access_token("gmail", user_id)
    try:
        return fn(access)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in (401, 403):
            raise
        access = force_refresh_access_token("gmail", user_id)
        return fn(access)


def _normalize_compare(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _message_content_for_voice(
    access: str,
    msg: dict[str, str],
) -> tuple[str, bool, str, str]:
    """Devuelve (texto, body_ok, source, mime_summary) para lectura por voz."""
    subject = str(msg.get("subject") or "")
    snippet = str(msg.get("snippet") or "").strip()
    mime_summary = ""
    try:
        detail = fetch_message_body_detail(access, msg["id"])
        body = detail.text.strip()
        source = detail.source
        mime_summary = detail.mime_summary
        if detail.ok and body:
            if _normalize_compare(body) == _normalize_compare(subject):
                logger.warning(
                    "[GMAIL] body equals subject msg=%s mime=%s",
                    str(msg.get("id") or "")[:12],
                    mime_summary[:120],
                )
                return _GMAIL_VOICE_UNAVAILABLE, False, source, mime_summary
            return body[:GMAIL_VOICE_BODY_LIMIT], True, source, mime_summary
        if body and source == "snippet":
            logger.warning(
                "[GMAIL] only snippet for msg=%s mime=%s",
                str(msg.get("id") or "")[:12],
                mime_summary[:120],
            )
            return _GMAIL_VOICE_UNAVAILABLE, False, source, mime_summary
    except Exception:  # noqa: BLE001
        logger.exception(
            "[GMAIL] body fetch failed msg=%s",
            str(msg.get("id") or "")[:12],
        )

    if snippet and _normalize_compare(snippet) != _normalize_compare(subject):
        return snippet[:GMAIL_VOICE_BODY_LIMIT], False, "snippet", mime_summary
    return _GMAIL_VOICE_UNAVAILABLE, False, "none", mime_summary


def _remember_last_read(user_id: str, msg: dict[str, str], *, body_ok: bool, source: str) -> None:
    vcs.set_gmail_last_read(
        user_id,
        {
            "id": msg.get("id"),
            "from_name": msg.get("from_name") or msg.get("from"),
            "from": msg.get("from"),
            "subject": msg.get("subject"),
            "snippet": msg.get("snippet"),
            "body_ok": body_ok,
            "body_source": source,
        },
    )


def _format_read_message(
    user_id: str,
    access: str,
    msg: dict[str, str],
) -> str:
    content, body_ok, source, mime_summary = _message_content_for_voice(access, msg)
    from_name = msg.get("from_name") or msg.get("from", "?")
    subject = str(msg.get("subject") or "(sin asunto)")
    _remember_last_read(user_id, msg, body_ok=body_ok, source=source)
    logger.info(
        "[GMAIL] read voice user=%s msg=%s from=%r subject=%r body_ok=%s source=%s len=%s mime=%s",
        user_id[:8],
        str(msg.get("id") or "")[:12],
        from_name[:40],
        subject[:60],
        body_ok,
        source,
        len(content),
        mime_summary[:120],
    )
    return format_gmail_spoken_user(
        from_name=from_name,
        subject=subject,
        body=content,
        body_ok=body_ok,
    )


def _read_latest_email(user_id: str) -> str:
    def _fetch(access: str) -> str:
        messages = list_inbox_messages(access, max_results=1)
        if not messages:
            vcs.set_gmail_awaiting_pick(user_id, False)
            return "Señor, no tiene correos recientes en su bandeja de entrada."
        msg = messages[0]
        vcs.set_gmail_awaiting_pick(user_id, False)
        when = msg.get("relative_date") or ""
        when_txt = f", recibido {when.lower()}" if when else ""
        return _format_read_message(user_id, access, msg) + (
            f"\n\n(Recibido{when_txt}.)" if when_txt else ""
        )

    return _gmail_api_call(user_id, _fetch)


def _summarize_inbox(
    category: str,
    *,
    user_id: str,
    max_results: int = 4,
) -> str:
    def _fetch(access: str) -> str:
        messages = list_messages_by_category(access, category, max_results=max_results)  # type: ignore[arg-type]
        label = CATEGORY_LABELS.get(category, "Principal")
        vcs.set_gmail_inbox_cache(user_id, messages)
        vcs.set_gmail_awaiting_pick(user_id, True)
        if not messages:
            vcs.set_gmail_awaiting_pick(user_id, False)
            return f"Señor, no tiene correos recientes en {label}."
        count = len(messages)
        parts: list[str] = []
        for msg in messages[:3]:
            from_name = msg.get("from_name") or msg.get("from", "?")
            subject = msg.get("subject", "(sin asunto)")
            when = msg.get("relative_date") or ""
            segment = f"Uno de {from_name} con asunto «{subject}»"
            if when:
                segment += f", recibido {when.lower()}"
            parts.append(segment)
        nuevo = "nuevo" if count == 1 else "nuevos"
        intro = f"Señor, tiene {count} email{'s' if count != 1 else ''} {nuevo} en {label}: "
        body = ". ".join(parts)
        return intro + body + ". ¿Cuál correo, dígame el nombre?"

    return _gmail_api_call(user_id, _fetch)


CATEGORY_LABELS = {
    "primary": "Principal",
    "promotions": "Promociones",
    "social": "Social",
    "updates": "Actualizaciones",
    "forums": "Foros",
}


def _read_sender_email(access: str, text: str, *, user_id: str) -> str:
    sender = extract_sender_query(text)
    query = f"from:{sender}" if sender else ""
    messages = list_messages(access, query=query, max_results=3)
    if not messages and sender:
        for msg in list_messages_by_category(access, "primary", max_results=10):
            haystack = f"{msg.get('from', '')} {msg.get('from_name', '')} {msg.get('subject', '')}".lower()
            if sender.lower() in haystack:
                messages = [msg]
                break
    if not messages:
        return "Señor, no encontré correos con ese criterio."
    msg = messages[0]
    return _format_read_message(user_id, access, msg)


def _read_last_cached_message(user_id: str) -> str:
    cached = vcs.get_gmail_last_read(user_id)
    if not cached:
        return (
            "Señor, no tengo un correo reciente en contexto. "
            "Dígame de quién desea leer el correo."
        )

    def _fetch(access: str) -> str:
        msg = {
            "id": str(cached.get("id") or ""),
            "from_name": cached.get("from_name") or cached.get("from"),
            "from": cached.get("from"),
            "subject": cached.get("subject"),
            "snippet": cached.get("snippet"),
        }
        return _format_read_message(user_id, access, msg)

    return _gmail_api_call(user_id, _fetch)


def _read_email_by_pick(user_id: str, hint: str) -> str:
    def _fetch(access: str) -> str:
        hint_norm = hint.strip().lower()
        cached = vcs.get_gmail_inbox_cache(user_id)
        tokens = [tok for tok in re.split(r"\s+", hint_norm) if len(tok) >= 2]

        best: dict | None = None
        best_score = 0
        for msg in cached:
            haystack = (
                f"{msg.get('from_name', '')} {msg.get('from', '')} {msg.get('subject', '')}"
            ).lower()
            score = 0
            if hint_norm and hint_norm in haystack:
                score += 10
            for tok in tokens:
                if tok in haystack:
                    score += 3
            if score > best_score:
                best_score = score
                best = msg

        if best and best_score >= 3:
            vcs.set_gmail_awaiting_pick(user_id, False)
            return _format_read_message(user_id, access, best)

        fallback = _read_sender_email(access, f"de {hint}", user_id=user_id)
        if "no encontré" not in fallback.lower():
            vcs.set_gmail_awaiting_pick(user_id, False)
        return fallback

    return _gmail_api_call(user_id, _fetch)


def _handle_gmail_query(user_id: str, text: str) -> str:
    t = text.lower()

    if is_gmail_read_body_followup(text):
        return _read_last_cached_message(user_id)

    if is_gmail_followup_pick(text, user_id):
        return _read_email_by_pick(user_id, text)

    if re.search(r"env[ií]a|mandar", t):
        def _send(access: str) -> str:
            recipient = extract_recipient(text)
            if not recipient:
                return "Señor, indique a quién enviar el correo y el mensaje."
            if "@" not in recipient:
                recipient = f"{recipient.replace(' ', '.').lower()}@example.com"
            body_match = re.search(r"(?:diciendo|que\s+diga|con\s+el\s+mensaje)\s+(.+)$", text, re.I)
            body = (body_match.group(1).strip() if body_match else "Mensaje enviado desde CED.")[:800]
            send_message(
                access,
                to=recipient,
                subject="Mensaje desde CED",
                body=body,
            )
            vcs.set_gmail_awaiting_pick(user_id, False)
            return f"Señor, envié el correo a {recipient}."

        return _gmail_api_call(user_id, _send)

    category = detect_gmail_category(text)
    if is_gmail_read_latest_intent(text):
        return _read_latest_email(user_id)

    if re.search(
        r"l[eé]eme\s+mis|qu[eé]\s+emails|qu[eé]\s+correos|cu[aá]ntos\s+emails|"
        r"emails?\s+tengo|correos?\s+tengo|gmail\s+que\s+tengo|"
        r"l[eé]e\s+(?:los\s+)?(?:gmail|correos?|emails?)\b",
        t,
    ):
        return _summarize_inbox(category, user_id=user_id)

    if re.search(
        r"l[eé]eme\s+(?:el\s+)?(?:email|correo)|"
        r"l[eé]e(?:me)?\s+(?:el\s+)?(?:correo|email)\s+de\b|"
        r"l[eé]e(?:me)?\s+el\s+de\s+",
        t,
    ):
        def _read_sender(access: str) -> str:
            vcs.set_gmail_awaiting_pick(user_id, False)
            return _read_sender_email(access, text, user_id=user_id)

        return _gmail_api_call(user_id, _read_sender)

    if re.search(r"important", t):
        return _summarize_inbox("primary", user_id=user_id)

    vcs.set_gmail_awaiting_pick(user_id, False)
    return _summarize_inbox(category, user_id=user_id)


def handle_gmail_read_sync(user_id: str, text: str) -> dict[str, str]:
    """Consulta Gmail — si piden enviar, redirige al flujo con confirmación."""
    if re.search(r"\b(?:env[ií]a(?:me|r)?|mandar|manda(?:me)?)\b", text or "", re.I):
        return {
            "spoken": (
                "Señor, para enviar un correo use confirmación explícita: "
                "diga por ejemplo «envía un correo a nombre@correo.com asunto Prueba "
                "diciendo Hola» y luego confirme con «sí»."
            ),
        }
    return handle_gmail_query_sync(user_id, text)


def handle_gmail_query_sync(user_id: str, text: str) -> dict[str, str]:
    try:
        spoken = _handle_gmail_query(user_id, text)
        return {"spoken": spoken}
    except Exception as exc:  # noqa: BLE001
        logger.exception("[GMAIL] sync query failed user=%s", user_id[:8])
        return {"spoken": _format_gmail_error(exc)}


class GmailModule(BaseModule):
    name = "gmail"

    async def activate(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        self._enter_active()
        return await self._run(user_id, user_text or transcript)

    async def handle_command(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        if idle := self._guard_passive():
            return idle
        text = user_text or transcript
        if is_gmail_intent(text) or is_gmail_followup_pick(text, user_id):
            return await self._run(user_id, text)
        return self._idle()

    async def _run(self, user_id: str, text: str) -> ModuleResult:
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(handle_gmail_query_sync, user_id, text),
                timeout=GMAIL_VOICE_TIMEOUT_SEC,
            )
            spoken = str(result.get("spoken") or "").strip()
            if not spoken:
                spoken = "Señor, no pude consultar su correo en este momento."
            return ModuleResult(
                ok=True,
                spoken=spoken,
                handles_response=True,
                send_filler=True,
                filler=MODULE_ACKS.get("gmail", "Revisando su correo, señor."),
            )
        except asyncio.TimeoutError:
            return ModuleResult(
                ok=False,
                spoken="Señor, Gmail tardó demasiado. ¿Lo intento de nuevo?",
                handles_response=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[GMAIL] query failed user=%s", user_id[:8])
            return ModuleResult(
                ok=False,
                spoken=_format_gmail_error(exc),
                handles_response=True,
            )
