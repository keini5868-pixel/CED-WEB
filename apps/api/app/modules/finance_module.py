"""Módulo Finanzas Personales — registrar movimientos y consultar por voz/chat."""

from __future__ import annotations

import logging
import re

from app.modules.base_module import BaseModule
from app.services.finance_ledger import (
    canonical_period,
    format_summary_spoken,
    save_transaction,
    summarize_finances,
)
from app.services.orchestrator_types import ModuleResult
from app.services.retell_llm_types import Utterance

logger = logging.getLogger(__name__)

# Verbos que indican un movimiento a registrar.
_INGRESO_VERBS = (
    r"recib[íi]", r"gan[ée]", r"me\s+pagaron", r"me\s+pag[óo]", r"cobr[ée]",
    r"factur[ée]", r"vend[íi]", r"ingres[óoée]", r"entr[óo]\s+", r"me\s+depositaron",
)
_GASTO_VERBS = (
    r"gast[ée]", r"pagu[ée]", r"compr[ée]", r"invert[íi]", r"me\s+cost[óo]",
    r"gastamos", r"pagamos", r"desembols[ée]", r"gasto\s+de",
)

_INGRESO_RE = re.compile(r"\b(?:" + "|".join(_INGRESO_VERBS) + r")\b", re.I)
_GASTO_RE = re.compile(r"\b(?:" + "|".join(_GASTO_VERBS) + r")\b", re.I)

# Monto: 50, 1,200.50, $800, 800 dólares
_AMOUNT_RE = re.compile(
    r"(?:\$\s*)?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
    r"\s*(?:d[óo]lares?|usd|dolar|pesos|euros?|\$)?",
    re.I,
)

# Consultas / análisis (no registran).
_QUERY_PATTERNS: tuple[str, ...] = (
    r"\bc[óo]mo\s+voy\b",
    r"\bc[óo]mo\s+van\s+mis\s+finanzas\b",
    r"\bmis\s+finanzas\b",
    r"\bresumen\s+financiero\b",
    r"\bbalance\b",
    r"\bcu[áa]nto\s+(?:he\s+)?gast[ée]\b",
    r"\bcu[áa]nto\s+(?:he\s+)?llev[oa]\b",
    r"\bcu[áa]nto\s+(?:he\s+)?ingres[ée]\b",
    r"\bgastos?\s+del?\s+(?:mes|d[íi]a|semana|a[ñn]o)\b",
    r"\bmis\s+gastos\b",
    r"\bmis\s+ingresos\b",
    r"\bestado\s+de\s+cuenta\b",
    r"\breporte\s+(?:de\s+)?finanzas\b",
)

_ADVICE_PATTERNS: tuple[str, ...] = (
    r"\bplan\s+de\s+ahorro\b",
    r"\bc[óo]mo\s+(?:puedo\s+)?ahorr",
    r"\bayud[aá]me\s+a\s+ahorrar\b",
    r"\bconsejo\s+financiero\b",
    r"\bplan\s+financiero\b",
    r"\bpresupuesto\b",
)

_FINANCE_CONTEXT = re.compile(
    r"(finanzas|dinero|plata|gast|ingres|ahorr|presupuesto|balance|deuda|financ)", re.I
)

_TIME_TAIL_RE = re.compile(
    r"\s+(hoy|ayer|esta\s+ma[ñn]ana|esta\s+tarde|esta\s+noche|"
    r"este\s+mes|esta\s+semana|el\s+lunes|el\s+martes)\b.*$",
    re.I,
)


def _detect_period(text: str) -> str:
    t = (text or "").lower()
    if re.search(r"\bhoy\b", t):
        return "hoy"
    if re.search(r"\bsemana\b", t):
        return "semana"
    if re.search(r"\bmes\s+pasad", t):
        return "mes_pasado"
    if re.search(r"\ba[ñn]o\b", t):
        return "anio"
    if re.search(r"\b(todo|historial|siempre)\b", t):
        return "todo"
    return "mes"


def is_finance_write_intent(text: str) -> bool:
    """True si el texto declara un movimiento con monto (registrar)."""
    t = (text or "").strip()
    if len(t) < 6:
        return False
    has_verb = bool(_INGRESO_RE.search(t) or _GASTO_RE.search(t))
    if not has_verb:
        return False
    return _AMOUNT_RE.search(t) is not None


def is_finance_query_intent(text: str) -> bool:
    t = (text or "").strip().lower()
    if len(t) < 5:
        return False
    if any(re.search(p, t) for p in _QUERY_PATTERNS):
        return True
    if any(re.search(p, t) for p in _ADVICE_PATTERNS) and _FINANCE_CONTEXT.search(t):
        return True
    return False


