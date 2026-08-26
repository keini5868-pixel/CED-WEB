"""Recargas: PI expandido, acreditación y monedero abre voz con trial vencido."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.domain.plans import quote_recharge, recharge_balance_to_bonus_minutes
from app.services.stripe_billing import _handle_checkout_completed, _payment_intent_id


def test_quote_recharge_ten_dollars_gives_six_credit_and_sixty_mins():
    q = quote_recharge(10)
    assert q["amount_paid_usd"] == 10.0
    assert q["client_balance_usd"] == 6.0
    assert q["estimated_voice_minutes"] == 60
    assert recharge_balance_to_bonus_minutes(6.0) == 60.0


def test_payment_intent_id_accepts_string_and_expanded_object():
    assert _payment_intent_id("pi_abc") == "pi_abc"
    assert _payment_intent_id({"id": "pi_exp"}) == "pi_exp"
    assert _payment_intent_id({"id": "  "}) is None
    assert _payment_intent_id(None) is None


def test_checkout_recharge_credits_when_payment_intent_is_dict():
    session = {
        "id": "cs_test",
        "mode": "payment",
        "amount_total": 1000,
        "customer": "cus_x",
        "client_reference_id": "user-adrian-1",
        "metadata": {
            "checkout_type": "recharge",
            "user_id": "user-adrian-1",
            "amount_paid_usd": "10",
        },
        "payment_intent": {
            "id": "pi_expanded_1",
            "metadata": {"checkout_type": "recharge", "user_id": "user-adrian-1"},
        },
    }
    with (
        patch(
            "app.services.stripe_billing.supabase_db.credit_recharge_balance",
            return_value=True,
        ) as credit,
        patch("app.services.stripe_billing.supabase_db.expire_trial_if_needed") as expire,
        patch(
            "app.services.stripe_billing.supabase_db.update_subscription_stripe_customer"
        ),
    ):
        _handle_checkout_completed(session, "evt_1")

    credit.assert_called_once()
    kwargs = credit.call_args.kwargs
    assert kwargs["stripe_payment_intent_id"] == "pi_expanded_1"
    assert kwargs["amount_paid_usd"] == 10.0
    assert kwargs["client_balance_usd"] == 6.0
    expire.assert_called_once_with("user-adrian-1")


def test_checkout_recharge_raises_when_credit_fails_so_stripe_retries():
    session = {
        "id": "cs_fail",
        "mode": "payment",
        "amount_total": 1000,
        "client_reference_id": "user-x",
        "metadata": {
            "checkout_type": "recharge",
            "user_id": "user-x",
            "amount_paid_usd": "10",
        },
        "payment_intent": "pi_fail",
    }
    with (
        patch(
            "app.services.stripe_billing.supabase_db.credit_recharge_balance",
            return_value=False,
        ),
        patch("app.services.stripe_billing.supabase_db.expire_trial_if_needed"),
    ):
        try:
            _handle_checkout_completed(session, "evt_fail")
            raised = False
        except RuntimeError:
            raised = True
    assert raised is True


def test_credit_recharge_balance_coerces_dict_pi_without_crash():
    from app.services import supabase_db

    client = MagicMock()
    client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[]
    )
    client.table.return_value.upsert.return_value.execute.return_value = MagicMock()
    client.table.return_value.insert.return_value.execute.return_value = MagicMock()

    with (
        patch("app.services.supabase_db._client", return_value=client),
        patch("app.services.supabase_db.get_recharge_balance_usd", return_value=0.0),
        patch("app.services.supabase_db.record_transaction"),
    ):
        ok = supabase_db.credit_recharge_balance(
            "user-x",
            amount_paid_usd=10.0,
            client_balance_usd=6.0,
            margin_keini_usd=4.0,
            stripe_payment_intent_id={"id": "pi_dict"},  # type: ignore[arg-type]
            stripe_event_id="evt_x",
        )
    assert ok is True


def test_voice_unlocks_when_trial_expired_but_wallet_has_balance():
    from app.services.voice_usage import voice_access_state

    sub = {
        "plan_id": "elite",
        "status": "canceled",
        "trial_ends_at": "2020-01-01T00:00:00+00:00",
    }
    with (
        patch(
            "app.services.supabase_db.get_profile",
            return_value={"email": "a@x.com", "role": "user"},
        ),
        patch("app.deps.auth.is_staff_admin", return_value=False),
        patch("app.services.supabase_db.get_usage_minutes_today", return_value=0.0),
        patch(
            "app.services.admin_users.get_user_access",
            return_value=(False, "trial_expired", 0),
        ),
        patch("app.services.supabase_db.get_subscription", return_value=sub),
        patch("app.services.supabase_db.get_recharge_balance_usd", return_value=6.0),
    ):
        state = voice_access_state("user-adrian")

    assert state["blocked"] is False
    assert state["allowed"] is True
    assert state["bonus_minutes_from_balance"] == 60.0
    assert state["total_available_minutes"] == 60.0
    assert state["needs_recharge"] is False


def test_voice_stays_blocked_when_trial_expired_and_wallet_empty():
    from app.services.voice_usage import voice_access_state

    sub = {"plan_id": "free_basic", "status": "canceled"}
    with (
        patch(
            "app.services.supabase_db.get_profile",
            return_value={"email": "a@x.com", "role": "user"},
        ),
        patch("app.deps.auth.is_staff_admin", return_value=False),
        patch("app.services.supabase_db.get_usage_minutes_today", return_value=0.0),
        patch(
            "app.services.admin_users.get_user_access",
            return_value=(False, "trial_expired", 0),
        ),
        patch("app.services.supabase_db.get_subscription", return_value=sub),
        patch("app.services.supabase_db.get_recharge_balance_usd", return_value=0.0),
    ):
        state = voice_access_state("user-empty")

    assert state["blocked"] is True
    assert state["allowed"] is False
    assert state["needs_recharge"] is True
