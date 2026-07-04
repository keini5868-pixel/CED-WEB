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
            .limit(80)
            .execute()
        )
        rows = list(res.data or [])
    except Exception:  # noqa: BLE001
        rows = []

    if not rows and conversation_id:
        try:
            msgs = supabase_db.get_conversation_messages(conversation_id, uid, limit=80)
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
    summary_text = str(parsed.get("text") or parsed.get("summary") or "").strip()
    topics_raw = parsed.get("topics") or []
    tasks_raw = parsed.get("tasks") or parsed.get("tasks_executed") or []
    topics = [str(t).strip() for t in topics_raw if str(t).strip()][:8]
    tasks = [str(t).strip() for t in tasks_raw if str(t).strip()][:12]
    if not summary_text and not topics and not tasks:
        return None
    return {
        "text": summary_text or " ".join(topics)[:600],
        "topics": topics,
        "tasks": tasks,
    }


def gemini_summarize_session(history: list[dict[str, str]]) -> dict[str, Any] | None:
    """Genera resumen estructurado con Gemini."""
    transcript = format_history(history)
    if not transcript.strip():
        return None

    settings = get_settings()
    api_key = settings.google_api_key.strip()
    if not api_key:
        return None

    prompt = f"""Resume esta conversación CED en máximo 3 oraciones en español.
Extrae temas principales y tareas ejecutadas (publicaciones, búsquedas, creativos, etc.).

Conversación:
{transcript[:12000]}

Responde SOLO JSON válido:
{{
  "text": "resumen breve",
  "topics": ["tema1", "tema2"],
  "tasks": ["publicó en Instagram", "buscó noticias"]
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
                max_output_tokens=700,
                response_mime_type="application/json",
            ),
        )
        parsed = _parse_summary_json(response.text or "")
        if parsed:
            return parsed
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SESSION_MEM] gemini summarize failed: %s", exc)

    return {
        "text": transcript[:600],
        "topics": [],
        "tasks": [],
    }


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

    row = {
        "user_id": uid,
        "session_id": sid,
        "summary": str(summary.get("text") or "")[:6000],
        "topics": summary.get("topics") or [],
        "tasks_executed": summary.get("tasks") or [],
    }
    try:
        _client().table("session_memories").upsert(row, on_conflict="session_id").execute()
        logger.info(
            "[SESSION_MEM] saved user=%s session=%s topics=%s tasks=%s",
            uid[:8],
            sid[:12],
            len(row["topics"]),
            len(row["tasks_executed"]),
        )
    except Exception as exc:  # noqa: BLE001
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
            .select("summary, topics, tasks_executed, created_at, session_id")
            .eq("user_id", uid)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SESSION_MEM] load failed: %s", exc)
        return None


def get_session_memory_context(user_id: str) -> str:
    memory = get_last_session_memory(user_id)
    if not memory:
        return ""
    when = calculate_days_ago(memory.get("created_at"))
    topics = ", ".join(str(t) for t in (memory.get("topics") or [])[:6])
    tasks = ", ".join(str(t) for t in (memory.get("tasks_executed") or [])[:6])
    summary = str(memory.get("summary") or "").strip()
    parts = [
        "MEMORIA DE SESIÓN ANTERIOR:",
        f"({when}) {summary}",
    ]
    if topics:
        parts.append(f"Temas: {topics}")
    if tasks:
        parts.append(f"Tareas realizadas: {tasks}")
    parts.append(
        "Usa este contexto para dar continuidad a la conversación. "
        "Si el usuario retoma un tema anterior, reconócelo naturalmente."
    )
    return "\n".join(parts)


def build_memory_greeting(user_id: str) -> str | None:
    memory = get_last_session_memory(user_id)
    if not memory:
        return None

    when = calculate_days_ago(memory.get("created_at"))
    topics = memory.get("topics") or []
    topic_label = str(topics[0]).strip() if topics else "nuestro último tema"
    summary = str(memory.get("summary") or "").strip()
    if len(summary) > 160:
        summary = summary[:157].rstrip() + "…"

    if summary:
        body = f"La última vez, {when}, hablamos de {topic_label}. {summary}"
    else:
        body = f"La última vez, {when}, hablamos de {topic_label}."
    return (
        f"Bienvenido de nuevo, señor. {body} "
        "¿Continuamos o hay algo nuevo en lo que pueda asistirle?"
    )


def build_text_chat_welcome(user_id: str) -> str:
    greeting = build_memory_greeting(user_id)
    return greeting or DEFAULT_TEXT_GREETING
