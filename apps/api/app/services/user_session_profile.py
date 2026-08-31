"""Memoria persistente estructurada por cliente (CRM corto).

Regla de oro: al prompt SOLO van unas pocas líneas de datos puntuales.
Nunca se inyecta el historial completo de conversaciones anteriores.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Campos por profundidad de plan
TIER_BASIC = "basic"  # free_basic, starter
TIER_MID = "mid"  # cierre, pro
TIER_FULL = "full"  # elite, founding
TIER_ADMIN = "admin"  # super_admin

BASIC_FIELDS = ("display_name", "business_niche")
MID_FIELDS = BASIC_FIELDS + (
    "plan_interest",
    "last_topic",
    "preferred_tone",
    "objections",
)
FULL_FIELDS = MID_FIELDS
ADMIN_FIELDS = FULL_FIELDS + ("tech_decisions", "speaking_style_notes")

COOLING_DAYS = 5
HOT_PRICE_ASKS = 2
HOT_TOPIC_HITS = 2
MAX_OBJECTIONS = 6
MAX_TECH = 12
MAX_TOPIC_LEN = 160
MAX_STYLE_LEN = 240

_NAME = re.compile(
    r"(?is)\b(?:me\s+llamo|soy|mi\s+nombre\s+es)\s+([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]+){0,2})",
)
_NICHE = re.compile(
    r"(?is)\b(?:mi\s+(?:negocio|empresa|rubro|marca)\s+(?:es|de)|"
    r"tengo\s+(?:un|una)\s+(?:negocio|empresa|tienda|marca)\s+de|"
    r"trabajo\s+(?:en|con)|vendo|vendemos)\s+([^.!?\n]{3,80})",
)
_PLAN_INTEREST = re.compile(
    r"(?is)\b(?:me\s+interesa|quiero|busco|estoy\s+viendo)\s+"
    r"(?:el\s+)?(?:plan\s+)?(starter|pro|elite|[eé]lite|founding|b[aá]sico|"
    r"cierre|pm(?:\s*international)?|fitline|avanzado|voz|imagen(?:es)?|"
    r"oportunidad(?:es)?|finanzas|m[oó]dulo\s+\w+)",
)
_PRICE = re.compile(
    r"(?is)\b(?:cu[aá]nto\s+(?:cuesta|vale|sale)|precio|costo|"
    r"tarifa|suscripci[oó]n|mensualidad|\$\s*\d+)\b",
)
_OBJECTION = re.compile(
    r"(?is)\b(?:es\s+caro|muy\s+caro|no\s+tengo\s+(?:tiempo|dinero|presupuesto)|"
    r"despu[eé]s|m[aá]s\s+adelante|lo\s+pienso|no\s+estoy\s+seguro|"
    r"tengo\s+miedo|no\s+creo|ya\s+prob[eé])\b",
)
_TONE = re.compile(
    r"(?is)\b(?:h[aá]blame\s+(?:en\s+)?(?:t[uú]|usted)|"
    r"prefiero\s+(?:t[uú]|usted)|ll[aá]mame\s+(?:se[nñ]or|se[nñ]ora|jefe)|"
    r"en\s+(?:espa[nñ]ol|ingl[eé]s)|m[aá]s\s+(?:corto|formal|directo|casual))\b",
)
_TECH_DECISION = re.compile(
    r"(?is)\b(?:descartamos|descarta|no\s+quiero|ya\s+(?:resolvimos|qued[oó]|decidimos)|"
    r"no\s+propongas|dejamos\s+de|fuera\s+eso|no\s+volver\s+a)\b"
    r".{0,120}",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(text: str) -> str:
    raw = unicodedata.normalize("NFKD", (text or "").strip().lower())
    return "".join(ch for ch in raw if not unicodedata.combining(ch))


def _client():
    from app.services import supabase_db

    return supabase_db._client()


def resolve_memory_tier(user_id: str) -> str:
    """Profundidad de memoria según plan / admin."""
    try:
        from app.deps.auth import is_super_admin
        from app.domain.plans import normalize_plan_id
        from app.services import supabase_db

        profile = supabase_db.get_profile(user_id) or {}
        if is_super_admin(profile.get("email"), profile.get("role")):
            return TIER_ADMIN
        sub = supabase_db.get_subscription(user_id) or {}
        plan = normalize_plan_id(sub.get("plan_id"))
        if plan in ("elite", "founding", "elite_founding", "elite_regular"):
            return TIER_FULL
        if plan in ("pro", "cierre"):
            return TIER_MID
        return TIER_BASIC
    except Exception:  # noqa: BLE001
        logger.warning("[USER_MEMORY] tier resolve failed user=%s", (user_id or "")[:8])
        return TIER_BASIC


def fields_for_tier(tier: str) -> tuple[str, ...]:
    if tier == TIER_ADMIN:
        return ADMIN_FIELDS
    if tier == TIER_FULL:
        return FULL_FIELDS
    if tier == TIER_MID:
        return MID_FIELDS
    return BASIC_FIELDS


def get_user_memory(user_id: str) -> dict[str, Any] | None:
    uid = (user_id or "").strip()
    if not uid:
        return None
    try:
        result = (
            _client()
            .table("ced_user_memory")
            .select("*")
            .eq("user_id", uid)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None
    except Exception:  # noqa: BLE001
        logger.warning("[USER_MEMORY] get failed user=%s", uid[:8])
        return None


def _upsert(user_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    uid = (user_id or "").strip()
    if not uid or not patch:
        return None
    row = {"user_id": uid, "updated_at": _now_iso(), **patch}
    try:
        result = (
            _client()
            .table("ced_user_memory")
            .upsert(row, on_conflict="user_id")
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else row
    except Exception:  # noqa: BLE001
        logger.exception("[USER_MEMORY] upsert failed user=%s", uid[:8])
        return None


def format_memory_prompt_block(user_id: str) -> str:
    """Resumen corto para el system prompt (pocas líneas)."""
    uid = (user_id or "").strip()
    if not uid:
        return ""
    tier = resolve_memory_tier(uid)
    allowed = set(fields_for_tier(tier))
    row = get_user_memory(uid) or {}
    if not row and tier != TIER_ADMIN:
        return ""

    lines: list[str] = ["# MEMORIA DEL CLIENTE (solo datos puntuales — no historial)"]
    if tier == TIER_ADMIN:
        lines.append(
            "Cuenta ADMIN: memoria completa. Respeta decisiones técnicas ya tomadas; "
            "no propongas de nuevo algo descartado o resuelto."
        )

    mapping = [
        ("display_name", "Nombre", lambda v: str(v).strip()),
        ("business_niche", "Rubro/negocio", lambda v: str(v).strip()),
        ("plan_interest", "Plan/módulo de interés", lambda v: str(v).strip()),
        ("last_topic", "Último tema", lambda v: str(v).strip()[:MAX_TOPIC_LEN]),
        ("preferred_tone", "Tono/idioma", lambda v: str(v).strip()),
    ]
    for key, label, fmt in mapping:
        if key not in allowed:
            continue
        val = row.get(key)
        if val:
            lines.append(f"- {label}: {fmt(val)}")

    if "objections" in allowed:
        objs = [str(o).strip() for o in (row.get("objections") or []) if str(o).strip()]
        if objs:
            lines.append(f"- Objeciones ya planteadas: {'; '.join(objs[:4])}")

    if "tech_decisions" in allowed:
        decisions = [
            str(d).strip() for d in (row.get("tech_decisions") or []) if str(d).strip()
        ]
        if decisions:
            lines.append(
                "- Decisiones técnicas ya tomadas (NO reabrir): "
                + "; ".join(decisions[-6:])
            )

    if "speaking_style_notes" in allowed:
        style = str(row.get("speaking_style_notes") or "").strip()
        if style:
            lines.append(f"- Forma de hablar / instrucciones: {style[:MAX_STYLE_LEN]}")

    cooling_days = int(row.get("cooling_days") or 0)
    if cooling_days >= COOLING_DAYS and row.get("last_topic"):
        lines.append(
            f"- SEGUIMIENTO: el cliente lleva ~{cooling_days} días sin escribir. "
            f"Retoma con calidez el tema «{str(row.get('last_topic'))[:80]}» "
            "sin sonar a spam."
        )
    elif row.get("last_conversation_at") and row.get("last_topic"):
        when = str(row.get("last_conversation_at"))[:10]
        lines.append(f"- Última conversación: {when}")

    if row.get("hot_lead_flagged_at"):
        lines.append(
            "- Señal: lead caliente (repitió tema o preguntó precio más de una vez). "
            "Prioriza claridad y cierre profesional."
        )

    if len(lines) <= 1:
        return ""
    lines.append(
        "Usa estos datos con naturalidad. PROHIBIDO recitar el bloque entero al saludar."
    )
    return "\n".join(lines)


def _topic_key(text: str) -> str:
    norm = _norm(text)
    # Quita muletillas cortas; toma primeras palabras útiles
    stop = {
        "que",
        "como",
        "cual",
        "donde",
        "cuando",
        "porque",
        "para",
        "por",
        "una",
        "uno",
        "los",
        "las",
        "del",
        "con",
        "sobre",
        "hola",
        "ced",
        "me",
        "mi",
        "el",
        "la",
        "de",
        "en",
        "es",
        "un",
    }
    words = [w for w in re.findall(r"[a-z0-9áéíóúñ]{3,}", norm) if w not in stop]
    return " ".join(words[:5])[:80]


def extract_updates_from_utterance(
    text: str,
    *,
    tier: str,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Heurísticas baratas (sin LLM) para actualizar campos permitidos."""
    q = (text or "").strip()
    if len(q) < 4:
        return {}
    allowed = set(fields_for_tier(tier))
    patch: dict[str, Any] = {}
    existing = existing or {}

    if "display_name" in allowed:
        m = _NAME.search(q)
        if m:
            name = m.group(1).strip()
            if len(name) >= 2:
                patch["display_name"] = name[:80]

    if "business_niche" in allowed:
        m = _NICHE.search(q)
        if m:
            niche = re.sub(r"\s+", " ", m.group(1)).strip(" .,")
            if len(niche) >= 3:
                patch["business_niche"] = niche[:120]

    if "plan_interest" in allowed:
        m = _PLAN_INTEREST.search(q)
        if m:
            patch["plan_interest"] = m.group(1).strip()[:80]

    if "preferred_tone" in allowed:
        m = _TONE.search(q)
        if m:
            patch["preferred_tone"] = m.group(0).strip()[:120]

    if "last_topic" in allowed and len(q) >= 18:
        # No guardar saludos como tema
        if not re.match(r"(?is)^(hola|hi|hey|buenas|gracias|ok|vale)[\s.!?]*$", q):
            patch["last_topic"] = q[:MAX_TOPIC_LEN]

    if "objections" in allowed and _OBJECTION.search(q):
        objs = list(existing.get("objections") or [])
        snippet = q[:100]
        if snippet not in objs:
            objs.append(snippet)
        patch["objections"] = objs[-MAX_OBJECTIONS:]

    if "tech_decisions" in allowed and _TECH_DECISION.search(q):
        decisions = list(existing.get("tech_decisions") or [])
        snippet = re.sub(r"\s+", " ", q)[:140]
        if snippet not in decisions:
            decisions.append(snippet)
        patch["tech_decisions"] = decisions[-MAX_TECH:]

    if "speaking_style_notes" in allowed:
        # Acumula pistas cortas de instrucción ("más corto", "sé directo")
        if re.search(r"(?is)\b(?:m[aá]s\s+corto|s[eé]\s+directo|sin\s+rodeos|en\s+lista)\b", q):
            prev = str(existing.get("speaking_style_notes") or "").strip()
            note = q[:120]
            if note and note not in prev:
                patch["speaking_style_notes"] = (
                    f"{prev}; {note}".strip("; ")[:MAX_STYLE_LEN]
                    if prev
                    else note
                )

    return patch


