"""Generación de PDF para reportes CED."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO

from fpdf import FPDF

_STORE: dict[str, tuple[bytes, str, datetime]] = {}
_TTL = timedelta(hours=2)


@dataclass(frozen=True)
class PdfArtifact:
    file_id: str
    filename: str


def _sanitize_filename(title: str) -> str:
    base = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE).strip().replace(" ", "-")
    base = (base or "ced-report")[:60].lower()
    return f"{base}.pdf"


def _latin1_safe(text: str) -> str:
    return text.encode("latin-1", "replace").decode("latin-1")


def generate_pdf_bytes(*, title: str, content: str) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_margins(18, 18, 18)

    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 9, _latin1_safe(title[:200]))
    pdf.ln(3)

    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6, _latin1_safe(f"Generado por CED · {datetime.now().strftime('%d/%m/%Y %H:%M')}"))
    pdf.ln(8)

    pdf.set_text_color(30, 30, 30)
    pdf.set_font("Helvetica", size=11)
    body = _latin1_safe(content.strip()[:12000])
    for paragraph in body.split("\n"):
        line = paragraph.strip()
        if not line:
            pdf.ln(4)
            continue
        pdf.multi_cell(0, 6, line)
        pdf.ln(1)

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()


def store_pdf(*, user_id: str, title: str, content: str) -> PdfArtifact:
    _purge_expired()
    file_id = uuid.uuid4().hex
    filename = _sanitize_filename(title)
    data = generate_pdf_bytes(title=title, content=content)
    _STORE[file_id] = (data, filename, datetime.now(timezone.utc))
    return PdfArtifact(file_id=file_id, filename=filename)


def get_pdf(file_id: str, user_id: str) -> tuple[bytes, str] | None:
    _purge_expired()
    row = _STORE.get(file_id)
    if not row:
        return None
    data, filename, _ = row
    return data, filename


def _purge_expired() -> None:
    now = datetime.now(timezone.utc)
    expired = [k for k, (_, _, ts) in _STORE.items() if now - ts > _TTL]
    for k in expired:
        _STORE.pop(k, None)
