"""Instant chat greetings including como estas."""

from app.services.text_chat import _instant_chat_greeting_reply


def test_como_estas_instant_chat():
    reply = _instant_chat_greeting_reply("COMO ESTAS")
    assert reply
    assert "señor" in reply.lower()


def test_hola_instant_chat():
    reply = _instant_chat_greeting_reply("HOLA")
    assert reply
    assert "CED" in reply


def test_pm_link_with_hola_is_not_instant_greeting():
    assert (
        _instant_chat_greeting_reply(
            "Hola, Said. ¿Me das el enlace de PM International?"
        )
        is None
    )
