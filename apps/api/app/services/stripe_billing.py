"""Stripe Checkout, webhooks y portal."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import stripe

from app.config import Settings, get_settings
from app.domain.plans import (
    FOUNDING_MEMBER_MAX_SLOTS,
    PLAN_LABELS,
    PLAN_PRICES_USD,
    RECHARGE_CLIENT_SHARE,
    RECHARGE_QUICK_AMOUNTS_USD,
    STRIPE_CHECKOUT_PLANS,
    PlanId,
    get_plan_limits,
    normalize_plan_id,
    plan_minutes_daily,
    quote_recharge,
)
from app.domain.video_edit_economy import quote_video_edit_pack
from app.services import supabase_db

logger = logging.getLogger(__name__)

_ACTIVE_STRIPE_STATUSES = frozenset({"active", "trialing", "past_due"})


def _stripe_enabled(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(s.stripe_secret_key.strip())


def _configure_stripe(settings: Settings | None = None) -> None:
    s = settings or get_settings()
    stripe.api_key = s.stripe_secret_key.strip()


def price_id_for_plan(plan_id: str, settings: Settings | None = None) -> str | None:
    s = settings or get_settings()
    pid = normalize_plan_id(plan_id)
    mapping = {
        PlanId.CIERRE.value: s.stripe_price_cierre.strip(),
        PlanId.STARTER.value: s.stripe_price_starter.strip(),
        PlanId.PRO.value: s.stripe_price_pro.strip(),
        PlanId.ELITE.value: s.stripe_price_elite.strip(),
        PlanId.FOUNDING.value: (
            s.stripe_price_founding.strip() or s.stripe_price_elite_founding.strip()
        ),
    }
    return mapping.get(pid) or None


def ensure_stripe_plan_price(plan_id: str, settings: Settings | None = None) -> str:
    """Devuelve price_id; si falta env para CED Cierre, crea Product+Price en Stripe."""
    s = settings or get_settings()
    pid = normalize_plan_id(plan_id)
    existing = price_id_for_plan(pid, s)
    if existing:
        return existing
    if pid != PlanId.CIERRE.value:
        raise ValueError(f"Price ID Stripe no configurado para plan {pid}.")
    if not _stripe_enabled(s):
        raise ValueError("Stripe no configurado (STRIPE_SECRET_KEY).")

    _configure_stripe(s)
    amount = int(PLAN_PRICES_USD[PlanId.CIERRE.value]) * 100
    label = PLAN_LABELS.get(PlanId.CIERRE.value, "CED PM International")
    description = (
        "Cerrador de clientes PM International / FitLine con voz Jarvis. "
        "Conocimiento de producto, objeciones y cierre estratégico."
    )

    for product in stripe.Product.list(limit=100, active=True).auto_paging_iter():
        meta = product.metadata or {}
        if meta.get("ced_plan_id") != PlanId.CIERRE.value:
            continue
        for price in stripe.Price.list(product=product.id, active=True, limit=20):
            recurring = getattr(price, "recurring", None)
            if (
                recurring
                and getattr(recurring, "interval", None) == "month"
                and int(price.unit_amount or 0) == amount
            ):
                logger.info(
                    "stripe cierre price reused product=%s price=%s",
                    product.id,
                    price.id,
                )
                return str(price.id)
        price = stripe.Price.create(
            product=product.id,
            unit_amount=amount,
            currency="usd",
            recurring={"interval": "month"},
            metadata={"ced_plan_id": PlanId.CIERRE.value},
            nickname=label,
        )
        logger.info("stripe cierre price created on existing product=%s price=%s", product.id, price.id)
        return str(price.id)

    product = stripe.Product.create(
        name=label,
        description=description,
        metadata={"ced_plan_id": PlanId.CIERRE.value},
    )
    price = stripe.Price.create(
        product=product.id,
        unit_amount=amount,
        currency="usd",
        recurring={"interval": "month"},
        metadata={"ced_plan_id": PlanId.CIERRE.value},
        nickname=label,
    )
    logger.info("stripe cierre product+price created product=%s price=%s", product.id, price.id)
    return str(price.id)


def price_id_for_recharge(amount_usd: float, settings: Settings | None = None) -> str | None:
    s = settings or get_settings()
    amount = int(round(float(amount_usd)))
    mapping = {
        10: s.stripe_price_recharge_10.strip(),
        20: s.stripe_price_recharge_20.strip(),
        40: s.stripe_price_recharge_40.strip(),
        50: s.stripe_price_recharge_50.strip(),
        100: s.stripe_price_recharge_100.strip(),
    }
    return mapping.get(amount) or None


def _apply_wallet_checkout_params(params: dict[str, Any]) -> dict[str, Any]:
    """Evita el bloqueo de Apple Pay: «actualiza el domicilio de facturación».

    Si Checkout pide dirección y el Customer de Stripe ya existe (a menudo sin
    calle/CP), Wallet no puede completar el pago. `auto` solo pide dirección
    cuando hace falta (impuestos) y `customer_update` deja que Apple Pay
    rellene nombre y domicilio en el Customer.
    """
    params["billing_address_collection"] = "auto"
    if params.get("customer"):
        params["customer_update"] = {
            "address": "auto",
            "name": "auto",
        }
    return params


def founding_slots_available(settings: Settings | None = None) -> tuple[int, int]:
    s = settings or get_settings()
    used, max_slots = supabase_db.get_founding_slots()
    cap = s.founding_slots_max or max_slots or FOUNDING_MEMBER_MAX_SLOTS
    return used, cap


def create_subscription_checkout(user_id: str, email: str, plan_id: str) -> dict[str, str]:
    settings = get_settings()
    if not _stripe_enabled(settings):
        raise ValueError("Stripe no configurado (STRIPE_SECRET_KEY).")

    pid = normalize_plan_id(plan_id)
    if pid not in STRIPE_CHECKOUT_PLANS:
        raise ValueError(f"Plan no válido para checkout: {plan_id}")

    if pid == PlanId.FOUNDING.value:
        used, cap = founding_slots_available(settings)
        if used >= cap:
            raise ValueError("Cupos Founding agotados.")

    try:
        price_id = ensure_stripe_plan_price(pid, settings)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    _configure_stripe(settings)
    web = settings.web_public_url.rstrip("/")
    sub = supabase_db.get_subscription(user_id) or {}
    customer_id = sub.get("stripe_customer_id")

    params: dict[str, Any] = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": f"{web}/dashboard?billing=success&plan={pid}&session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{web}/pricing?billing=cancelled",
        "client_reference_id": user_id,
        "metadata": {"user_id": user_id, "plan_id": pid, "checkout_type": "subscription"},
        "subscription_data": {"metadata": {"user_id": user_id, "plan_id": pid}},
    }
    if customer_id:
        params["customer"] = customer_id
    elif email:
        params["customer_email"] = email
    _apply_wallet_checkout_params(params)

    session = stripe.checkout.Session.create(**params)
    if not session.url:
        raise ValueError("Stripe no devolvió URL de checkout.")
    return {"url": session.url, "session_id": session.id}


def price_id_for_video_edit_pack(
    amount_usd: float, settings: Settings | None = None
) -> str | None:
    s = settings or get_settings()
    key = int(round(float(amount_usd)))
    mapping = {
        10: s.stripe_price_video_edit_10.strip(),
        20: s.stripe_price_video_edit_20.strip(),
        50: s.stripe_price_video_edit_50.strip(),
    }
    pid = mapping.get(key) or ""
    return pid or None


def create_video_edit_token_checkout(
    user_id: str, email: str, amount_usd: float
) -> dict[str, str]:
    """Pack de tokens Video Edit — crédito 1:1 ($1 = 100 tokens)."""
    settings = get_settings()
    if not _stripe_enabled(settings):
        raise ValueError("Stripe no configurado (STRIPE_SECRET_KEY).")

    quote = quote_video_edit_pack(amount_usd)
    paid = float(quote["amount_paid_usd"])
    tokens = int(quote["tokens"])
    _configure_stripe(settings)
    web = settings.web_public_url.rstrip("/")
    sub = supabase_db.get_subscription(user_id) or {}
    customer_id = sub.get("stripe_customer_id")

    price_id = price_id_for_video_edit_pack(paid, settings)
    if price_id:
        line_items = [{"price": price_id, "quantity": 1}]
    else:
        line_items = [
            {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": int(round(paid * 100)),
                    "product_data": {
                        "name": f"CED Video Edit — {tokens} tokens",
                        "description": (
                            f"{tokens} tokens de edición de video "
                            f"(1 token = 1 segundo; mín. 30s por render)"
                        ),
                    },
                },
                "quantity": 1,
            }
        ]

    params: dict[str, Any] = {
        "mode": "payment",
        "line_items": line_items,
        "success_url": (
            f"{web}/dashboard?billing=video_edit_success"
            f"&amount={paid:.0f}&tokens={tokens}&videoEditModule=pilot"
        ),
        "cancel_url": f"{web}/dashboard?billing=video_edit_cancelled&videoEditModule=pilot",
        "client_reference_id": user_id,
        "metadata": {
            "user_id": user_id,
            "checkout_type": "video_edit_tokens",
            "amount_paid_usd": str(paid),
            "tokens": str(tokens),
        },
    }
    if customer_id:
        params["customer"] = customer_id
    elif email:
        params["customer_email"] = email
    _apply_wallet_checkout_params(params)

    session = stripe.checkout.Session.create(**params)
    if not session.url:
        raise ValueError("Stripe no devolvió URL de checkout.")
    return {
        "url": session.url,
        "session_id": session.id,
        "quote": quote,
    }


def create_recharge_checkout(user_id: str, email: str, amount_usd: float) -> dict[str, str]:
    settings = get_settings()
    if not _stripe_enabled(settings):
        raise ValueError("Stripe no configurado (STRIPE_SECRET_KEY).")

    quote = quote_recharge(amount_usd)
    paid = float(quote["amount_paid_usd"])
    _configure_stripe(settings)
    web = settings.web_public_url.rstrip("/")
    sub = supabase_db.get_subscription(user_id) or {}
    customer_id = sub.get("stripe_customer_id")

    price_id = price_id_for_recharge(paid, settings)
    if price_id:
        line_items = [{"price": price_id, "quantity": 1}]
    else:
        line_items = [
            {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": int(round(paid * 100)),
                    "product_data": {"name": f"CED Recarga ${paid:.0f}"},
                },
                "quantity": 1,
            }
        ]

    recharge_meta = {
        "user_id": user_id,
        "email": (email or "").strip(),
        "checkout_type": "recharge",
        "amount_paid_usd": str(paid),
        "client_balance_usd": str(quote["client_balance_usd"]),
    }
    params: dict[str, Any] = {
        "mode": "payment",
        "line_items": line_items,
        "success_url": (
            f"{web}/dashboard?billing=recharge_success&amount={paid:.0f}"
            "&session_id={CHECKOUT_SESSION_ID}"
        ),
        "cancel_url": f"{web}/dashboard?billing=recharge_cancelled",
        "client_reference_id": user_id,
        "metadata": recharge_meta,
        "payment_intent_data": {"metadata": recharge_meta},
    }
    if customer_id:
        params["customer"] = customer_id
    elif email:
        params["customer_email"] = email
    _apply_wallet_checkout_params(params)

    session = stripe.checkout.Session.create(**params)
    if not session.url:
        raise ValueError("Stripe no devolvió URL de checkout.")
    return {"url": session.url, "session_id": session.id}


def create_portal_session(user_id: str) -> dict[str, str]:
    settings = get_settings()
    if not _stripe_enabled(settings):
        raise ValueError("Stripe no configurado.")
    sub = supabase_db.get_subscription(user_id) or {}
    customer_id = sub.get("stripe_customer_id")
    if not customer_id:
        raise ValueError("No hay cliente Stripe asociado.")

    _configure_stripe(settings)
    web = settings.web_public_url.rstrip("/")
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{web}/dashboard",
    )
    return {"url": session.url}


def verify_webhook(payload: bytes, sig_header: str | None) -> dict[str, Any]:
    settings = get_settings()
    secret = settings.stripe_webhook_secret.strip()
    if not secret:
        raise ValueError("STRIPE_WEBHOOK_SECRET no configurado.")
    return stripe.Webhook.construct_event(payload, sig_header or "", secret)


def _period_end_iso(raw: Any) -> str | None:
    if raw is None:
        return None
    try:
        return datetime.fromtimestamp(int(raw), tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def _resolve_user_id(
    metadata: dict[str, Any],
    client_ref: str | None,
    session: dict[str, Any] | None = None,
) -> str | None:
    uid = (metadata.get("user_id") or client_ref or "").strip()
    if uid:
        return uid
    sess = session or {}
    customer_id = str(sess.get("customer") or "").strip()
    if customer_id:
        found = supabase_db.get_user_id_by_stripe_customer(customer_id)
        if found:
            return found
    details = sess.get("customer_details") or {}
    email = str(
        details.get("email")
        or sess.get("customer_email")
        or metadata.get("email")
        or ""
    ).strip()
    if email:
        found = supabase_db.get_user_id_by_email(email)
        if found:
            logger.info("[STRIPE] user resuelto por email=%s", email)
            return found
    return None


def handle_stripe_event(event: dict[str, Any]) -> None:
    event_id = str(event.get("id") or "")
    if event_id and supabase_db.stripe_event_processed(event_id):
        logger.info("[STRIPE] evento duplicado ignorado %s", event_id)
        return

    event_type = event.get("type", "")
    data = (event.get("data") or {}).get("object") or {}

    if event_type == "checkout.session.completed":
        _handle_checkout_completed(data, event_id)
    elif event_type == "payment_intent.succeeded":
        _handle_payment_intent_succeeded(data, event_id)
    elif event_type in ("customer.subscription.created", "customer.subscription.updated"):
        _handle_subscription_updated(data, event_id)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(data, event_id)
    elif event_type == "invoice.payment_failed":
        _handle_payment_failed(data, event_id)
    elif event_type == "charge.refunded":
        _handle_charge_refunded(data, event_id)
    else:
        logger.debug("[STRIPE] evento ignorado: %s", event_type)


def _handle_payment_intent_succeeded(pi: dict[str, Any], event_id: str) -> None:
    """Backup si checkout.session.completed falló o no llegó."""
    metadata = pi.get("metadata") or {}
    if str(metadata.get("checkout_type") or "").strip() != "recharge":
        return
    user_id = _resolve_user_id(metadata, None, None)
    if not user_id:
        logger.error(
            "[STRIPE] PI recarga sin user_id pi=%s email=%s",
            pi.get("id"),
            metadata.get("email"),
        )
        return
    paid = 0.0
    if metadata.get("amount_paid_usd"):
        try:
            paid = float(metadata.get("amount_paid_usd") or 0)
        except (TypeError, ValueError):
            paid = 0.0
    if paid <= 0 and pi.get("amount_received"):
        paid = float(pi["amount_received"]) / 100.0
    if paid <= 0 and pi.get("amount"):
        paid = float(pi["amount"]) / 100.0
    if int(round(paid)) not in {10, 20, 40, 50, 100}:
        return
    q = quote_recharge(paid)
    ok = supabase_db.credit_recharge_balance(
        user_id,
        amount_paid_usd=float(q["amount_paid_usd"]),
        client_balance_usd=float(q["client_balance_usd"]),
        margin_keini_usd=float(q["margin_keini_usd"]),
        stripe_payment_intent_id=_payment_intent_id(pi.get("id") or pi),
        stripe_event_id=event_id,
    )
    try:
        supabase_db.expire_trial_if_needed(user_id)
    except Exception:  # noqa: BLE001
        pass
    logger.info(
        "[STRIPE] PI recarga %s user=%s paid=%.2f",
        "ok" if ok else "FAIL",
        user_id[:8],
        float(q["amount_paid_usd"]),
    )
    if not ok:
        raise RuntimeError(f"PI credit_recharge failed user={user_id[:8]}")


def confirm_checkout_session(session_id: str, user_id: str) -> dict[str, Any]:
    """Cliente vuelve de Stripe: acredita si el webhook aún no lo hizo."""
    sid = (session_id or "").strip()
    uid = (user_id or "").strip()
    if not sid or not uid:
        raise ValueError("session_id y user_id requeridos.")
    settings = get_settings()
    if not _stripe_enabled(settings):
        raise ValueError("Stripe no configurado.")
    _configure_stripe(settings)
    session = stripe.checkout.Session.retrieve(sid)
    sess = session.to_dict() if hasattr(session, "to_dict") else dict(session)
    payment_status = str(sess.get("payment_status") or "")
    if payment_status not in ("paid", "no_payment_required"):
        return {"ok": False, "status": payment_status, "credited": False}

    owner = _resolve_user_id(
        sess.get("metadata") or {},
        sess.get("client_reference_id"),
        sess,
    )
    if owner and owner != uid:
        raise ValueError("Esta sesión de pago no pertenece a tu cuenta.")
    if not owner:
        # Forzar user_id del cliente autenticado si Stripe no trae metadata.
        meta = dict(sess.get("metadata") or {})
        meta["user_id"] = uid
        sess["metadata"] = meta
        sess["client_reference_id"] = uid

    event_id = f"confirm_{sid}"
    _handle_checkout_completed(sess, event_id)
    bal = supabase_db.get_recharge_balance_usd(uid)
    sub = supabase_db.get_subscription(uid) or {}
    return {
        "ok": True,
        "credited": True,
        "payment_status": payment_status,
        "checkout_type": (sess.get("metadata") or {}).get("checkout_type"),
        "recharge_balance_usd": round(bal, 2),
        "plan_id": sub.get("plan_id"),
        "subscription_status": sub.get("status"),
    }


def _payment_intent_id(raw: Any) -> str | None:
    """Stripe a veces manda el PI como string y a veces como objeto expandido."""
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw.strip() or None
    if isinstance(raw, dict):
        pid = str(raw.get("id") or "").strip()
        return pid or None
    pid = str(raw).strip()
    return pid or None


def _handle_checkout_completed(session: dict[str, Any], event_id: str) -> None:
    metadata = session.get("metadata") or {}
    checkout_type = str(metadata.get("checkout_type") or "").strip()
    pi_obj = session.get("payment_intent")
    if isinstance(pi_obj, dict):
        metadata = {**(pi_obj.get("metadata") or {}), **metadata}
    pi_id = _payment_intent_id(pi_obj)
    user_id = _resolve_user_id(metadata, session.get("client_reference_id"), session)
    customer_id = session.get("customer")
    mode = str(session.get("mode") or "")
    paid_guess = 0.0
    if metadata.get("amount_paid_usd"):
        try:
            paid_guess = float(metadata.get("amount_paid_usd") or 0)
        except (TypeError, ValueError):
            paid_guess = 0.0
    if paid_guess <= 0 and session.get("amount_total"):
        paid_guess = float(session["amount_total"]) / 100.0
    looks_like_recharge = checkout_type == "recharge" or (
        mode == "payment"
        and checkout_type not in ("video_edit_tokens",)
        and int(round(paid_guess)) in {10, 20, 40, 50, 100}
    )

    if looks_like_recharge:
        if not user_id:
            logger.error(
                "[STRIPE] recarga sin user_id session=%s email=%s pi=%s",
                session.get("id"),
                (session.get("customer_details") or {}).get("email"),
                (pi_id or "")[:24],
            )
            return
        paid = paid_guess
        if paid <= 0 and session.get("amount_total"):
            paid = float(session["amount_total"]) / 100.0
        q = quote_recharge(paid)
        ok = supabase_db.credit_recharge_balance(
            user_id,
            amount_paid_usd=float(q["amount_paid_usd"]),
            client_balance_usd=float(q["client_balance_usd"]),
            margin_keini_usd=float(q["margin_keini_usd"]),
            stripe_payment_intent_id=pi_id,
            stripe_event_id=event_id,
        )
        # Si el trial ya venció, bajar a free_basic para que el monedero abra voz.
        try:
            supabase_db.expire_trial_if_needed(user_id)
        except Exception:  # noqa: BLE001
            logger.warning(
                "[STRIPE] expire_trial tras recarga falló user=%s",
                user_id[:8],
                exc_info=True,
            )
        if customer_id:
            supabase_db.update_subscription_stripe_customer(user_id, str(customer_id))
        logger.info(
            "[STRIPE] recarga %s user=%s paid=%.2f credit=%.2f pi=%s",
            "ok" if ok else "FAIL",
            user_id[:8],
            float(q["amount_paid_usd"]),
            float(q["client_balance_usd"]),
            (pi_id or "")[:24],
        )
        if not ok:
            # 500 → Stripe reintenta el webhook (antes se tragaba el error).
            raise RuntimeError(
                f"credit_recharge_balance failed user={user_id[:8]} pi={pi_id}"
            )
        return

    if checkout_type == "video_edit_tokens" and user_id:
        paid = float(metadata.get("amount_paid_usd") or 0)
        if paid <= 0 and session.get("amount_total"):
            paid = float(session["amount_total"]) / 100.0
        q = quote_video_edit_pack(paid)
        from app.services.video_edit_pilot.tokens import credit_from_pack_usd

        credit_from_pack_usd(
            user_id,
            float(q["amount_paid_usd"]),
            metadata={
                "stripe_payment_intent_id": pi_id,
                "stripe_event_id": event_id,
                "checkout_session": session.get("id"),
            },
        )
        supabase_db.record_transaction(
            user_id=user_id,
            tx_type="video_edit_tokens",
            amount_usd=float(q["amount_paid_usd"]),
            stripe_event_id=event_id,
            metadata={
                "tokens": q["tokens"],
                "checkout_session": session.get("id"),
            },
        )
        if customer_id:
            supabase_db.update_subscription_stripe_customer(user_id, str(customer_id))
        return

    subscription_id = session.get("subscription")
    plan_id = normalize_plan_id(metadata.get("plan_id"))
    if user_id and subscription_id:
        if customer_id:
            supabase_db.update_subscription_stripe_customer(user_id, str(customer_id))
        _sync_stripe_subscription(user_id, str(subscription_id), plan_id_hint=plan_id)
        supabase_db.record_transaction(
            user_id=user_id,
            tx_type="subscription",
            amount_usd=float(PLAN_PRICES_USD.get(plan_id, 0)),
            stripe_event_id=event_id,
            metadata={"checkout_session": session.get("id"), "plan_id": plan_id},
        )


def _plan_from_stripe_subscription(sub: dict[str, Any], hint: str | None) -> str:
    if hint and hint in STRIPE_CHECKOUT_PLANS:
        return normalize_plan_id(hint)
    meta = sub.get("metadata") or {}
    if meta.get("plan_id"):
        return normalize_plan_id(str(meta["plan_id"]))
    items = (sub.get("items") or {}).get("data") or []
    if items:
        price_id = ((items[0].get("price") or {}).get("id") or "").strip()
        settings = get_settings()
        for pid in STRIPE_CHECKOUT_PLANS:
            if price_id_for_plan(pid, settings) == price_id:
                return pid
    return PlanId.ELITE.value


def _sync_stripe_subscription(
    user_id: str,
    stripe_subscription_id: str,
    *,
    plan_id_hint: str | None = None,
) -> None:
    _configure_stripe()
    sub = stripe.Subscription.retrieve(stripe_subscription_id)
    plan_id = _plan_from_stripe_subscription(sub, plan_id_hint)
    status = str(sub.get("status") or "active")
    is_founding = plan_id == PlanId.FOUNDING.value

    if is_founding:
        supabase_db.claim_founding_slot(user_id)

    minutes = plan_minutes_daily(plan_id)
    supabase_db.upsert_paid_subscription(
        user_id=user_id,
        plan_id=plan_id,
        status=status if status in _ACTIVE_STRIPE_STATUSES else status,
        stripe_subscription_id=stripe_subscription_id,
        stripe_customer_id=str(sub.get("customer") or "") or None,
        current_period_end=_period_end_iso(sub.get("current_period_end")),
        price_locked_for_life=is_founding,
        minutes_daily=minutes,
    )
    if is_founding:
        supabase_db.mark_founding_profile(user_id, PLAN_PRICES_USD[PlanId.FOUNDING.value])


def _handle_subscription_updated(subscription: dict[str, Any], event_id: str) -> None:
    customer_id = subscription.get("customer")
    if not customer_id:
        return
    user_id = supabase_db.get_user_id_by_stripe_customer(str(customer_id))
    if not user_id:
        meta = subscription.get("metadata") or {}
        user_id = meta.get("user_id")
    if not user_id:
        logger.warning("[STRIPE] subscription.updated sin user_id")
        return

    plan_id = _plan_from_stripe_subscription(subscription, None)
    status = str(subscription.get("status") or "inactive")
    is_founding = plan_id == PlanId.FOUNDING.value

    supabase_db.upsert_paid_subscription(
        user_id=str(user_id),
        plan_id=plan_id,
        status=status,
        stripe_subscription_id=str(subscription.get("id") or ""),
        stripe_customer_id=str(customer_id),
        current_period_end=_period_end_iso(subscription.get("current_period_end")),
        price_locked_for_life=is_founding,
        minutes_daily=plan_minutes_daily(plan_id),
    )
    supabase_db.record_transaction(
        user_id=str(user_id),
        tx_type="subscription",
        amount_usd=float(PLAN_PRICES_USD.get(plan_id, 0)),
        stripe_event_id=event_id,
        metadata={"subscription_id": subscription.get("id"), "status": status},
    )


def _handle_subscription_deleted(subscription: dict[str, Any], event_id: str) -> None:
    customer_id = subscription.get("customer")
    if not customer_id:
        return
    user_id = supabase_db.get_user_id_by_stripe_customer(str(customer_id))
    if not user_id:
        return
    supabase_db.downgrade_to_free_basic(str(user_id))
    supabase_db.record_transaction(
        user_id=str(user_id),
        tx_type="subscription",
        amount_usd=0,
        stripe_event_id=event_id,
        metadata={"event": "subscription_deleted"},
    )


def _handle_payment_failed(invoice: dict[str, Any], event_id: str) -> None:
    customer_id = invoice.get("customer")
    if not customer_id:
        return
    user_id = supabase_db.get_user_id_by_stripe_customer(str(customer_id))
    if not user_id:
        return
    supabase_db.update_subscription_status(str(user_id), "past_due")


def _handle_charge_refunded(charge: dict[str, Any], event_id: str) -> None:
    metadata = charge.get("metadata") or {}
    user_id = metadata.get("user_id")
    if not user_id:
        return
    amount = float(charge.get("amount_refunded") or 0) / 100.0
    if amount > 0:
        supabase_db.debit_recharge_balance(str(user_id), amount * RECHARGE_CLIENT_SHARE)
        supabase_db.record_transaction(
            user_id=str(user_id),
            tx_type="refund",
            amount_usd=amount,
            stripe_event_id=event_id,
            metadata={"charge_id": charge.get("id")},
        )


def recharge_catalog(settings: Settings | None = None) -> list[dict[str, Any]]:
    s = settings or get_settings()
    out = []
    for amount in RECHARGE_QUICK_AMOUNTS_USD:
        q = quote_recharge(amount)
        out.append(
            {
                "amount_usd": amount,
                "price_id": price_id_for_recharge(amount, s),
                **q,
            }
        )
    return out
