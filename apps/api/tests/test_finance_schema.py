"""Tests — diagnóstico esquema finanzas."""

from __future__ import annotations

from unittest.mock import patch

from app.services.finance_schema import finance_db_diagnostics, finance_db_ready


def test_finance_db_ready_true_when_probe_ok():
    with patch(
        "app.services.finance_schema._probe_finance_table",
        return_value=(True, None),
    ):
        assert finance_db_ready(force_refresh=True) is True


def test_finance_db_ready_false_when_table_missing():
    with patch(
        "app.services.finance_schema._probe_finance_table",
        return_value=(
            False,
            "Tabla public.finance_transactions ausente.",
        ),
    ):
        assert finance_db_ready(force_refresh=True) is False
        diag = finance_db_diagnostics()
        assert diag["ready"] is False
