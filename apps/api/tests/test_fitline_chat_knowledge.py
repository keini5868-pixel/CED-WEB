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


def test_wants_fitline_store_entry_phrases():
    assert wants_fitline_knowledge("cómo entro a la tienda")
    assert wants_fitline_knowledge("me trabé en el registro")
    assert wants_fitline_knowledge("primer pedido pendiente")
    assert wants_fitline_knowledge("qué es Partner Area")
    assert wants_fitline_knowledge("verificar el patrocinador en el registro")


def test_store_entry_checklist_in_curated_block():
    format_fitline_knowledge_for_prompt.cache_clear()
    block = format_fitline_knowledge_for_prompt()
    assert "CHECKLIST DE ENTRADA" in block or "Entrar a la tienda" in block
    assert "Sponsor ID" in block or "patrocinador" in block.lower()
    assert "Reiniciar" in block or "Pagar" in block
    assert "Partner Area" in block


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


def test_wants_fitline_spanish_pm_and_bare_pm():
    """Regresión: PM Internacional / «cómo empiezo en PM» ≠ project management."""
    assert wants_fitline_knowledge("PM Internacional")
    assert wants_fitline_knowledge("me refiero a PM Internacional")
    assert wants_fitline_knowledge("Como comienzo en pm")
    assert wants_fitline_knowledge("cómo empiezo en PM")
    assert wants_fitline_knowledge("háblame de PM Internacional")
    assert wants_fitline_knowledge("qué es PM")
    assert prefers_fitline_over_web("Como comienzo en pm") is True
    assert prefers_fitline_over_web("PM Internacional") is True

    chat = _build_chat_system_light("u-pm-es", "Como comienzo en pm")
    assert "CONOCIMIENTO CURADO — PM International" in chat or "HECHOS OBLIGATORIOS FITLINE" in chat
    assert "FitLine" in chat
    assert "DESAMBIGUACIÓN" in chat or "PM-International" in chat
    assert "PROHIBIDO interpretar PM como Project Management" in chat

def test_wants_fitline_rejects_other_pm_meanings():
    assert wants_fitline_knowledge("explícame project management") is False
    assert wants_fitline_knowledge("gestión de proyectos con scrum") is False
    assert wants_fitline_knowledge("comercio internacional y exportaciones") is False
    assert wants_fitline_knowledge("reunión a las 3 pm") is False
    assert wants_fitline_knowledge("explícame the basics of marketing") is False
    assert wants_fitline_knowledge("hola cómo estás") is False


def test_wants_fitline_rejects_generic_basics():
    assert wants_fitline_knowledge("explícame the basics of marketing") is False
    assert wants_fitline_knowledge("hola cómo estás") is False


def test_excel_and_body_topics_do_not_want_fitline():
    """Regresión: Excel / meditación / cuerpo ≠ Activize / Cell Energy."""
    for q in (
        "Qué es Excel",
        "Quiero saber qué es Excel",
        "mi sobrina escuchó algo en YouTube sobre Excel del cuerpo",
        "investiga el punto Excel de meditación",
        "hablaban de un punto que conectaba a otra dimensión",
    ):
        assert wants_fitline_knowledge(q) is False, q
        assert prefers_fitline_over_web(q) is False, q


def test_cierre_plan_does_not_force_fitline_on_excel(monkeypatch):
    from app.services import voice_client_session as vcs
    from app.services.opportunities_pilot.fitline_knowledge import (
        should_inject_fitline_for_turn,
    )
    from app.services.voice_llm_common import build_voice_system

    uid = "excel-user-cierre"
    monkeypatch.setattr(
        "app.services.opportunities_pilot.fitline_guide_mode.user_plan_is_fitline_focus",
        lambda _uid: True,
    )
    monkeypatch.setattr(
        "app.services.insight_questions.capture_insight_question",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "app.services.user_session_profile.touch_and_learn",
        lambda *a, **k: None,
    )
    vcs.set_fitline_topic_suppressed(uid, False)
    assert should_inject_fitline_for_turn(uid, "Qué es Excel") is False
    system = build_voice_system(uid, "Qué es Excel")
    # La identidad base puede mencionar FitLine como capacidad; lo prohibido es
    # inyectar la ficha/closer en un turno de Excel.
    assert "HECHOS OBLIGATORIOS FITLINE" not in system
    assert "ASESOR COMERCIAL" not in system
    assert "CONOCIMIENTO CURADO — PM International" not in system
    assert "CIERRE PRIORITARIO" not in system
    assert "portal de oportunidades" not in system.lower()


