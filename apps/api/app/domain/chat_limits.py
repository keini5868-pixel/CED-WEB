"""Límites de mensaje de chat (texto pegado)."""

from __future__ import annotations

# Alineado con el extracto máximo de documentos (PDF/Word).
CHAT_MESSAGE_MAX_CHARS = 50_000

CHAT_MESSAGE_TOO_LONG_ES = (
    f"Tu texto es demasiado largo (máximo {CHAT_MESSAGE_MAX_CHARS} caracteres). "
    "Súbelo como archivo PDF o Word (.docx) con el botón de documento."
)


def assert_chat_message_length(text: str) -> None:
    """Lanza ValueError con mensaje claro si el texto supera el límite."""
    if len(text) > CHAT_MESSAGE_MAX_CHARS:
        raise ValueError(CHAT_MESSAGE_TOO_LONG_ES)
