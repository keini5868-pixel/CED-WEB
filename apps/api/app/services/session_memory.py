"""Memoria sesión a sesión — resumen Gemini al cerrar y saludo con contexto al abrir."""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.services import supabase_db

logger = logging.getLogger(__name__)

DEFAULT_TEXT_GREETING = (
    "Hola, soy CED. Escríbeme aquí, dicta con el micrófono o adjunta una imagen. "
    "Puedo analizarla, generar variaciones o crear imágenes nuevas."
)

PUBLIC_SUMMARY_MAX = 320
INTERNAL_CONTEXT_MAX = 12_000
HISTORY_TURN_LIMIT = 120
_TRANSCRIPT_LINE_RE = re.compile(r"(?m)^(user|assistant|model):\s", re.I)

SESSION_MEMORY_INTERNAL_RULES = (
    "REGLAS DE MEMORIA DE SESIÓN (críticas):\n"
    "- Este bloque es SOLO contexto interno. NUNCA lo copies, leas ni muestres al usuario.\n"
    "- Si preguntan «¿recuerdas la conversación anterior?», «¿recuerdas cuando…?» o retoman un tema "
    "(lanzamiento, estrategia, plan, negocio): SÍ tienes contexto — responde con continuidad natural.\n"
    "- PROHIBIDO decir que no retienes historial ni que la memoria está «en desarrollo» si aquí hay datos relevantes.\n"
    "- Resume con tus palabras lo que acordaron; ofrece seguir donde lo dejaron."
)


def _client():
    return supabase_db._client()


def get_conversation_history(
    user_id: str,
    session_id: str,
    *,
    conversation_id: str | None = None,
) -> list[dict[str, str]]:
    """Turnos recientes de la sesión (user_conversations o voice_messages)."""
    sid = (session_id or "").strip()
    uid = (user_id or "").strip()
    if not sid or not uid:
        return []

    rows: list[dict[str, Any]] = []
    try:
        res = (
            _client()
            .table("user_conversations")
            .select("role, content, created_at")
            .eq("user_id", uid)
            .eq("session_id", sid)
            .order("created_at")
            .limit(HISTORY_TURN_LIMIT)
            .execute()
        )
        rows = list(res.data or [])
    except Exception:  # noqa: BLE001
        rows = []

    if not rows and conversation_id:
        try:
            msgs = supabase_db.get_conversation_messages(conversation_id, uid, limit=HISTORY_TURN_LIMIT)
            for msg in msgs:
                rows.append(
                    {
                        "role": msg.get("role") or "user",
                        "content": msg.get("content") or "",
                    }
                )
        except Exception:  # noqa: BLE001
            pass

    history: list[dict[str, str]] = []
    for row in rows:
        role = str(row.get("role") or "user").lower()
        if role in ("assistant", "model"):
            role = "assistant"
        elif role != "user":
            continue
        content = str(row.get("content") or "").strip()
        if content:
            history.append({"role": role, "content": content[:8000]})
    return history


