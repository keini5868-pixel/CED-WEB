"""Generación de PDF para reportes CED."""

from __future__ import annotations

import json
import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fpdf import FPDF

logger = logging.getLogger(__name__)

PDF_COMPOSE_TIMEOUT_SEC = 18.0
PDF_STORE_TIMEOUT_SEC = 20.0
PDF_MIN_BYTES = 120

# Caché en memoria (L1) — Supabase es la fuente de verdad en producción.
_STORE: dict[str, tuple[bytes, str, datetime, str]] = {}
_USER_INDEX: dict[str, list[dict[str, str]]] = {}
_TTL = timedelta(hours=48)
_CED_PDF_PREFIX = "[CED_PDF]"
_PDF_BODY_MAX_CHARS = 50_000
_PDF_COMPOSE_MIN_CHARS = 160
_PDF_COMPOSE_MODEL = "gemini-2.5-flash"


def normalize_pdf_fields(params: dict[str, Any]) -> tuple[str, str]:
    title = str(
        params.get("titulo") or params.get("title") or params.get("titulo_documento") or "Documento CED"
    ).strip()
    content = str(
        params.get("contenido")
        or params.get("content")
        or params.get("body")
        or params.get("texto")
        or ""
    ).strip()
    return title, content


def resolve_pdf_content(
    title: str,
    content: str,
    *,
    fallback_texts: list[str] | None = None,
) -> str:
    """Usa el cuerpo completo; si el modelo solo pasó el título, toma texto previo del chat."""
    safe_title = (title or "Documento CED").strip()
    body = (content or "").strip()
    min_body = max(80, len(safe_title) + 24)
    if body and len(body) >= min_body and body.lower() != safe_title.lower():
        return body[:_PDF_BODY_MAX_CHARS]
    if body and body.lower() != safe_title.lower() and len(body) > len(safe_title) + 8:
        return body[:_PDF_BODY_MAX_CHARS]
    for candidate in reversed(fallback_texts or []):
        text = (candidate or "").strip()
        if not text or text.lower() == safe_title.lower():
            continue
        if len(text) >= min_body or len(text) > len(safe_title) + 12:
            return text[:_PDF_BODY_MAX_CHARS]
    if body:
        return body[:_PDF_BODY_MAX_CHARS]
    return ""


