"""FitLine curated knowledge available to chat when products/brand are mentioned."""

from __future__ import annotations

from app.services.chat_module_context import fetch_module_stream_context
from app.services.opportunities_pilot.fitline_knowledge import (
    append_fitline_knowledge_if_needed,
    fitline_explicit_live_web_override,
    format_fitline_knowledge_for_prompt,
    prefers_fitline_over_web,
    wants_fitline_knowledge,
)
from app.services.retell_custom_llm import resolve_web_search_request
from app.services.text_chat import _build_chat_system_light, _can_stream_chat_text


def test_wants_fitline_on_brand_and_products():
    assert wants_fitline_knowledge("genera una idea de imagen de venta de Activise")
    assert wants_fitline_knowledge("háblame de FitLine")
    assert wants_fitline_knowledge("qué es PM International")
    assert wants_fitline_knowledge("precio de Restorate")
    assert wants_fitline_knowledge("FitLine Basics beneficios")
    assert wants_fitline_knowledge("PowerCocktail vs Activize")
    assert wants_fitline_knowledge("quién fundó PM International Rolf Sorg")
    assert wants_fitline_knowledge("qué es el NTC de FitLine")
    assert wants_fitline_knowledge("Optimal Set beneficios")


def test_wants_fitline_rejects_generic_basics():
    assert wants_fitline_knowledge("explícame the basics of marketing") is False
    assert wants_fitline_knowledge("hola cómo estás") is False


def test_format_includes_curated_products_not_invented():
    format_fitline_knowledge_for_prompt.cache_clear()
    block = format_fitline_knowledge_for_prompt()
    assert "Activize" in block or "Activise" in block
    assert "Restorate" in block
    assert "Basics" in block
    assert "Optimal Set" in block or "Optimal-Set" in block
    assert "NTC" in block or "Nutrient Transport" in block
    assert "Rolf Sorg" in block
    assert "Speyer" in block
    assert "Schengen" in block or "Luxemburgo" in block
    assert "3.22" in block or "3,22" in block
    assert "Frankfurt" in block or "2011" in block
    assert "TÜV" in block or "TUV" in block.upper() or "Tüv" in block
    assert "QR" in block
    assert "Nutrient Transport Concept" in block
    assert "NO «Nutrient Timing»" in block or "NO \"Nutrient Timing\"" in block
    assert "HECHOS OBLIGATORIOS" in block
    assert "Partner Area" in block or "no invent" in block.lower()
    assert "compensación 2026" in block.lower() or "income plan" in block.lower()
    assert "Prospección" in block or "prospección" in block.lower()
    assert "Investigando" in block or "investigando" in block.lower()
    assert "NO inventes" in block or "no inventes" in block.lower() or "NO invent" in block
    assert "módulo Oportunidades" in block


def test_compensation_rule_no_invent_percentages():
    format_fitline_knowledge_for_prompt.cache_clear()
    block = format_fitline_knowledge_for_prompt()
    assert "Income Plan" in block or "Partner Area" in block
    assert "NO invent" in block or "no invent" in block.lower()


def test_append_only_when_triggered():
    base = "SYSTEM BASE"
    assert append_fitline_knowledge_if_needed(base, "hola") == base
    out = append_fitline_knowledge_if_needed(base, "idea de venta Activise")
    assert out.startswith(base)
    assert "FitLine" in out or "Activize" in out


def test_chat_light_system_includes_fitline_for_activise():
    system = _build_chat_system_light("user-test", "idea de imagen de Activise")
    assert "Activize" in system or "Oxyplus" in system
    assert "NO inventes" in system or "no inventes" in system.lower()
    # No debe incentivar preguntar qué es el producto
    assert "Oportunidades" in system
    assert "ENTREGA el texto" in system or "ENTREGA FITLINE" in system


def test_module_stream_context_returns_fitline_block():
    ctx, meta = fetch_module_stream_context(
        "user-test",
        "dame una idea de copy para vender Activise",
    )
    assert ctx
    assert "Activize" in ctx or "Restorate" in ctx
    assert meta and meta.get("intent") == "fitline_opportunity"
    assert "no preguntes qué es el producto" in ctx.lower() or "NO preguntes" in ctx


def test_prompt_for_activise_is_text_not_image_and_gets_fitline():
    from app.services.chat_intents import (
        is_generate_image_intent,
        is_text_ideation_request,
    )

    msg = "hazme un prompt para vender Activise"
    assert is_text_ideation_request(msg) is True
    assert is_generate_image_intent(msg) is False
    system = _build_chat_system_light("user-test", msg)
    assert "Oportunidades" in system
    assert "NO generes imagen" in system or "no generes imagen" in system.lower()


def test_prefers_fitline_over_web_for_product_questions():
    assert prefers_fitline_over_web("precio de Restorate") is True
    assert prefers_fitline_over_web("qué es Activize") is True
    assert prefers_fitline_over_web("beneficios de FitLine Basics") is True
    assert fitline_explicit_live_web_override("precio de Restorate") is False
    # Override explícito: internet / precio de hoy
    assert prefers_fitline_over_web("busca FitLine en internet") is False
    assert prefers_fitline_over_web("precio actual de Restorate hoy") is False
    assert fitline_explicit_live_web_override("busca FitLine en google") is True


def test_voice_resolve_web_search_skips_fitline_internal():
    assert resolve_web_search_request("precio de Restorate", []) is None
    assert resolve_web_search_request("qué es Activize", []) is None
    # Con override sí puede ir a web
    req = resolve_web_search_request("busca FitLine en internet", [])
    assert req is not None
    assert "FitLine" in req["query"] or "fitline" in req["query"].lower()


def test_chat_can_stream_fitline_price_without_blocking_for_web():
    assert _can_stream_chat_text("precio de Restorate") is True


def test_advanced_pipeline_not_forced_for_fitline_investiga():
    from app.services.advanced_mode.intents import needs_advanced_full_pipeline

    # «investiga» genérico + FitLine → Oportunidades, no forzar search_web
    assert needs_advanced_full_pipeline("investiga qué es FitLine", []) is False
    assert needs_advanced_full_pipeline("busca noticias de hoy", []) is True


def test_fitline_user_prefix_anchors_facts():
    from app.services.opportunities_pilot.fitline_knowledge import (
        with_fitline_user_prefix,
    )

    out = with_fitline_user_prefix("qué es FitLine")
    assert out.startswith("[CED-OPORTUNIDADES")
    assert "Nutrient Transport" in out
    assert "1993" in out
    assert with_fitline_user_prefix("hola") == "hola"
