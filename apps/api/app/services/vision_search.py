"""Visión + búsqueda web — identifica imagen y consulta Tavily."""

from __future__ import annotations

import base64
import logging
import re
from typing import Any

from app.config import get_settings
from app.services.tavily_search import DEFAULT_MAX_RESULTS, tavily_answer, tavily_search

logger = logging.getLogger(__name__)

VISION_MODEL = "gemini-2.5-flash"
# Gemini 2.5 Flash gasta presupuesto en thinking; sin desactivarlo
# max_output_tokens=180 deja ~5 tokens de respuesta (corte tipo «Es una figura»).
VISION_ANALYZE_MAX_TOKENS = 512
VISION_IDENTIFY_MAX_TOKENS = 256

ANALYZE_PROMPT_DEFAULT = (
    "Visión CED. Español latinoamericano, 2 o 3 oraciones completas:\n"
    "1) Qué es el objeto con el máximo detalle posible "
    "(tipo, material, color, forma, uso si se ve claro).\n"
    "2) Marca, modelo o texto legible en el objeto entre comillas si aparece.\n"
    "3) Si no hay marca, di exactamente: «no veo marca legible».\n"
    "Sé concreto. Si el objeto es genérico (figura, botella, etc.), "
    "describe estilo y rasgos distintivos.\n"
    "PROHIBIDO cortar a mitad de frase. PROHIBIDO inventar marcas."
)


def _decode_image(image_b64: str) -> bytes:
    raw = image_b64.strip()
    if "," in raw:
        raw = raw.split(",", 1)[1]
    return base64.b64decode(raw)


def _response_text_and_meta(response: Any) -> tuple[str, str, dict[str, Any]]:
    text = (getattr(response, "text", None) or "").strip()
    finish = "?"
    usage: dict[str, Any] = {}
    candidates = getattr(response, "candidates", None) or []
    if candidates:
        finish = str(getattr(candidates[0], "finish_reason", None) or "?")
        if not text:
            # Algunos SDKs dejan texto en parts aunque .text falle
            content = getattr(candidates[0], "content", None)
            parts = getattr(content, "parts", None) or []
            chunks: list[str] = []
            for part in parts:
                part_text = getattr(part, "text", None)
                if part_text:
                    chunks.append(str(part_text))
            text = " ".join(chunks).strip()
    um = getattr(response, "usage_metadata", None)
    if um:
        usage = {
            "prompt": getattr(um, "prompt_token_count", None),
            "candidates": getattr(um, "candidates_token_count", None),
            "thoughts": getattr(um, "thoughts_token_count", None),
            "total": getattr(um, "total_token_count", None),
        }
    return text, finish, usage


def _gemini_vision(image_bytes: bytes, prompt: str, *, max_tokens: int = 512) -> str:
    settings = get_settings()
    api_key = settings.google_api_key.strip()
    if not api_key:
        logger.warning("[VISION:GEMINI] status=skip reason=no_api_key")
        return ""
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=VISION_MODEL,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                        types.Part.from_text(text=prompt),
                    ],
                )
            ],
            config=types.GenerateContentConfig(
                temperature=0.12,
                max_output_tokens=max_tokens,
                # Crítico: thinking se cuenta contra max_output_tokens.
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        text, finish, usage = _response_text_and_meta(response)
        if text:
            logger.info(
                "[VISION:GEMINI] status=ok len=%s finish=%s usage=%s bytes=%s",
                len(text),
                finish,
                usage,
                len(image_bytes),
            )
            if str(finish).upper().endswith("MAX_TOKENS"):
                logger.warning(
                    "[VISION:GEMINI] truncated finish=MAX_TOKENS len=%s preview=%r",
                    len(text),
                    text[:80],
                )
        else:
            logger.warning(
                "[VISION:GEMINI] status=empty finish=%s usage=%s bytes=%s",
                finish,
                usage,
                len(image_bytes),
            )
        return text
    except Exception as exc:  # noqa: BLE001
        logger.warning("[VISION:GEMINI] status=fail error=%s", exc)
        return ""


def _openai_vision_fallback(image_bytes: bytes, prompt: str, *, max_tokens: int = 512) -> str:
    settings = get_settings()
    api_key = settings.openai_api_key.strip()
    model = (settings.openai_model_retell_llm or "gpt-4.1-mini-2025-04-14").strip()
    if not api_key:
        logger.warning("[VISION:OPENAI_FALLBACK] status=skip reason=no_api_key")
        return ""
    try:
        import httpx

        b64 = base64.b64encode(image_bytes).decode("utf-8")
        with httpx.Client(timeout=12.0) as client:
            res = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                                },
                            ],
                        }
                    ],
                    "max_tokens": max_tokens,
                },
            )
            res.raise_for_status()
            data = res.json()
        text = str(
            data.get("choices", [{}])[0].get("message", {}).get("content") or ""
        ).strip()
        if text:
            logger.info("[VISION:OPENAI_FALLBACK] status=ok len=%s", len(text))
        else:
            logger.warning("[VISION:OPENAI_FALLBACK] status=empty")
        return text
    except Exception as exc:  # noqa: BLE001
        logger.warning("[VISION:OPENAI_FALLBACK] status=fail error=%s", exc)
        return ""


