"""Tests aislados del detector de intención (Fase 1 v2).

No tocan red: el clasificador de Etapa 2 se inyecta como stub.
"""

from __future__ import annotations

from app.services.module_detector import (
    CONF_ANCHOR,
    CONF_LLM,
    CONF_NONE,
    CONF_SOFT,
    Detection,
    detect_intent,
)


def _always_action(_text: str, _module: str) -> bool:
    return True


def _never_action(_text: str, _module: str) -> bool:
    return False


# ---------------------------------------------------------------------------
# Etapa 1 — anclas estrictas activan directo, sin LLM.
# ---------------------------------------------------------------------------
def test_strict_finance_summary():
    d = detect_intent("dame un resumen de mis finanzas", classify=_never_action)
    assert d.module == "finance"
    assert d.confidence == CONF_ANCHOR
    assert d.is_action is True
    assert d.activate is True


def test_strict_finance_pending_payment():
    d = detect_intent("guárdame que mañana tengo que pagar 850", classify=_never_action)
    assert d.module == "finance"
    assert d.confidence == CONF_ANCHOR
    assert d.activate is True


def test_strict_map_navigation():
    d = detect_intent("llévame a Charlotte", classify=_never_action)
    assert d.module == "map"
    assert d.confidence == CONF_ANCHOR
    assert d.activate is True


def test_strict_pdf_not_image():
    d = detect_intent("hazme un pdf de análisis de finanzas", classify=_never_action)
    assert d.module == "pdf"
    assert d.confidence == CONF_ANCHOR


def test_strict_image_not_pdf():
    d = detect_intent("genérame una imagen de un logo", classify=_never_action)
    assert d.module == "image_gen"
    assert d.confidence == CONF_ANCHOR


def test_strict_weather_question():
    d = detect_intent("¿cómo va a estar el clima hoy?", classify=_never_action)
    assert d.module == "weather"
    assert d.confidence == CONF_ANCHOR


def test_strict_datetime():
    d = detect_intent("¿qué hora es?", classify=_never_action)
    assert d.module == "datetime"
    assert d.confidence == CONF_ANCHOR


def test_strict_gmail_read():
    d = detect_intent("léeme los correos importantes", classify=_never_action)
    assert d.module == "gmail"
    assert d.confidence == CONF_ANCHOR


def test_strict_calendar():
    d = detect_intent("qué tengo programado mañana", classify=_never_action)
    assert d.module == "calendar"
    assert d.confidence == CONF_ANCHOR


def test_strict_stripe():
    d = detect_intent("cancela mi suscripción", classify=_never_action)
    assert d.module == "stripe"
    assert d.confidence == CONF_ANCHOR


# ---------------------------------------------------------------------------
# Falsos positivos — frases normales NO activan módulo.
# ---------------------------------------------------------------------------
def test_directional_words_do_not_trigger_map():
    d = detect_intent("entonces gira a la derecha y sigue", classify=_never_action)
    assert d.module is None
    assert d.confidence == CONF_NONE
    assert d.activate is False


def test_casual_finance_mention_is_not_action():
    # "financiera" es señal suave → Etapa 2 dice CASUAL → no activa.
    d = detect_intent("mi situación financiera está difícil", classify=_never_action)
    assert d.module == "finance"
    assert d.confidence == CONF_LLM
    assert d.is_action is False
    assert d.activate is False


def test_casual_weather_mention_is_not_action():
    d = detect_intent("el clima estuvo loco ayer, qué locura", classify=_never_action)
    assert d.module == "weather"
    assert d.confidence == CONF_LLM
    assert d.is_action is False
    assert d.activate is False


def test_unrelated_long_sentence_no_module():
    d = detect_intent(
        "estaba pensando en cómo mejorar mi negocio y crecer este año",
        classify=_never_action,
    )
    assert d.module is None
    assert d.confidence == CONF_NONE


# ---------------------------------------------------------------------------
# Etapa 2 — candidato suave confirmado como acción por el clasificador.
# ---------------------------------------------------------------------------
def test_soft_weather_confirmed_as_action():
    d = detect_intent("oye y el clima", classify=_always_action)
    assert d.module == "weather"
    assert d.confidence == CONF_LLM
    assert d.is_action is True
    assert d.activate is True


