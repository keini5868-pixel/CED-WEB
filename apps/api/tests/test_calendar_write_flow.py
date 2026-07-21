"""Tests — Calendario escritura con confirmación (piloto nativo)."""

from __future__ import annotations

from unittest.mock import patch

from app.services import voice_client_session as vcs
from app.services.calendar_write_flow import (
    cancel_calendar_write,
    confirm_calendar_write,
    is_calendar_write_confirm,
    prepare_calendar_write,
)

USER = "550e8400-e29b-41d4-a716-446655440099"
CALL = "call_calendar_test_1"


def setup_function() -> None:
    vcs.clear_calendar_pending_write(USER)


def test_is_calendar_write_confirm():
    assert is_calendar_write_confirm("sí, agéndalo")
    assert is_calendar_write_confirm("Sí.", allow_short_yes=True)
    assert is_calendar_write_confirm("sí", allow_short_yes=True)
    assert not is_calendar_write_confirm("ok gracias")


def test_is_calendar_write_confirm_recognizes_accented_confirmalo():
    """Regresión (auditoría pre-lanzamiento): mismo bug de tilde que en finanzas/gmail."""
    assert is_calendar_write_confirm("sí, confírmalo")
    assert is_calendar_write_confirm("confírmalo")


def test_is_calendar_write_confirm_tolerates_natural_voice_noise():
    """Regresión: confirmaciones reales por voz vienen con ruido (vocativos,
    puntuación de STT, cortesía, muletillas) — antes un "sí" con cualquier
    palabra extra (p.ej. "Sí señor") no se detectaba como confirmación y el
    flujo fallaba con "no detecté una confirmación clara" pese a que el
    usuario sí confirmó.
    """
    variantes_validas = [
        "Sí",
        "Sí.",
        "Sí,",
        "Sí señor",
        "Sí, por favor",
        "Sí, adelante",
        "Eh, sí",
        "Sí, así es",
        "Claro que sí",
        "Sí, agéndalo para mañana",
    ]
    for v in variantes_validas:
        assert is_calendar_write_confirm(v, allow_short_yes=True), f"debió confirmar: {v!r}"

    variantes_invalidas = ["No", "No, cancela", "Mejor no", "¿Qué hora es?"]
    for v in variantes_invalidas:
        assert not is_calendar_write_confirm(v, allow_short_yes=True), f"NO debió confirmar: {v!r}"


def test_parse_time_spanish_meridiem_phrases():
    """Regresión: '5 de la tarde' se guardaba como 5:00 a.m. (solo se
    reconocía am/pm literal, no los meridianos en español que la gente
    realmente dice por voz)."""
    from app.modules.calendar_module import _parse_time

    assert _parse_time("hoy a las 5 de la tarde") == (17, 0)
    assert _parse_time("a las 9 de la mañana") == (9, 0)
    assert _parse_time("a las 11 de la noche") == (23, 0)
    assert _parse_time("a las 12 de la noche") == (0, 0)
    assert _parse_time("a las 2 de la madrugada") == (2, 0)


def test_prepare_needs_details():
    out = prepare_calendar_write(USER, call_id=CALL, query="hola")
    assert out["status"] == "needs_details"


def test_prepare_missing_write_scope():
    with patch(
        "app.services.calendar_write_flow.get_valid_access_token",
        return_value="tok",
    ):
        with patch(
            "app.services.calendar_write_flow.token_has_calendar_write_scope",
            return_value=False,
        ):
            out = prepare_calendar_write(
                USER,
                call_id=CALL,
                query="agéndame reunión con Ana mañana a las 3 pm",
            )
    assert out["status"] == "missing_write_scope"
    assert "permiso de escritura" in out["spoken"].lower()
    assert vcs.get_calendar_pending_write(USER) is None


