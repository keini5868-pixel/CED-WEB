"""PDF — generar y descargar reportes CED."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services.pdf_report import generate_pdf_bytes, get_pdf, store_pdf

router = APIRouter(prefix="/v1/pdf", tags=["pdf"])


class GeneratePdfBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=12000)


@router.post("/generate")
def post_generate_pdf(
    body: GeneratePdfBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    artifact = store_pdf(user_id=user_id, title=body.title.strip(), content=body.content.strip())
    return {
        "ok": True,
        "file_id": artifact.file_id,
        "filename": artifact.filename,
        "download_path": f"/v1/pdf/download/{artifact.file_id}",
    }


@router.get("/download/{file_id}")
def get_pdf_download(
    file_id: str,
    user_id: str = Depends(require_user_id),
) -> Response:
    row = get_pdf(file_id, user_id)
    if not row:
        raise HTTPException(status_code=404, detail="PDF no encontrado o expirado.")
    data, filename = row
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
