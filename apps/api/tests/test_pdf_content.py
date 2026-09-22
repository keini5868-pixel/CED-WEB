"""Tests — contenido completo en PDF y filtros de chat."""

from unittest.mock import patch

from app.services.pdf_report import (
    pdf_content_needs_composition,
    resolve_pdf_content,
    store_pdf,
)
from app.services.text_chat import _contains_internal_kb_leak, _dedupe_chat_reply


def test_resolve_pdf_content_uses_previous_assistant_text():
    title = "Calendario de contenido semanal"
    body = title
    fallback = (
        "Lunes: post educativo sobre cejas.\n"
        "Martes: reel de antes/después.\n"
        "Miércoles: tips de micropigmentación.\n"
        "Jueves: testimonial.\n"
        "Viernes: promoción fin de semana."
    )
    resolved = resolve_pdf_content(title, body, fallback_texts=[fallback])
    assert "Lunes" in resolved
    assert "Viernes" in resolved
    assert resolved != title


def test_pdf_content_needs_composition_when_body_equals_title():
    title = "Los consejos del alquimista"
    assert pdf_content_needs_composition(title, title, user_request=title)


def test_pdf_content_needs_composition_when_body_is_short_request():
    req = "¿Me puedes dar los consejos más relevantes de El Alquimista en un PDF?"
    assert pdf_content_needs_composition("Consejos de El Alquimista", req[:40], user_request=req)


def test_store_pdf_composes_when_model_only_passes_title(monkeypatch):
    composed = (
        "1. Sigue tu Leyenda Personal.\n"
        "2. Escucha las señales del universo.\n"
        "3. El miedo es el peor enemigo del viaje.\n"
        "4. El tesoro está donde menos lo esperas.\n"
        "5. Cada paso enseña algo sobre ti mismo."
    )
    fake_pdf = b"%PDF-1.4 " + (b"x" * 200)

    def fake_compose(**kwargs):
        assert "Alquimista" in kwargs["user_request"] or "alquimista" in kwargs["user_request"].lower()
        return composed

    monkeypatch.setattr("app.services.pdf_report.compose_pdf_body", fake_compose)
    monkeypatch.setattr("app.services.supabase_db.save_pdf_artifact", lambda **_: True)
    monkeypatch.setattr(
        "app.services.supabase_db.get_pdf_artifact",
        lambda file_id, user_id: (fake_pdf, "doc.pdf", "Los consejos del alquimista"),
    )

    artifact = store_pdf(
        user_id="user-test",
        title="Los consejos del alquimista",
        content="Los consejos del alquimista",
        user_request="Dame los consejos más relevantes de El Alquimista en un PDF",
    )
    assert artifact.title
    assert artifact.file_id


@patch("app.services.pdf_report.compose_pdf_body", return_value="")
def test_store_pdf_raises_when_compose_fails(mock_compose):
    try:
        store_pdf(
            user_id="user-test",
            title="Los consejos del alquimista",
            content="Los consejos del alquimista",
            user_request="PDF de El Alquimista",
        )
    except ValueError as exc:
        assert "redactar" in str(exc).lower()
        mock_compose.assert_called_once()
    else:
        raise AssertionError("expected ValueError")


def test_store_pdf_accepts_short_composed_body_between_80_and_160_chars(monkeypatch):
    """Regresión: cuerpo redactado de 80-159 chars (o que menciona 'documento')
    no debe rechazarse — `compose_pdf_body` ya validó que es contenido real.
    """
    composed = (
        "Este documento presenta una breve descripción del clima de Caracas, "
        "la capital de Venezuela."
    )
    assert 80 <= len(composed) < 220
    fake_pdf = b"%PDF-1.4 " + (b"x" * 200)

    monkeypatch.setattr("app.services.pdf_report.compose_pdf_body", lambda **_: composed)
    monkeypatch.setattr("app.services.supabase_db.save_pdf_artifact", lambda **_: True)
    monkeypatch.setattr(
        "app.services.supabase_db.get_pdf_artifact",
        lambda file_id, user_id: (fake_pdf, "doc.pdf", "Prueba"),
    )

    artifact = store_pdf(
        user_id="user-test",
        title="Prueba diagnostico",
        content="Este es un PDF de prueba",
        user_request="genera un pdf de prueba sobre el clima en Caracas",
        detail_level="brief",
    )
    assert artifact.file_id


