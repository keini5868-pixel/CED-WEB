"""Tratamiento personalizado del usuario — saludo, género y título preferido."""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from app.services import supabase_db
from app.services.cognitive_memory import get_memory, save_memory

logger = logging.getLogger(__name__)

Gender = Literal["male", "female", "neutral"]
ADDRESS_MEMORY_KEYS = frozenset(
    {"tratamiento", "como_llamarme", "preferred_address", "titulo", "titulo_preferido"}
)
INVALID_HONORIFICS = frozenset(
    {
        "si",
        "sí",
        "sir",
        "yes",
        "ok",
        "va",
        "no",
        "que",
        "qué",
        "ke",
        "se",
        "me",
        "te",
        "lo",
        "la",
    }
)


def _is_valid_stored_honorific(raw: str) -> bool:
    t = (raw or "").strip()
    if not t or len(t) < 3:
        return False
    low = t.lower().rstrip(".")
    if low in INVALID_HONORIFICS:
        return False
    if low in {"sr", "sra"}:
        return True
    if _normalize_honorific(t) in ("Señor", "Señora", "Don", "Doña"):
        return True
    return len(t) >= 4 and low not in INVALID_HONORIFICS


def _sanitize_honorific(raw: str, gender: str) -> str:
    h = _normalize_honorific(raw)
    g_default = _gender_default_honorific(gender)
    # Género registrado manda sobre un título Señor/Señora contradictorio.
    if g_default and h in ("Señor", "Señora", "Don", "Doña"):
        if gender == "male" and h in ("Señora", "Doña"):
            return "Señor"
        if gender == "female" and h in ("Señor", "Don"):
            return "Señora"
    if h and _is_valid_stored_honorific(h):
        # Nombre propio u otro título pedido por el usuario.
        return h
    return g_default or "Señor"


def _first_name(full_name: str) -> str:
    name = (full_name or "").strip()
    if not name:
        return ""
    return name.split()[0]


def _normalize_honorific(raw: str) -> str:
    t = (raw or "").strip()
    if not t:
        return ""
    low = t.lower().rstrip(".")
    mapping = {
        "senor": "Señor",
        "señor": "Señor",
        "sr": "Señor",
        "senora": "Señora",
        "señora": "Señora",
        "sra": "Señora",
        "don": "Don",
        "dona": "Doña",
        "doña": "Doña",
    }
    if low in mapping:
        return mapping[low]
    return t[0].upper() + t[1:] if t else t


def _gender_default_honorific(gender: str) -> str:
    g = (gender or "").strip().lower()
    if g == "male":
        return "Señor"
    if g == "female":
        return "Señora"
    return ""


HONORIFICS_WITH_NAME = frozenset(
    {"señor", "senor", "señora", "senora", "don", "doña", "dona", "sr", "sra", "sr.", "sra."}
)


def _build_display_name(honorific: str, first_name: str) -> str:
    h = _normalize_honorific(honorific)
    if not h:
        return first_name or "Usuario"
    if h.lower().rstrip(".") in HONORIFICS_WITH_NAME and first_name:
        return f"{h} {first_name}"
    return h


def _greeting_phrase(
    display_name: str,
    first_name: str,
    honorific: str,
    gender: str,
    *,
    jarvis: bool,
) -> str:
    h = _normalize_honorific(honorific) or _gender_default_honorific(gender)
    if jarvis:
        if h in ("Señor", "Don"):
            return "Hola, señor. ¿Cómo está? ¿En qué lo puedo ayudar?"
        if h in ("Señora", "Doña"):
            return "Hola, señora. ¿Cómo está? ¿En qué la puedo ayudar?"
        name = (display_name or first_name or "").strip()
        if name:
            return f"Hola, {name}. ¿Cómo está? ¿En qué lo puedo ayudar?"
        return "Hola, ¿cómo estás? ¿En qué te puedo ayudar?"
    return f"Hola {first_name or display_name or 'Usuario'}. ¿En qué trabajamos?"


def _read_memory_address(user_id: str) -> str:
    for key in ("tratamiento", "como_llamarme", "preferred_address"):
        data = get_memory(user_id, key)
        if data.get("ok") and (data.get("content") or "").strip():
            return str(data["content"]).strip()
    return ""


def resolve_user_address(user_id: str) -> dict[str, Any]:
    profile = supabase_db.get_profile(user_id) or {}
    full_name = str(profile.get("full_name") or "").strip()
    first = _first_name(full_name)
    gender = str(profile.get("gender") or "").strip().lower()
    if gender not in ("male", "female", "neutral"):
        gender = ""

    preferred = str(profile.get("preferred_address") or "").strip()
    if not preferred:
        preferred = _read_memory_address(user_id)

    honorific = _sanitize_honorific(preferred or _gender_default_honorific(gender), gender)
    display_name = _build_display_name(honorific, first)
    if not first and full_name:
        first = _first_name(full_name) or full_name

    return {
        "ok": True,
        "fullName": full_name,
        "firstName": first,
        "honorific": honorific,
        "displayName": display_name,
        "gender": gender or None,
        "preferredAddress": preferred if _is_valid_stored_honorific(preferred) else None,
        "greetingPhraseJarvis": _greeting_phrase(display_name, first, honorific, gender, jarvis=True),
        "greetingPhraseStandard": _greeting_phrase(display_name, first, honorific, gender, jarvis=False),
    }