def test_soft_gmail_confirmed_as_action():
    d = detect_intent("revisa mi bandeja", classify=_always_action)
    # "bandeja" es suave para gmail; strict "revisa ... bandeja" también aplica.
    assert d.module == "gmail"
    assert d.activate is True


# ---------------------------------------------------------------------------
# Modo solo-estricto y candidatos sin resolver.
# ---------------------------------------------------------------------------
def test_soft_unresolved_when_no_classifier():
    d = detect_intent("hablemos de finanzas", classify=None)
    assert d.module == "finance"
    assert d.confidence == CONF_SOFT
    assert d.is_action is False
    assert d.activate is False


def test_strict_only_mode_skips_stage2():
    d = detect_intent("hablemos de finanzas", run_stage2=False)
    assert d.module == "finance"
    assert d.confidence == CONF_SOFT


def test_empty_text():
    d = detect_intent("   ", classify=_always_action)
    assert d == Detection(module=None, confidence=CONF_NONE, is_action=False)


# ---------------------------------------------------------------------------
# Prioridad — PDF gana sobre la mención suave de finanzas.
# ---------------------------------------------------------------------------
def test_pdf_priority_over_finance_soft():
    d = detect_intent("hazme un pdf sobre mis finanzas", classify=_never_action)
    assert d.module == "pdf"
    assert d.confidence == CONF_ANCHOR


# ---------------------------------------------------------------------------
# Frases reales del usuario — anchors estrictos agregados.
# ---------------------------------------------------------------------------
def test_user_phrase_gmail_leer_mis_correos():
    d = detect_intent("leer mis correos", classify=_never_action)
    assert d.module == "gmail"
    assert d.activate is True


def test_user_phrase_gmail_leeme_correo_de():
    d = detect_intent("léeme el correo de Juan", classify=_never_action)
    assert d.module == "gmail"
    assert d.activate is True


def test_user_phrase_camera_abre_y_analiza():
    d1 = detect_intent("abre la cámara", classify=_never_action)
    d2 = detect_intent("analiza esto", classify=_never_action)
    d3 = detect_intent("analiza lo que tengo en la mano", classify=_never_action)
    assert d1.module == "camera" and d1.activate
    assert d2.module == "camera" and d2.activate
    assert d3.module == "camera" and d3.activate


def test_user_phrase_finance_qué_tengo_en_finanzas():
    d = detect_intent(
        "Oye, ¿qué tengo en finanzas? Dame un reporte",
        classify=_never_action,
    )
    assert d.module == "finance"
    assert d.activate is True


def test_user_phrase_weather_dime_el_clima():
    d = detect_intent("Dime el clima", classify=_never_action)
    assert d.module == "weather"
    assert d.activate is True


def test_user_phrase_social_publicame():
    d1 = detect_intent("publícame esto", classify=_never_action)
    d2 = detect_intent("haz la publicación", classify=_never_action)
    assert d1.module == "social" and d1.activate
    assert d2.module == "social" and d2.activate


def test_user_phrase_finance_como_van():
    d = detect_intent("cómo van mis finanzas", classify=_never_action)
    assert d.module == "finance"
    assert d.activate is True


def test_user_phrase_finance_guardame_que():
    d = detect_intent("guárdame que mañana pago el alquiler", classify=_never_action)
    assert d.module == "finance"
    assert d.activate is True


# ---------------------------------------------------------------------------
# Detector solo-estricto (voz): fuerza el orquestador por keyword, 0 latencia.
# Frases reales del usuario que antes caían en respuesta genérica de Gemini.
# ---------------------------------------------------------------------------
def test_strict_only_finance_guardame_en_finanzas():
    from app.services.ced_orchestrator import detect_strict_intent_v2

    assert (
        detect_strict_intent_v2(
            "guárdame en finanzas que el viernes tengo que pagar 1000 dólares"
        )
        == "finance"
    )


def test_strict_only_pdf():
    from app.services.ced_orchestrator import detect_strict_intent_v2

    assert detect_strict_intent_v2("hazme un pdf con un resumen del sistema") == "pdf"


def test_strict_only_no_false_positive_on_smalltalk():
    from app.services.ced_orchestrator import detect_strict_intent_v2

    # Conversación casual → NO fuerza módulo (sin falsos positivos).
    assert detect_strict_intent_v2("hola cómo estás") is None
    assert detect_strict_intent_v2("ok guardaste ese dato") is None
    assert detect_strict_intent_v2("mira el historial") is None