def test_fitline_topic_opt_out_blocks_until_reopen(monkeypatch):
    from app.services import voice_client_session as vcs
    from app.services.opportunities_pilot.fitline_knowledge import (
        append_fitline_knowledge_if_needed,
        is_fitline_topic_opt_out_phrase,
        should_inject_fitline_for_turn,
        sync_fitline_topic_preference,
    )

    uid = "opt-out-user"
    phrase = (
        "Quiero que investigues eso y no me hables sobre el negocio de "
        "PM International ni nada de eso"
    )
    assert is_fitline_topic_opt_out_phrase(phrase)
    sync_fitline_topic_preference(uid, phrase)
    assert vcs.is_fitline_topic_suppressed(uid) is True
    assert should_inject_fitline_for_turn(uid, "investiga el punto del cuerpo") is False
    # force=True no debe colar ficha en tema ajeno con opt-out activo
    out = append_fitline_knowledge_if_needed(
        "BASE", "investiga el punto del cuerpo", force=True, user_id=uid
    )
    assert out == "BASE"
    # Reabrir al pedir FitLine explícito
    assert should_inject_fitline_for_turn(uid, "cuéntame de FitLine") is True
    assert vcs.is_fitline_topic_suppressed(uid) is False
    out2 = append_fitline_knowledge_if_needed(
        "BASE", "cuéntame de FitLine", user_id=uid
    )
    assert "FitLine" in out2 or "Activize" in out2


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
    assert "4" in block and ("mil millones" in block or "billion" in block.lower())
    assert "Sarasota" in block or "Manatee" in block or "América" in block or "America" in block
    assert "Frankfurt" in block or "2011" in block
    assert "TÜV" in block or "TUV" in block.upper() or "Tüv" in block
    assert "QR" in block
    assert "GMP" in block
    assert "Cologne" in block or "cologne" in block.lower()
    assert "ATP" in block
    assert "We Care" in block or "WeCare" in block
    assert "Nutrient Transport Concept" in block
    assert "NO «Nutrient Timing»" in block or "NO \"Nutrient Timing\"" in block
    assert "HECHOS OBLIGATORIOS" in block
    assert "Partner Area" in block or "no invent" in block.lower()
    assert "compensación 2026" in block.lower() or "income plan" in block.lower()
    assert "Prospección" in block or "prospección" in block.lower()
    assert "Investigando" in block or "investigando" in block.lower()
    assert "NO inventes" in block or "no inventes" in block.lower() or "NO invent" in block
    assert "módulo Oportunidades" in block
    assert "ASESOR COMERCIAL" in block or "VENDER SIN PARECER" in block
    assert "CIERRE ESTRATÉGICO" in block or "cierre" in block.lower()
    assert "search_web" in block.lower() or "Tavily" in block or "PROHIBIDO" in block
    assert "coincida exactamente" in block


def test_wants_fitline_expanded_catalog_skus():
    assert wants_fitline_knowledge("qué es PowerCocktail Junior")
    assert wants_fitline_knowledge("beneficios de Generation 50+")
    assert wants_fitline_knowledge("Protein Max para deporte")
    assert wants_fitline_knowledge("ProShape All-in-1")
    assert wants_fitline_knowledge("Get in Shape FitLine")
    assert wants_fitline_knowledge("Zellschutz Antioxy")
    assert wants_fitline_knowledge("microSolve HeartDuo")
    assert wants_fitline_knowledge("microSolve Omega 3")
    assert wants_fitline_knowledge("Joint-Health Set")
    assert wants_fitline_knowledge("Basen Plus")
    assert wants_fitline_knowledge("Herbaslim Tea")
    assert wants_fitline_knowledge("Feel Good Yoghurt")
    assert wants_fitline_knowledge("Endurance de FitLine")
    assert wants_fitline_knowledge("qué es la Cologne List de FitLine")
    assert wants_fitline_knowledge("PM We Care donaciones")
    # Genéricos solos no deben disparar FitLine
    assert wants_fitline_knowledge("entrenamiento de endurance") is False
    assert wants_fitline_knowledge("recetas con whey") is False