def format_history(history: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for turn in history:
        role = turn.get("role") or "user"
        content = str(turn.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def looks_like_raw_transcript(text: str) -> bool:
    return bool(_TRANSCRIPT_LINE_RE.search(text or ""))


def sanitize_public_summary(text: str) -> str:
    """Texto seguro para saludo visible — nunca transcript user:/assistant:."""
    raw = (text or "").strip()
    if not raw:
        return ""
    if looks_like_raw_transcript(raw):
        user_msgs: list[str] = []
        for line in raw.splitlines():
            match = re.match(r"^user:\s*(.+)$", line.strip(), flags=re.I)
            if match:
                snippet = match.group(1).strip()
                if snippet and not looks_like_raw_transcript(snippet):
                    user_msgs.append(snippet)
        for snippet in user_msgs:
            if len(snippet) >= 8:
                return f"Conversamos sobre {snippet[:140].rstrip()}."
        if user_msgs:
            return f"Conversamos sobre {user_msgs[0][:80].rstrip()}."
        return ""
    cleaned = " ".join(raw.split())
    if len(cleaned) > PUBLIC_SUMMARY_MAX:
        return cleaned[: PUBLIC_SUMMARY_MAX - 1].rstrip() + "…"
    return cleaned


def _parse_summary_json(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None

    summary_short = str(
        parsed.get("summary_short") or parsed.get("text") or parsed.get("summary") or ""
    ).strip()
    internal_detail = str(
        parsed.get("internal_detail") or parsed.get("detail") or parsed.get("full_summary") or ""
    ).strip()
    topics_raw = parsed.get("topics") or []
    tasks_raw = parsed.get("tasks") or parsed.get("tasks_executed") or []
    projects_raw = parsed.get("projects") or []
    user_context = parsed.get("user_context") or {}
    topics = [str(t).strip() for t in topics_raw if str(t).strip()][:12]
    tasks = [str(t).strip() for t in tasks_raw if str(t).strip()][:16]
    projects = [str(t).strip() for t in projects_raw if str(t).strip()][:8]

    if not summary_short and not internal_detail and not topics and not tasks:
        return None

    summary_short = sanitize_public_summary(summary_short) or sanitize_public_summary(internal_detail[:280])
    if looks_like_raw_transcript(internal_detail):
        internal_detail = ""

    if isinstance(user_context, dict):
        user_context = {
            str(k).strip()[:80]: str(v).strip()[:500]
            for k, v in user_context.items()
            if str(k).strip() and str(v).strip()
        }
    else:
        user_context = {}

    return {
        "summary_short": summary_short or " ".join(topics)[:PUBLIC_SUMMARY_MAX] or "Conversación reciente con CED.",
        "internal_detail": internal_detail,
        "topics": topics,
        "tasks": tasks,
        "projects": projects,
        "user_context": user_context,
    }


def fallback_summary_from_history(history: list[dict[str, str]]) -> dict[str, Any]:
    """Resumen heurístico cuando Gemini falla — nunca guarda transcript crudo como summary público."""
    user_msgs = [str(t.get("content") or "").strip() for t in history if t.get("role") == "user"]
    user_msgs = [m for m in user_msgs if m]
    first_substantial = next((m for m in user_msgs if len(m) >= 12), user_msgs[0] if user_msgs else "")
    summary_short = (
        f"Conversamos sobre {first_substantial[:140].rstrip()}."
        if first_substantial
        else "Conversación breve con CED."
    )

    internal_lines: list[str] = ["Resumen reconstruido de la sesión anterior:"]
    for turn in history[-50:]:
        role_label = "Usuario" if turn.get("role") == "user" else "CED"
        content = str(turn.get("content") or "").strip()
        if content:
            internal_lines.append(f"- {role_label}: {content[:700]}")

    return {
        "summary_short": sanitize_public_summary(summary_short),
        "internal_detail": "\n".join(internal_lines)[:INTERNAL_CONTEXT_MAX],
        "topics": [],
        "tasks": [],
        "projects": [],
        "user_context": {},
    }


def _build_internal_context(summary: dict[str, Any]) -> str:
    parts: list[str] = []
    detail = str(summary.get("internal_detail") or "").strip()
    if detail and not looks_like_raw_transcript(detail):
        parts.append(detail)

    topics = summary.get("topics") or []
    tasks = summary.get("tasks") or []
    projects = summary.get("projects") or []
    user_context = summary.get("user_context") or {}

    if topics:
        parts.append("Temas principales: " + ", ".join(str(t) for t in topics[:12]))
    if projects:
        parts.append("Proyectos o iniciativas: " + ", ".join(str(p) for p in projects[:8]))
    if tasks:
        parts.append("Acciones realizadas o acordadas:\n" + "\n".join(f"- {t}" for t in tasks[:16]))
    if isinstance(user_context, dict) and user_context:
        ctx_lines = [f"- {k}: {v}" for k, v in list(user_context.items())[:10]]
        parts.append("Contexto del usuario:\n" + "\n".join(ctx_lines))

    short = sanitize_public_summary(str(summary.get("summary_short") or ""))
    if short:
        parts.insert(0, f"Resumen breve: {short}")

    return "\n\n".join(parts).strip()[:INTERNAL_CONTEXT_MAX]


def gemini_summarize_session(history: list[dict[str, str]]) -> dict[str, Any] | None:
    """Genera memoria rica con Gemini (público corto + detalle interno)."""
    transcript = format_history(history)
    if not transcript.strip():
        return None

    settings = get_settings()
    api_key = settings.google_api_key.strip()
    if not api_key:
        return fallback_summary_from_history(history)

    prompt = f"""Analiza esta conversación entre usuario y CED (marketing, ventas, estrategia, negocio u otros temas).
Genera memoria RICA para continuidad en la próxima sesión.

Conversación:
{transcript[:24000]}

Responde SOLO JSON válido:
{{
  "summary_short": "1-2 oraciones naturales en español para saludar (SIN formato user:/assistant:, SIN copiar el transcript)",
  "internal_detail": "8-15 oraciones detalladas: temas, decisiones, público ideal, soluciones, planes, estrategias, lanzamientos, pendientes y acuerdos",
  "topics": ["tema1", "tema2"],
  "tasks": ["acción concreta acordada o ejecutada"],
  "projects": ["proyecto o iniciativa mencionada"],
  "user_context": {{"publico": "...", "negocio": "...", "objetivo": "..."}}
}}"""
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        model = settings.gemini_voice_model.strip() or "gemini-2.5-flash"
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=2200,
                response_mime_type="application/json",
            ),
        )
        parsed = _parse_summary_json(response.text or "")
        if parsed:
            if not parsed.get("internal_detail"):
                parsed["internal_detail"] = _build_internal_context(parsed)
            return parsed
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SESSION_MEM] gemini summarize failed: %s", exc)

    return fallback_summary_from_history(history)


