"""Tests — migración RLS 015 cubre todas las tablas public."""

from __future__ import annotations

import re
from pathlib import Path

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "015_enable_rls_all_public_tables.sql"

EXPECTED_TABLES = [
    "profiles",
    "subscriptions",
    "founding_registry",
    "usage_logs",
    "recharge_balances",
    "recharges",
    "transactions",
    "admin_audit_logs",
    "voice_conversations",
    "voice_messages",
    "meta_connections",
    "detected_leads",
    "ced_activity_logs",
    "cognitive_memories",
    "usage_limits",
    "internal_knowledge_articles",
    "ced_pdf_artifacts",
    "openai_usage_log",
    "generated_images",
    "user_conversations",
    "session_summaries",
    "long_term_memory",
    "support_conversations",
    "support_messages",
]

SERVICE_ONLY_TABLES = {
    "founding_registry",
    "admin_audit_logs",
    "meta_connections",
    "ced_pdf_artifacts",
    "internal_knowledge_articles",
    "support_conversations",
    "support_messages",
}


def test_rls_migration_enables_all_public_tables():
    sql = MIGRATION.read_text(encoding="utf-8")
    for table in EXPECTED_TABLES:
        assert re.search(
            rf"alter table public\.{table} enable row level security",
            sql,
            re.I,
        ), f"RLS not enabled for {table}"


def test_rls_migration_protects_sensitive_tables():
    sql = MIGRATION.read_text(encoding="utf-8")
    for table in SERVICE_ONLY_TABLES:
        assert f"public.{table}" in sql
        assert re.search(
            rf"create policy .* on public\.{table}\s+for all using \(false\)",
            sql,
            re.I | re.S,
        ), f"Missing deny-all policy for sensitive table {table}"


def test_rls_migration_profiles_allows_own_select():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "profiles_select_own" in sql
    assert "auth.uid() = id" in sql
