#!/usr/bin/env python3
"""Aplica solo 046_sentinel_privacy_subscriptions.sql."""

from __future__ import annotations

import os
import sys
from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parent.parent / "migrations" / "046_sentinel_privacy_subscriptions.sql"
)


def main() -> int:
    password = os.environ.get("SUPABASE_DB_PASSWORD", "").strip()
    project_ref = os.environ.get("SUPABASE_PROJECT_REF", "foscutjtuscqrduugklm")
    if not password:
        print("Define SUPABASE_DB_PASSWORD o pega el SQL en Supabase → SQL Editor:")
        print(MIGRATION)
        return 1
    try:
        import psycopg2
    except ImportError:
        print("pip install psycopg2-binary")
        return 1

    host = f"db.{project_ref}.supabase.co"
    dsn = (
        f"host={host} port=5432 dbname=postgres user=postgres "
        f"password={password} sslmode=require"
    )
    sql = MIGRATION.read_text(encoding="utf-8")
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()
    print(f"Aplicando {MIGRATION.name}…")
    cur.execute(sql)
    cur.close()
    conn.close()
    print("OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