def _maybe_flag_hot_lead(
    user_id: str,
    row: dict[str, Any],
    *,
    text: str,
) -> dict[str, Any]:
    """Lead caliente → aviso al foro admin (sin revisión manual)."""
    patch: dict[str, Any] = {}
    price_count = int(row.get("price_ask_count") or 0)
    if _PRICE.search(text or ""):
        price_count += 1
        patch["price_ask_count"] = price_count

    hits = dict(row.get("topic_hits") or {})
    key = _topic_key(text or "")
    topic_count = 0
    if key:
        topic_count = int(hits.get(key) or 0) + 1
        hits[key] = topic_count
        # Limitar tamaño del jsonb
        if len(hits) > 40:
            hits = dict(sorted(hits.items(), key=lambda kv: kv[1], reverse=True)[:30])
        patch["topic_hits"] = hits

    already = bool(row.get("hot_lead_flagged_at"))
    is_hot = (price_count >= HOT_PRICE_ASKS) or (topic_count >= HOT_TOPIC_HITS)
    if is_hot and not already:
        patch["hot_lead_flagged_at"] = _now_iso()
        try:
            from app.services.insight_questions import capture_insight_question

            capture_insight_question(
                user_id,
                text or "Lead caliente detectado",
                channel="other",
                force=True,
                tags_extra=["hot_lead", "business"],
                priority="high",
                metadata={
                    "alert": "hot_lead",
                    "price_ask_count": price_count,
                    "topic_key": key,
                    "topic_hits": topic_count,
                    "auto": True,
                },
            )
            # Fuerza tags high vía metadata + pregunta con keywords de negocio
            logger.info(
                "[USER_MEMORY] hot_lead flagged user=%s price=%s topic=%s",
                user_id[:8],
                price_count,
                key,
            )
        except Exception:  # noqa: BLE001
            logger.exception("[USER_MEMORY] hot_lead notify failed")
    return patch