def save_session_memory(
    *,
    user_id: str,
    session_id: str,
    conversation_id: str | None = None,
) -> None:
    """Persiste resumen de sesión en Supabase (sesiones con al menos 2 turnos)."""
    uid = (user_id or "").strip()
    sid = (session_id or "").strip()
    if not uid or not sid:
        return

    history = get_conversation_history(uid, sid, conversation_id=conversation_id)
    if len(history) < 2:
        logger.info("[SESSION_MEM] skip short session user=%s session=%s", uid[:8], sid[:12])
        return

    summary = gemini_summarize_session(history)
    if not summary:
        return

    public_summary = sanitize_public_summary(str(summary.get("summary_short") or ""))
    if not public_summary:
        public_summary = "Conversación reciente con CED."

    internal_context = _build_internal_context(summary)
    if not internal_context:
        internal_context = fallback_summary_from_history(history)["internal_detail"]

    row: dict[str, Any] = {
        "user_id": uid,
        "session_id": sid,
        "summary": public_summary[:6000],
        "topics": summary.get("topics") or [],
        "tasks_executed": summary.get("tasks") or [],
        "internal_context": internal_context[:INTERNAL_CONTEXT_MAX],
        "projects": summary.get("projects") or [],
        "user_context": summary.get("user_context") or {},
    }
    try:
        _client().table("session_memories").upsert(row, on_conflict="session_id").execute()
        logger.info(
            "[SESSION_MEM] saved user=%s session=%s topics=%s tasks=%s internal_chars=%s",
            uid[:8],
            sid[:12],
            len(row["topics"]),
            len(row["tasks_executed"]),
            len(row["internal_context"]),
        )
    except Exception as exc:  # noqa: BLE001
        if "internal_context" in str(exc).lower():
            legacy_row = {
                "user_id": uid,
                "session_id": sid,
                "summary": public_summary[:6000],
                "topics": row["topics"],
                "tasks_executed": row["tasks_executed"],
            }
            try:
                _client().table("session_memories").upsert(legacy_row, on_conflict="session_id").execute()
                logger.warning("[SESSION_MEM] saved legacy row (run migration 017 for internal_context)")
            except Exception as exc2:  # noqa: BLE001
                logger.warning("[SESSION_MEM] save failed: %s", exc2)
        else:
            logger.warning("[SESSION_MEM] save failed: %s", exc)


def save_session_memory_async(
    *,
    user_id: str,
    session_id: str,
    conversation_id: str | None = None,
) -> None:
    def _run() -> None:
        save_session_memory(
            user_id=user_id,
            session_id=session_id,
            conversation_id=conversation_id,
        )

    threading.Thread(target=_run, daemon=True).start()


