"""Generación de PDF para reportes CED."""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fpdf import FPDF

logger = logging.getLogger(__name__)

# Caché en memoria (L1) — Supabase es la fuente de verdad en producción.
_STORE: dict[str, tuple[bytes, str, datetime, str]] = {}
_USER_INDEX: dict[str, list[dict[str, str]]] = {}
_TTL = timedelta(hours=48)
_CED_PDF_PREFIX = "[CED_PDF]"


@dataclass(frozen=True)
class PdfArtifact:
    file_id: str
    filename: str
    title: str


def _sanitize_filename(title: str) -> str:
    base = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE).strip().replace(" ", "-")
    base = (base or "ced-report")[:60].lower()
    return f"{base}.pdf"


def _strip_markdown(text: str) -> str:
    out = text.strip()
    out = re.sub(r"```[\s\S]*?```", lambda m: m.group(0).strip("`").strip(), out)
    out = re.sub(r"`([^`]+)`", r"\1", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"\1", out)
    out = re.sub(r"\*([^*]+)\*", r"\1", out)
    out = re.sub(r"^#+\s*", "", out, flags=re.MULTILINE)
    out = re.sub(r"^\s*[-*]\s+", "• ", out, flags=re.MULTILINE)
    return out.strip()


def _latin1_safe(text: str) -> str:
    return text.encode("latin-1", "replace").decode("latin-1")


def generate_pdf_bytes(*, title: str, content: str) -> bytes:
    clean_title = _strip_markdown(title) or "Documento CED"
    clean_body = _strip_markdown(content)
    if not clean_body:
        clean_body = clean_title

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_margins(18, 18, 18)

    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 9, _latin1_safe(clean_title[:200]))
    pdf.ln(3)

    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(
        0,
        6,
        _latin1_safe(
            f"Generado por CED · Castillo Digital · {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        ),
    )
    pdf.ln(8)

    pdf.set_text_color(30, 30, 30)
    pdf.set_font("Helvetica", size=11)
    body = _latin1_safe(clean_body[:12000])
    for paragraph in body.split("\n"):
        line = paragraph.strip()
        if not line:
            pdf.ln(4)
            continue
        pdf.multi_cell(0, 6, line)
        pdf.ln(1)

    raw = pdf.output()
    return raw if isinstance(raw, (bytes, bytearray)) else str(raw).encode("latin-1", "replace")


def store_pdf(
    *,
    user_id: str,
    title: str,
    content: str,
    conversation_id: str | None = None,
) -> PdfArtifact:
    _purge_expired()
    file_id = uuid.uuid4().hex
    safe_title = _strip_markdown(title) or "Documento CED"
    safe_content = _strip_markdown(content) or safe_title
    filename = _sanitize_filename(safe_title)
    data = generate_pdf_bytes(title=safe_title, content=safe_content)
    now = datetime.now(timezone.utc)
    _STORE[file_id] = (data, filename, now, user_id)

    meta = {
        "file_id": file_id,
        "filename": filename,
        "title": safe_title,
        "conversation_id": conversation_id or "",
        "created_at": now.isoformat(),
    }
    _USER_INDEX.setdefault(user_id, []).insert(0, meta)
    _USER_INDEX[user_id] = _USER_INDEX[user_id][:100]

    try:
        from app.services import supabase_db

        supabase_db.save_pdf_artifact(
            file_id=file_id,
            user_id=user_id,
            title=safe_title,
            filename=filename,
            pdf_bytes=data,
            conversation_id=conversation_id,
        )
    except Exception:  # noqa: BLE001
        logger.warning("PDF guardado solo en memoria (Supabase no disponible)")

    if conversation_id:
        try:
            from app.services import supabase_db

            marker = json.dumps(
                {
                    "ced_type": "pdf",
                    "file_id": file_id,
                    "filename": filename,
                    "title": safe_title,
                },
                ensure_ascii=False,
            )
            supabase_db.append_message(
                conversation_id,
                user_id,
                "system",
                f"{_CED_PDF_PREFIX}{marker}",
            )
        except Exception:  # noqa: BLE001
            logger.warning("No se pudo registrar PDF en conversación %s", conversation_id)

    return PdfArtifact(file_id=file_id, filename=filename, title=safe_title)


def get_pdf(file_id: str, user_id: str) -> tuple[bytes, str] | None:
    _purge_expired()
    row = _STORE.get(file_id)
    if row:
        data, filename, _, owner = row
        if owner == user_id:
            return data, filename

    try:
        from app.services import supabase_db

        db_row = supabase_db.get_pdf_artifact(file_id, user_id)
        if db_row:
            data, filename, _title = db_row
            _STORE[file_id] = (data, filename, datetime.now(timezone.utc), user_id)
            return data, filename
    except Exception:  # noqa: BLE001
        logger.warning("Fallo lectura PDF desde Supabase file_id=%s", file_id)

    return None


def list_pdfs_for_user(user_id: str, *, limit: int = 40) -> list[dict[str, str]]:
    _purge_expired()
    try:
        from app.services import supabase_db

        db_rows = supabase_db.list_pdf_artifacts(user_id, limit=limit)
        if db_rows:
            return [
                {
                    "file_id": str(r.get("file_id") or ""),
                    "filename": str(r.get("filename") or "documento.pdf"),
                    "title": str(r.get("title") or "Documento CED"),
                    "conversation_id": str(r.get("conversation_id") or ""),
                    "created_at": str(r.get("created_at") or ""),
                }
                for r in db_rows
                if r.get("file_id")
            ]
    except Exception:  # noqa: BLE001
        pass
    return list(_USER_INDEX.get(user_id, [])[:limit])


def _purge_expired() -> None:
    now = datetime.now(timezone.utc)
    expired = [k for k, (_, _, ts, _) in _STORE.items() if now - ts > _TTL]
    for k in expired:
        row = _STORE.pop(k, None)
        if not row:
            continue
        _, _, _, owner = row
        pdfs = _USER_INDEX.get(owner)
        if pdfs:
            _USER_INDEX[owner] = [p for p in pdfs if p.get("file_id") != k]
