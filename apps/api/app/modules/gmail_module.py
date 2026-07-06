"""Módulo Gmail — leer y enviar correos por voz."""

from __future__ import annotations

import logging
import re

from app.modules.base_module import BaseModule
from app.services.google_gmail_api import (
    extract_recipient,
    extract_sender_query,
    get_message_body,
    list_messages,
    send_message,
)
from app.services.google_oauth import get_valid_access_token
from app.services.orchestrator_types import ModuleResult
from app.services.retell_llm_types import Utterance

logger = logging.getLogger(__name__)

GMAIL_PATTERNS: tuple[str, ...] = (
    r"\b(?:emails?|correos?|gmail)\b",
    r"\b(?:tengo|hay)\s+.*(?:emails?|correos?)\b",
    r"\b(?:tengo|hay)\s+.*(?:emails?|correos?)\s+importantes\b",
    r"\bl[eé]eme\s+(?:el\s+)?(?:email|correo)\b",
    r"\benv[ií]a\s+(?:un\s+)?(?:email|correo)\b",
    r"\bmandar\s+(?:un\s+)?(?:email|correo)\b",
)


def is_gmail_intent(text: str) -> bool:
    t = (text or "").strip().lower()
    if len(t) < 6:
        return False
    return any(re.search(p, t) for p in GMAIL_PATTERNS)


def _not_connected_message() -> str:
    return (
        "Señor, aún no tiene Gmail conectado. "
        "Use el botón Conectar Gmail en configuración de voz."
    )


def _handle_gmail_query(user_id: str, text: str) -> str:
    access = get_valid_access_token("gmail", user_id)
    t = text.lower()

    if re.search(r"env[ií]a|mandar", t):
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
        return f"Señor, envié el correo a {recipient}."

    if re.search(r"l[eé]eme", t):
        sender = extract_sender_query(text)
        query = f"from:{sender}" if sender else ""
        messages = list_messages(access, query=query, max_results=1)
        if not messages:
            return "Señor, no encontré correos con ese criterio."
        msg = messages[0]
        body = get_message_body(access, msg["id"])
        return (
            f"Señor, de {msg['from']}: asunto «{msg['subject']}». "
            f"{body[:400]}"
        )

    query = "is:unread"
    if re.search(r"important", t):
        query = "is:important"
    messages = list_messages(access, query=query, max_results=4)
    if not messages:
        return "Señor, no tiene correos sin leer pendientes."
    count = len(messages)
    parts = [f"«{m['subject']}» de {m['from']}" for m in messages[:3]]
    return f"Señor, tiene {count} correos sin leer. " + "; ".join(parts) + "."


def handle_gmail_query_sync(user_id: str, text: str) -> dict[str, str]:
    try:
        spoken = _handle_gmail_query(user_id, text)
        return {"spoken": spoken}
    except ValueError as exc:
        if str(exc) == "not_connected":
            return {"spoken": _not_connected_message()}
        return {"spoken": "Señor, no pude acceder a su Gmail. Revise la conexión."}
    except Exception:  # noqa: BLE001
        logger.exception("[GMAIL] sync query failed user=%s", user_id[:8])
        return {"spoken": "Señor, no pude consultar su correo en este momento."}


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
        self._active = True
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
        if is_gmail_intent(user_text or transcript):
            return await self._run(user_id, user_text or transcript)
        return self._idle()

    async def _run(self, user_id: str, text: str) -> ModuleResult:
        try:
            spoken = _handle_gmail_query(user_id, text)
            return ModuleResult(ok=True, spoken=spoken, handles_response=True)
        except ValueError as exc:
            if str(exc) == "not_connected":
                return ModuleResult(ok=False, spoken=_not_connected_message(), handles_response=True)
            return ModuleResult(
                ok=False,
                spoken="Señor, no pude acceder a su Gmail. Revise la conexión.",
                handles_response=True,
            )
        except Exception:  # noqa: BLE001
            logger.exception("[GMAIL] query failed user=%s", user_id[:8])
            return ModuleResult(
                ok=False,
                spoken="Señor, no pude consultar su correo en este momento.",
                handles_response=True,
            )