def _maybe_flag_cooling(user_id: str, row: dict[str, Any]) -> dict[str, Any]:
    """Cliente enfriándose: antes activo, varios días sin responder."""
    last_raw = row.get("last_conversation_at")
    if not last_raw:
        return {}
    try:
        last = datetime.fromisoformat(str(last_raw).replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - last.astimezone(timezone.utc)).days
    except Exception:  # noqa: BLE001
        return {}

    patch: dict[str, Any] = {"cooling_days": days}
    already = bool(row.get("cooling_flagged_at"))
    if days >= COOLING_DAYS and not already:
        patch["cooling_flagged_at"] = _now_iso()
        try:
            from app.services.insight_questions import capture_insight_question

            topic = str(row.get("last_topic") or "sin tema")[:120]
            capture_insight_question(
                user_id,
                f"Cliente enfriándose (~{days} días sin responder). Último tema: {topic}",
                channel="other",
                force=True,
                tags_extra=["cooling", "business"],
                priority="high",
                metadata={
                    "alert": "cooling",
                    "days": days,
                    "last_topic": topic,
                    "auto": True,
                },
            )
            logger.info(
                "[USER_MEMORY] cooling flagged user=%s days=%s",
                user_id[:8],
                days,
            )
        except Exception:  # noqa: BLE001
            logger.exception("[USER_MEMORY] cooling notify failed")
    elif days < COOLING_DAYS and already:
        # Volvió a escribir: limpia bandera de enfriamiento
        patch["cooling_flagged_at"] = None
        patch["cooling_days"] = 0
    return patch