def calculate_days_ago(created_at: str | datetime | None) -> str:
    if not created_at:
        return "poco tiempo"
    try:
        if isinstance(created_at, datetime):
            created = created_at
        else:
            created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - created.astimezone(timezone.utc)
        days = delta.days
        if days <= 0:
            hours = int(delta.total_seconds() // 3600)
            if hours <= 1:
                return "hace un momento"
            return f"hace {hours} horas"
        if days == 1:
            return "ayer"
        if days < 7:
            return f"hace {days} días"
        weeks = days // 7
        if weeks == 1:
            return "hace una semana"
        return f"hace {weeks} semanas"
    except Exception:  # noqa: BLE001
        return "recientemente"


def get_last_session_memory(user_id: str) -> dict[str, Any] | None:
    uid = (user_id or "").strip()
    if not uid:
        return None
    try:
        res = (
            _client()
            .table("session_memories")
            .select(
                "summary, topics, tasks_executed, created_at, session_id, "
                "internal_context, projects, user_context"
            )
            .eq("user_id", uid)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as exc:  # noqa: BLE001
        if "internal_context" in str(exc).lower():
            try:
                res = (
                    _client()
                    .table("session_memories")
                    .select("summary, topics, tasks_executed, created_at, session_id")
                    .eq("user_id", uid)
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                )
                rows = res.data or []
                return rows[0] if rows else None
            except Exception as exc2:  # noqa: BLE001
                logger.warning("[SESSION_MEM] load failed: %s", exc2)
                return None
        logger.warning("[SESSION_MEM] load failed: %s", exc)
        return None


def get_session_memory_context(user_id: str) -> str:
    memory = get_last_session_memory(user_id)
    if not memory:
        return ""
    when = calculate_days_ago(memory.get("created_at"))
    topics = ", ".join(str(t) for t in (memory.get("topics") or [])[:8])
    tasks = ", ".join(str(t) for t in (memory.get("tasks_executed") or [])[:8])
    projects = ", ".join(str(t) for t in (memory.get("projects") or [])[:6])

    internal = str(memory.get("internal_context") or "").strip()
    if not internal or looks_like_raw_transcript(internal):
        internal = sanitize_public_summary(str(memory.get("summary") or ""))

    parts = [
        "# MEMORIA DE SESIÓN ANTERIOR (CONTEXTO INTERNO — NO LEER AL USUARIO)",
        f"Cuándo: {when}",
        internal[:INTERNAL_CONTEXT_MAX],
    ]
    if topics:
        parts.append(f"Temas: {topics}")
    if projects:
        parts.append(f"Proyectos: {projects}")
    if tasks:
        parts.append(f"Acciones: {tasks}")
    user_context = memory.get("user_context") or {}
    if isinstance(user_context, dict) and user_context:
        ctx = "; ".join(f"{k}: {v}" for k, v in list(user_context.items())[:8])
        parts.append(f"Datos del usuario: {ctx}")
    parts.append(SESSION_MEMORY_INTERNAL_RULES)
    return "\n".join(parts)


_WELCOME_SUMMARY_MAX = 140


def _friendly_topic_phrase(topics: list[str], summary: str = "") -> str:
    blob = f"{' '.join(topics)} {summary}".lower()
    if re.search(r"plan\s+semanal|estrategia\s+semanal", blob):
        if "lanzamiento" in blob and "ced" in blob:
            return "su plan semanal de estrategia para el lanzamiento de CED"
        return "su plan semanal de estrategia"
    if topics:
        return ", ".join(str(t).strip() for t in topics[:2] if str(t).strip())
    return ""


def humanize_session_summary_for_user(summary: str, topics: list[str] | None = None) -> str:
    """Convierte resumen interno (a veces en tercera persona) a lenguaje natural para el usuario."""
    topics = topics or []
    raw = sanitize_public_summary(summary)
    verbose_third_person = bool(raw and re.search(r"\bel usuario\b", raw, re.I) and len(raw) > 100)
    friendly = _friendly_topic_phrase(topics, raw)
    if friendly and (not raw or verbose_third_person):
        phrase = friendly
        blob = raw.lower()
        if "pdf" in blob:
            phrase += ", que le entregamos en PDF"
        if re.search(r"dolor de cabeza|mal de cabeza|cambiando el tema", blob):
            phrase += ", y después comentó que tenía dolor de cabeza"
        return f"hablamos de {phrase}"

    if not raw:
        if friendly:
            return f"hablamos de {friendly}"
        return ""

    t = raw
    t = re.sub(r"^El usuario solicitó\s+", "", t, flags=re.I)
    t = re.sub(r"^El usuario pidió\s+", "", t, flags=re.I)
    t = re.sub(r"^El usuario mencionó\s+", "también comentó que ", t, flags=re.I)
    t = re.sub(
        r"Posteriormente, el usuario mencionó\s+",
        "Después comentó que ",
        t,
        flags=re.I,
    )
    t = re.sub(r", el cual fue generado y entregado\.?", ", que le entregamos en PDF", t, flags=re.I)
    t = re.sub(r"\bel usuario\b", "usted", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip()

    if not re.match(r"^(hablamos|trabajamos|coment|mencion|después|su |el plan|la estrategia|también)", t, re.I):
        t = f"hablamos de {t[0].lower()}{t[1:]}" if t else t

    if len(t) > 240:
        t = t[:237].rsplit(" ", 1)[0] + "…"
    return t.rstrip(".")


def _extract_recall_query(text: str) -> str:
    t = (text or "").strip()
    for pat in (
        r"recuerdas\s+cuando\s+(.+?)[?.!]*$",
        r"te acuerdas\s+(?:de\s+|cuando\s+)?(.+?)[?.!]*$",
        r"de qu[eé] hablamos\s+(?:de\s+|sobre\s+)?(.+?)[?.!]*$",
    ):
        match = re.search(pat, t, re.I)
        if match:
            return match.group(1).strip()[:200]
    return ""


def _recall_from_current_history(history: list[dict[str, str]] | None) -> str | None:
    if not history or len(history) < 2:
        return None
    from app.services.chat_intents import is_casual_chat_interrupt, is_pdf_intent
    from app.services.deliverable_replies import is_deliverable_request

    parts: list[str] = []
    for row in history[-10:]:
        if str(row.get("role") or "").lower() not in ("user",):
            continue
        msg = str(row.get("content") or "").strip()
        if len(msg) < 12:
            continue
        if is_deliverable_request(msg) or is_pdf_intent(msg):
            if "plan semanal" in msg.lower() or "estrategia" in msg.lower():
                parts.append("su plan semanal de estrategia")
            else:
                parts.append("un plan o entregable que pidió")
        elif is_casual_chat_interrupt(msg):
            parts.append("algo personal, como un dolor de cabeza")
    if not parts:
        return None
    unique: list[str] = []
    for part in parts:
        if part not in unique:
            unique.append(part)
    return "Claro. En esta misma charla, " + " y ".join(unique[:2]) + "."


def build_conversation_recall_reply(
    user_id: str,
    text: str,
    *,
    channel: str = "text",
    history: list[dict[str, str]] | None = None,
) -> str:
    """Respuesta natural cuando preguntan por la conversación anterior — sin tool_code."""
    memory = get_last_session_memory(user_id)
    prefix = "Sí, señor." if channel == "voice" else "Claro."
    closing = (
        " ¿Desea retomarlo o hay algo nuevo?"
        if channel == "voice"
        else " ¿Quiere retomarlo o hay algo en lo que le ayude ahora?"
    )

    if memory:
        when = calculate_days_ago(memory.get("created_at"))
        topics = memory.get("topics") or []
        snippet = humanize_session_summary_for_user(str(memory.get("summary") or ""), topics)
        if snippet:
            when_label = when[0].upper() + when[1:] if when.startswith("hace") else when
            body = f"{prefix} {when_label}, {snippet.rstrip('.')}."
            return body + closing

    same_session = _recall_from_current_history(history)
    if same_session:
        return same_session + closing

    query = _extract_recall_query(text)
    from app.services.conversation_memory import format_recall_for_voice, recall_previous_conversations

    conv = recall_previous_conversations(user_id, query or text, days_back=30)
    if conv.get("ok") and conv.get("results"):
        spoken = format_recall_for_voice(conv)
        if spoken and "no encontré" not in spoken.lower():
            natural = spoken.replace("Recuerdo esto: ", "recuerdo que ", 1)
            return f"{prefix} {natural.rstrip('.')}.{closing}"

    from app.services.cognitive_memory import search_memory

    mem = search_memory(user_id, query or text, limit=3)
    items = mem.get("results") or []
    if items:
        bits = [f"{i.get('key', 'dato')}: {str(i.get('content') or '')[:120]}" for i in items[:2]]
        return f"{prefix} Recuerdo que {'; '.join(bits)}.{closing}"

    if channel == "voice":
        return "Aún no tengo una sesión anterior guardada con detalle, señor."
    return (
        "Todavía no tengo guardada una conversación anterior con detalle. "
        "Cuando cerremos esta charla, la recordaré la próxima vez."
    )


def build_memory_greeting(user_id: str) -> str | None:
    memory = get_last_session_memory(user_id)
    if not memory:
        return None

    when = calculate_days_ago(memory.get("created_at"))
    topics = memory.get("topics") or []
    snippet = humanize_session_summary_for_user(str(memory.get("summary") or ""), topics)
    if not snippet:
        topic_label = str(topics[0]).strip() if topics else "nuestro último tema"
        snippet = f"hablamos de {topic_label}"

    if len(snippet) > _WELCOME_SUMMARY_MAX:
        snippet = snippet[: _WELCOME_SUMMARY_MAX - 1].rsplit(" ", 1)[0] + "…"

    body = f"La última vez, {when}, {snippet.rstrip('.')}."
    return (
        f"Bienvenido de nuevo. {body} "
        "¿En qué te ayudo hoy? Puedo seguir con eso o lo que necesites."
    )


def build_text_chat_welcome(user_id: str) -> str:
    greeting = build_memory_greeting(user_id)
    return greeting or DEFAULT_TEXT_GREETING