def test_prepare_and_confirm_short_yes():
    with patch(
        "app.services.calendar_write_flow.get_valid_access_token",
        return_value="tok",
    ):
        with patch(
            "app.services.calendar_write_flow.token_has_calendar_write_scope",
            return_value=True,
        ):
            prep = prepare_calendar_write(
                USER,
                call_id=CALL,
                query="agéndame reunión con Ana mañana a las 3 pm",
            )
    assert prep["status"] == "awaiting_confirmation"
    assert prep["transition"] == "transition_to_calendar_confirm_pending"
    assert "calendar_confirm_write" in prep["spoken"]
    draft_id = prep["draft_id"]

    with patch(
        "app.services.calendar_write_flow.get_valid_access_token",
        return_value="tok",
    ):
        with patch(
            "app.services.calendar_write_flow.token_has_calendar_write_scope",
            return_value=True,
        ):
            with patch(
                "app.services.calendar_write_flow._calendar_api_call",
                side_effect=lambda _uid, fn: fn("tok"),
            ):
                with patch(
                    "app.services.calendar_write_flow.create_event",
                    return_value={"id": "evt-1"},
                ):
                    conf = confirm_calendar_write(
                        USER,
                        call_id=CALL,
                        draft_id=draft_id,
                        payload={
                            "call": {
                                "transcript_object": [
                                    {"role": "user", "content": "Sí."},
                                ]
                            }
                        },
                    )
    assert conf["ok"] is True
    assert conf["status"] == "written"
    assert "Ana" in conf["spoken"] or "reunión" in conf["spoken"].lower()


def test_confirm_uses_transcript_string_fallback_like_finance():
    """Regresión: Retell a veces envía transcript_object vacío al confirmar;
    Finance ya caía a call.transcript — Calendar debe hacer lo mismo o el
    write nunca ejecuta y el usuario queda en bucle de confirmación.
    """
    with patch(
        "app.services.calendar_write_flow.get_valid_access_token",
        return_value="tok",
    ):
        with patch(
            "app.services.calendar_write_flow.token_has_calendar_write_scope",
            return_value=True,
        ):
            prep = prepare_calendar_write(
                USER,
                call_id=CALL,
                query="agéndame junta con Luis mañana a las 4 pm",
            )
    draft_id = prep["draft_id"]

    with patch(
        "app.services.calendar_write_flow.get_valid_access_token",
        return_value="tok",
    ):
        with patch(
            "app.services.calendar_write_flow.token_has_calendar_write_scope",
            return_value=True,
        ):
            with patch(
                "app.services.calendar_write_flow._calendar_api_call",
                side_effect=lambda _uid, fn: fn("tok"),
            ):
                with patch(
                    "app.services.calendar_write_flow.create_event",
                    return_value={"id": "evt-transcript-str"},
                ) as mock_create:
                    conf = confirm_calendar_write(
                        USER,
                        call_id=CALL,
                        draft_id=draft_id,
                        payload={
                            "call": {
                                "transcript_object": [],
                                "transcript": (
                                    "User: agéndame junta con Luis mañana a las 4 pm\n"
                                    "Agent: ¿Desea que lo agende?\n"
                                    "User: sí"
                                ),
                            }
                        },
                    )
    assert conf["ok"] is True, conf
    assert conf["status"] == "written"
    mock_create.assert_called_once()


def test_confirm_treats_empty_utterance_as_yes_when_tool_invoked_with_pending_draft():
    """Si Retell llama calendar_confirm_write con transcript aún vacío (carrera),
    no deben quedarse en confirm_required: la invocación del tool cuenta.
    """
    with patch(
        "app.services.calendar_write_flow.get_valid_access_token",
        return_value="tok",
    ):
        with patch(
            "app.services.calendar_write_flow.token_has_calendar_write_scope",
            return_value=True,
        ):
            prep = prepare_calendar_write(
                USER,
                call_id=CALL,
                query="agéndame yoga mañana a las 8 am",
            )
    draft_id = prep["draft_id"]

    with patch(
        "app.services.calendar_write_flow.get_valid_access_token",
        return_value="tok",
    ):
        with patch(
            "app.services.calendar_write_flow.token_has_calendar_write_scope",
            return_value=True,
        ):
            with patch(
                "app.services.calendar_write_flow._calendar_api_call",
                side_effect=lambda _uid, fn: fn("tok"),
            ):
                with patch(
                    "app.services.calendar_write_flow.create_event",
                    return_value={"id": "evt-empty-utterance"},
                ) as mock_create:
                    conf = confirm_calendar_write(
                        USER,
                        call_id=CALL,
                        draft_id=draft_id,
                        payload={"call": {"transcript_object": [], "transcript": ""}},
                    )
    assert conf["ok"] is True, conf
    assert conf["status"] == "written"
    mock_create.assert_called_once()


