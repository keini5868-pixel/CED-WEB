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


def test_recent_tables_are_service_role_only():
    """Tablas nuevas: RLS on + deny-all (solo API con service_role)."""
    root = Path(__file__).resolve().parents[1] / "migrations"
    files = {
        "ced_insight_questions": "028_insight_questions_and_fitline_engagement.sql",
        "ced_fitline_engagement": "028_insight_questions_and_fitline_engagement.sql",
        "users_referrals": "031_users_referrals.sql",
        "referral_activity_events": "031_users_referrals.sql",
        "pm_structure_partners": "033_pm_structure_partners.sql",
        "video_edit_token_balances": "025_video_edit_tokens.sql",
        "video_edit_token_ledger": "025_video_edit_tokens.sql",
        "video_edit_jobs": "025_video_edit_tokens.sql",
        "fitline_action_plans": "027_fitline_action_plans.sql",
    }
    for table, filename in files.items():
        sql = (root / filename).read_text(encoding="utf-8")
        assert re.search(
            rf"alter table public\.{table} enable row level security",
            sql,
            re.I,
        ), f"RLS missing for {table}"
        assert re.search(
            rf"create policy .* on public\.{table}\s+for all using \(false\)",
            sql,
            re.I | re.S,
        ), f"deny-all missing for {table}"


def test_rls_migration_profiles_allows_own_select():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "profiles_select_own" in sql
    assert "auth.uid() = id" in sql
