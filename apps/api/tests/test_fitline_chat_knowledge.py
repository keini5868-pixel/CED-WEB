"""FitLine curated knowledge available to chat when products/brand are mentioned."""

from __future__ import annotations

from app.services.chat_module_context import fetch_module_stream_context
from app.services.opportunities_pilot.fitline_knowledge import (
    append_fitline_knowledge_if_needed,
    format_fitline_knowledge_for_prompt,
    wants_fitline_knowledge,
)
from app.services.text_chat import _build_chat_system_light


def test_wants_fitline_on_brand_and_products():
    assert wants_fitline_knowledge("genera una idea de imagen de venta de Activise")
    assert wants_fitline_knowledge("háblame de FitLine")
    assert wants_fitline_knowledge("qué es PM International")
    assert wants_fitline_knowledge("precio de Restorate")
    assert wants_fitline_knowledge("FitLine Basics beneficios")
    assert wants_fitline_knowledge("PowerCocktail vs Activize")


def test_wants_fitline_rejects_generic_basics():
    assert wants_fitline_knowledge("explícame the basics of marketing") is False
    assert wants_fitline_knowledge("hola cómo estás") is False


def test_format_includes_curated_products_not_invented():
    format_fitline_knowledge_for_prompt.cache_clear()
    block = format_fitline_knowledge_for_prompt()
    assert "Activize" in block or "Activise" in block
    assert "Restorate" in block
    assert "Basics" in block
    assert "NTC" in block or "Nutrient Transport" in block
    assert "Schengen" in block or "Luxemburgo" in block
    assert "TÜV" in block or "TUV" in block.upper() or "Tüv" in block
    assert "Partner Area" in block or "no invent" in block.lower()
    assert "Prospección" in block or "prospección" in block.lower()
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
