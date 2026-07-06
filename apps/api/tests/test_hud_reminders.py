from app.services.hud_reminders import is_reminder_intent


def test_is_reminder_intent_singular():
    assert is_reminder_intent("que recordatorio tengo")
    assert is_reminder_intent("¿qué recordatorios tengo?")


def test_is_reminder_intent_create():
    assert is_reminder_intent("recuérdame llamar a Marvin mañana a las 3pm")
