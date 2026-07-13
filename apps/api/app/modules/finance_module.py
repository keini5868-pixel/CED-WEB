"""Módulo Finanzas Personales — registrar movimientos y consultar por voz/chat."""

from __future__ import annotations

import logging
import re

from app.modules.base_module import BaseModule
from app.modules.module_acks import MODULE_ACKS
from app.services.finance_ledger import (
    canonical_period,
    format_pending_spoken,
    format_summary_spoken,
    list_pending_payments,
    resolve_due_date,
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

# Monto: 50, 1,200.50, $800, 800 dólares, 1000
# La primera alternativa exige el separador de miles (+), si no "1000" se
# recortaría a "100" al matchear solo el primer grupo \d{1,3}. Sin separador,
# cae a la segunda alternativa \d+ que captura el entero completo.
_AMOUNT_RE = re.compile(
    r"(?:\$\s*)?(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
    r"\s*(?:d[óo]lares?|usd|dolar|pesos|euros?|\$)?",
    re.I,
)

# Consultas / análisis (no registran).
_QUERY_PATTERNS: tuple[str, ...] = (
    r"\bqu[ée]\s+tengo\s+en\s+finanzas\b",
    r"\bdame\s+un\s+reporte\b.*\bfinanzas\b",
    r"\bfinanzas\b.*\bdame\s+un\s+reporte\b",
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

# Pagos pendientes / programados (compromisos a futuro, no gastos ya hechos).
_PENDING_TRIGGER = re.compile(
    r"\b(tengo\s+que\s+pagar|debo\s+pagar|hay\s+que\s+pagar|tengo\s+un\s+pago|"
    r"tengo\s+que\s+tener|debo\s+tener|necesito\s+tener|tengo\s+que\s+juntar|"
    r"pago\s+pendiente|pagos?\s+pendientes?|por\s+pagar|dejar?\s+programad)\b",
    re.I,
)
_SCHEDULED_GASTO = re.compile(
    r"\b(?:guardar|registrar|anotar|programar|dejar)\s+(?:un\s+)?(?:gasto|pago)\b",
    re.I,
)
_FUTURE_SCHEDULE_HINT = re.compile(
    r"\b(?:para\s+(?:el\s+)?(?:d[ií]a\s+de\s+)?(?:ma[nñ]ana|pasado\s+ma[nñ]ana|"
    r"lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo|"
    r"la\s+pr[oó]xima\s+semana|el\s+pr[oó]ximo))\b",
    re.I,
)
# Categorías que en realidad son expresiones de tiempo (no una categoría real).
_TEMPORAL_CATEGORY = re.compile(
    r"^(?:d[íi]a|semana|mes|a[ñn]o|pr[óo]xim[oa]|que\s+viene|siguiente|"
    r"lunes|martes|mi[eé]rcoles|jueves|viernes|s[áa]bado|domingo|de|la|el|"
    r"\s)+$",
    re.I,
)
_PENDING_QUERY = re.compile(
    r"\b(pagos?\s+pendientes?|qu[eé]\s+(?:tengo\s+que|debo)\s+pagar|"
    r"cu[áa]nto\s+debo|qu[eé]\s+pagos?\s+tengo|mis\s+pagos)\b",
    re.I,
)
_DAY_TOKEN = re.compile(
    r"\b(hoy|ma[nñ]ana|pasado\s+ma[nñ]ana|lunes|martes|mi[eé]rcoles|jueves|"
    r"viernes|s[áa]bado|domingo|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b",
    re.I,
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


def is_finance_pending_query(text: str) -> bool:
    t = (text or "").strip()
    return bool(_PENDING_QUERY.search(t)) and not _AMOUNT_RE.search(t)


def is_finance_pending_write(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 8:
        return False
    return bool(_PENDING_TRIGGER.search(t)) and bool(_AMOUNT_RE.search(t))


def is_finance_future_write(text: str) -> bool:
    """Gasto/pago con fecha futura — pending aunque diga 'gasto de' o 'gasté'."""
    t = (text or "").strip()
    if is_finance_pending_write(t):
        return True
    if len(t) < 6 or not _AMOUNT_RE.search(t):
        return False
    rows = parse_pending_statements(t)
    return bool(rows and any(r.get("due_date") for r in rows))


def is_finance_breakdown_intent(text: str) -> bool:
    """Seguimiento: pedir desglose de una cifra o categorías del mes."""
    t = (text or "").strip().lower()
    if len(t) < 5:
        return False
    if re.search(r"\b(desglose|detall|desglosar|explica|explicar)\b", t):
        return True
    if re.search(r"\bde\s+qu[eé]\b", t) and re.search(
        r"\d|gastos?|incluye|son|es", t
    ):
        return True
    if re.search(r"\bqu[eé]\s+(son|es|incluye)\b", t) and re.search(r"\d", t):
        return True
    return False


def format_finance_breakdown_spoken(user_id: str, text: str) -> str:
    """Detalle por categoría y pagos pendientes del mes."""
    summary = summarize_finances(user_id, period=canonical_period("mes"))
    parts: list[str] = []
    top = summary.get("top_categories") or []
    if top:
        for cat, amt in top[:6]:
            parts.append(f"{cat} {_fmt_money_short(amt)}")
    pending_rows = summary.get("pending_rows") or []
    for row in pending_rows[:6]:
        try:
            amt = float(row.get("amount") or 0)
        except (TypeError, ValueError):
            amt = 0.0
        parts.append(
            f"pendiente {_fmt_money_short(amt)} el {_fmt_due_short(row.get('due_date'))}"
        )
    if not parts:
        return (
            "Señor, no encuentro un desglose para esa cifra en este mes. "
            "¿Quiere que revise otro período?"
        )
    total_gasto = float(summary.get("total_gasto") or 0)
    pending_gasto = float(summary.get("pending_gasto") or 0)
    intro = f"Señor, los gastos de este mes suman {_fmt_money_short(total_gasto)}"
    if pending_gasto:
        intro += f" más {_fmt_money_short(pending_gasto)} en pagos pendientes"
    return f"{intro}. Desglose: {'; '.join(parts)}."


def _fmt_money_short(value: float, currency: str = "USD") -> str:
    return f"{value:,.2f} {currency}"


def _fmt_due_short(due_raw: object) -> str:
    from app.services.finance_ledger import _fmt_due

    return _fmt_due(due_raw)


def is_finance_register_intent(text: str) -> bool:
    """True si el usuario pide registrar un movimiento (inmediato o futuro)."""
    return (
        is_finance_write_intent(text)
        or is_finance_pending_write(text)
        or is_finance_future_write(text)
    )


def is_finance_intent(text: str) -> bool:
    return (
        is_finance_register_intent(text)
        or is_finance_query_intent(text)
        or is_finance_pending_query(text)
        or is_finance_breakdown_intent(text)
    )


def parse_pending_statements(text: str) -> list[dict[str, object]]:
    """Extrae uno o varios compromisos de pago futuros de una frase.

    Ej: 'el lunes tengo que pagar 850, el miércoles 300, el viernes 300 para el mercado'
    """
    t = (text or "").strip()
    if not t:
        return []
    # Divide por cláusulas, pero NO por la coma de un separador de miles
    # (","seguida de dígito, ej. "1,200"): solo separa comas de enumeración.
    clauses = re.split(r"\s*(?:;|\by\b)\s*|,(?!\d)\s*", t)
    results: list[dict[str, object]] = []
    last_day: str | None = None
    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue
        amount_match = _AMOUNT_RE.search(clause)
        if not amount_match:
            continue
        raw_amount = amount_match.group(1)
        normalized = _normalize_amount_str(raw_amount)
        day_match = _DAY_TOKEN.search(clause)
        day_text = day_match.group(1) if day_match else last_day
        if day_match:
            last_day = day_match.group(1)
        due = resolve_due_date(day_text) if day_text else None
        cat_match = re.search(r"\b(?:para|de|en)\s+(?:el\s+|la\s+|un[ao]?\s+)?(.+?)$", clause, re.I)
        category = None
        if cat_match:
            cat = _TIME_TAIL_RE.sub("", cat_match.group(1)).strip(" .,")
            cat = _DAY_TOKEN.sub("", cat).strip(" .,")
            cat = _AMOUNT_RE.sub("", cat).strip(" .,")
            cat = re.sub(r"\s+", " ", cat).strip(" .,")
            # Descarta "categorías" que son solo expresiones de tiempo
            # (ej. "día de mañana", "día de la semana que viene").
            if (
                2 <= len(cat) <= 60
                and not _TEMPORAL_CATEGORY.match(cat)
                and not re.search(r"\b(d[ií]a\s+de|dolares?|usd)\b", cat, re.I)
            ):
                category = cat
        results.append(
            {
                "amount": normalized,
                "category": category,
                "due_date": due.isoformat() if due else None,
                "description": clause[:400],
            }
        )
    return results


def _normalize_amount_str(raw_amount: str) -> str:
    normalized = raw_amount
    if "," in normalized and "." in normalized:
        if normalized.rfind(",") > normalized.rfind("."):
            normalized = normalized.replace(".", "").replace(",", ".")
        else:
            normalized = normalized.replace(",", "")
    elif "," in normalized:
        parts = normalized.split(",")
        normalized = normalized.replace(",", ".") if len(parts[-1]) <= 2 else normalized.replace(",", "")
    return normalized


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


def _confirm_pending_spoken(saved: list[dict[str, object]]) -> str:
    if not saved:
        return "Señor, no entendí el pago pendiente. ¿Me lo repite con monto y día?"
    total = 0.0
    for s in saved:
        try:
            total += float(str(s.get("amount") or 0))
        except (TypeError, ValueError):
            pass
    if len(saved) == 1:
        from app.services.finance_ledger import _fmt_due

        s = saved[0]
        cat = s.get("category")
        cat_txt = f" para {cat}" if cat else ""
        due_raw = s.get("due_date")
        due = _fmt_due(due_raw) if due_raw else "la fecha indicada"
        return f"Señor, anoté un pago pendiente de {s.get('amount')}{cat_txt} para {due}."
    return (
        f"Señor, registré {len(saved)} pagos pendientes por un total de "
        f"{total:,.2f}. Se los recordaré."
    )


def handle_finance_read_sync(user_id: str, text: str) -> dict[str, str]:
    """Solo lectura para piloto nativo — escritura va por finance_prepare_write."""
    try:
        if is_finance_register_intent(text):
            return {
                "spoken": (
                    "Señor, para registrar un gasto, ingreso o pago pendiente, "
                    "dígame el monto y el concepto; le pediré confirmación antes de guardarlo."
                ),
            }

        if is_finance_pending_query(text):
            rows = list_pending_payments(user_id)
            return {"spoken": format_pending_spoken(rows)}

        if is_finance_breakdown_intent(text):
            return {"spoken": format_finance_breakdown_spoken(user_id, text)}

        period = _detect_period(text)
        summary = summarize_finances(user_id, period=canonical_period(period))
        return {"spoken": format_summary_spoken(summary)}
    except Exception:  # noqa: BLE001
        logger.exception("[FINANCE] read sync failed user=%s", user_id[:8])
        return {"spoken": "Señor, no pude procesar su consulta de finanzas en este momento."}


def handle_finance_query_sync(user_id: str, text: str) -> dict[str, str]:
    """Registra un movimiento o devuelve el resumen — usado por chat y voz."""
    try:
        if is_finance_pending_query(text):
            rows = list_pending_payments(user_id)
            return {"spoken": format_pending_spoken(rows)}

        if is_finance_breakdown_intent(text):
            return {"spoken": format_finance_breakdown_spoken(user_id, text)}

        if is_finance_future_write(text):
            statements = parse_pending_statements(text)
            saved_list: list[dict[str, object]] = []
            last_save_error = ""
            for st in statements:
                saved = save_transaction(
                    user_id,
                    tx_type="gasto",
                    amount=st["amount"],
                    category=st.get("category"),  # type: ignore[arg-type]
                    description=st.get("description"),  # type: ignore[arg-type]
                    status="pendiente",
                    due_date=st.get("due_date"),
                )
                if saved.get("ok"):
                    saved.setdefault("category", st.get("category"))
                    saved_list.append(saved)
                else:
                    last_save_error = str(saved.get("error") or last_save_error)
            if saved_list:
                return {"spoken": _confirm_pending_spoken(saved_list)}
            schema_hint = ""
            last_err = last_save_error
            if not last_err:
                from app.services.finance_schema import finance_db_error

                last_err = finance_db_error() or ""
            if last_err:
                schema_hint = f" Detalle: {last_err[:120]}."
            return {
                "spoken": (
                    "Señor, no pude guardar los pagos pendientes."
                    f"{schema_hint} "
                    "Si persiste, ejecute las migraciones 021 y 022 de finanzas en Supabase."
                ),
            }

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
        self._enter_active()
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
        if idle := self._guard_passive():
            return idle
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
                ok=True,
                spoken=str(result.get("spoken") or ""),
                handles_response=True,
                send_filler=True,
                filler=MODULE_ACKS.get("finance", "Revisando sus finanzas, señor."),
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