def test_prepare_and_confirm_with_natural_noisy_yes():
    """Regresión del bug reportado: 'Agéndame llamar a mi papá hoy a las 5 de
    la tarde' -> confirmar con 'Sí señor' (frase natural, no un 'sí' limpio)
    debía fallar con confirm_required antes del fix.
    """
    with patch(
        "app.services.calendar_write_flow.get_valid_access_token",
        return_value="tok",
    ):
        with patch(
            "app.services.calendar_write_flow.token_has_calendar_write_scope",
            return_value=True,
        ):
            prep = prepare_calendar_write(
                USER,
                call_id=CALL,
                query="agéndame llamar a mi papá hoy a las 5 de la tarde",
            )
    assert prep["status"] == "awaiting_confirmation"
    assert "5:00 PM" in prep["spoken"]
    draft_id = prep["draft_id"]

    with patch(
        "app.services.calendar_write_flow.get_valid_access_token",
        return_value="tok",
    ):
        with patch(
            "app.services.calendar_write_flow.token_has_calendar_write_scope",
            return_value=True,
        ):
            with patch(
                "app.services.calendar_write_flow._calendar_api_call",
                side_effect=lambda _uid, fn: fn("tok"),
            ):
                with patch(
                    "app.services.calendar_write_flow.create_event",
                    return_value={"id": "evt-2"},
                ):
                    conf = confirm_calendar_write(
                        USER,
                        call_id=CALL,
                        draft_id=draft_id,
                        payload={
                            "call": {
                                "transcript_object": [
                                    {"role": "user", "content": "agéndame llamar a mi papá hoy a las 5 de la tarde"},
                                    {"role": "agent", "content": prep["spoken"]},
                                    {"role": "user", "content": "Sí señor"},
                                ]
                            }
                        },
                    )
    assert conf["ok"] is True
    assert conf["status"] == "written"


def test_write_intent_recognizes_natural_verbs_beyond_agendame():
    """Regresión: 'Guarda una llamada para Rafael a las 10 am del lunes' no
    era reconocida como intención de agendar (solo 'agéndame/agendar/
    programa(me)/recuérdame' matcheaban) — prepare_calendar_write devolvía
    needs_details en silencio, dejando al LLM sin borrador real que confirmar
    aunque el usuario ya había dicho claramente qué quería agendar.
    """
    with patch(
        "app.services.calendar_write_flow.get_valid_access_token",
        return_value="tok",
    ):
        with patch(
            "app.services.calendar_write_flow.token_has_calendar_write_scope",
            return_value=True,
        ):
            for query in [
                "guarda una llamada para Rafael Armando a las 10 de la mañana del día lunes",
                "anótame una cita con el doctor mañana a las 3 pm",
                "apunta reunión con Ana el lunes a las 9 am",
                "reserva una llamada con mi papá mañana a las 5 de la tarde",
            ]:
                out = prepare_calendar_write(USER, call_id=CALL, query=query)
                assert out["status"] == "awaiting_confirmation", (
                    f"debió preparar un borrador real para: {query!r}, obtuvo: {out}"
                )
                vcs.clear_calendar_pending_write(USER)