def test_format_includes_expanded_catalog_categories():
    format_fitline_knowledge_for_prompt.cache_clear()
    block = format_fitline_knowledge_for_prompt()
    assert "NUTRICIÓN BASE" in block or "Nutrición base" in block or "Optimal-Set" in block
    assert "PowerCocktail Junior" in block
    assert "Generation 50+" in block
    assert "Endurance" in block
    assert "Protein Max" in block
    assert "Get in Shape" in block
    assert "ProShape All-in-1" in block or "ProShape All-in" in block
    assert "Zellschutz" in block or "Antioxy" in block
    assert "Munogen" in block
    assert "microSolve" in block
    assert "HeartDuo" in block or "Heart Duo" in block
    assert "Joint-Health" in block or "Joint Health" in block
    assert "Belleza" in block


def test_all_three_modes_get_same_curated_block():
    """Voz, chat light y bloque format comparten los mismos hechos curados."""
    format_fitline_knowledge_for_prompt.cache_clear()
    block = format_fitline_knowledge_for_prompt()
    from app.services.text_chat import _build_chat_system_light
    from app.services.voice_llm_common import build_base_voice_system

    q = "cuéntame la historia de PM International y el NTC"
    chat = _build_chat_system_light("user-test", q)
    voice = build_base_voice_system("user-test", q)
    for hay in (block, chat, voice):
        assert "1993" in hay
        assert "Schengen" in hay or "Luxemburgo" in hay
        assert "Cologne" in hay or "cologne" in hay.lower()
        assert "GMP" in hay
        assert "We Care" in hay
        assert "Optimal Set" in hay or "Optimal-Set" in hay
        assert "Partner Area" in hay or "no invent" in hay.lower()
        assert "Investigando" in hay or "investigando" in hay.lower()


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


def test_fitline_sales_closer_is_internal_only():
    from app.services.opportunities_pilot.fitline_knowledge import (
        fitline_sales_closer_overlay,
    )

    overlay = fitline_sales_closer_overlay()
    assert "ASESOR COMERCIAL" in overlay or "VENDER SIN PARECER" in overlay
    assert "SOLO ESTE TEMA" in overlay or "ÚNICAMENTE" in overlay
    assert "search_web" in overlay.lower() or "Tavily" in overlay
    assert "PROHIBIDO" in overlay
    assert "sin retener" in overlay.lower() or "información real" in overlay.lower()
    # Compacto: persuasión operativa, no novelón
    assert len(overlay) < 7500
    assert "expansión" in overlay.lower() or "América" in overlay or "America" in overlay


def test_voice_system_includes_sales_closer_for_fitline():
    from app.services.voice_llm_common import build_base_voice_system

    format_fitline_knowledge_for_prompt.cache_clear()
    system = build_base_voice_system("user-test", "qué es FitLine")
    assert "ASESOR COMERCIAL" in system or "VENDER SIN PARECER" in system
    assert "CIERRE" in system.upper() or "cierre" in system.lower()


def test_realtime_fitline_prompt_has_knowledge_not_jarvis():
    from app.domain.openai_voice_prompt import build_realtime_instructions
    from app.services.opportunities_pilot.fitline_knowledge import (
        format_fitline_knowledge_for_prompt,
    )

    format_fitline_knowledge_for_prompt.cache_clear()
    text = build_realtime_instructions(voice_profile="fitline")
    assert "CED" in text
    assert "FitLine" in text or "FITLINE" in text.upper()
    assert (
        "ASESOR COMERCIAL" in text
        or "VENDER SIN PARECER" in text
        or "CHECKLIST DE ENTRADA" in text
        or "HECHOS OBLIGATORIOS FITLINE" in text
    )
    low = text.lower()
    assert (
        "no abras cada respuesta" in low
        or "sin vocativo" in low
        or "nunca re-emitas" in low
        or "español siempre" in low
        or "paridad retell" in low
        or "partner area" in low
    )
    assert "NTC" in text or "Nutrient Transport" in text
    assert len(text) > 5000
    assert len(text) <= 24500

