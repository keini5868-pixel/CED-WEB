"""Tests — pulido de comandos de voz (detección + Gmail follow-up + cámara)."""

from __future__ import annotations

from unittest.mock import patch

from app.modules.gmail_module import (
    GmailModule,
    is_gmail_followup_pick,
    is_gmail_intent,
    is_gmail_read_latest_intent,
)
from app.services import voice_client_session as vcs
from app.services.ced_orchestrator import detect_module, detect_strict_intent_v2, is_module_command
from app.services.cognitive_intents import is_camera_voice_command
from app.services.module_detector import CONF_ANCHOR, detect_intent
from app.services.retell_custom_llm import resolve_camera_voice_request


def test_finance_voice_phrase_anchor():
    phrase = "Oye, ¿qué tengo en finanzas? Dame un reporte"
    d = detect_intent(phrase, classify=lambda _t, _m: False)
    assert d.module == "finance"
    assert d.confidence == CONF_ANCHOR
    assert d.activate is True


def test_weather_dime_el_clima_anchor():
    d = detect_intent("Dime el clima", classify=lambda _t, _m: False)
    assert d.module == "weather"
    assert d.confidence == CONF_ANCHOR


def test_gmail_lee_los_gmail_anchor():
    d = detect_intent("Lee los Gmail que tengo", classify=lambda _t, _m: False)
    assert d.module == "gmail"
    assert d.activate is True
    assert is_gmail_intent("Lee los Gmail que tengo")


def test_camera_analiza_lo_que_tengo_en_la_mano():
    phrase = "analiza lo que tengo en la mano"
    assert is_camera_voice_command(phrase)
    assert resolve_camera_voice_request(phrase) == "analyze_camera_frame"
    d = detect_intent(phrase, classify=lambda _t, _m: False)
    assert d.module == "camera"
    assert d.activate is True


def test_gmail_followup_pick_after_list():
    uid = "user-gmail-pick"
    vcs.set_gmail_awaiting_pick(uid, True)
    vcs.set_gmail_inbox_cache(
        uid,
        [
            {
                "id": "msg-1",
                "from": "jomed@corp.com",
                "from_name": "JOMED",
                "subject": "Factura pendiente",
            },
        ],
    )
    assert is_gmail_followup_pick("JOMED", uid)
    assert detect_module("JOMED", [], user_id=uid) == "gmail"
    assert is_module_command("JOMED", "gmail", [], user_id=uid)


def test_gmail_module_reads_picked_email():
    uid = "user-gmail-read"
    module = GmailModule()
    vcs.set_gmail_awaiting_pick(uid, True)
    vcs.set_gmail_inbox_cache(
        uid,
        [
            {
                "id": "msg-99",
                "from": "marvin@x.com",
                "from_name": "Marvin",
                "subject": "Reunión",
            },
        ],
    )

    async def run():
        module._enter_active()
        with patch(
            "app.modules.gmail_module.get_valid_access_token",
            return_value="token",
        ):
            with patch(
                "app.modules.gmail_module.get_message_body",
                return_value="Contenido del correo de prueba.",
            ):
                return await module.handle_command(
                    "Marvin",
                    user_id=uid,
                    call_id="call-1",
                    user_text="Marvin",
                )

    import asyncio

    result = asyncio.run(run())
    assert result.ok
    assert "Marvin" in result.spoken
    assert "Contenido del correo" in result.spoken
    assert result.send_filler is True
    assert not vcs.is_gmail_awaiting_pick(uid)


def test_gmail_latest_email_phrases():
    phrases = [
        "me puedes leer el ultimo Gmail que me llego?",
        "lee mi ultimo Gmail",
        "me puedes leer el ultimo correo?",
    ]
    for p in phrases:
        assert is_gmail_intent(p), p
        assert is_gmail_read_latest_intent(p), p
        d = detect_intent(p, classify=lambda _t, _m: False)
        assert d.module == "gmail" and d.activate is True, p
        assert detect_strict_intent_v2(p) == "gmail", p


def test_gmail_ack_not_followup_pick():
    uid = "user-gmail-ack"
    vcs.set_gmail_awaiting_pick(uid, True)
    assert not is_gmail_followup_pick("Si, me escuchaste.", uid)
    assert detect_module("Si, me escuchaste.", [], user_id=uid, active_module="gmail") == "gmail"


def test_gmail_module_reads_latest_email():
    uid = "user-gmail-latest"
    module = GmailModule()

    async def run():
        with patch(
            "app.modules.gmail_module.get_valid_access_token",
            return_value="token",
        ):
            with patch(
                "app.modules.gmail_module.list_inbox_messages",
                return_value=[
                    {
                        "id": "latest-1",
                        "from": "ana@corp.com",
                        "from_name": "Ana",
                        "subject": "Factura julio",
                        "relative_date": "hoy",
                        "snippet": "Resumen del correo.",
                    },
                ],
            ):
                with patch(
                    "app.modules.gmail_module.get_message_body",
                    return_value="Contenido completo del ultimo correo.",
                ):
                    return await module.activate(
                        "me puedes leer el ultimo Gmail que me llego?",
                        user_id=uid,
                        call_id="call-1",
                        user_text="me puedes leer el ultimo Gmail que me llego?",
                    )

    import asyncio

    result = asyncio.run(run())
    assert result.ok
    assert "ultimo correo" in result.spoken.lower() or "último correo" in result.spoken.lower()
    assert "Contenido completo" in result.spoken
    assert "Factura julio" in result.spoken
    assert "Resumen del correo" in result.spoken or "Contenido completo" in result.spoken


def test_gmail_list_prompts_for_name():
    uid = "user-gmail-list"
    module = GmailModule()

    async def run():
        with patch(
            "app.modules.gmail_module.get_valid_access_token",
            return_value="token",
        ):
            with patch(
                "app.modules.gmail_module.list_messages_by_category",
                return_value=[
                    {
                        "id": "1",
                        "from": "a@x.com",
                        "from_name": "Ana",
                        "subject": "Hola",
                        "relative_date": "hoy",
                    },
                ],
            ):
                return await module.activate(
                    "Lee los Gmail que tengo",
                    user_id=uid,
                    call_id="call-1",
                    user_text="Lee los Gmail que tengo",
                )

    import asyncio

    result = asyncio.run(run())
    assert "¿Cuál correo, dígame el nombre?" in result.spoken
    assert vcs.is_gmail_awaiting_pick(uid)
