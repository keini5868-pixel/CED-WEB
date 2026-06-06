"""Voces PrebuiltVoiceConfig válidas para Gemini Live (jun 2026)."""

from __future__ import annotations

DEFAULT_VOICE = "Aoede"
DEFAULT_VOICE_MALE = "Charon"

VALID_GEMINI_VOICES: frozenset[str] = frozenset(
    {
        # Femeninas
        "Aoede",
        "Kore",
        "Leda",
        "Zephyr",
        "Autonoe",
        "Umbriel",
        "Erinome",
        "Laomedeia",
        "Callirrhoe",
        "Despina",
        "Achernar",
        "Gacrux",
        "Pulcherrima",
        "Vindemiatrix",
        "Sulafat",
        # Masculinas
        "Puck",
        "Charon",
        "Fenrir",
        "Orus",
        "Enceladus",
        "Iapetus",
        "Algieba",
        "Algenib",
        "Rasalgethi",
        "Alnilam",
        "Schedar",
        "Achird",
        "Zubenelgenubi",
        "Sadachbia",
        "Sadaltager",
    }
)


def normalize_voice_name(name: str | None) -> str:
    if not name:
        return DEFAULT_VOICE
    cleaned = name.strip()
    if cleaned in VALID_GEMINI_VOICES:
        return cleaned
    return DEFAULT_VOICE
