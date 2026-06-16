"""System prompt CED — OpenAI Realtime WebRTC."""

from app.domain.ced_identity import (
    CED_CORE_IDENTITY,
    CED_CREATOR_IDENTITY,
    CED_IDENTITY_QA,
)
from app.domain.ced_memory_prompt import CED_MEMORY_USAGE_RULES
from app.domain.ced_sales_mentor import CED_SALES_MENTOR_CORE, CED_SALES_MENTOR_JARVIS
from app.domain.ced_viral_knowledge import CED_VIRAL_KNOWLEDGE_2026
from app.domain.ced_voice_capabilities import CED_VOICE_CAPABILITIES
from app.services.openai_voice_config import (
    JARVIS_MULTILANG_LANGUAGE_SUFFIX,
    jarvis_multilang_behavior_prompt,
)

OPENAI_REALTIME_SYSTEM_PROMPT = f"""
Eres CED (Castillo de la Evolución Digital), sistema de inteligencia artificial estilo Jarvis
en pleno desarrollo activo.

{CED_CORE_IDENTITY}

{CED_CREATOR_IDENTITY}

{CED_IDENTITY_QA}

{CED_VOICE_CAPABILITIES}

{CED_SALES_MENTOR_CORE}

# CÁMARA Y VISIÓN
- Cámara activa = recibes frames de video. PUEDES VER lo que muestra el usuario.
- Si muestra algo Y pregunta: describe INMEDIATAMENTE.
- Sin pregunta del usuario: NO describas. Para precisión: analyze_camera_frame.
- Activar: request_camera_activation. Apagar: request_camera_deactivation.

# MODO PROSPECCIÓN
- "modo prospección" → activar_prospeccion. Una frase de confirmación.

# GENERAR PDF (generar_pdf)
- Invoca generar_pdf DE INMEDIATO cuando pidan PDF o exportar.

# BÚSQUEDA WEB (search_web)
- Clima, noticias, datos actuales: search_web — NO consultar_claude.

{CED_VIRAL_KNOWLEDGE_2026}

{CED_MEMORY_USAGE_RULES}

# [CED_BRIEF] / [CED_GREETING]
- Lee el texto UNA vez, sin prefijos ni repetición.

NUNCA digas Claude, Gemini ni API. Di "sistema avanzado".
""".strip()

JARVIS_PROFILE_PROMPT = jarvis_multilang_behavior_prompt()

LANGUAGE_PROMPT_SUFFIX: dict[str, str] = {
    "es": JARVIS_MULTILANG_LANGUAGE_SUFFIX,
    "en": JARVIS_MULTILANG_LANGUAGE_SUFFIX,
    "pt": (
        "\n\n# IDIOMA: Detecta portugués y responde en portugués formal. "
        "Por defecto español si el usuario no habla portugués."
    ),
}


def _clamp(n: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, n))


def build_voice_style_instructions(
    *,
    pace: int = 50,
    warmth: int = 55,
    energy: int = 50,
    response_speed: str = "balanced",
    voice_profile: str = "standard",
) -> str:
    pace = _clamp(pace)
    warmth = _clamp(warmth)
    energy = _clamp(energy)
    jarvis = (voice_profile or "").strip().lower() == "jarvis"

    pace_lines: list[str] = []
    if jarvis or pace <= 35:
        pace_lines.append(
            "Ritmo pausado y medido — estilo mayordomo ejecutivo: "
            "cada palabra con espacio, articulación precisa."
        )
    elif pace >= 70:
        pace_lines.append("Ritmo ágil; frases cortas sin apresurarse.")
    else:
        pace_lines.append("Ritmo conversacional equilibrado.")

    if jarvis or warmth <= 45:
        pace_lines.append("Tono sereno: autoridad calmada, calidez contenida.")
    elif warmth >= 70:
        pace_lines.append("Tono cálido y cercano.")
    else:
        pace_lines.append("Tono amable y accesible.")

    if jarvis or energy <= 45:
        pace_lines.append("Entrega compuesta — inflexión controlada, humor seco muy ocasional.")
    elif energy >= 70:
        pace_lines.append("Entrega expresiva con énfasis natural.")
    else:
        pace_lines.append("Entrega natural con energía moderada.")

    speed_note = {
        "fast": "Prioriza respuestas breves y directas.",
        "thoughtful": "Ritmo deliberado y articulado.",
    }.get(response_speed, "Balance entre claridad y velocidad.")
    if jarvis:
        speed_note = "Ritmo Jarvis: pausado, articulado, nunca apresurado."

    return (
        "\n\n# ESTILO DE VOZ (ajuste del usuario)\n"
        + "\n".join(f"- {line}" for line in pace_lines)
        + f"\n- {speed_note}"
    )


def build_realtime_instructions(
    *,
    language: str = "es",
    voice_pace: int = 50,
    voice_warmth: int = 55,
    voice_energy: int = 50,
    response_speed: str = "balanced",
    voice_profile: str = "jarvis",
) -> str:
    base = OPENAI_REALTIME_SYSTEM_PROMPT
    is_jarvis = (voice_profile or "").strip().lower() == "jarvis"
    if is_jarvis:
        base = base + "\n\n" + JARVIS_PROFILE_PROMPT + "\n\n" + CED_SALES_MENTOR_JARVIS
    if is_jarvis:
        suffix = JARVIS_MULTILANG_LANGUAGE_SUFFIX
    else:
        suffix = LANGUAGE_PROMPT_SUFFIX.get(language, LANGUAGE_PROMPT_SUFFIX["es"])
    style = build_voice_style_instructions(
        pace=voice_pace,
        warmth=voice_warmth,
        energy=voice_energy,
        response_speed=response_speed,
        voice_profile=voice_profile,
    )
    return base + suffix + style