def _identify_subject(image_bytes: bytes, question: str = "") -> str:
    prompt = (
        question.strip()
        or "Identifica el objeto, producto, marca o texto principal en esta imagen. "
        "Responde en UNA frase corta en español, ideal para buscar en Google. "
        "Ejemplo: 'procesador AMD Ryzen' o 'logo Nike'. Sin markdown."
    )
    text = _gemini_vision(image_bytes, prompt, max_tokens=VISION_IDENTIFY_MAX_TOKENS)
    text = re.sub(r"^(es|se ve|parece)\s+(un|una)\s+", "", text, flags=re.I)
    return text[:200]


def _spoken(text: str, limit: int = 520) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    if not t:
        return ""
    if len(t) <= limit:
        return t
    chunk = t[:limit]
    last_end = max(chunk.rfind(". "), chunk.rfind("! "), chunk.rfind("? "))
    if last_end >= int(limit * 0.45):
        return chunk[: last_end + 1].strip()
    last_space = chunk.rfind(" ")
    if last_space >= int(limit * 0.55):
        return f"{chunk[:last_space].strip()}."
    return f"{chunk.strip()}."


def analyze_image(
    image_b64: str,
    *,
    question: str = "",
) -> dict[str, Any]:
    """Describe lo visible con precisión — sin buscar en internet."""
    try:
        image_bytes = _decode_image(image_b64)
    except Exception:
        return {"ok": False, "error": "Imagen inválida"}

    if len(image_bytes) < 800:
        logger.warning("[VISION:GEMINI] status=skip reason=image_too_small bytes=%s", len(image_bytes))
        return {"ok": False, "error": "La captura de cámara quedó vacía o incompleta"}

    user_q = question.strip()
    prompt = ANALYZE_PROMPT_DEFAULT
    if user_q and len(user_q) > 8:
        prompt = f"{ANALYZE_PROMPT_DEFAULT}\n\nPregunta del usuario: {user_q}"

    subject = _gemini_vision(
        image_bytes, prompt, max_tokens=VISION_ANALYZE_MAX_TOKENS
    )
    if not subject:
        subject = _openai_vision_fallback(
            image_bytes, prompt, max_tokens=VISION_ANALYZE_MAX_TOKENS
        )
    if not subject:
        return {"ok": False, "error": "No pude analizar la imagen"}
    summary = _spoken(subject, limit=520)
    return {"ok": True, "summary": summary, "subject": summary[:220]}


def vision_search_web(
    image_b64: str,
    *,
    question: str = "",
) -> dict[str, Any]:
    """Identifica imagen → Tavily (campo answer + results)."""
    try:
        image_bytes = _decode_image(image_b64)
    except Exception:
        return {"ok": False, "error": "Imagen inválida"}

    subject = _identify_subject(image_bytes, question)
    if not subject:
        return {"ok": False, "error": "No identifiqué qué buscar en la imagen"}

    query = subject
    if question.strip():
        query = f"{subject} {question.strip()}"

    answer = tavily_answer(query)
    if answer and len(answer) >= 36:
        logger.info("[VISION:WEB] tavily answer len=%s q=%s", len(answer), query[:60])
        return {
            "ok": True,
            "summary": _spoken(answer),
            "query": query,
            "subject": subject,
            "source": "tavily",
        }

    rows = tavily_search(query, max_results=DEFAULT_MAX_RESULTS, kind="general")
    for row in rows:
        content = str(row.get("content") or "").strip()
        if len(content) >= 40:
            return {
                "ok": True,
                "summary": _spoken(content[:380]),
                "query": query,
                "subject": subject,
                "source": "tavily",
            }

    settings = get_settings()
    if not settings.tavily_api_key.strip():
        return {
            "ok": False,
            "error": "Configure TAVILY_API_KEY para buscar lo que ve la cámara",
            "subject": subject,
            "code": "missing_tavily",
        }

    return {
        "ok": False,
        "error": f"No encontré información sobre {subject}",
        "subject": subject,
    }
