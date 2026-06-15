"""Memoria persistente — mensajes, resúmenes de sesión y memoria a largo plazo."""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import get_settings
from app.services import supabase_db
from app.services.cognitive_memory import save_memory

logger = logging.getLogger(__name__)

MAX_CONTENT = 8000
MAX_CONTEXT_CHARS = 2200
ROLE_MAP = {"model": "assistant", "assistant": "assistant", "user": "user", "system": "system"}


def _client():
    return supabase_db._client()


def _normalize_role(role: str) -> str:
    r = (role or "user").strip().lower()
    return ROLE_MAP.get(r, "user")


def _generate_embedding(text: str) -> list[float] | None:
    settings = get_settings()
    api_key = settings.openai_api_key.strip()
    topic = (text or "").strip()[:8000]
    if not api_key or not topic:
        return None
    try:
        with httpx.Client(timeout=20.0) as client:
            res = client.post(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": "text-embedding-3-small", "input": topic},
            )
            if res.status_code >= 400:
                return None
            data = res.json()
            items = data.get("data") or []
            if not items:
                return None
            emb = items[0].get("embedding")
            return emb if isinstance(emb, list) else None
    except Exception:  # noqa: BLE001
        return None


def save_message(
    *,
    user_id: str,
    session_id: str,
    channel: str,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    body = (content or "").strip()[:MAX_CONTENT]
    sid = (session_id or "").strip()
    if not body or not sid:
        return
    ch = channel if channel in ("voice", "text", "mixed") else "mixed"
    norm_role = _normalize_role(role)
    row: dict[str, Any] = {
        "user_id": user_id,
        "session_id": sid,
        "channel": ch,
        "role": norm_role,
        "content": body,
        "metadata": metadata or {},
    }
    embedding = _generate_embedding(body)
    if embedding:
        row["embedding"] = embedding
    try:
        _client().table("user_conversations").insert(row).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[CONV_MEM] save_message failed: %s", exc)


def save_long_term_memory(
    user_id: str,
    *,
    category: str,
    key: str,
    value: str,
    importance: int = 5,
    source_session_id: str | None = None,
) -> dict[str, Any]:
    mem_key = (key or "").strip()[:120]
    body = (value or "").strip()[:4000]
    cat = (category or "fact").strip()[:40]
    imp = max(1, min(10, int(importance or 5)))
    if not mem_key or not body:
        return {"ok": False, "error": "Clave y valor son obligatorios"}

    now = datetime.now(timezone.utc).isoformat()
    row: dict[str, Any] = {
        "user_id": user_id,
        "category": cat,
        "mem_key": mem_key,
        "value": body,
        "importance": imp,
        "updated_at": now,
        "last_accessed_at": now,
    }
    if source_session_id:
        row["source_session_id"] = source_session_id
    embedding = _generate_embedding(f"{cat} {mem_key}: {body}")
    if embedding:
        row["embedding"] = embedding

    try:
        _client().table("long_term_memory").upsert(
            row,
            on_conflict="user_id,mem_key",
        ).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[CONV_MEM] long_term save failed: %s", exc)
        return {
            "ok": False,
            "error": "Ejecute migración 013_persistent_memory.sql en Supabase",
        }

    save_memory(user_id, mem_key, body, category=cat)
    return {"ok": True, "key": mem_key, "category": cat}


def _safe_ilike(q: str) -> str:
    return re.sub(r"[%_\\]", "", (q or "").strip())


def recall_previous_conversations(
    user_id: str,
    query: str,
    *,
    days_back: int = 30,
) -> dict[str, Any]:
    q = _safe_ilike(query)
    since = (datetime.now(timezone.utc) - timedelta(days=max(1, min(days_back, 365)))).isoformat()
    hits: list[dict[str, Any]] = []

    try:
        client = _client()
        if q:
            msg_res = (
                client.table("user_conversations")
                .select("content, role, channel, created_at, session_id")
                .eq("user_id", user_id)
                .gte("created_at", since)
                .ilike("content", f"%{q}%")
                .order("created_at", desc=True)
                .limit(8)
                .execute()
            )
            for row in msg_res.data or []:
                hits.append(
                    {
                        "type": "message",
                        "content": str(row.get("content") or "")[:400],
                        "role": row.get("role"),
                        "channel": row.get("channel"),
                        "at": row.get("created_at"),
                    }
                )

            sum_res = (
                client.table("session_summaries")
                .select("summary, topics, key_facts, pending_actions, started_at")
                .eq("user_id", user_id)
                .gte("started_at", since)
                .ilike("summary", f"%{q}%")
                .order("started_at", desc=True)
                .limit(5)
                .execute()
            )
            for row in sum_res.data or []:
                hits.append(
                    {
                        "type": "session_summary",
                        "content": str(row.get("summary") or "")[:500],
                        "topics": row.get("topics") or [],
                        "pending_actions": row.get("pending_actions") or [],
                        "at": row.get("started_at"),
                    }
                )

            lt_res = (
                client.table("long_term_memory")
                .select("mem_key, value, category, importance, updated_at")
                .eq("user_id", user_id)
                .or_(f"value.ilike.%{q}%,mem_key.ilike.%{q}%")
                .order("importance", desc=True)
                .limit(6)
                .execute()
            )
            for row in lt_res.data or []:
                hits.append(
                    {
                        "type": "long_term",
                        "key": row.get("mem_key"),
                        "content": str(row.get("value") or "")[:300],
                        "category": row.get("category"),
                        "at": row.get("updated_at"),
                    }
                )
        else:
            sum_res = (
                client.table("session_summaries")
                .select("summary, topics, pending_actions, started_at")
                .eq("user_id", user_id)
                .order("started_at", desc=True)
                .limit(3)
                .execute()
            )
            for row in sum_res.data or []:
                hits.append(
                    {
                        "type": "session_summary",
                        "content": str(row.get("summary") or "")[:400],
                        "topics": row.get("topics") or [],
                        "pending_actions": row.get("pending_actions") or [],
                        "at": row.get("started_at"),
                    }
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[CONV_MEM] recall failed: %s", exc)
        from app.services.cognitive_memory import search_memory

        fallback = search_memory(user_id, query, limit=5)
        items = fallback.get("results") or []
        if items:
            return {
                "ok": True,
                "query": query,
                "results": [
                    {"type": "cognitive_memory", "key": i["key"], "content": i["content"]}
                    for i in items
                ],
                "source": "cognitive_fallback",
            }
        return {"ok": False, "error": "Memoria no disponible. Ejecute migración 013.", "results": []}

    return {"ok": True, "query": query, "results": hits[:12], "source": "persistent"}


def _get_recent_summaries(user_id: str, *, limit: int = 5) -> list[dict[str, Any]]:
    try:
        res = (
            _client()
            .table("session_summaries")
            .select("summary, topics, pending_actions, started_at, channel")
            .eq("user_id", user_id)
            .order("started_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception:  # noqa: BLE001
        return []


def _get_top_memories(user_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    try:
        res = (
            _client()
            .table("long_term_memory")
            .select("mem_key, value, category, importance, updated_at")
            .eq("user_id", user_id)
            .order("importance", desc=True)
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception:  # noqa: BLE001
        return []


def _get_pending_actions(user_id: str) -> list[str]:
    actions: list[str] = []
    for row in _get_recent_summaries(user_id, limit=8):
        for item in row.get("pending_actions") or []:
            text = str(item).strip()
            if text and text not in actions:
                actions.append(text)
        if len(actions) >= 8:
            break
    return actions[:8]


def load_user_context(user_id: str) -> str:
    """Fragmento para inyectar al iniciar sesión voz/chat."""
    summaries = _get_recent_summaries(user_id, limit=5)
    memories = _get_top_memories(user_id, limit=15)
    pending = _get_pending_actions(user_id)

    if not summaries and not memories and not pending:
        return ""

    parts: list[str] = ["# CONTEXTO DEL USUARIO (SESIONES ANTERIORES)"]

    if summaries:
        lines = []
        for s in summaries[:5]:
            when = str(s.get("started_at") or "")[:10]
            snippet = str(s.get("summary") or "")[:280]
            topics = ", ".join(str(t) for t in (s.get("topics") or [])[:4])
            line = f"- [{when}] {snippet}"
            if topics:
                line += f" (temas: {topics})"
            lines.append(line)
        parts.append("## ÚLTIMAS CONVERSACIONES\n" + "\n".join(lines))

    if memories:
        lines = [
            f"- [{m.get('category', 'fact')}] {m.get('mem_key')}: {str(m.get('value') or '')[:160]}"
            for m in memories[:15]
        ]
        parts.append("## DATOS IMPORTANTES\n" + "\n".join(lines))

    if pending:
        parts.append("## ACCIONES PENDIENTES\n" + "\n".join(f"- {p}" for p in pending))

    parts.append(
        "Usa este contexto solo cuando sea relevante. NO recites todo. Conecta con naturalidad."
    )
    text = "\n\n".join(parts)
    if len(text) > MAX_CONTEXT_CHARS:
        return text[: MAX_CONTEXT_CHARS - 24] + "\n… [contexto truncado]"
    return text


def format_recall_for_voice(data: dict[str, Any]) -> str:
    if not data.get("ok"):
        return str(data.get("error") or "No encontré conversaciones previas sobre eso.")
    results = data.get("results") or []
    if not results:
        return "No encontré nada en conversaciones anteriores sobre eso."
    lines: list[str] = []
    for hit in results[:4]:
        if hit.get("type") == "long_term":
            lines.append(f"{hit.get('key')}: {hit.get('content')}")
        else:
            lines.append(str(hit.get("content") or "")[:200])
    return "Recuerdo esto: " + ". ".join(lines)


def _summarize_with_claude(messages_text: str) -> dict[str, Any] | None:
    settings = get_settings()
    key = settings.anthropic_api_key.strip()
    if not key or not messages_text.strip():
        return None
    prompt = f"""Analiza esta conversación CED y responde SOLO JSON válido:
{{
  "summary": "2-3 párrafos en español",
  "topics": ["tema1", "tema2"],
  "key_facts": {{"clave": "valor"}},
  "pending_actions": ["acción pendiente"]
}}

Conversación:
{messages_text[:12000]}"""
    try:
        with httpx.Client(timeout=60.0) as client:
            res = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 900,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            if res.status_code >= 400:
                return None
            blocks = res.json().get("content") or []
            text = ""
            for b in blocks:
                if isinstance(b, dict) and b.get("type") == "text":
                    text += str(b.get("text") or "")
            text = text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
    except Exception:  # noqa: BLE001
        return None


def generate_session_summary(
    *,
    user_id: str,
    session_id: str,
    channel: str = "voice",
    started_at: datetime | None = None,
    duration_minutes: float | None = None,
    conversation_id: str | None = None,
) -> None:
    sid = (session_id or "").strip()
    if not sid:
        return
    started = started_at or datetime.now(timezone.utc)
    lines: list[str] = []

    try:
        res = (
            _client()
            .table("user_conversations")
            .select("role, content, created_at")
            .eq("user_id", user_id)
            .eq("session_id", sid)
            .order("created_at")
            .limit(80)
            .execute()
        )
        for row in res.data or []:
            role = row.get("role") or "user"
            content = str(row.get("content") or "").strip()
            if content:
                lines.append(f"{role}: {content}")
    except Exception:  # noqa: BLE001
        pass

    if not lines and conversation_id:
        try:
            msgs = supabase_db.get_conversation_messages(conversation_id, user_id, limit=80)
            for m in msgs:
                content = str(m.get("content") or "").strip()
                if content:
                    lines.append(f"{m.get('role', 'user')}: {content}")
        except Exception:  # noqa: BLE001
            pass

    if not lines:
        return

    transcript = "\n".join(lines)[-12000:]
    summary_data = _summarize_with_claude(transcript)
    if not summary_data:
        summary_data = {
            "summary": transcript[:800],
            "topics": [],
            "key_facts": {},
            "pending_actions": [],
        }

    now = datetime.now(timezone.utc)
    row = {
        "user_id": user_id,
        "session_id": sid,
        "summary": str(summary_data.get("summary") or transcript[:600])[:6000],
        "topics": summary_data.get("topics") or [],
        "key_facts": summary_data.get("key_facts") or {},
        "pending_actions": summary_data.get("pending_actions") or [],
        "channel": channel if channel in ("voice", "text", "mixed") else "mixed",
        "duration_minutes": duration_minutes,
        "started_at": started.isoformat(),
        "ended_at": now.isoformat(),
    }
    try:
        _client().table("session_summaries").upsert(row, on_conflict="session_id").execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[CONV_MEM] session summary save failed: %s", exc)
        return

    facts = summary_data.get("key_facts") or {}
    if isinstance(facts, dict):
        for k, v in list(facts.items())[:12]:
            key = str(k).strip()[:120]
            val = str(v).strip()[:4000]
            if key and val:
                save_long_term_memory(
                    user_id,
                    category="fact",
                    key=key,
                    value=val,
                    importance=6,
                    source_session_id=sid,
                )


def finalize_voice_session_async(
    *,
    user_id: str,
    session_id: str,
    conversation_id: str | None,
    started_at_epoch: float,
) -> None:
    def _run() -> None:
        duration = max(0.0, (__import__("time").time() - started_at_epoch) / 60.0)
        started = datetime.fromtimestamp(started_at_epoch, tz=timezone.utc)
        generate_session_summary(
            user_id=user_id,
            session_id=session_id,
            channel="voice",
            started_at=started,
            duration_minutes=round(duration, 2),
            conversation_id=conversation_id,
        )

    threading.Thread(target=_run, daemon=True).start()
