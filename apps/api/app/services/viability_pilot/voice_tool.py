"""Tool Retell — módulo viabilidad (kill-switch VIABILITY_MODULE_ENABLED)."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.services.viability_pilot.gate import viability_module_enabled
from app.services.viability_pilot.service import analyze_viability, format_report_for_voice

logger = logging.getLogger(__name__)

TOOL_NAME = "analyze_product_viability"

ANALYZE_VIABILITY_DESCRIPTION = (
    "Análisis de viabilidad de mercado de un PRODUCTO o SERVICIO del usuario. "
    "SOLO llamar cuando el usuario pida explícitamente: «analiza la viabilidad», "
    "«estudio de mercado de mi…», «qué tan viable es mi…», «probabilidad de éxito de…», "
    "«análisis de mercado de mi producto/servicio». "
    "PROHIBIDO usar para: generar/editar imagen o flyer, publicar en redes, prospección, "
    "noticias genéricas, «busca en internet», modo avanzado, o solo preguntar un precio suelto. "
    "Si pide generar un flyer/imagen → generate_image. Si pide investigar un tema general → search_web."
)

ANALYZE_VIABILITY_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "description": {
            "type": "string",
            "description": (
                "Descripción completa del producto/servicio/negocio que el usuario quiere evaluar. "
                "Incluye región o ciudad si la mencionó."
            ),
        },
        "region": {
            "type": "string",
            "description": "Ciudad/país/región si el usuario la indicó.",
        },
    },
    "required": ["description"],
}


def build_analyze_product_viability_tool(*, api_public_url: str) -> dict[str, Any]:
    from app.services.retell_native_pilot import _build_custom_tool

    return _build_custom_tool(
        api_public_url=api_public_url,
        name=TOOL_NAME,
        description=ANALYZE_VIABILITY_DESCRIPTION,
        parameters=ANALYZE_VIABILITY_PARAMETERS,
        filler="Analizando la viabilidad de mercado, señor. Puede tardar un momento.",
        timeout_ms=55_000,
    )


def should_register_viability_voice_tool() -> bool:
    return viability_module_enabled()


async def execute_analyze_product_viability_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    """Ejecutor Retell — no toca pending de finanzas."""
    started = time.perf_counter()
    if not viability_module_enabled():
        return {
            "result": "El módulo de viabilidad no está activo en este entorno, señor.",
            "ok": False,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }

    description = str(args.get("description") or args.get("query") or "").strip()
    region = str(args.get("region") or "").strip() or None

    # Soft gate: if description alone isn't viability-phrased, still allow when
    # Retell already chose this tool (description param is the offering, not the trigger).
    if not description:
        return {
            "result": "Señor, descríbame el producto o servicio para analizar su viabilidad.",
            "ok": False,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }

    try:
        report = analyze_viability(
            description=description,
            region=region,
            polish=True,
        )
        spoken = format_report_for_voice(report)
        ok = bool(report.get("ok"))
    except Exception:  # noqa: BLE001
        logger.exception(
            "[VIABILITY-PILOT] voice tool failed user=%s",
            (user_id or "")[:8],
        )
        spoken = "Señor, no pude completar el análisis de viabilidad en este momento."
        ok = False
        report = {"ok": False}

    latency_ms = int((time.perf_counter() - started) * 1000)
    # Metrics optional — avoid coupling if record_tool_metric import fails
    try:
        from app.services.retell_native_pilot import record_tool_metric

        call_id = ""
        if isinstance(payload, dict):
            call = payload.get("call") or {}
            call_id = str(
                payload.get("call_id")
                or call.get("call_id")
                or ""
            )
        record_tool_metric(
            call_id=call_id,
            tool_name=TOOL_NAME,
            latency_ms=latency_ms,
            ok=ok,
            query=description[:120],
        )
    except Exception:  # noqa: BLE001
        pass

    # Include a compact markdown trailer so Retell can paraphrase facts vs advice.
    extra = ""
    if ok and report.get("data_gaps"):
        extra = " Limitaciones: " + "; ".join(str(g) for g in report["data_gaps"][:2])

    return {
        "result": spoken + extra,
        "ok": ok,
        "latency_ms": latency_ms,
        "report_preview": {
            "likelihood": report.get("likelihood"),
            "competitors": report.get("competitors"),
            "data_gaps": report.get("data_gaps"),
        }
        if ok
        else None,
    }


def voice_prompt_line() -> str:
    """Línea opcional para el state prompt del piloto nativo."""
    if not should_register_viability_voice_tool():
        return ""
    return (
        "- Viabilidad de producto/servicio: solo con «analiza la viabilidad / estudio de mercado "
        "de mi… / qué tan viable es mi…» → analyze_product_viability. "
        "NO confundir con generate_image, search_web, prospection ni modo avanzado."
    )

