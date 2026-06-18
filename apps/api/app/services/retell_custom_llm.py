"""Utilidades del protocolo Retell Custom LLM."""

from __future__ import annotations

from app.services.retell_llm_types import Utterance

_ECHO_USER_LINES = frozenset(
    {
        "a su servicio, señor",
        "a su servicio señor",
        "a su servicio, señor.",
        "a su servicio señor.",
    }
)


def should_respond_to_transcript(
    transcript: list[Utterance],
    *,
    interaction_type: str,
) -> bool:
    """Evita autorespuestas tras el saludo o en recordatorios vacíos."""
    if interaction_type == "reminder_required":
        return False

    user_lines = [
        (u.content or "").strip()
        for u in transcript
        if u.role == "user" and (u.content or "").strip()
    ]
    if not user_lines:
        return False

    last = user_lines[-1].strip().lower()
    if last in _ECHO_USER_LINES:
        return False

    # Solo saludo del agente en transcript → esperar voz real del usuario
    agent_lines = [u for u in transcript if u.role == "agent" and (u.content or "").strip()]
    if len(user_lines) == 1 and len(agent_lines) >= 1:
        normalized = last.rstrip(".")
        if normalized in ("hola", "buenos días", "buenas tardes", "buenas noches"):
            return True

    return True