def user_texts_from_messages(messages: list[dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    for row in messages:
        if str(row.get("role") or "") != "user":
            continue
        content = row.get("content")
        if isinstance(content, str) and content.strip():
            texts.append(content.strip())
    return texts


def pdf_content_needs_composition(
    title: str,
    body: str,
    *,
    user_request: str = "",
) -> bool:
    """True si el PDF solo repite la petición/título y hay que redactar contenido real."""
    t = (title or "").strip().lower()
    b = (body or "").strip().lower()
    if not b:
        return True
    if b == t:
        return True
    if len(b) < _PDF_COMPOSE_MIN_CHARS:
        return True
    req = (user_request or "").strip().lower()
    if req and len(b) <= len(req) + 20 and (b in req or req in b):
        return True
    if re.search(r"\b(pdf|documento|exporta(?:r|me)?)\b", b) and len(b) < 220:
        return True
    return False


def _compose_pdf_prompt(
    *,
    title: str,
    user_request: str,
    draft_content: str = "",
    context_snippets: list[str] | None = None,
    detail_level: str = "brief",
) -> str:
    req = (user_request or title or "").strip()
    safe_title = (title or "Documento CED").strip()
    draft = (draft_content or "").strip()
    context_lines = [
        (snippet or "").strip()[:500]
        for snippet in (context_snippets or [])
        if (snippet or "").strip()
    ][-6:]
    context_block = (
        "\n".join(f"- {line}" for line in context_lines) if context_lines else "(sin contexto previo)"
    )
    level = (detail_level or "brief").strip().lower()
    if level == "full":
        length_rules = (
            "- Extensión: contenido COMPLETO y detallado (aprox. 500–900 palabras cuando el tema lo permita).\n"
            "- Desarrolla secciones con explicación útil; no rellenes con paja."
        )
    else:
        length_rules = (
            "- Extensión: RESUMEN BREVE por defecto (aprox. 120–220 palabras).\n"
            "- Solo lo esencial: 3–6 puntos o secciones cortas. PROHIBIDO un tratado largo."
        )
    return f"""Redacta el CONTENIDO de un documento PDF en español.

Título del documento: {safe_title}

Petición del usuario: {req}

Borrador recibido (puede ser solo el título o la petición — NO lo copies tal cual):
{draft[:900] if draft else "(vacío)"}

Contexto de la conversación:
{context_block}

INSTRUCCIONES:
- Entrega el documento que el usuario pidió (consejos, resumen, guía, listado, análisis, etc.).
- PROHIBIDO devolver solo el título o repetir la petición del usuario.
- Si piden consejos de "El Alquimista", escribe consejos reales inspirados en la obra de Paulo Coelho (Leyenda Personal, señales, miedo, viaje, tesoro, etc.).
- Usa secciones numeradas o viñetas cuando ayude.
{length_rules}
- Texto plano legible (sin markdown con asteriscos).
- Entrega SOLO el cuerpo del documento, sin saludo ni despedida.
- PROHIBIDO copiar este bloque de instrucciones ni la etiqueta «INSTRUCCIONES» en el documento."""


def _sanitize_pdf_composed_body(text: str) -> str:
    """Evita que el modelo de texto filtre el bloque de instrucciones al PDF."""
    body = (text or "").strip()
    if not body:
        return ""
    if body.upper().startswith("INSTRUCCIONES"):
        parts = re.split(r"\n\s*\n", body, maxsplit=1)
        if len(parts) == 2 and len(parts[1].strip()) >= 40:
            body = parts[1].strip()
    body = re.sub(r"(?im)^\s*INSTRUCCIONES\s*:\s*$", "", body).strip()
    return body[:_PDF_BODY_MAX_CHARS]


def _compose_pdf_body_cloud_fallback(prompt: str, *, detail_level: str = "brief") -> str:
    """Gemini/Claude cuando la composición directa con Gemini falla."""
    from app.services.cloud_llm_fallback import chat_cloud_reply

    max_tokens = 4096 if (detail_level or "").lower() == "full" else 1200
    try:
        text = chat_cloud_reply(
            system=(
                "Eres un redactor profesional en español. "
                "Genera el cuerpo de documentos PDF claros y útiles. "
                "Respeta la extensión pedida (breve por defecto)."
            ),
            messages=[{"role": "user", "content": prompt}],
            user_text=prompt[:240],
            max_tokens=max_tokens,
        )
        if text and len(text.strip()) >= 80:
            logger.info("[PDF] composed body via cloud fallback chars=%s", len(text))
            return _sanitize_pdf_composed_body(text.strip())
    except Exception:  # noqa: BLE001
        logger.exception("[PDF] cloud compose fallback failed")
    return ""


def compose_pdf_body(
    *,
    title: str,
    user_request: str,
    draft_content: str = "",
    context_snippets: list[str] | None = None,
    detail_level: str = "brief",
) -> str:
    """Redacta el cuerpo del PDF con Gemini cuando el modelo no pasó contenido sustantivo."""
    from app.config import get_settings

    settings = get_settings()
    api_key = settings.google_api_key.strip()
    safe_title = (title or "Documento CED").strip()
    req = (user_request or title or "").strip()
    level = (detail_level or "brief").strip().lower() or "brief"
    prompt = _compose_pdf_prompt(
        title=safe_title,
        user_request=req,
        draft_content=draft_content,
        context_snippets=context_snippets,
        detail_level=level,
    )
    max_tokens = 4096 if level == "full" else 1200

    def _call_gemini() -> str:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=_PDF_COMPOSE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.55,
                max_output_tokens=max_tokens,
            ),
        )
        return (response.text or "").strip()

    if api_key:
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                text = pool.submit(_call_gemini).result(timeout=PDF_COMPOSE_TIMEOUT_SEC)
            if text and len(text) >= 80:
                cleaned = _sanitize_pdf_composed_body(text)
                logger.info(
                    "[PDF] composed body chars=%s title=%s level=%s",
                    len(cleaned),
                    safe_title[:60],
                    level,
                )
                return cleaned
        except FuturesTimeoutError:
            logger.warning("[PDF] compose timeout title=%s", safe_title[:60])
        except Exception:  # noqa: BLE001
            logger.exception("[PDF] compose_pdf_body failed title=%s", safe_title[:60])
    else:
        logger.warning("[PDF] compose skipped — no GOOGLE_API_KEY")

    return _compose_pdf_body_cloud_fallback(prompt, detail_level=level)


def _persist_pdf_artifact(
    *,
    file_id: str,
    user_id: str,
    title: str,
    filename: str,
    pdf_bytes: bytes,
    conversation_id: str | None,
) -> bool:
    from app.services import supabase_db

    attempts: list[str | None] = []
    if conversation_id:
        attempts.append(conversation_id)
    attempts.append(None)
    seen: set[str | None] = set()
    for conv_id in attempts:
        if conv_id in seen:
            continue
        seen.add(conv_id)
        saved = supabase_db.save_pdf_artifact(
            file_id=file_id,
            user_id=user_id,
            title=title,
            filename=filename,
            pdf_bytes=pdf_bytes,
            conversation_id=conv_id,
        )
        if not saved:
            continue
        verify = supabase_db.get_pdf_artifact(file_id, user_id)
        if verify and len(verify[0]) >= PDF_MIN_BYTES:
            return True
        logger.warning(
            "[PDF] Supabase verify failed file_id=%s conv=%s",
            file_id,
            conv_id or "none",
        )
    return False


