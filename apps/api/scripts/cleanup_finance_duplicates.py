"""Elimina filas duplicadas en finance_transactions (mismo user, monto, descripción)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.supabase_db import _client  # noqa: E402


def main() -> int:
    client = _client()
    result = (
        client.table("finance_transactions")
        .select("id, user_id, amount, description, status, created_at")
        .order("created_at", desc=False)
        .execute()
    )
    rows = result.data or []
    print(f"Total filas: {len(rows)}")
    for row in rows:
        print(
            f"  {row.get('id')} user={str(row.get('user_id'))[:8]} "
            f"amt={row.get('amount')} status={row.get('status')} "
            f"desc={str(row.get('description') or '')[:60]!r}"
        )

    seen: dict[tuple[str, str, str, str], str] = {}
    to_delete: list[str] = []
    for row in rows:
        key = (
            str(row.get("user_id") or ""),
            str(row.get("amount") or ""),
            str(row.get("description") or "")[:200],
            str(row.get("status") or ""),
        )
        row_id = str(row.get("id") or "")
        if not row_id:
            continue
        if key in seen:
            to_delete.append(row_id)
            print(f"DUPLICADO -> borrar {row_id} (conservar {seen[key]})")
        else:
            seen[key] = row_id

    if not to_delete:
        print("Sin duplicados que borrar.")
        return 0

    for row_id in to_delete:
        client.table("finance_transactions").delete().eq("id", row_id).execute()
        print(f"Borrado: {row_id}")

    print(f"Listo. Eliminadas {len(to_delete)} fila(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
