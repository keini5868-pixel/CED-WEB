"""Aplica migraciones 021 y 022 (finance_transactions) en Supabase."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

REF = os.environ.get("SUPABASE_PROJECT_REF", "foscutjtuscqrduugklm").strip()
MIGRATIONS = (
    Path(__file__).resolve().parent.parent / "migrations" / "021_finance_transactions.sql",
    Path(__file__).resolve().parent.parent / "migrations" / "022_finance_pending_payments.sql",
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


def main() -> int:
    conn = connect()
    try:
        for path in MIGRATIONS:
            sql = path.read_text(encoding="utf-8")
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
            print(f"OK: {path.name}")
    finally:
        conn.close()

    # Verificar tabla (import tardío — script puede ejecutarse fuera del paquete app).
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.services.finance_schema import finance_db_diagnostics

    diag = finance_db_diagnostics()
    print("finance_db_ready:", diag.get("ready"))
    if not diag.get("ready"):
        print("diag:", diag)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