def address_context_for_prompt(user_id: str) -> str:
    data = resolve_user_address(user_id)
    display = data.get("displayName") or "Usuario"
    honorific = data.get("honorific") or ""
    first = data.get("firstName") or ""
    full = data.get("fullName") or ""
    gender = data.get("gender")
    jarvis_greeting = data.get("greetingPhraseJarvis") or ""
    standard_greeting = data.get("greetingPhraseStandard") or ""

    gender_note = ""
    if gender == "male":
        gender_note = (
            "Género registrado: masculino — español: Señor; inglés: Sir. "
            "PROHIBIDO Señora/Madam."
        )
    elif gender == "female":
        gender_note = (
            "Género registrado: femenino — español: Señora; inglés: Madam/Ma'am. "
            "PROHIBIDO Señor/Sir."
        )
    elif gender == "neutral":
        gender_note = "Género registrado: neutral (usa nombre sin título salvo preferencia explícita)."

    return (
        "# USUARIO ACTUAL — TRATAMIENTO\n"
        f"- Nombre completo: {full or '(sin registrar)'}\n"
        f"- Nombre corto: {first or display}\n"
        f"- Tratamiento preferido: {honorific or display}\n"
        f"- Si usas vocativo, el correcto es: **{display}**\n"
        + (f"- {gender_note}\n" if gender_note else "")
        + "- Saludo de recepción YA emitido (NO repetir, NO inventar nombres): "
        + f"\"Hola, {honorific or 'señor'}. ¿Cómo está? ¿En qué lo puedo ayudar?\"\n"
        + "- PROHIBIDO saludar de nuevo, decir 'Mire, [nombre]', inventar nombres, o monólogos de apertura.\n"
        + "- PROHIBIDO inglés espontáneo (Hi there, What's on your mind) o «Claro, claro».\n"
        + "- UNA sola respuesta por turno. NUNCA generes dos versiones apiladas ni re-emitas la anterior.\n"
        + "- Si el usuario solo dice hola, ¿cómo estás? o charla casual: SILENCIO o una frase muy breve — "
        "PROHIBIDO preguntar cómo llamarlo si ya tienes tratamiento registrado.\n"
        + "- PROHIBIDO: '¿Cómo te gustaría que te llame?', '¿Prefieres tu nombre o un título?'.\n"
        + "- Si solo escuchas 'bien', 'gracias' o ruido/TV sin una petición clara: SILENCIO TOTAL — NO digas 'Entendido' ni respondas.\n"
        + "\n"
        + "Reglas de tratamiento (conversación natural):\n"
        + "- NO abras cada respuesta con el nombre ni con Señor/Señora.\n"
        + "- El saludo ya usó el trato. Después: habla normal, sin vocativo en cada turno.\n"
        + "- Puedes usar Señor/Señora/nombre como máximo 1 vez cada varios turnos si aporta calor; "
        "el resto del tiempo responde directo al contenido.\n"
        + "- PROHIBIDO inventar género: si es masculino nunca Señora; si es femenino nunca Señor.\n"
        + "- Si el usuario pide cambiar cómo lo llamas "
        "(\"llámame señor\", \"dime señora\", \"trátame de jefe\", \"llámame Keini\"): "
        "invoca save_memory con key \"tratamiento\" y el valor exacto que pidió; confirma en una frase.\n"
        "- Si pide otro título distinto, reemplaza el anterior — no acumules títulos.\n"
        "- PROHIBIDO inventar otro nombre o título distinto al registrado aquí."
    )


def update_user_address(
    user_id: str,
    *,
    preferred_address: str | None = None,
    gender: Gender | None = None,
    sync_memory: bool = True,
) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if preferred_address is not None:
        raw = (preferred_address or "").strip()[:80]
        if raw and _is_valid_stored_honorific(raw):
            fields["preferred_address"] = _normalize_honorific(raw)
        elif not raw:
            fields["preferred_address"] = None
        else:
            logger.warning("[ADDRESS] rejected invalid preferred_address: %r", raw)
    if gender is not None:
        g = (gender or "").strip().lower()
        fields["gender"] = g if g in ("male", "female", "neutral") else None

    if fields:
        try:
            supabase_db._client().table("profiles").update(fields).eq("id", user_id).execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ADDRESS] profile update failed: %s", exc)

    if sync_memory and preferred_address is not None and fields.get("preferred_address"):
        save_memory(
            user_id,
            "tratamiento",
            fields["preferred_address"],
            category="preferencia",
        )

    return resolve_user_address(user_id)


def sync_address_from_memory_key(user_id: str, key: str, content: str) -> None:
    mem_key = (key or "").strip().lower()
    if mem_key not in ADDRESS_MEMORY_KEYS:
        return
    body = (content or "").strip()
    if not body:
        return
    # Extraer título si el contenido es una frase larga
    m = re.search(
        r"\b(se[nñ]or[a]?|don|do[nñ]a|jefe|jefa|doctor[a]?|capit[aá]n)\b",
        body,
        re.I,
    )
    preferred = _normalize_honorific(m.group(1)) if m else ""
    if preferred and _is_valid_stored_honorific(preferred):
        update_user_address(user_id, preferred_address=preferred, sync_memory=False)
