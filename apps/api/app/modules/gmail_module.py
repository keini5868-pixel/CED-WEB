"""Módulo Gmail — leer y enviar correos por voz."""

from __future__ import annotations

import asyncio
import logging
import re

from app.modules.base_module import BaseModule
from app.modules.module_acks import MODULE_ACKS
from app.services import voice_client_session as vcs
from app.services.google_gmail_api import (
    detect_gmail_category,
    extract_recipient,
    extract_sender_query,
    get_message_body,
    list_messages,
    list_messages_by_category,
    send_message,
)
from app.services.google_oauth import get_valid_access_token
from app.services.orchestrator_types import ModuleResult
from app.services.retell_llm_types import Utterance

logger = logging.getLogger(__name__)

GMAIL_VOICE_TIMEOUT_SEC = 18.0

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


def _read_latest_email(access: str, user_id: str, category: str) -> str:
    messages = list_messages_by_category(access, category, max_results=1)  # type: ignore[arg-type]
    if not messages:
        vcs.set_gmail_awaiting_pick(user_id, False)
        label = CATEGORY_LABELS.get(category, "Principal")
        return f"Señor, no tiene correos recientes en {label}."
    msg = messages[0]
    body = get_message_body(access, msg["id"])
    from_name = msg.get("from_name") or msg.get("from", "?")
    vcs.set_gmail_awaiting_pick(user_id, False)
    when = msg.get("relative_date") or ""
    when_txt = f", recibido {when.lower()}" if when else ""
    return (
        f"Señor, su último correo es de {from_name}{when_txt}: "
        f"asunto «{msg['subject']}». {body[:800]}"
    )


CATEGORY_LABELS = {
    "primary": "Principal",
    "promotions": "Promociones",
    "social": "Social",
    "updates": "Actualizaciones",
    "forums": "Foros",
}


def _not_connected_message() -> str:
    return (
        "Señor, aún no tiene Gmail conectado. "
        "Use el botón Conectar Gmail en configuración de voz."
    )


def _summarize_inbox(
    access: str,
    category: str,
    *,
    user_id: str,
    max_results: int = 4,
) -> str:
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


def _read_sender_email(access: str, text: str) -> str:
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
    body = get_message_body(access, msg["id"])
    from_name = msg.get("from_name") or msg.get("from", "?")
    return (
        f"Señor, de {from_name}: asunto «{msg['subject']}». "
        f"{body[:800]}"
    )


def _read_email_by_pick(access: str, user_id: str, hint: str) -> str:
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
        body = get_message_body(access, best["id"])
        from_name = best.get("from_name") or best.get("from", "?")
        vcs.set_gmail_awaiting_pick(user_id, False)
        return (
            f"Señor, de {from_name}: asunto «{best['subject']}». "
            f"{body[:800]}"
        )

    fallback = _read_sender_email(access, f"de {hint}")
    if "no encontré" not in fallback.lower():
        vcs.set_gmail_awaiting_pick(user_id, False)
    return fallback


def _handle_gmail_query(user_id: str, text: str) -> str:
    access = get_valid_access_token("gmail", user_id)
    t = text.lower()

    if is_gmail_followup_pick(text, user_id):
        return _read_email_by_pick(access, user_id, text)

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
        vcs.set_gmail_awaiting_pick(user_id, False)
        return f"Señor, envié el correo a {recipient}."

    category = detect_gmail_category(text)
    if is_gmail_read_latest_intent(text):
        return _read_latest_email(access, user_id, category)

    if re.search(
        r"l[eé]eme\s+mis|qu[eé]\s+emails|qu[eé]\s+correos|cu[aá]ntos\s+emails|"
        r"emails?\s+tengo|correos?\s+tengo|gmail\s+que\s+tengo|"
        r"l[eé]e\s+(?:los\s+)?(?:gmail|correos?|emails?)\b",
        t,
    ):
        return _summarize_inbox(access, category, user_id=user_id)

    if re.search(
        r"l[eé]eme\s+(?:el\s+)?(?:email|correo)|l[eé]e(?:me)?\s+(?:el\s+)?(?:correo|email)\s+de\b",
        t,
    ):
        vcs.set_gmail_awaiting_pick(user_id, False)
        return _read_sender_email(access, text)

    if re.search(r"important", t):
        return _summarize_inbox(access, "primary", user_id=user_id)

    vcs.set_gmail_awaiting_pick(user_id, False)
    return _summarize_inbox(access, category, user_id=user_id)


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
        text = user_text or transcript
        if is_gmail_intent(text) or is_gmail_followup_pick(text, user_id):
            return await self._run(user_id, text)
        return self._idle()

    async def _run(self, user_id: str, text: str) -> ModuleResult:
        try:
            spoken = await asyncio.wait_for(
                asyncio.to_thread(_handle_gmail_query, user_id, text),
                timeout=GMAIL_VOICE_TIMEOUT_SEC,
            )
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