def test_compose_pdf_body_uses_cloud_fallback_when_gemini_empty(monkeypatch):
    from app.services.pdf_report import compose_pdf_body

    monkeypatch.setattr("app.config.get_settings", lambda: type("S", (), {"google_api_key": "fake-key"})())
    monkeypatch.setattr(
        "app.services.pdf_report.ThreadPoolExecutor",
        lambda **_: type(
            "Pool",
            (),
            {
                "submit": lambda self, fn: type(
                    "F",
                    (),
                    {"result": lambda self, timeout=0: ""},
                )(),
                "__enter__": lambda self: self,
                "__exit__": lambda *a: None,
            },
        )(),
    )
    monkeypatch.setattr(
        "app.services.pdf_report._compose_pdf_body_cloud_fallback",
        lambda prompt, **_kwargs: "Contenido extenso del documento generado por fallback cloud. " * 8,
    )
    body = compose_pdf_body(
        title="Plan semanal",
        user_request="Hazme un PDF del plan semanal",
        draft_content="Plan semanal",
    )
    assert len(body) >= 80
    assert "fallback cloud" in body


def test_store_pdf_memory_only_without_service_role(monkeypatch):
    from app.services.pdf_report import store_pdf

    composed = "Sección uno del informe.\n" * 12
    fake_pdf = b"%PDF-1.4 " + (b"x" * 200)

    monkeypatch.setattr("app.services.pdf_report.compose_pdf_body", lambda **_: composed)
    monkeypatch.setattr("app.services.pdf_report._persist_pdf_artifact", lambda **_: False)
    monkeypatch.setattr(
        "app.services.supabase_client.service_role_configured",
        lambda: False,
    )

    artifact = store_pdf(
        user_id="user-test",
        title="Informe",
        content="Informe",
        user_request="PDF del informe",
    )
    assert artifact.file_id
    assert "informe" in artifact.title.lower()


def test_store_pdf_revise_keeps_source_and_forces_compose(monkeypatch):
    source = (
        "Presupuesto de publicidad para Carolina Certific\n"
        "1. Fee único $600\n2. Mensual $550\n3. Pauta $200\n"
        "TOTAL $1350"
    )
    captured: dict[str, str] = {}

    def fake_compose(**kwargs):
        captured["draft"] = kwargs.get("draft_content") or ""
        captured["level"] = kwargs.get("detail_level") or ""
        captured["request"] = kwargs.get("user_request") or ""
        return (
            "Presupuesto de publicidad — Carolina Exotic Fish\n"
            "1. Infraestructura: $600\n2. Gestión mensual: $550\n"
            "3. Campaña de lanzamiento: $200\nTotal inicial: $1,350"
        )

    fake_pdf = b"%PDF-1.4 " + (b"x" * 200)
    monkeypatch.setattr("app.services.pdf_report.compose_pdf_body", fake_compose)
    monkeypatch.setattr("app.services.supabase_db.save_pdf_artifact", lambda **_: True)
    monkeypatch.setattr(
        "app.services.supabase_db.get_pdf_artifact",
        lambda file_id, user_id: (fake_pdf, "doc.pdf", "Presupuesto"),
    )

    artifact = store_pdf(
        user_id="user-test",
        title="Presupuesto de publicidad — Carolina Exotic Fish",
        content=source,
        user_request="GENERA ESTO CON MEJOR ESTRUCTURA. El nombre es Carolina Exotic Fish",
        detail_level="revise",
    )
    assert artifact.file_id
    assert captured["level"] == "revise"
    assert "$600" in captured["draft"]
    assert "Carolina Exotic Fish" in captured["request"]


def test_compose_pdf_revise_prompt_keeps_source():
    from app.services.pdf_report import _compose_pdf_prompt

    prompt = _compose_pdf_prompt(
        title="Presupuesto",
        user_request="cámbiale el nombre a Carolina Exotic Fish",
        draft_content="1. Fee $600\n2. Mensual $550",
        detail_level="revise",
    )
    assert "MODO EDICIÓN" in prompt
    assert "Fee $600" in prompt
    assert "NO ignores el borrador" in prompt


def test_dedupe_chat_reply_removes_exact_duplicate_halves():
    text = "Bloque A.\n\nBloque A."
    assert _dedupe_chat_reply(text) == "Bloque A."


def test_internal_kb_leak_patterns():
    leaked = (
        "Conocimiento interno CED (priorizar sobre suposiciones):\n"
        "- [Marketing digital] SEO básico para negocios: ..."
    )
    assert _contains_internal_kb_leak(leaked)
