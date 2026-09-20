"""Tests — CED Shield aislado: hash, dry-run, kill-switch, sin contenido on-chain."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.services.ced_shield.gate import ced_shield_enabled, require_ced_shield
from app.services.ced_shield.hashing import on_chain_payload, sha256_hex
from app.services.ced_shield.intents import is_shield_seal_intent
from app.services.ced_shield.store import reset_for_tests
from app.services.ced_shield.writer import submit_commitment


@pytest.fixture(autouse=True)
def _clean_store():
    reset_for_tests()
    yield
    reset_for_tests()


def test_kill_switch_off_by_default():
    assert ced_shield_enabled() is False
    with pytest.raises(HTTPException) as exc:
        require_ced_shield()
    assert exc.value.status_code == 404


def test_on_chain_payload_has_no_content_fields():
    payload = on_chain_payload(
        content_sha256="a" * 64,
        sealed_at="2026-09-20T18:00:00Z",
        wallet="addr_test1qqexample",
        kind="pdf",
        seal_id="abc123",
    )
    blob = " ".join(payload.values())
    assert "content" not in payload
    assert "transcript" not in payload
    assert "presupuesto" not in blob.lower()
    assert payload["content_sha256"] == "a" * 64


def test_writer_rejects_content_keys():
    with pytest.raises(ValueError, match="contenido"):
        submit_commitment({"content": "secreto", "seal_id": "x"})


def test_writer_dry_run_when_no_url(monkeypatch):
    monkeypatch.setattr(
        "app.services.ced_shield.writer.get_settings",
        lambda: type("S", (), {"ced_shield_midnight_submit_url": ""})(),
    )
    out = submit_commitment(
        on_chain_payload(
            content_sha256="b" * 64,
            sealed_at="2026-09-20T18:00:00Z",
            wallet="addr1",
            kind="session",
            seal_id="seal1",
        )
    )
    assert out["ok"] is True
    assert out["mode"] == "dry_run"
    assert out["submitted"] is False


def test_seal_pdf_hashes_bytes_not_title(monkeypatch):
    from app.services.ced_shield import service as shield

    pdf_bytes = b"%PDF-1.4 secret-client-budget"
    monkeypatch.setattr(
        "app.services.ced_shield.service.ced_shield_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.pdf_report.get_pdf",
        lambda file_id, user_id: (pdf_bytes, "doc.pdf"),
    )
    monkeypatch.setattr(
        "app.services.ced_shield.writer.get_settings",
        lambda: type("S", (), {"ced_shield_midnight_submit_url": ""})(),
    )

    connected = shield.connect_wallet("user-1", "addr_test1shieldwallet")
    assert connected["ok"] is True
    result = shield.seal_artifact("user-1", kind="pdf", file_id="file-aa")
    assert result["ok"] is True
    assert result["seal"]["content_sha256"] == sha256_hex(pdf_bytes)
    assert "secret-client-budget" not in str(result["on_chain"])
    assert result["on_chain"]["kind"] == "pdf"


def test_seal_session_requires_client_hash(monkeypatch):
    from app.services.ced_shield import service as shield

    monkeypatch.setattr(
        "app.services.ced_shield.service.ced_shield_enabled",
        lambda: True,
    )
    shield.connect_wallet("user-1", "addr_test1shieldwallet")
    missing = shield.seal_artifact("user-1", kind="session")
    assert missing["ok"] is False
    ok = shield.seal_artifact("user-1", kind="session", content_sha256="c" * 64)
    assert ok["ok"] is True
    assert ok["on_chain"]["content_sha256"] == "c" * 64


def test_midnight_failure_does_not_raise(monkeypatch):
    from app.services.ced_shield import service as shield

    monkeypatch.setattr(
        "app.services.ced_shield.service.ced_shield_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.ced_shield.writer.get_settings",
        lambda: type("S", (), {"ced_shield_midnight_submit_url": "https://example.invalid/submit"})(),
    )
    monkeypatch.setattr(
        "app.services.ced_shield.writer.httpx.post",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError("down")),
    )
    shield.connect_wallet("user-1", "addr_test1shieldwallet")
    result = shield.seal_artifact("user-1", kind="session", content_sha256="d" * 64)
    assert result["ok"] is True
    assert result["seal"]["write_ok"] is False
    assert "siguen igual" in result["spoken"]


def test_seal_intent_not_generic_chat():
    assert is_shield_seal_intent("sella este pdf")
    assert is_shield_seal_intent("CED Shield")
    assert not is_shield_seal_intent("genera un pdf del presupuesto")
    assert not is_shield_seal_intent("hola ced")


def test_status_payload_points_to_compact_demo():
    from app.services.ced_shield.service import status_payload

    body = status_payload()
    assert body["enabled"] is False
    assert body["voice_untouched"] is True
    assert body["compact_circuit"] == "recordSeal"
    assert body["demo_path"] == "/shield"
    assert "CedShield.compact" in body["compact_contract"]
    assert body["lace_network"] == "preprod"


def test_compact_source_is_hash_only():
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[1]
        / "app/services/ced_shield/compact/CedShield.compact"
    )
    src = path.read_text(encoding="utf-8")
    assert "recordSeal" in src
    assert "pragma language_version 0.16" in src
    import re

    executable = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    executable = re.sub(r"//.*?$", "", executable, flags=re.M)
    lower = executable.lower()
    for banned in ("transcript", "pdf_bytes", "audio", "prompt", "tavily", "retell", "gemini"):
        assert banned not in lower


def test_status_http_ok_when_kill_switch_off():
    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app())
    res = client.get("/v1/shield/status")
    assert res.status_code == 200
    body = res.json()
    assert body["enabled"] is False
    assert body["voice_untouched"] is True


def test_wallet_404_when_kill_switch_off():
    from fastapi.testclient import TestClient

    from app.deps.auth import require_user_id
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[require_user_id] = lambda: "user-test"
    client = TestClient(app)
    res = client.post("/v1/shield/wallet", json={"address": "addr_test1shieldwallet"})
    assert res.status_code == 404


def test_seal_stores_client_tx_ref(monkeypatch):
    from app.services.ced_shield import service as shield

    monkeypatch.setattr(
        "app.services.ced_shield.service.ced_shield_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.ced_shield.writer.get_settings",
        lambda: type("S", (), {"ced_shield_midnight_submit_url": ""})(),
    )
    shield.connect_wallet("user-1", "addr_test1shieldwallet")
    result = shield.seal_artifact(
        "user-1",
        kind="session",
        content_sha256="e" * 64,
        tx_ref="lace:preview-1",
    )
    assert result["ok"] is True
    assert result["seal"]["tx_ref"] == "lace:preview-1"
    assert result["seal"]["tx_source"] == "lace_client"
    assert "e" * 64 == result["on_chain"]["content_sha256"]
