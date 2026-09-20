"""CED Shield — sella un hash + fecha. El contenido no sale de CED."""

from __future__ import annotations

import re
import uuid
from typing import Any

from app.services.ced_shield.gate import ced_shield_enabled
from app.services.ced_shield.hashing import (
    normalize_content_sha256,
    on_chain_payload,
    sha256_hex,
)
from app.services.ced_shield.store import (
    add_seal,
    bind_wallet,
    get_wallet,
    list_seals,
    utc_now_iso,
)
from app.services.ced_shield.writer import submit_commitment

_WALLET_RE = re.compile(r"^[A-Za-z0-9:_-]{8,128}$")
_ALLOWED_KINDS = frozenset({"pdf", "session"})

COMPACT_CONTRACT_PATH = "apps/api/app/services/ced_shield/compact/CedShield.compact"
COMPACT_CIRCUIT = "recordSeal"
LACE_NETWORK = "preprod"
DEMO_PATH = "/shield"


def status_payload() -> dict[str, Any]:
    return {
        "enabled": ced_shield_enabled(),
        "module": "ced_shield",
        "on_chain": "hash+timestamp+wallet only",
        "never_on_chain": ["audio", "transcript", "pdf_bytes", "prompts"],
        "voice_untouched": True,
        "kill_switch": "CED_SHIELD_ENABLED",
        "compact_contract": COMPACT_CONTRACT_PATH,
        "compact_circuit": COMPACT_CIRCUIT,
        "lace_network": LACE_NETWORK,
        "demo_path": DEMO_PATH,
    }


def connect_wallet(user_id: str, address: str) -> dict[str, Any]:
    cleaned = (address or "").strip()
    if not _WALLET_RE.fullmatch(cleaned):
        return {
            "ok": False,
            "error": "Dirección de wallet no válida.",
        }
    bound = bind_wallet(user_id, cleaned)
    return {"ok": True, "wallet": bound}


def seal_artifact(
    user_id: str,
    *,
    kind: str,
    file_id: str = "",
    content_sha256: str = "",
    tx_ref: str = "",
) -> dict[str, Any]:
    """Crea el sello. Fallo de Midnight no afecta voz ni chat."""
    if not ced_shield_enabled():
        return {"ok": False, "code": "disabled", "error": "CED Shield está apagado."}

    kind_norm = (kind or "").strip().lower()
    if kind_norm not in _ALLOWED_KINDS:
        return {"ok": False, "error": "Usa kind=pdf o kind=session."}

    wallet = get_wallet(user_id)
    if not wallet:
        return {
            "ok": False,
            "code": "wallet_required",
            "error": "Conecte una wallet Midnight antes de sellar.",
        }

    digest = ""
    source_id = ""
    if kind_norm == "pdf":
        source_id = (file_id or "").strip()
        if not source_id:
            return {"ok": False, "error": "Falta file_id del PDF."}
        from app.services.pdf_report import get_pdf

        artifact = get_pdf(source_id, user_id)
        if not artifact:
            return {"ok": False, "error": "No encontré ese PDF."}
        pdf_bytes, _name = artifact
        digest = sha256_hex(pdf_bytes)
    else:
        source_id = "session"
        digest = normalize_content_sha256(content_sha256) or ""
        if not digest:
            return {
                "ok": False,
                "error": "Para session envíe content_sha256 (hash local). CED no sube el transcript.",
            }

    seal_id = uuid.uuid4().hex
    sealed_at = utc_now_iso()
    payload = on_chain_payload(
        content_sha256=digest,
        sealed_at=sealed_at,
        wallet=wallet,
        kind=kind_norm,
        seal_id=seal_id,
    )
    write = submit_commitment(payload)
    record = {
        "seal_id": seal_id,
        "kind": kind_norm,
        "source_id": source_id,
        "content_sha256": digest,
        "sealed_at": sealed_at,
        "wallet": wallet,
        "write_mode": write.get("mode"),
        "submitted": bool(write.get("submitted")),
        "tx_ref": write.get("tx_ref") or "",
        "write_ok": bool(write.get("ok")),
    }
    client_tx = (tx_ref or "").strip()[:128]
    if client_tx:
        record["tx_ref"] = client_tx
        record["tx_source"] = "lace_client"
    if write.get("error"):
        record["write_error"] = str(write["error"])
    add_seal(user_id, record)
    spoken = (
        "Sello creado. En la cadena solo va el hash y la fecha, no el contenido."
        if write.get("ok")
        else "Guardé el sello aquí. Midnight no respondió; voz y chat siguen igual."
    )
    return {"ok": True, "seal": record, "on_chain": payload, "spoken": spoken}


def wallet_and_seals(user_id: str) -> dict[str, Any]:
    return {
        "ok": True,
        "wallet": get_wallet(user_id),
        "seals": list_seals(user_id),
    }