def assistant_fallback_texts_from_messages(messages: list[dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    for row in messages:
        role = str(row.get("role") or "")
        if role not in {"assistant", "model"}:
            continue
        content = row.get("content")
        if isinstance(content, str) and content.strip():
            texts.append(content.strip())
    return texts

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
    out = re.sub(r"\s+\?\s+", " ", out)
    out = re.sub(r"(?<=\w)\?(?=\w)", ", ", out)
    out = re.sub(r"\s{2,}", " ", out)
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
    body = _latin1_safe(clean_body[:_PDF_BODY_MAX_CHARS])
    for paragraph in body.split("\n"):
        line = paragraph.strip()
        if not line:
            pdf.ln(4)
            continue
        pdf.multi_cell(0, 6, line)
        pdf.ln(1)

    raw = pdf.output()
    if isinstance(raw, bytearray):
        return bytes(raw)
    if isinstance(raw, bytes):
        return raw
    return str(raw).encode("latin-1", "replace")


def store_pdf(
    *,
    user_id: str,
    title: str,
    content: str,
    conversation_id: str | None = None,
    fallback_texts: list[str] | None = None,
    user_request: str | None = None,
    detail_level: str = "brief",
) -> PdfArtifact:
    _purge_expired()
    file_id = uuid.uuid4().hex
    safe_title = _strip_markdown(title) or "Documento CED"
    raw_body = _strip_markdown(content)
    req = (user_request or safe_title).strip()
    level = (detail_level or "brief").strip().lower() or "brief"
    resolved = resolve_pdf_content(
        safe_title,
        raw_body,
        fallback_texts=fallback_texts,
    )
    context = [*(fallback_texts or [])]
    if req and req not in context:
        context.append(req)

    if pdf_content_needs_composition(safe_title, resolved, user_request=req):
        composed = compose_pdf_body(
            title=safe_title,
            user_request=req,
            draft_content=raw_body or resolved,
            context_snippets=context,
            detail_level=level,
        )
        if composed:
            resolved = composed

    if pdf_content_needs_composition(safe_title, resolved, user_request=req):
        raise ValueError("No se pudo redactar el contenido del PDF")

    from app.services.chat_intents import infer_pdf_title

    if safe_title == "Documento CED" or len(safe_title.strip()) < 12:
        inferred = infer_pdf_title(req, resolved)
        if inferred and inferred != "Documento CED":
            safe_title = inferred[:200]

    safe_content = resolved[:_PDF_BODY_MAX_CHARS]
    if len(safe_content.strip()) < 40:
        raise ValueError("No se pudo redactar el contenido del PDF")

    filename = _sanitize_filename(safe_title)
    data = generate_pdf_bytes(title=safe_title, content=safe_content)
    if len(data) < PDF_MIN_BYTES or not data.startswith(b"%PDF"):
        raise ValueError("PDF generado inválido o vacío")

    now = datetime.now(timezone.utc)
    meta = {
        "file_id": file_id,
        "filename": filename,
        "title": safe_title,
        "conversation_id": conversation_id or "",
        "created_at": now.isoformat(),
    }

    saved = False
    try:
        saved = _persist_pdf_artifact(
            file_id=file_id,
            user_id=user_id,
            title=safe_title,
            filename=filename,
            pdf_bytes=data,
            conversation_id=conversation_id,
        )
    except Exception:  # noqa: BLE001
        logger.exception("[PDF] Supabase persist failed file_id=%s user=%s", file_id, user_id[:8])

    _STORE[file_id] = (data, filename, now, user_id)
    _USER_INDEX.setdefault(user_id, []).insert(0, meta)
    _USER_INDEX[user_id] = _USER_INDEX[user_id][:100]

    if not saved:
        from app.services.supabase_client import service_role_configured

        if service_role_configured():
            raise RuntimeError("No se pudo guardar el PDF en el servidor")
        logger.error(
            "[PDF] PDF solo en memoria (falta SUPABASE_SERVICE_ROLE_KEY) file_id=%s user=%s",
            file_id,
            user_id[:8],
        )

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


def store_pdf_with_timeout(**kwargs: Any) -> PdfArtifact:
    """Genera PDF con límite de tiempo — evita colgar el chat si Gemini tarda."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(store_pdf, **kwargs)
        try:
            return future.result(timeout=PDF_STORE_TIMEOUT_SEC)
        except FuturesTimeoutError as exc:
            raise TimeoutError("PDF generation timed out") from exc


def get_pdf(file_id: str, user_id: str) -> tuple[bytes, str] | None:
    _purge_expired()
    row = _STORE.get(file_id)
    if row:
        data, filename, _, owner = row
        if owner == user_id:
            payload = bytes(data) if isinstance(data, bytearray) else data
            return payload, filename

    try:
        from app.services import supabase_db

        db_row = supabase_db.get_pdf_artifact(file_id, user_id)
        if db_row:
            data, filename, _title = db_row
            payload = bytes(data) if isinstance(data, bytearray) else data
            _STORE[file_id] = (payload, filename, datetime.now(timezone.utc), user_id)
            return payload, filename
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
