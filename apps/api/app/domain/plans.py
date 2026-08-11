"""Planes CED — suscripciones + recargas."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PlanId(StrEnum):
    CIERRE = "cierre"
    STARTER = "starter"
    PRO = "pro"
    ELITE = "elite"
    FOUNDING = "founding"
    FREE_BASIC = "free_basic"
    # Legacy (compat)
    ELITE_FOUNDING = "elite_founding"
    ELITE_REGULAR = "elite_regular"


FOUNDING_MEMBER_MAX_SLOTS = 50
TRIAL_DAYS = 7
# Voz durante los 7 días de prueba — se renueva cada día (usage_logs es por
# fecha). Al día 8 el usuario cae a free_basic (voice_enabled=False, 0 min).
TRIAL_VOICE_MINUTES_PER_DAY = 5
# Funnel FitLine / CED Cierre: 20 min de voz en una sola ventana de 24 h,
# luego debe pagar (no es el trial de 7 días).
CIERRE_TRIAL_HOURS = 24
CIERRE_TRIAL_VOICE_MINUTES = 20
CIERRE_TRIAL_OFFER = "cierre"
USAGE_WARNING_PERCENT = 80

# Costo unitario de recarga (monedero multi-recurso) — aprobado Keini 2026-07
VOICE_COST_PER_MIN_USD = 0.10
IMAGE_STD_COST_USD = 0.10
IMAGE_HD_COST_USD = 0.16
# Ideogram 4.0 Turbo ($0.03 costo real) — texto legible en imagen (aprobado Keini 2026-07)
IMAGE_TEXT_COST_USD = 0.06
WEB_SEARCH_COST_USD = 0.01
PDF_COST_USD = 0.05
VISION_COST_USD = 0.03
ADVANCED_TURN_COST_USD = 0.05
MAPS_ROUTE_COST_USD = 0.02

# Alias: 1 h voz = 60 * $0.10
OPENAI_VOICE_COST_PER_HOUR_USD = VOICE_COST_PER_MIN_USD * 60.0
GEMINI_COST_PER_HOUR_USD = OPENAI_VOICE_COST_PER_HOUR_USD
RECHARGE_MARGIN_KEINI = 0.40
RECHARGE_CLIENT_SHARE = 0.60
RECHARGE_MIN_USD = 10
RECHARGE_MAX_USD = 500
RECHARGE_QUICK_AMOUNTS_USD = (10, 20, 40, 50, 100)

RESOURCE_UNIT_COSTS_USD: dict[str, float] = {
    "voice_min": VOICE_COST_PER_MIN_USD,
    "image_std": IMAGE_STD_COST_USD,
    "image_hd": IMAGE_HD_COST_USD,
    "image_text": IMAGE_TEXT_COST_USD,
    "web_search": WEB_SEARCH_COST_USD,
    "pdf": PDF_COST_USD,
    "vision": VISION_COST_USD,
    "advanced_turn": ADVANCED_TURN_COST_USD,
    "maps_route": MAPS_ROUTE_COST_USD,
}

# Minutos diarios Founding (cap margen — peor caso provider ≤ precio − $10)
FOUNDING_VOICE_CAP_MINUTES = 30

# COGS provider (peor caso) para planificar margen mínimo $10 sin subir precio.
# Voz: Retell+Cartesia+LLM proxy; imágenes Gemini std / HD; Ideogram Turbo; Tavily.
PROVIDER_COGS_VOICE_PER_MIN_USD = 0.06
# CED Cierre usa voz económica (Gemini Live–style), no Retell/Jarvis.
PROVIDER_COGS_VOICE_CIERRE_PER_MIN_USD = 0.03
PROVIDER_COGS_IMAGE_STD_USD = 0.067  # Nano Banana 2 @ ~1K
PROVIDER_COGS_IMAGE_HD_USD = 0.101  # Nano Banana 2 @ ~2K
# Ideogram Turbo ~$0.03; GPT Image 1.5 medium ~$0.034 — usamos el techo para margen.
PROVIDER_COGS_IMAGE_TEXT_USD = 0.034
PROVIDER_COGS_WEB_SEARCH_USD = 0.008
MARGIN_BILLING_DAYS_PER_MONTH = 30
MIN_PLAN_MARGIN_USD = 10.0
# Cierre ($20) acepta margen ~$5–8 por diseño (voz barata + foco PM).
MIN_PLAN_MARGIN_CIERRE_USD = 5.0
# Cupo interno ~400 min/mes ≈ 13 min/día (no se muestra en copy público).
CIERRE_VOICE_MINUTES_PER_DAY = 13
CIERRE_VOICE_MINUTES_PER_MONTH = CIERRE_VOICE_MINUTES_PER_DAY * MARGIN_BILLING_DAYS_PER_MONTH

PLAN_PRICES_USD: dict[str, int] = {
    PlanId.CIERRE.value: 20,
    PlanId.STARTER.value: 30,
    PlanId.PRO.value: 59,
    PlanId.ELITE.value: 99,
    PlanId.FOUNDING.value: 149,
    PlanId.FREE_BASIC.value: 0,
    PlanId.ELITE_FOUNDING.value: 149,
    PlanId.ELITE_REGULAR.value: 99,
}

STRIPE_CHECKOUT_PLANS = frozenset(
    {
        PlanId.CIERRE.value,
        PlanId.STARTER.value,
        PlanId.PRO.value,
        PlanId.ELITE.value,
        PlanId.FOUNDING.value,
    }
)

# Planes con stack de voz económico (sin Retell/Jarvis).
PLAN_VOICE_STACK_GEMINI = frozenset({PlanId.CIERRE.value})
# Foco comercial PM International / FitLine.
PLAN_PM_FITLINE_FOCUS = frozenset({PlanId.CIERRE.value})


@dataclass(frozen=True)
class PlanLimits:
    voice_minutes_per_day: int
    web_searches_per_day: int  # -1 = ilimitado
    ai_images_standard_per_day: int
    ai_images_hd_per_day: int
    voice_enabled: bool
    camera_enabled: bool
    meta_social_enabled: bool
    prospection_enabled: bool
    pdf_reports: bool
    claude_messages_per_day: int  # -1 = ilimitado
    # -1 = ilimitado (planes pagados, sin cambios). Solo Básico usa un tope > 0
    # para dar PDF gratis de forma permanente sin abrir la puerta a abuso.
    pdf_reports_per_day: int = -1
    # Ideogram (texto legible en imagen) — 0 = sin acceso (Básico gratis, aprobado
    # Keini 2026-07: excluido por completo, solo Gemini + disclaimer + upsell suave).
    ai_images_text_per_day: int = 0

    @property
    def gemini_minutes_per_day(self) -> int:
        return self.voice_minutes_per_day

    @property
    def ai_images_per_month(self) -> int:
        std = self.ai_images_standard_per_day
        hd = self.ai_images_hd_per_day
        if std < 0 or hd < 0:
            return -1
        return std + hd

    # Alias legacy (antes era mensual; ahora la cuota real es diaria)
    @property
    def ai_images_standard_per_month(self) -> int:
        return self.ai_images_standard_per_day

    @property
    def ai_images_hd_per_month(self) -> int:
        return self.ai_images_hd_per_day


# Límites calibrados a margen mínimo $10/mes (peor caso provider, 30 días).
# Nano Banana 2 (gemini-3.1-flash-image): ~$0.067 std / ~$0.101 HD — cupos
# diarios recortados vs. el accounting antiguo ($0.01/$0.02) para no romper margen.
PLAN_LIMITS: dict[str, PlanLimits] = {
    # CED Cierre — experto PM/FitLine, voz económica (~400 min/mes internos).
    # Cupos lean: margen ~$7 con COGS voz Gemini ($0.03/min), sin Retell.
    PlanId.CIERRE.value: PlanLimits(
        voice_minutes_per_day=CIERRE_VOICE_MINUTES_PER_DAY,
        web_searches_per_day=5,
        ai_images_standard_per_day=0,
        ai_images_hd_per_day=0,
        voice_enabled=True,
        camera_enabled=False,
        meta_social_enabled=True,
        prospection_enabled=True,
        pdf_reports=True,
        claude_messages_per_day=40,
        ai_images_text_per_day=0,
    ),
    PlanId.STARTER.value: PlanLimits(
        voice_minutes_per_day=5,
        web_searches_per_day=15,
        ai_images_standard_per_day=3,
        ai_images_hd_per_day=0,
        voice_enabled=True,
        camera_enabled=False,
        meta_social_enabled=False,
        prospection_enabled=False,
        pdf_reports=False,
        claude_messages_per_day=-1,
        ai_images_text_per_day=1,
    ),
    PlanId.PRO.value: PlanLimits(
        voice_minutes_per_day=12,
        web_searches_per_day=-1,
        ai_images_standard_per_day=6,
        ai_images_hd_per_day=1,
        voice_enabled=True,
        camera_enabled=True,
        meta_social_enabled=True,
        prospection_enabled=False,
        pdf_reports=True,
        claude_messages_per_day=-1,
        ai_images_text_per_day=3,
    ),
    PlanId.ELITE.value: PlanLimits(
        voice_minutes_per_day=20,
        web_searches_per_day=-1,
        ai_images_standard_per_day=14,
        ai_images_hd_per_day=3,
        voice_enabled=True,
        camera_enabled=True,
        meta_social_enabled=True,
        prospection_enabled=True,
        pdf_reports=True,
        claude_messages_per_day=-1,
        ai_images_text_per_day=5,
    ),
    PlanId.FOUNDING.value: PlanLimits(
        voice_minutes_per_day=FOUNDING_VOICE_CAP_MINUTES,
        web_searches_per_day=-1,
        ai_images_standard_per_day=24,
        ai_images_hd_per_day=6,
        voice_enabled=True,
        camera_enabled=True,
        meta_social_enabled=True,
        prospection_enabled=True,
        pdf_reports=True,
        claude_messages_per_day=-1,
        ai_images_text_per_day=8,
    ),
    # Básico permanente (post-trial): SIN voz, siempre. Blindado a propósito —
    # el trial de 7 días ya dio 5 min/día vía TRIAL_VOICE_MINUTES_PER_DAY
    # (get_user_access status=="trialing"); una vez ese trial vence, la
    # suscripción cae a este plan y voice_enabled=False corta la voz a 0 sin
    # excepción, para que nadie use voz gratis indefinidamente sin pagar.
    # Imágenes y PDF SÍ quedan gratis de forma permanente (muestra continua de
    # capacidades CED, aprobado Keini 2026-07) con tope diario bajo — COGS
    # real Nano Banana 2 (~$0.067/img) sigue acotado a 2/día.
    PlanId.FREE_BASIC.value: PlanLimits(
        voice_minutes_per_day=0,
        web_searches_per_day=0,
        ai_images_standard_per_day=2,
        ai_images_hd_per_day=0,
        voice_enabled=False,
        camera_enabled=False,
        meta_social_enabled=False,
        prospection_enabled=False,
        pdf_reports=True,
        claude_messages_per_day=50,
        pdf_reports_per_day=1,
        ai_images_text_per_day=0,
    ),
}

PLAN_LIMITS[PlanId.ELITE_FOUNDING.value] = PLAN_LIMITS[PlanId.FOUNDING.value]
PLAN_LIMITS[PlanId.ELITE_REGULAR.value] = PLAN_LIMITS[PlanId.ELITE.value]

PLAN_LABELS: dict[str, str] = {
    PlanId.CIERRE.value: "CED Cierre",
    PlanId.STARTER.value: "CED Starter",
    PlanId.PRO.value: "CED Pro",
    PlanId.ELITE.value: "CED Élite",
    PlanId.FOUNDING.value: "CED Founding",
    PlanId.FREE_BASIC.value: "CED Básico Gratis",
    PlanId.ELITE_FOUNDING.value: "CED Founding",
    PlanId.ELITE_REGULAR.value: "CED Élite",
}


def normalize_plan_id(plan_id: str | None) -> str:
    pid = (plan_id or PlanId.FREE_BASIC.value).strip()
    if pid == PlanId.ELITE_FOUNDING.value:
        return PlanId.FOUNDING.value
    if pid == PlanId.ELITE_REGULAR.value:
        return PlanId.ELITE.value
    if pid in PLAN_LIMITS:
        return pid
    return PlanId.FREE_BASIC.value


def get_plan_limits(plan_id: str | None) -> PlanLimits:
    return PLAN_LIMITS[normalize_plan_id(plan_id)]


def plan_minutes_daily(plan_id: str | None) -> int:
    return get_plan_limits(plan_id).voice_minutes_per_day


def plan_uses_gemini_voice_stack(plan_id: str | None) -> bool:
    """True si el plan usa voz económica (sin Retell/Jarvis)."""
    return normalize_plan_id(plan_id) in PLAN_VOICE_STACK_GEMINI


def plan_voice_transport(plan_id: str | None) -> str:
    """Transporte de audio: ``openai`` (FitLine/Cierre) o ``retell`` (Jarvis premium)."""
    if plan_uses_gemini_voice_stack(plan_id):
        return "openai"
    return "retell"


def plan_is_pm_fitline_focus(plan_id: str | None) -> bool:
    return normalize_plan_id(plan_id) in PLAN_PM_FITLINE_FOCUS


def is_cierre_fitline_trial(sub: dict | None) -> bool:
    """Trial corto FitLine: plan cierre + status trialing (ventana 24 h)."""
    if not sub:
        return False
    if str(sub.get("status") or "") != "trialing":
        return False
    return normalize_plan_id(sub.get("plan_id")) == PlanId.CIERRE.value


def trial_voice_minutes_for_subscription(sub: dict | None) -> int:
    if is_cierre_fitline_trial(sub):
        return CIERRE_TRIAL_VOICE_MINUTES
    return TRIAL_VOICE_MINUTES_PER_DAY


# Alias legacy
CED_ELITE = get_plan_limits(PlanId.ELITE.value)


def recharge_balance_to_bonus_minutes(balance_usd: float) -> float:
    """Minutos de voz equivalentes al monedero (balance ya es crédito neto 60%)."""
    if balance_usd <= 0 or VOICE_COST_PER_MIN_USD <= 0:
        return 0.0
    return round(float(balance_usd) / VOICE_COST_PER_MIN_USD, 2)


def quote_recharge(amount_usd: float) -> dict[str, float | bool | int]:
    paid = max(RECHARGE_MIN_USD, min(RECHARGE_MAX_USD, float(amount_usd)))
    client_balance = paid * RECHARGE_CLIENT_SHARE
    margin_keini = paid * RECHARGE_MARGIN_KEINI
    voice_mins = (
        client_balance / VOICE_COST_PER_MIN_USD if VOICE_COST_PER_MIN_USD else 0.0
    )
    extra_hours = voice_mins / 60.0
    return {
        "amount_paid_usd": round(paid, 2),
        "client_balance_usd": round(client_balance, 2),
        "margin_keini_usd": round(margin_keini, 2),
        "estimated_extra_hours": round(extra_hours, 2),
        "estimated_voice_minutes": int(voice_mins),
        "estimated_images_std": int(
            client_balance / IMAGE_STD_COST_USD if IMAGE_STD_COST_USD else 0
        ),
        "estimated_images_hd": int(
            client_balance / IMAGE_HD_COST_USD if IMAGE_HD_COST_USD else 0
        ),
        "estimated_web_searches": int(
            client_balance / WEB_SEARCH_COST_USD if WEB_SEARCH_COST_USD else 0
        ),
        "estimated_pdfs": int(client_balance / PDF_COST_USD if PDF_COST_USD else 0),
        "estimated_images_text": int(
            client_balance / IMAGE_TEXT_COST_USD if IMAGE_TEXT_COST_USD else 0
        ),
        "never_expires": True,
        "margin_percent_keini": RECHARGE_MARGIN_KEINI * 100,
        "voice_cost_per_min_usd": VOICE_COST_PER_MIN_USD,
    }


def unit_cost_usd(resource: str) -> float:
    return float(RESOURCE_UNIT_COSTS_USD.get(resource) or 0.0)


def estimate_plan_monthly_provider_cogs_usd(
    plan_id: str,
    *,
    include_web_searches: bool = True,
    web_search_cap_if_unlimited: int = 40,
) -> float:
    """COGS provider mensual si el usuario agota el cupo diario todos los días.

    web_searches=-1 (ilimitado) se modela con ``web_search_cap_if_unlimited``
    usos/día para poder acotar margen; la feature de producto sigue ilimitada.
    """
    pid = normalize_plan_id(plan_id)
    limits = get_plan_limits(pid)
    days = MARGIN_BILLING_DAYS_PER_MONTH
    voice_cogs = (
        PROVIDER_COGS_VOICE_CIERRE_PER_MIN_USD
        if plan_uses_gemini_voice_stack(pid)
        else PROVIDER_COGS_VOICE_PER_MIN_USD
    )
    voice = max(0, limits.voice_minutes_per_day) * days * voice_cogs
    img_std = (
        max(0, limits.ai_images_standard_per_day) * days * PROVIDER_COGS_IMAGE_STD_USD
    )
    img_hd = max(0, limits.ai_images_hd_per_day) * days * PROVIDER_COGS_IMAGE_HD_USD
    img_text = (
        max(0, limits.ai_images_text_per_day) * days * PROVIDER_COGS_IMAGE_TEXT_USD
    )
    web = 0.0
    if include_web_searches:
        web_day = limits.web_searches_per_day
        if web_day < 0:
            web_day = web_search_cap_if_unlimited
        web = max(0, web_day) * days * PROVIDER_COGS_WEB_SEARCH_USD
    return round(voice + img_std + img_hd + img_text + web, 2)


def estimate_plan_monthly_margin_usd(
    plan_id: str,
    *,
    include_web_searches: bool = True,
    web_search_cap_if_unlimited: int = 40,
) -> float:
    pid = normalize_plan_id(plan_id)
    price = float(PLAN_PRICES_USD.get(pid) or 0)
    cogs = estimate_plan_monthly_provider_cogs_usd(
        pid,
        include_web_searches=include_web_searches,
        web_search_cap_if_unlimited=web_search_cap_if_unlimited,
    )
    return round(price - cogs, 2)


def public_plans_catalog() -> list[dict]:
    order = (
        PlanId.CIERRE,
        PlanId.STARTER,
        PlanId.PRO,
        PlanId.ELITE,
        PlanId.FOUNDING,
    )
    out: list[dict] = []
    for pid in order:
        limits = PLAN_LIMITS[pid.value]
        out.append(
            {
                "id": pid.value,
                "label": PLAN_LABELS[pid.value],
                "price_usd": PLAN_PRICES_USD[pid.value],
                "minutes_per_day": limits.voice_minutes_per_day,
                "web_searches_per_day": limits.web_searches_per_day,
                "ai_images_standard_per_day": limits.ai_images_standard_per_day,
                "ai_images_hd_per_day": limits.ai_images_hd_per_day,
                "ai_images_text_per_day": limits.ai_images_text_per_day,
                "voice_enabled": limits.voice_enabled,
                "camera_enabled": limits.camera_enabled,
                "meta_social_enabled": limits.meta_social_enabled,
                "prospection_enabled": limits.prospection_enabled,
                "pm_fitline_focus": plan_is_pm_fitline_focus(pid.value),
                "voice_stack": (
                    "gemini" if plan_uses_gemini_voice_stack(pid.value) else "retell"
                ),
                "voice_transport": plan_voice_transport(pid.value),
            }
        )
    return out