def touch_and_learn(
    user_id: str,
    user_text: str,
    *,
    channel: str = "chat",
) -> dict[str, Any] | None:
    """Actualiza memoria tras un turno del cliente. Best-effort, sin LLM."""
    uid = (user_id or "").strip()
    if not uid:
        return None
    del channel  # reservado para telemetría futura
    try:
        tier = resolve_memory_tier(uid)
        existing = get_user_memory(uid) or {}
        # Detectar enfriamiento ANTES de tocar last_conversation_at
        cooling_patch = _maybe_flag_cooling(uid, existing)
        extract = extract_updates_from_utterance(
            user_text, tier=tier, existing=existing
        )
        hot_patch = _maybe_flag_hot_lead(uid, {**existing, **extract}, text=user_text)
        patch: dict[str, Any] = {
            "last_conversation_at": _now_iso(),
            **cooling_patch,
            **extract,
            **hot_patch,
        }
        # Si acaba de volver, no dejes cooling_days alto
        if existing.get("cooling_flagged_at") and patch.get("cooling_flagged_at") is None:
            patch["cooling_days"] = 0
        return _upsert(uid, patch)
    except Exception:  # noqa: BLE001
        logger.exception("[USER_MEMORY] touch_and_learn failed user=%s", uid[:8])
        return None


def append_client_memory_to_prompt(system: str, user_id: str | None) -> str:
    """Helper: añade el bloque corto al system prompt si hay datos."""
    if not user_id:
        return system
    try:
        block = format_memory_prompt_block(user_id)
    except Exception:  # noqa: BLE001
        return system
    if not block:
        return system
    base = (system or "").rstrip()
    return f"{base}\n\n{block}" if base else block
