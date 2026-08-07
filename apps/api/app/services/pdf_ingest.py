"""Inbound PDF ingest — extract selectable text for chat / advanced / modules."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from io import BytesIO

logger = logging.getLogger(__name__)

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_EXTRACT_CHARS = 50_000
MIN_USEFUL_CHARS = 20


class PdfIngestError(Exception):
    """Error de lectura / validación de PDF entrante."""

    def __init__(self, message: str, *, http_status: int = 400):
        super().__init__(message)
        self.http_status = http_status


@dataclass(frozen=True)
class PdfExtractResult:
    text: str
    filename: str
    page_count: int
    truncated: bool
    char_count: int


def _safe_filename(name: str | None) -> str:
    raw = (name or "documento.pdf").strip() or "documento.pdf"
    raw = raw.replace("\\", "/").split("/")[-1]
    raw = re.sub(r"[^\w.\- ()áéíóúÁÉÍÓÚñÑ]+", "_", raw, flags=re.UNICODE)
    if not raw.lower().endswith(".pdf"):
        raw = f"{raw}.pdf"
    return raw[:120]


def validate_pdf_bytes(data: bytes, *, filename: str | None = None) -> None:
    if not data:
        raise PdfIngestError("El PDF está vacío.")
    if len(data) > MAX_PDF_BYTES:
        raise PdfIngestError(
            f"PDF demasiado grande. Máximo {MAX_PDF_BYTES // (1024 * 1024)} MB.",
        )
    head = data[:8]
    if not head.startswith(b"%PDF"):
        raise PdfIngestError(
            "El archivo no parece un PDF válido (falta la cabecera %PDF).",
        )
    _ = filename  # reserved for future MIME/name checks


def extract_pdf_text(
    data: bytes,
    *,
    filename: str | None = None,
    max_chars: int = MAX_EXTRACT_CHARS,
) -> PdfExtractResult:
    """Extrae texto seleccionable con pypdf. No OCR (escaneos → error claro)."""
    validate_pdf_bytes(data, filename=filename)
    safe_name = _safe_filename(filename)

    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise PdfIngestError(
            "Servicio de lectura PDF no disponible (falta pypdf).",
            http_status=503,
        ) from exc

    try:
        reader = PdfReader(BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        logger.warning("[PDF-INGEST] open failed: %s", exc)
        raise PdfIngestError(
            "No pude abrir ese PDF. Prueba con otro archivo o exporta de nuevo a PDF.",
        ) from exc

    if getattr(reader, "is_encrypted", False):
        try:
            ok = reader.decrypt("")
            if ok == 0:
                raise PdfIngestError(
                    "Este PDF está protegido con contraseña. Quita la protección e inténtalo de nuevo.",
                )
        except PdfIngestError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise PdfIngestError(
                "Este PDF está protegido o no se puede desencriptar.",
            ) from exc

    pages = list(reader.pages or [])
    page_count = len(pages)
    if page_count == 0:
        raise PdfIngestError("El PDF no tiene páginas legibles.")

    parts: list[str] = []
    total = 0
    truncated = False
    for i, page in enumerate(pages, start=1):
        try:
            raw = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            logger.warning("[PDF-INGEST] page %s extract failed name=%s", i, safe_name)
            raw = ""
        chunk = raw.strip()
        if not chunk:
            continue
        header = f"--- Página {i} ---\n"
        piece = f"{header}{chunk}"
        if total + len(piece) + 2 > max_chars:
            remain = max_chars - total - len(header) - 20
            if remain > 80:
                parts.append(f"{header}{chunk[:remain]}\n…[texto truncado]")
            truncated = True
            break
        parts.append(piece)
        total += len(piece) + 2

    text = "\n\n".join(parts).strip()
    # Contar solo el cuerpo (sin encabezados de página) para el umbral mínimo.
    body_only = re.sub(r"---\s*Página\s+\d+\s*---", "", text, flags=re.I)
    useful = re.sub(r"\s+", "", body_only)
    if len(useful) < MIN_USEFUL_CHARS:
        raise PdfIngestError(
            "Este PDF parece escaneado o sin texto seleccionable. "
            "Por ahora CED lee PDFs con texto copiable; si es escaneo, "
            "sube fotos claras de las páginas como imagen.",
        )

    return PdfExtractResult(
        text=text,
        filename=safe_name,
        page_count=page_count,
        truncated=truncated,
        char_count=len(text),
    )


def format_pdf_for_llm(
    extracted: PdfExtractResult,
    user_message: str,
) -> str:
    """Bloque de contexto para el turno LLM (no se guarda entero en historial)."""
    note = ""
    if extracted.truncated:
        note = (
            "\n(Nota: el documento es largo; solo se incluye el inicio "
            f"hasta ~{MAX_EXTRACT_CHARS} caracteres.)\n"
        )
    caption = (user_message or "").strip() or (
        "Analiza este documento PDF: resume lo importante, "
        "destaca puntos clave y responde con claridad."
    )
    return (
        f"[DOCUMENTO PDF ADJUNTO: {extracted.filename} — "
        f"{extracted.page_count} página(s)]\n"
        f"{note}"
        f"{extracted.text}\n"
        f"---\n"
        f"Pedido del usuario: {caption}"
    )


def user_display_for_pdf(filename: str, user_message: str) -> str:
    """Texto corto para historial / UI (sin volcar el PDF entero)."""
    name = _safe_filename(filename)
    caption = (user_message or "").strip()
    if caption:
        return f"📄 PDF: {name}\n{caption}"
    return f"📄 PDF: {name}"
