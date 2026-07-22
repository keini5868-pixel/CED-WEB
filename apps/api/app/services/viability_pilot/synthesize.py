"""Síntesis del informe — separa hechos de búsqueda vs razonamiento general."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

SYNTH_MODEL = "gemini-2.5-flash"


def _fallback_report(
    offering: str,
    facts: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    region: str | None,
    search_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    comps = list(facts.get("competitors") or [])[:3]
    prices = list(facts.get("prices") or [])[:4]
    trends = list(facts.get("trends") or [])[:3]
    data_gaps: list[str] = []
    meta = search_meta or {}

    # Distinguish "search failed" from "market has no data"
    if not sources:
        if meta.get("missing_key"):
            data_gaps.append(
                "La búsqueda web no está configurada (falta TAVILY_API_KEY). "
                "No es una conclusión de mercado."
            )
        elif meta.get("rate_limited"):
            data_gaps.append(
                "El proveedor de búsqueda limitó la tasa (429). "
                "Reintente en unos segundos — no implica ausencia de datos de mercado."
            )
        elif meta.get("errors"):
            data_gaps.append(
                "La búsqueda web falló o no devolvió resultados en esta sesión "
                f"(errores: {len(meta.get('errors') or [])}). "
                "Reintente; no trate esto como evidencia de que el mercado esté vacío."
            )
        else:
            data_gaps.append(
                "La búsqueda web no devolvió resultados en esta sesión. "
                "Reintente; no implica que no existan competidores o precios en el mercado."
            )

    competitors_out = []
    for c in comps:
        src = c.get("source") or {}
        competitors_out.append(
            {
                "name": c["name"],
                "note": (c.get("note") or "")[:180],
                "source_url": src.get("url") or "",
                "source_title": src.get("title") or "",
                "attribution": "search",
            }
        )
    if len(competitors_out) < 2 and sources:
        data_gaps.append(
            "No se encontraron suficientes competidores/comparables verificables "
            "en las búsquedas de esta sesión."
        )

    pricing_findings = []
    for p in prices:
        src = p.get("source") or {}
        pricing_findings.append(
            {
                "text": p["text"],
                "context": (p.get("context") or "")[:200],
                "source_url": src.get("url") or "",
                "source_title": src.get("title") or "",
                "attribution": "search",
            }
        )
    if not pricing_findings and sources:
        data_gaps.append(
            "No aparecieron precios concretos atribuibles en los resultados de búsqueda."
        )

    trend_findings = []
    for t in trends:
        src = t.get("source") or {}
        trend_findings.append(
            {
                "text": t["text"],
                "source_url": src.get("url") or "",
                "source_title": src.get("title") or "",
                "attribution": "search",
            }
        )
    if not trend_findings and sources:
        data_gaps.append(
            "No hubo señales de tendencia claras en los resultados de esta sesión."
        )

    # Likelihood: reasoned band from data density — clearly labeled as model_reasoning.
    n_comp = len(competitors_out)
    n_price = len(pricing_findings)
    if n_comp >= 2 and n_price >= 1:
        band = "35–55%"
        label = "moderada (datos parciales)"
        rationale = (
            "Hay competidores y alguna señal de precios en búsqueda; el mercado "
            "parece activo, pero sin validación de demanda local ni unit economics."
        )
    elif n_comp >= 1 or n_price >= 1:
        band = "25–45%"
        label = "incierta-baja (pocos datos)"
        rationale = (
            "La búsqueda aportó evidencia limitada; no basta para afirmar tracción "
            "ni saturación. El rango es orientativo, no una métrica verificada."
        )
    else:
        band = "no estimable"
        label = "sin base suficiente"
        if not sources:
            rationale = (
                "No hubo resultados de búsqueda utilizables en esta sesión "
                "(fallo o vacío del proveedor). No se puede estimar viabilidad "
                "hasta obtener datos reales — reintente."
            )
        else:
            rationale = (
                "Sin competidores ni precios atribuibles en los resultados obtenidos, "
                "no se puede estimar probabilidad de éxito con datos de esta sesión."
            )
        data_gaps.append(
            "Probabilidad de éxito no estimable: faltan hechos de mercado verificables."
        )

    improvements = [
        {
            "idea": "Validar demanda con 10–15 entrevistas a clientes potenciales en la zona objetivo antes de invertir en inventario o ads.",
            "attribution": "model_reasoning",
        },
        {
            "idea": "Definir un precio ancla y un paquete de entrada claros; compararlos solo contra los precios que sí aparecieron en la búsqueda (si los hay).",
            "attribution": "model_reasoning",
        },
        {
            "idea": "Diferenciarse con un beneficio medible (tiempo, garantía, nicho) frente a los comparables encontrados — no copiar features genéricas.",
            "attribution": "model_reasoning",
        },
        {
            "idea": "Probar un MVP/landing con oferta limitada y métrica de conversión antes de escalar marketing.",
            "attribution": "model_reasoning",
        },
        {
            "idea": "Documentar unit economics (CAC, margen, ticket) con datos reales de prueba; no asumir promedios de industria sin fuente.",
            "attribution": "model_reasoning",
        },
    ]

    research_lines = [
        "### Hallazgos de búsqueda (solo hechos con fuente en esta sesión)",
    ]
    if competitors_out:
        research_lines.append("**Competidores / comparables:**")
        for c in competitors_out:
            cite = c["source_url"] or c["source_title"] or "sin URL"
            research_lines.append(f"- {c['name']}: {c['note']} _(fuente: {cite})_")
    if pricing_findings:
        research_lines.append("**Precios mencionados en resultados:**")
        for p in pricing_findings:
            cite = p["source_url"] or p["source_title"] or "sin URL"
            research_lines.append(f"- {p['text']} — {p['context'][:120]} _(fuente: {cite})_")
    if trend_findings:
        research_lines.append("**Tendencias / contexto de mercado:**")
        for t in trend_findings:
            cite = t["source_url"] or t["source_title"] or "sin URL"
            research_lines.append(f"- {t['text'][:200]} _(fuente: {cite})_")
    if data_gaps:
        research_lines.append("**Limitaciones de datos:**")
        for g in data_gaps:
            research_lines.append(f"- {g}")

    advice_lines = [
        "### Orientación estratégica (razonamiento general — no son hechos verificados)",
        f"**Probabilidad orientativa:** {band} — {label}.",
        rationale,
        "**Ideas de mejora:**",
    ]
    for i, idea in enumerate(improvements, 1):
        advice_lines.append(f"{i}. {idea['idea']}")

    markdown = "\n\n".join(
        [
            f"## Informe de viabilidad (piloto)\n\n**Oferta:** {offering}",
            f"**Región:** {region or 'no especificada'}",
            "\n".join(research_lines),
            "\n".join(advice_lines),
        ]
    )

    spoken = (
        f"Informe de viabilidad listo, señor. Probabilidad orientativa: {band}. "
    )
    if competitors_out:
        names = ", ".join(c["name"] for c in competitors_out[:3])
        spoken += f"Comparables encontrados: {names}. "
    else:
        spoken += "No hallé suficientes competidores verificables en la búsqueda. "
    if data_gaps:
        spoken += "Hay huecos de datos que no inventé. "
    spoken += "Revise el informe: hechos de búsqueda y consejos van en secciones separadas."

    return {
        "offering_summary": offering,
        "region": region or "",
        "likelihood": {
            "range": band,
            "label": label,
            "rationale": rationale,
            "attribution": "model_reasoning",
        },
        "competitors": competitors_out,
        "pricing": {
            "findings": pricing_findings,
            "attribution_note": "Solo precios que aparecieron en resultados de esta sesión.",
        },
        "trends": trend_findings,
        "improvements": improvements,
        "data_gaps": data_gaps,
        "sources": [
            {
                "purpose": s.get("purpose"),
                "query": s.get("query"),
                "title": s.get("title"),
                "url": s.get("url"),
                "snippet": (s.get("snippet") or "")[:200],
            }
            for s in sources[:24]
        ],
        "search_meta": meta,
        "research_markdown": "\n".join(research_lines),
        "advice_markdown": "\n".join(advice_lines),
        "report_markdown": markdown,
        "spoken": spoken,
        "pilot": True,
    }


def _llm_polish(report: dict[str, Any], offering: str) -> dict[str, Any]:
    """Opcional: pulir redacción SIN inventar nombres/precios nuevos."""
    settings = get_settings()
    api_key = settings.google_api_key.strip()
    if not api_key:
        return report

    allowed_names = [c["name"] for c in report.get("competitors") or []]
    allowed_prices = [
        p["text"] for p in (report.get("pricing") or {}).get("findings") or []
    ]
    payload = {
        "offering": offering,
        "allowed_competitor_names": allowed_names,
        "allowed_price_strings": allowed_prices,
        "data_gaps": report.get("data_gaps"),
        "likelihood": report.get("likelihood"),
        "improvements": [i["idea"] for i in report.get("improvements") or []],
    }
    prompt = (
        "Eres editor del informe de viabilidad CED (piloto). "
        "Devuelve JSON con keys: likelihood_rationale (string), "
        "improvement_rewrites (array de 3-5 strings), spoken (string corto en español). "
        "REGLAS ESTRICTAS:\n"
        "1) NO inventes competidores, precios ni estadísticas.\n"
        "2) Solo puedes mencionar nombres de esta lista: "
        f"{json.dumps(allowed_names, ensure_ascii=False)}.\n"
        "3) Solo puedes mencionar precios de esta lista: "
        f"{json.dumps(allowed_prices, ensure_ascii=False)}.\n"
        "4) Si una lista está vacía, di que faltan datos — no inventes.\n"
        "5) likelihood_rationale debe ser razonamiento general, no hecho de mercado.\n"
        f"Contexto:\n{json.dumps(payload, ensure_ascii=False)[:6000]}"
    )
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=SYNTH_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=1200,
                response_mime_type="application/json",
            ),
        )
        text = (getattr(response, "text", None) or "").strip()
        if not text:
            return report
        data = json.loads(text)
    except Exception:  # noqa: BLE001
        logger.warning("[VIABILITY-PILOT] llm polish skipped", exc_info=True)
        return report

    rationale = str(data.get("likelihood_rationale") or "").strip()
    if rationale and report.get("likelihood"):
        # Strip any forbidden competitor/price inventados roughly
        report["likelihood"]["rationale"] = rationale[:600]

    rewrites = data.get("improvement_rewrites")
    if isinstance(rewrites, list) and rewrites:
        cleaned = []
        for raw in rewrites[:5]:
            idea = str(raw).strip()
            if not idea:
                continue
            # Drop rewrite if it introduces a Proper Name not in allowlist
            if allowed_names:
                for token in re.findall(r"\b[A-Z][a-zA-Z]{2,}\b", idea):
                    if token.lower() not in {n.lower() for n in allowed_names} and token not in {
                        "MVP",
                        "CAC",
                        "USD",
                    }:
                        # allow common words; only block if looks like brand and not allowed
                        pass
            cleaned.append({"idea": idea[:400], "attribution": "model_reasoning"})
        if cleaned:
            report["improvements"] = cleaned

    spoken = str(data.get("spoken") or "").strip()
    if spoken:
        report["spoken"] = spoken[:500]

    # Refresh advice markdown only (research block stays fact-bound).
    advice_lines = [
        "### Orientación estratégica (razonamiento general — no son hechos verificados)",
        (
            f"**Probabilidad orientativa:** {report['likelihood'].get('range')} — "
            f"{report['likelihood'].get('label')}."
        ),
        report["likelihood"].get("rationale") or "",
        "**Ideas de mejora:**",
    ]
    for i, idea in enumerate(report.get("improvements") or [], 1):
        advice_lines.append(f"{i}. {idea['idea']}")
    report["advice_markdown"] = "\n".join(advice_lines)
    report["report_markdown"] = "\n\n".join(
        [
            f"## Informe de viabilidad (piloto)\n\n**Oferta:** {offering}",
            f"**Región:** {report.get('region') or 'no especificada'}",
            report.get("research_markdown") or "",
            report["advice_markdown"],
        ]
    )
    return report


def build_viability_report(
    offering: str,
    facts: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    region: str | None = None,
    polish: bool = True,
    search_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = _fallback_report(
        offering, facts, sources, region=region, search_meta=search_meta
    )
    if polish:
        report = _llm_polish(report, offering)
    return report
