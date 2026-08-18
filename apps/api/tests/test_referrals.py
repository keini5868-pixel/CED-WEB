"""Referidos — Referral ID, claim y actividad relevante de venta."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.referrals import (
    add_structure_partner,
    claim_referral,
    display_name_from_profile,
    generate_referral_code,
    is_relevant_sales_chat,
    normalize_pm_partner_id,
    normalize_referral_code,
)


def test_generate_referral_code_from_uuid():
    assert (
        generate_referral_code("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        == "CEDA1B2C3D4"
    )


def test_normalize_referral_code():
    assert normalize_referral_code("ced7a3f2c1") == "CED7A3F2C1"
    assert normalize_referral_code("7A3F2C1") == "CED7A3F2C1"
    assert normalize_referral_code("  CED-7A3F-2C1 ") == "CED7A3F2C1"
    assert normalize_referral_code("") == ""
    assert normalize_referral_code("ab") == ""


def test_display_name_privacy():
    assert display_name_from_profile({"full_name": "Ana García"}) == "Ana G."
    assert display_name_from_profile({"full_name": "Luis"}) == "Luis"
    assert display_name_from_profile({"email": "socio@example.com"}) == "socio"
    assert display_name_from_profile({}) == "Invitado"


def test_sales_chat_counts_pm_and_prospecting():
    assert is_relevant_sales_chat("cómo vendo FitLine a un prospecto nuevo")
    assert is_relevant_sales_chat("quiero el plan de compensación de PM International")
    assert is_relevant_sales_chat("ayúdame a prospectar para la franquicia")
    assert is_relevant_sales_chat("cómo uso mi enlace de patrocinio")
    assert is_relevant_sales_chat("hola, qué hora es en Madrid?") is False
    assert is_relevant_sales_chat("ok") is False


def test_claim_rejects_self_and_unknown():
    with patch(
        "app.services.referrals.find_referrer_by_code",
        return_value={"id": "user-1"},
    ):
        result = claim_referral("user-1", "CEDAAAA1111")
    assert result["ok"] is False
    assert result["reason"] == "self"

    with patch("app.services.referrals.find_referrer_by_code", return_value=None):
        result = claim_referral("user-2", "CEDUNKNOWN1")
    assert result["ok"] is False
    assert result["reason"] == "unknown_code"

    assert claim_referral("user-2", "")["reason"] == "invalid"


def test_claim_inserts_once():
    existing = MagicMock()
    existing.data = []
    inserted = MagicMock()
    client = MagicMock()
    table = MagicMock()
    client.table.return_value = table
    table.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
        existing
    )
    table.insert.return_value.execute.return_value = inserted

    with (
        patch(
            "app.services.referrals.find_referrer_by_code",
            return_value={"id": "referrer-1"},
        ),
        patch("app.services.referrals._client", return_value=client),
    ):
        result = claim_referral("invitee-1", "CEDAAAA1111")

    assert result["ok"] is True
    assert result["already"] is False
    table.insert.assert_called_once()
    payload = table.insert.call_args[0][0]
    assert payload["referrer_id"] == "referrer-1"
    assert payload["referred_id"] == "invitee-1"
    assert payload["referral_code"] == "CEDAAAA1111"


def test_claim_already_linked_does_not_reinsert():
    existing = MagicMock()
    existing.data = [{"id": "row-1", "referrer_id": "referrer-1", "referral_code": "CEDA"}]
    client = MagicMock()
    table = MagicMock()
    client.table.return_value = table
    table.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
        existing
    )

    with (
        patch(
            "app.services.referrals.find_referrer_by_code",
            return_value={"id": "referrer-1"},
        ),
        patch("app.services.referrals._client", return_value=client),
    ):
        result = claim_referral("invitee-1", "CEDAAAA1111")

    assert result["ok"] is True
    assert result["already"] is True
    table.insert.assert_not_called()


def _empty_client() -> MagicMock:
    result = MagicMock()
    result.data = []

    def table(_name: str) -> MagicMock:
        t = MagicMock()
        t.select.return_value = t
        t.eq.return_value = t
        t.gte.return_value = t
        t.limit.return_value = t
        t.in_.return_value = t
        t.order.return_value = t
        t.execute.return_value = result
        return t

    client = MagicMock()
    client.table.side_effect = table
    return client


def test_guest_activity_unused_without_sales_signals():
    from app.services.referrals import _guest_activity

    with patch("app.services.referrals._client", return_value=_empty_client()):
        activity = _guest_activity("user-x")
    assert activity["status"] == "unused"
    assert activity["signals"]["voice"]["used"] is False
    assert activity["signals"]["chat_sales"]["used"] is False
    assert activity["signals"]["finance"]["used"] is False
    assert activity["signals"]["opps"]["used"] is False


def test_dashboard_mi_equipo_route_registered():
    from app.routers.referrals import dashboard_router, router

    assert any(getattr(r, "path", None) == "/v1/referrals/me" for r in router.routes)
    assert any(getattr(r, "path", None) == "/v1/referrals/claim" for r in router.routes)
    assert any(getattr(r, "path", None) == "/v1/referrals/partners" for r in router.routes)
    assert any(getattr(r, "path", None) == "/v1/referrals/profile" for r in router.routes)
    assert any(
        getattr(r, "path", None) == "/v1/dashboard/mi-equipo"
        for r in dashboard_router.routes
    )


def test_normalize_pm_partner_id():
    assert normalize_pm_partner_id(" 8845123 ") == "8845123"
    assert normalize_pm_partner_id("PM-12 345") == "PM-12345"
    assert normalize_pm_partner_id("ab") == ""
    assert normalize_pm_partner_id("") == ""


def test_add_partner_validates_name_and_email():
    from app.services.referrals import add_structure_partner

    with patch("app.services.referrals.ensure_referral_code", return_value="CEDAAAA1111"):
        assert add_structure_partner("s1", full_name="Al", email="a@b.com")["reason"] == "invalid_name"
        assert add_structure_partner("s1", full_name="Ana García", email="no")["reason"] == "invalid_email"


def test_add_partner_requires_pm_partner_id():
    from app.services.referrals import add_structure_partner

    result = add_structure_partner("s1", full_name="Ana García", email="ana@example.com")
    assert result["reason"] == "invalid_pm_partner_id"


def test_add_partner_accepts_pm_id_not_ced_code():
    from app.services.referrals import add_structure_partner

    with (
        patch("app.services.referrals.ensure_referral_code", return_value="CEDAAAA1111"),
        patch("app.services.referrals.find_profile_by_email", return_value=None),
        patch("app.services.referrals.snapshot_structure_partner", return_value=True) as snap,
        patch("app.services.referrals.list_my_team", return_value={"ok": True, "guests": []}),
    ):
        result = add_structure_partner(
            "s1",
            full_name="Ana García",
            email="ana@example.com",
            pm_partner_id="8845123",
        )
    assert result["ok"] is True
    assert snap.call_args.kwargs["pm_partner_id"] == "8845123"


def test_complete_profile_rejects_short_name():
    from app.services.referrals import complete_pm_profile

    assert complete_pm_profile("u1", full_name="Al")["reason"] == "invalid_name"
