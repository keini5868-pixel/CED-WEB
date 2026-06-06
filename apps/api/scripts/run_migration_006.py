"""Ejecuta migración 006 contra Supabase Postgres."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

REF = "foscutjtuscqrduugklm"
MIGRATION = (
    Path(__file__).resolve().parent.parent / "migrations" / "006_admin_user_management.sql"
)


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
    sql = MIGRATION.read_text(encoding="utf-8")
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        print("006_admin_user_management.sql OK")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
