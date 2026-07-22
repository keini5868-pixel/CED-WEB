"""Síntesis del informe de tendencias — Research vs Reasoning separados."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


def _cite(item: dict[str, Any]) -> str:
    return item.get("source_url") or item.get("source_title") or "sin URL"


def build_trends_report(
    *,
    description: str,
    profile: dict[str, Any],
    facts: dict[str, list[dict[str, Any]]],
    sources: list[dict[str, Any]],
    region: str | None,
    search_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta = search_meta or {}
    data_gaps: list[str] = []

    if not sources:
        if meta.get("missing_key"):
            data_gaps.append(
                "La búsqueda web no está configurada (falta TAVILY_API_KEY). "
                "No es una conclusión de mercado."
            )
        elif meta.get("rate_limited"):
            data_gaps.append(
                "El proveedor de búsqueda limitó la tasa (429). Reintente."
            )
        elif meta.get("errors"):
            data_gaps.append(
                "La búsqueda web falló o no devolvió resultados en esta sesión. "
                "Reintente; no inventamos tendencias."
            )
        else:
            data_gaps.append(
                "Sin resultados de búsqueda en esta sesión. "
                "No hay base para afirmar tendencias."
            )

    trending = list(facts.get("trending_now") or [])
    needs = list(facts.get("consumer_needs") or [])
    outlook_search = list(facts.get("outlook_6m") or [])
    opps_search = list(facts.get("opportunities") or [])

    if sources and not trending:
        data_gaps.append(
            "No hubo señales claras de 'trending ahora' atribuibles en los resultados."
        )
    if sources and not needs:
        data_gaps.append(
            "No aparecieron necesidades emergentes de consumidores con fuente clara."
        )
    if sources and not outlook_search:
        data_gaps.append(
            "No hubo forecast/outlook a ~6 meses en los resultados de búsqueda; "
            "la sección de predicción se marca como razonamiento del modelo."
        )

    # Always include outlook section
    if outlook_search:
        outlook = {
            "attribution": "search",
            "findings": outlook_search[:4],
            "model_note": None,
        }
    else:
        outlook = {
            "attribution": "model_reasoning",
            "findings": [],
            "model_note": (
                "Sin forecast verificable en esta sesión. Orientación cualitativa: "
                "observe señales de demanda del ancla descrito, pruebe ofertas "
                "pequeñas y mida conversión antes de escalar. Esto NO es un "
                "pronóstico de mercado con cifras."
            ),
        }

    opportunities = _build_opportunities(
        description=description,
        profile=profile,
        trending=trending,
        needs=needs,
        opps_search=opps_search,
    )

    research_lines = [
        "### Hallazgos de búsqueda (hechos con fuente en esta sesión)",
        f"**Ancla:** {profile.get('anchor') or description[:80]}",
    ]
    if trending:
        research_lines.append("**Trending ahora:**")
        for t in trending[:4]:
            research_lines.append(f"- {t['text'][:200]} _(fuente: {_cite(t)})_")
    if needs:
        research_lines.append("**Necesidades emergentes:**")
        for n in needs[:4]:
            research_lines.append(f"- {n['text'][:200]} _(fuente: {_cite(n)})_")
    if outlook_search:
        research_lines.append("**Outlook (~6 meses) en resultados:**")
        for o in outlook_search[:3]:
            research_lines.append(f"- {o['text'][:200]} _(fuente: {_cite(o)})_")
    if data_gaps:
        research_lines.append("**Limitaciones:**")
        for g in data_gaps:
            research_lines.append(f"- {g}")

    advice_lines = [
        "### Orientación (razonamiento — no son hechos verificados de mercado)",
    ]
    if outlook["attribution"] == "model_reasoning":
        advice_lines.append("**Predicción ~6 meses (model_reasoning):**")
        advice_lines.append(outlook["model_note"] or "")
    else:
        advice_lines.append(
            "**Predicción ~6 meses:** basada en findings de búsqueda arriba "
            "(no inventamos % adicionales)."
        )
    advice_lines.append("**Oportunidades concretas:**")
    for i, opp in enumerate(opportunities, 1):
        tag = opp.get("attribution") or "model_reasoning"
        advice_lines.append(f"{i}. [{tag}] {opp['idea']}")

    markdown = "\n\n".join(
        [
            "## Informe de tendencias (piloto)\n",
            f"**Rubro:** {description[:300]}",
            f"**Región:** {region or 'no especificada'}",
            "\n".join(research_lines),
            "\n".join(advice_lines),
        ]
    )

    spoken = (
        f"Informe de tendencias listo. Ancla: {profile.get('anchor') or 'su rubro'}. "
    )
    if trending:
        spoken += f"{len(trending)} señales de trending con fuente. "
    else:
        spoken += "Pocas señales de trending verificables. "
    if outlook["attribution"] == "model_reasoning":
        spoken += "El outlook a 6 meses es razonamiento etiquetado, no forecast con datos."

    return {
        "description": description,
        "region": region or "",
        "profile": {
            "anchor": profile.get("anchor") or "",
            "industry_label": profile.get("industry_label") or "",
            "category": profile.get("category") or "",
            "product_kind": profile.get("product_kind") or "",
            "named_entities": profile.get("named_entities") or [],
        },
        "trending_now": trending,
        "consumer_needs": needs,
        "outlook_6m": outlook,
        "opportunities": opportunities,
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


def _build_opportunities(
    *,
    description: str,
    profile: dict[str, Any],
    trending: list[dict[str, Any]],
    needs: list[dict[str, Any]],
    opps_search: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Oportunidades: preferir search; completar con reasoning anclado a hallazgos."""
    out: list[dict[str, Any]] = []
    for o in opps_search[:3]:
        out.append(
            {
                "idea": o["text"][:280],
                "attribution": "search",
                "source_url": o.get("source_url") or "",
                "source_title": o.get("source_title") or "",
            }
        )

    # Reasoning fill only if we have some search signal to anchor on
    anchors = (trending + needs)[:4]
    if len(out) < 3 and anchors:
        settings = get_settings()
        api_key = settings.google_api_key.strip()
        if api_key:
            try:
                from google import genai
                from google.genai import types

                payload = {
                    "rubro": description[:300],
                    "anchor": profile.get("anchor"),
                    "hallazgos": [
                        {"text": a.get("text"), "url": a.get("source_url")}
                        for a in anchors
                    ],
                }
                prompt = (
                    "Propón 2-3 oportunidades CONCRETAS para este rubro. "
                    "Cada idea DEBE apoyarse en uno de los hallazgos listados "
                    "(cita la idea del hallazgo). NO inventes porcentajes ni "
                    "estadísticas. JSON: "
                    '{"opportunities":[{"idea":"...","based_on_finding":"..."}]}\n'
                    f"{json.dumps(payload, ensure_ascii=False)[:5000]}"
                )
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.2,
                        max_output_tokens=700,
                        response_mime_type="application/json",
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
                    ),
                )
                raw = (getattr(response, "text", None) or "").strip()
                data = json.loads(raw) if raw else {}
                rows = data.get("opportunities") if isinstance(data, dict) else None
                if isinstance(rows, list):
                    for row in rows[:3]:
                        if not isinstance(row, dict):
                            continue
                        idea = str(row.get("idea") or "").strip()
                        if not idea:
                            continue
                        based = str(row.get("based_on_finding") or "").strip()
                        text = idea if not based else f"{idea} (anclado a: {based[:120]})"
                        out.append(
                            {
                                "idea": text[:320],
                                "attribution": "model_reasoning",
                            }
                        )
                        if len(out) >= 5:
                            break
            except Exception:  # noqa: BLE001
                logger.warning("[TRENDS-PILOT] opportunities polish skipped", exc_info=True)

    if not out:
        out.append(
            {
                "idea": (
                    "Sin hallazgos de oportunidad en búsqueda: valide demanda con "
                    "entrevistas cortas a clientes del ancla descrito antes de invertir."
                ),
                "attribution": "model_reasoning",
            }
        )
    return out[:5]