def is_finance_intent(text: str) -> bool:
    return is_finance_write_intent(text) or is_finance_query_intent(text)


def parse_finance_statement(text: str) -> dict[str, object] | None:
    """Extrae tipo, monto, categoría y descripción de una frase conversacional."""
    t = (text or "").strip()
    if not t:
        return None
    amount_match = _AMOUNT_RE.search(t)
    if not amount_match:
        return None
    raw_amount = amount_match.group(1)
    # Normaliza separadores: "1,200.50" -> "1200.50"; "1.200,50" -> "1200.50"
    normalized = raw_amount
    if "," in normalized and "." in normalized:
        if normalized.rfind(",") > normalized.rfind("."):
            normalized = normalized.replace(".", "").replace(",", ".")
        else:
            normalized = normalized.replace(",", "")
    elif "," in normalized:
        parts = normalized.split(",")
        normalized = normalized.replace(",", ".") if len(parts[-1]) <= 2 else normalized.replace(",", "")

    is_ingreso = bool(_INGRESO_RE.search(t))
    is_gasto = bool(_GASTO_RE.search(t))
    if is_ingreso and not is_gasto:
        tx_type = "ingreso"
    elif is_gasto:
        tx_type = "gasto"
    else:
        return None

    category = None
    if tx_type == "gasto":
        m = re.search(r"\ben\s+(.+?)(?:$)", t, re.I)
    else:
        m = re.search(r"\b(?:de|por)\s+(?:un[ao]?\s+)?(.+?)(?:$)", t, re.I)
    if m:
        cat = _TIME_TAIL_RE.sub("", m.group(1)).strip(" .,")
        cat = re.sub(r"\s+", " ", cat)
        if 2 <= len(cat) <= 60:
            category = cat

    occurred_on = "ayer" if re.search(r"\bayer\b", t, re.I) else "hoy"

    return {
        "type": tx_type,
        "amount": normalized,
        "category": category,
        "description": t[:400],
        "occurred_on": occurred_on,
    }


def _confirm_spoken(saved: dict[str, object]) -> str:
    kind = "ingreso" if saved.get("type") == "ingreso" else "gasto"
    amount = saved.get("amount")
    currency = saved.get("currency", "USD")
    cat = saved.get("category")
    tail = f" en {cat}" if cat else ""
    verb = "Registré" if kind == "gasto" else "Anoté"
    return f"Señor, {verb} un {kind} de {amount} {currency}{tail}."


def handle_finance_query_sync(user_id: str, text: str) -> dict[str, str]:
    """Registra un movimiento o devuelve el resumen — usado por chat y voz."""
    try:
        if is_finance_write_intent(text):
            parsed = parse_finance_statement(text)
            if parsed:
                saved = save_transaction(
                    user_id,
                    tx_type=str(parsed["type"]),
                    amount=parsed["amount"],
                    category=parsed.get("category"),  # type: ignore[arg-type]
                    description=parsed.get("description"),  # type: ignore[arg-type]
                    occurred_on=parsed.get("occurred_on"),
                )
                if saved.get("ok"):
                    return {"spoken": _confirm_spoken(saved)}
                return {
                    "spoken": (
                        "Señor, no pude guardar el movimiento. "
                        "Revise que la base de datos de finanzas esté lista."
                    )
                }
        period = _detect_period(text)
        summary = summarize_finances(user_id, period=canonical_period(period))
        return {"spoken": format_summary_spoken(summary)}
    except Exception:  # noqa: BLE001
        logger.exception("[FINANCE] sync query failed user=%s", user_id[:8])
        return {"spoken": "Señor, no pude procesar su consulta de finanzas en este momento."}


class FinanceModule(BaseModule):
    name = "finance"

    async def activate(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        self._active = True
        return await self._run(user_id, user_text or transcript)

    async def handle_command(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        if is_finance_intent(user_text or transcript):
            return await self._run(user_id, user_text or transcript)
        return self._idle()

    async def _run(self, user_id: str, text: str) -> ModuleResult:
        import asyncio

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(handle_finance_query_sync, user_id, text),
                timeout=15.0,
            )
            return ModuleResult(
                ok=True, spoken=str(result.get("spoken") or ""), handles_response=True
            )
        except asyncio.TimeoutError:
            return ModuleResult(
                ok=False,
                spoken="Señor, la consulta de finanzas tardó demasiado. ¿La intento de nuevo?",
                handles_response=True,
            )
        except Exception:  # noqa: BLE001
            logger.exception("[FINANCE] query failed user=%s", user_id[:8])
            return ModuleResult(
                ok=False,
                spoken="Señor, no pude procesar sus finanzas en este momento.",
                handles_response=True,
            )