def test_prepare_and_confirm_with_guarda_verb_end_to_end():
    """Reproduce el reporte exacto del usuario end-to-end: preparar con
    'Guarda...' y confirmar con 'Sí, guárdalo' debe escribir el evento real,
    no fallar con 'no encontró el borrador'."""
    with patch(
        "app.services.calendar_write_flow.get_valid_access_token",
        return_value="tok",
    ):
        with patch(
            "app.services.calendar_write_flow.token_has_calendar_write_scope",
            return_value=True,
        ):
            prep = prepare_calendar_write(
                USER,
                call_id=CALL,
                query="Guarda una llamada para Rafael Armando a las 10 de la mañana del día lunes",
            )
    assert prep["status"] == "awaiting_confirmation", prep
    assert "Rafael Armando" in prep["spoken"]
    draft_id = prep["draft_id"]

    with patch(
        "app.services.calendar_write_flow.get_valid_access_token",
        return_value="tok",
    ):
        with patch(
            "app.services.calendar_write_flow.token_has_calendar_write_scope",
            return_value=True,
        ):
            with patch(
                "app.services.calendar_write_flow._calendar_api_call",
                side_effect=lambda _uid, fn: fn("tok"),
            ):
                with patch(
                    "app.services.calendar_write_flow.create_event",
                    return_value={"id": "evt-guarda-1"},
                ):
                    conf = confirm_calendar_write(
                        USER,
                        call_id=CALL,
                        draft_id=draft_id,
                        payload={
                            "call": {
                                "transcript_object": [
                                    {"role": "agent", "content": prep["spoken"]},
                                    {"role": "user", "content": "Sí, guárdalo"},
                                ]
                            }
                        },
                    )
    assert conf["ok"] is True
    assert conf["status"] == "written"
    assert conf["event_id"] == "evt-guarda-1"


def test_confirm_reports_missing_write_scope():
    with patch(
        "app.services.calendar_write_flow.get_valid_access_token",
        return_value="tok",
    ):
        with patch(
            "app.services.calendar_write_flow.token_has_calendar_write_scope",
            return_value=True,
        ):
            prep = prepare_calendar_write(
                USER,
                call_id=CALL,
                query="recuérdame pagar el lunes a las 9",
            )
    draft_id = prep["draft_id"]
    with patch(
        "app.services.calendar_write_flow.get_valid_access_token",
        return_value="tok",
    ):
        with patch(
            "app.services.calendar_write_flow.token_has_calendar_write_scope",
            return_value=False,
        ):
            conf = confirm_calendar_write(
                USER,
                call_id=CALL,
                draft_id=draft_id,
                payload={
                    "call": {
                        "transcript_object": [{"role": "user", "content": "sí"}]
                    }
                },
            )
    assert conf["status"] == "missing_write_scope"
    assert "permiso de escritura" in conf["spoken"].lower()


def test_cancel_calendar_write():
    with patch(
        "app.services.calendar_write_flow.get_valid_access_token",
        return_value="tok",
    ):
        with patch(
            "app.services.calendar_write_flow.token_has_calendar_write_scope",
            return_value=True,
        ):
            prepare_calendar_write(
                USER,
                call_id=CALL,
                query="agéndame dentista mañana a las 10",
            )
    out = cancel_calendar_write(USER)
    assert out["status"] == "cancelled"
    assert vcs.get_calendar_pending_write(USER) is None


def test_confirm_with_stale_prepare_utterance_writes():
    """Retell invokes confirm while transcript still shows «Guarda…» prepare line."""
    with patch(
        "app.services.calendar_write_flow.get_valid_access_token",
        return_value="tok",
    ):
        with patch(
            "app.services.calendar_write_flow.token_has_calendar_write_scope",
            return_value=True,
        ):
            prep = prepare_calendar_write(
                USER,
                call_id=CALL,
                query="Guarda una llamada con Ana mañana a las 3 pm",
            )
    assert prep["ok"] is True
    draft_id = prep["draft_id"]
    with patch(
        "app.services.calendar_write_flow.get_valid_access_token",
        return_value="tok",
    ):
        with patch(
            "app.services.calendar_write_flow.token_has_calendar_write_scope",
            return_value=True,
        ):
            with patch(
                "app.services.calendar_write_flow._calendar_api_call",
                side_effect=lambda _uid, fn: fn("tok"),
            ):
                with patch(
                    "app.services.calendar_write_flow.create_event",
                    return_value={"id": "evt-stale-1", "htmlLink": "https://cal.test/1"},
                ) as mock_create:
                    conf = confirm_calendar_write(
                        USER,
                        call_id=CALL,
                        draft_id=draft_id,
                        payload={
                            "call": {
                                "transcript_object": [
                                    {
                                        "role": "user",
                                        "content": "Guarda una llamada con Ana mañana a las 3 pm",
                                    },
                                    {"role": "agent", "content": prep["spoken"]},
                                ]
                            }
                        },
                    )
    assert conf["ok"] is True, conf
    assert conf["status"] == "written"
    mock_create.assert_called_once()
