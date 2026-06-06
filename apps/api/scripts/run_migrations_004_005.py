"""Ejecuta migraciones 004 y 005 contra Supabase Postgres."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg2

REF = "foscutjtuscqrduugklm"
MIGRATIONS = [
    Path(__file__).resolve().parent.parent / "migrations" / "004_hud_phase3c.sql",
    Path(__file__).resolve().parent.parent / "migrations" / "005_cognitive_memory.sql",
]


def connect():
    password = os.environ.get("SUPABASE_DB_PASSWORD", "").strip()
    if not password:
        raise RuntimeError("SUPABASE_DB_PASSWORD no configurada en apps/api/.env")
    hosts = [f"db.{REF}.supabase.co", f"aws-0-us-east-1.pooler.supabase.com"]
    users = ["postgres", f"postgres.{REF}"]
    ports = [5432, 6543]
    last_err = None
    for host in hosts:
        for user in users:
            for port in ports:
                try:
                    return psycopg2.connect(
                        host=host,
                        port=port,
                        dbname="postgres",
                        user=user,
                        password=password,
                        sslmode="require",
                        connect_timeout=20,
                    )
                except Exception as exc:  # noqa: BLE001
                    last_err = exc
    raise RuntimeError(f"No DB connection: {last_err}")


def main() -> None:
    conn = connect()
    print("Connected to Supabase Postgres")
    cur = conn.cursor()
    for path in MIGRATIONS:
        sql = path.read_text(encoding="utf-8")
        cur.execute(sql)
        conn.commit()
        print(f"Applied {path.name}")
    cur.execute(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name IN (
            'meta_connections', 'detected_leads',
            'ced_activity_logs', 'cognitive_memories'
          )
        ORDER BY 1
        """
    )
    print("Tables:", [r[0] for r in cur.fetchall()])
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'profiles'
          AND column_name IN ('niche', 'prospection_enabled', 'news_keywords')
        ORDER BY 1
        """
    )
    print("Profile columns:", [r[0] for r in cur.fetchall()])
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
