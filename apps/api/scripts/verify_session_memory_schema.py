"""Verifica migración 017 en Supabase (session_memories)."""

from __future__ import annotations

from app.services import supabase_db


def main() -> int:
    client = supabase_db._client()
    try:
        res = (
            client.table("session_memories")
            .select("id, summary, internal_context, projects, user_context, topics, created_at")
            .order("created_at", desc=True)
            .limit(3)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: {exc}")
        return 1

    rows = res.data or []
    print("OK: columnas internal_context, projects, user_context existen y son legibles")
    print(f"Filas recientes en session_memories: {len(rows)}")

    for i, row in enumerate(rows, 1):
        summary = str(row.get("summary") or "")
        internal = str(row.get("internal_context") or "")
        bad = "user:" in summary.lower() or "assistant:" in summary.lower()
        print(
            f"  [{i}] created={str(row.get('created_at') or '')[:19]} "
            f"summary_len={len(summary)} internal_len={len(internal)} "
            f"projects={len(row.get('projects') or [])} "
            f"transcript_leak={'YES' if bad else 'no'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
