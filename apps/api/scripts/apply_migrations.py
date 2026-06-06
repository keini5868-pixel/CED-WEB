#!/usr/bin/env python3
"""Aplica migraciones SQL vía conexión directa PostgreSQL (opcional)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"


def main() -> int:
    password = os.environ.get("SUPABASE_DB_PASSWORD", "").strip()
    project_ref = os.environ.get("SUPABASE_PROJECT_REF", "foscutjtuscqrduugklm")

    if not password:
        print("Define SUPABASE_DB_PASSWORD y vuelve a ejecutar.")
        print("O pega 001_initial_schema.sql en Supabase → SQL Editor.")
        return 1

    try:
        import psycopg2
    except ImportError:
        print("pip install psycopg2-binary  (o usa SQL Editor en Supabase)")
        return 1

    host = f"db.{project_ref}.supabase.co"
    dsn = (
        f"host={host} port=5432 dbname=postgres user=postgres "
        f"password={password} sslmode=require"
    )

    files = sorted(MIGRATIONS.glob("*.sql"))
    if not files:
        print("No hay archivos .sql en migrations/")
        return 1

    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()

    for path in files:
        print(f"Aplicando {path.name}…")
        sql = path.read_text(encoding="utf-8")
        cur.execute(sql)
        print(f"  OK: {path.name}")

    cur.close()
    conn.close()
    print("Migraciones aplicadas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
