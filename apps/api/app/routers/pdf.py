"""PDF — generar, listar, descargar e ingest (lectura entrante)."""

from __future__ import annotations

import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.deps.plan_access import charge_pdf_from_wallet_if_needed, require_pdf_reports
from app.services.pdf_ingest import PdfIngestError, extract_pdf_text
from app.services.pdf_report import get_pdf, list_pdfs_for_user, store_pdf_with_timeout

router = APIRouter(prefix="/v1/pdf", tags=["pdf"])


class GeneratePdfBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=12000)
    conversation_id: str | None = None
    user_request: str | None = Field(default=None, max_length=4000)


@router.post("/generate")
def post_generate_pdf(
    body: GeneratePdfBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    included_in_plan = require_pdf_reports(user_id)
    user_request = (body.user_request or body.content or body.title).strip()
    try:
        artifact = store_pdf_with_timeout(
            user_id=user_id,
            title=body.title.strip(),
            content=body.content.strip(),
            conversation_id=body.conversation_id,
            user_request=user_request,
        )
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="No pude generar el PDF a tiempo. Intenta de nuevo.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    charge_pdf_from_wallet_if_needed(user_id, included_in_plan=included_in_plan)
    return {
        "ok": True,
        "file_id": artifact.file_id,
        "filename": artifact.filename,
        "title": artifact.title,
        "download_path": f"/v1/pdf/download/{artifact.file_id}",
    }


@router.get("/list")
def get_pdf_list(
    user_id: str = Depends(require_user_id),
    limit: int = Query(default=40, ge=1, le=100),
) -> dict:
    return {"pdfs": list_pdfs_for_user(user_id, limit=limit)}


@router.get("/download/{file_id}")
async def get_pdf_download(
    file_id: str,
    user_id: str = Depends(require_user_id),
) -> Response:
    safe_id = file_id.strip().lower()
    if not re.fullmatch(r"[a-f0-9]{32}", safe_id):
        raise HTTPException(status_code=400, detail="ID de PDF inválido.")
    row = get_pdf(safe_id, user_id)
    if not row:
        raise HTTPException(status_code=404, detail="PDF no encontrado o expirado.")
    data, filename = row
    payload = bytes(data) if isinstance(data, bytearray) else data
    if len(payload) < 100 or not payload.startswith(b"%PDF"):
        raise HTTPException(status_code=500, detail="El PDF está corrupto. Genera uno nuevo.")
    safe_name = re.sub(r"[^\w\s.-]", "", filename) or "documento-ced.pdf"
    ascii_name = safe_name.encode("ascii", "ignore").decode("ascii") or "documento-ced.pdf"
    quoted = quote(safe_name)
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quoted}'
            ),
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/ingest")
async def post_ingest_pdf(
    pdf: UploadFile = File(...),
    user_id: str = Depends(require_user_id),
) -> dict:
    """Lee un PDF entrante y devuelve texto extraído (sin generar reporte)."""
    _ = user_id
    try:
        data = await pdf.read()
        extracted = extract_pdf_text(data, filename=pdf.filename)
    except PdfIngestError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail="No pude leer ese PDF. Intenta de nuevo.",
        ) from exc
    return {
        "ok": True,
        "filename": extracted.filename,
        "page_count": extracted.page_count,
        "char_count": extracted.char_count,
        "truncated": extracted.truncated,
        "text": extracted.text,
    }
