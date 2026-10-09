"""Tests — generación de imágenes con referencia de sesión (chat normal y avanzado)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.chat_image_generation import (
    build_enriched_generation_context,
    effective_user_prompt,
    extract_vision_context_from_history,
    run_chat_image_generation,
    salvage_image_turn,
    should_take_direct_image_path,
    should_use_reference_generation,
)
from app.services.chat_intents import (
    is_image_subject_correction,
    parse_followup_image_prompt,
    user_requests_prior_reference,
    wants_image_reference_edit,
)
from app.services.marketing_creative import resolve_image_creation_from_text
from app.services.publish_image_context import (
    clear_session_image,
    get_last_image_generation_prompt,
    get_session_vision_analysis,
    register_text_chat_image,
    register_text_chat_image_url,
    resolve_reference_image_bytes,
    set_session_vision_analysis,
)

USER = "user-img-test"
CONV = "conv-img-test"
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
)

VISION_REPLY = (
    "**Qué es** — Flyer promocional DUGLE STUDIO.\n"
    "**Detalle visible** — Nombre «DUGLE STUDIO», precios $49 / $79 / $99, fondo oscuro.\n"
    "**Contexto** — Estilo flyer vertical.\n"
    "**Observaciones** — Tipografía sans-serif blanca."
)

HISTORY_AFTER_ANALYSIS = [
    {"role": "user", "content": "analiza esta imagen"},
    {"role": "model", "content": VISION_REPLY},
]


@pytest.fixture(autouse=True)
def _clean_image_session():
    clear_session_image(USER, CONV)
    yield
    clear_session_image(USER, CONV)


def test_register_text_chat_image_stores_bytes_for_followup():
    register_text_chat_image(USER, CONV, PNG, "image/png", filename="ref.png")
    resolved = resolve_reference_image_bytes(USER, CONV)
    assert resolved is not None
    data, mime = resolved
    assert data == PNG
    assert mime == "image/png"


def test_vision_analysis_cached_and_injected_in_context():
    set_session_vision_analysis(USER, CONV, VISION_REPLY)
    cached = get_session_vision_analysis(USER, CONV)
    assert "DUGLE STUDIO" in cached
    ctx = build_enriched_generation_context(
        "genera flyer igual con mismos precios",
        HISTORY_AFTER_ANALYSIS,
        user_id=USER,
        conversation_id=CONV,
    )
    assert "DUGLE STUDIO" in ctx
    assert "Instrucciones actuales del usuario" not in ctx
    # Visión/hechos sí; el pedido del usuario ya no se duplica con etiqueta meta.

def test_extract_vision_context_from_history():
    text = extract_vision_context_from_history(HISTORY_AFTER_ANALYSIS)
    assert "Qué es" in text
    assert "$49" in text


def test_user_requests_prior_reference_detects_phrases():
    assert user_requests_prior_reference("créame una imagen igual a la que te pasé")
    assert user_requests_prior_reference("mismos precios y mismo diseño")
    assert not user_requests_prior_reference("hola, cómo estás")


def test_resolve_image_creation_uses_reference_flag():
    register_text_chat_image(USER, CONV, PNG, "image/png")
    msg = (
        "genera una imagen igual a la que te pasé con el nombre DUGLE STUDIO, "
        "los mismos precios y diseño estilo flyer"
    )
    resolved = resolve_image_creation_from_text(
        msg,
        HISTORY_AFTER_ANALYSIS,
        has_reference_image=True,
    )
    assert resolved is not None
    assert "Usa la foto adjunta" in resolved["internal_prompt"]
    assert "DUGLE STUDIO" in resolved["internal_prompt"] or "STUDIO" in resolved["internal_prompt"]


@patch("app.services.image_reference_generator.generate_image_with_reference")
def test_run_generation_uses_reference_bytes(mock_ref: MagicMock):
    register_text_chat_image(USER, CONV, PNG, "image/png")
    set_session_vision_analysis(USER, CONV, VISION_REPLY)
    mock_ref.return_value = {
        "ok": True,
        "url": "https://example.com/gen.jpg",
        "quality": "standard",
    }

    msg = "genera creativo igual a la referencia con nombre DUGLE STUDIO y precios $49 $79 $99"
    result = run_chat_image_generation(USER, CONV, msg, HISTORY_AFTER_ANALYSIS, plan_id="elite")

    assert result["ok"] is True
    assert result["url"]
    assert result["used_reference"] is True
    mock_ref.assert_called_once()
    call_kw = mock_ref.call_args.kwargs
    assert call_kw["reference_image"] == PNG
    prompt = call_kw["prompt"]
    assert "DUGLE STUDIO" in prompt or "STUDIO" in prompt or "49" in prompt


@patch("app.services.gemini_images.generate_image")
def test_run_generation_plain_without_reference(mock_gen: MagicMock):
    mock_gen.return_value = {
        "ok": True,
        "url": "https://example.com/plain.jpg",
        "caption": "Atardecer",
        "quality": "standard",
    }
    msg = "genera una imagen de un atardecer en la playa estilo fotorrealista"
    result = run_chat_image_generation(USER, CONV, msg, [], plan_id="elite")

    assert result["ok"] is True
    assert result["url"]
    assert result["used_reference"] is False
    mock_gen.assert_called_once()


@patch("app.services.image_reference_generator.generate_image_with_reference")
def test_run_generation_failure_never_returns_false_success(mock_ref: MagicMock):
    register_text_chat_image(USER, CONV, PNG, "image/png")
    mock_ref.return_value = {"ok": False, "error": "Límite diario alcanzado", "code": "quota_exhausted"}

    msg = "genera otra imagen igual a la referencia con DUGLE STUDIO"
    result = run_chat_image_generation(USER, CONV, msg, HISTORY_AFTER_ANALYSIS, plan_id="elite")

    assert result["ok"] is False
    assert not result.get("url")
    assert "Límite" in result["reply"] or "No pude generar" in result["reply"]
    assert "Listo, señor" not in result["reply"]


@patch("app.services.gemini_images.generate_image")
@patch("app.services.image_reference_generator.generate_image_with_reference")
def test_repeat_generations_stay_on_direct_path(mock_ref: MagicMock, mock_gen: MagicMock):
    register_text_chat_image(USER, CONV, PNG, "image/png")
    set_session_vision_analysis(USER, CONV, VISION_REPLY)
    mock_ref.return_value = {
        "ok": True,
        "url": "https://example.com/repeat.jpg",
        "quality": "standard",
    }
    mock_gen.return_value = {
        "ok": True,
        "url": "https://example.com/gpt-flyer.jpg",
        "quality": "text",
        "provider": "gpt_image",
        "ideogram_used": True,
    }

    history = list(HISTORY_AFTER_ANALYSIS)
    prompts = [
        'genera flyer "DUGLE STUDIO" con precios $49 $79 $99',
        "otra vez igual con los mismos precios",
        "hazlo de nuevo mismo diseño",
        "genera otra imagen creativo referencia",
    ]
    for prompt in prompts:
        assert should_take_direct_image_path(prompt, history)
        result = run_chat_image_generation(USER, CONV, prompt, history, plan_id="elite")
        assert result["ok"] is True, result
        assert result["url"]
        history.append({"role": "user", "content": prompt})
        history.append(
            {
                "role": "model",
                "content": "Listo, señor. Aquí está su creativo — imagen generada.",
            }
        )

    # Flyer con copy → GPT Image (referencia conservada). El resto sigue el path
    # de referencia Gemini si el pedido actual no pide tipografía crítica.
    assert mock_gen.call_count + mock_ref.call_count == len(prompts)
    assert mock_gen.call_count >= 1
    first_gen = mock_gen.call_args_list[0]
    assert first_gen.kwargs["prefer_ideogram"] is True
    assert first_gen.kwargs.get("reference_image")


def test_followup_prompt_after_vision_analysis():
    followup = parse_followup_image_prompt(
        "otra vez con los mismos precios",
        HISTORY_AFTER_ANALYSIS,
    )
    assert followup == "otra vez con los mismos precios"


def test_should_use_reference_when_session_has_upload():
    register_text_chat_image(USER, CONV, PNG, "image/png")
    assert should_use_reference_generation(
        "genera creativo estilo flyer con DUGLE STUDIO",
        HISTORY_AFTER_ANALYSIS,
        user_id=USER,
        conversation_id=CONV,
    )


def test_plain_image_request_ignores_stale_session_upload():
    """Una imagen en sesión (análisis/edit fallido) no debe secuestrar text-to-image plano."""
    register_text_chat_image(USER, CONV, PNG, "image/png")
    assert not should_use_reference_generation(
        "Genera una imagen de un pajaro",
        HISTORY_AFTER_ANALYSIS,
        user_id=USER,
        conversation_id=CONV,
    )
    assert should_use_reference_generation(
        "Haz una variacion de esta imagen con colores mas vivos",
        HISTORY_AFTER_ANALYSIS,
        user_id=USER,
        conversation_id=CONV,
    )


@patch("app.services.gemini_images.generate_image")
@patch("app.services.image_reference_generator.generate_image_with_reference")
def test_failed_reference_does_not_block_later_plain(
    mock_ref: MagicMock, mock_gen: MagicMock
):
    register_text_chat_image(USER, CONV, PNG, "image/png")
    mock_ref.return_value = {
        "ok": False,
        "error": "No pude generar la imagen con referencia. Reintenta en unos segundos.",
        "code": "internal_error",
    }
    mock_gen.return_value = {
        "ok": True,
        "url": "https://example.com/plain-after.jpg",
        "caption": "Pajaro",
        "quality": "standard",
    }

    fail = run_chat_image_generation(
        USER,
        CONV,
        "Haz una variacion de esta imagen con colores mas vivos",
        HISTORY_AFTER_ANALYSIS,
        plan_id="elite",
    )
    assert fail["ok"] is False
    mock_ref.assert_called_once()

    plain = run_chat_image_generation(
        USER,
        CONV,
        "Genera una imagen de un pajaro",
        HISTORY_AFTER_ANALYSIS,
        plan_id="elite",
    )
    assert plain["ok"] is True
    assert plain["used_reference"] is False
    mock_gen.assert_called_once()


@patch("app.services.chat_image_generation.run_chat_image_generation")
@patch("app.services.text_chat.supabase_db")
def test_text_chat_direct_path_returns_image_not_template(mock_db: MagicMock, mock_run: MagicMock):
    from app.services.text_chat import send_message

    mock_db.get_subscription.return_value = {"plan_id": "elite"}
    mock_db.get_profile.return_value = {"email": "u@test.com", "role": "user"}
    mock_db.get_conversation.return_value = {"id": CONV, "channel": "text"}
    mock_db.get_conversation_messages.return_value = HISTORY_AFTER_ANALYSIS
    mock_db.append_message.return_value = None
    mock_db.create_conversation.return_value = {"id": CONV}

    register_text_chat_image(USER, CONV, PNG, "image/png")
    mock_run.return_value = {
        "ok": True,
        "url": "https://example.com/out.jpg",
        "reply": "Listo, señor. Aquí está su creativo.",
        "caption": "Flyer — DUGLE STUDIO",
        "quality": "standard",
        "used_reference": True,
    }

    with patch("app.services.chat_rate_limit.check_chat_rate_limit", return_value=(True, 0)):
        with patch("app.deps.plan_access.chat_message_limit", return_value=-1):
            with patch("app.services.text_chat._cached_messages_today", return_value=0):
                out = send_message(
                    USER,
                    content="genera imagen igual a la referencia DUGLE STUDIO precios $49",
                    conversation_id=CONV,
                )

    assert out.get("image", {}).get("url")
    mock_run.assert_called_once()


@patch("app.services.chat_image_generation.run_chat_image_generation")
def test_advanced_direct_image_followup(mock_run: MagicMock):
    from app.services.advanced_mode.service import _try_direct_image

    register_text_chat_image(USER, CONV, PNG, "image/png")
    mock_run.return_value = {
        "ok": True,
        "url": "https://example.com/adv.jpg",
        "reply": "Listo, señor. Aquí está su creativo.",
        "caption": "Creativo",
        "quality": "standard",
        "used_reference": True,
    }

    result = _try_direct_image(
        USER,
        "otra vez igual con mismos precios DUGLE STUDIO",
        HISTORY_AFTER_ANALYSIS,
        CONV,
    )
    assert result is not None
    assert result.get("image", {}).get("url")
    mock_run.assert_called_once()


HISTORY_AFTER_FLYER = [
    {"role": "user", "content": "genera un flyer de Restorate con fondo oscuro"},
    {"role": "assistant", "content": "Listo. Aquí está tu imagen generada."},
]


def test_color_followup_is_same_image_edit():
    assert wants_image_reference_edit("cambiale el color") is True
    assert wants_image_reference_edit("hazlo mas oscuro") is True
    follow = parse_followup_image_prompt("cambiale el color", HISTORY_AFTER_FLYER)
    assert follow == "cambiale el color"
    assert should_take_direct_image_path("cambiale el color", HISTORY_AFTER_FLYER) is True
    merged = effective_user_prompt("cambiale el color", HISTORY_AFTER_FLYER)
    assert "Restorate" in merged
    assert "Ajuste sobre la misma imagen" in merged
    assert "cambiale el color" in merged


def test_thicker_letters_followup_is_same_image_edit():
    msg = "ok pero las letras que sean un poco mas gruesas"
    history = [
        {
            "role": "user",
            "content": 'genera una imagen con fondo azul oscuro y las letras "credibilidad"',
        },
        {"role": "assistant", "content": "Listo. Aqui esta la imagen con los cambios pedidos."},
    ]
    assert wants_image_reference_edit(msg) is True
    assert parse_followup_image_prompt(msg, history) == msg
    assert should_take_direct_image_path(msg, history) is True
    from app.services.chat_image_generation import reply_is_image_wait_filler

    assert reply_is_image_wait_filler("Va. Generando letras mas gruesas.") is True


def test_url_only_session_hydrates_bytes_from_disk(tmp_path, monkeypatch):
    from app.services import publish_media

    fname = "userimg1_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png"
    path = tmp_path / fname
    path.write_bytes(PNG)
    monkeypatch.setattr(publish_media, "media_file_path", lambda name: path if name == fname else None)
    url = f"/api/ced/media/publish/{fname}"
    register_text_chat_image_url(USER, CONV, url, prompt="flyer Restorate fondo oscuro")
    resolved = resolve_reference_image_bytes(USER, CONV)
    assert resolved is not None
    assert resolved[0] == PNG
    assert get_last_image_generation_prompt(USER, CONV) == "flyer Restorate fondo oscuro"
    assert should_use_reference_generation(
        "cambiale el color",
        HISTORY_AFTER_FLYER,
        user_id=USER,
        conversation_id=CONV,
    )


@patch("app.services.gemini_images.generate_image")
@patch("app.services.image_reference_generator.generate_image_with_reference")
def test_followup_color_does_not_plain_fallback(mock_ref: MagicMock, mock_gen: MagicMock):
    register_text_chat_image(USER, CONV, PNG, "image/png")
    mock_ref.return_value = {"ok": False, "error": "referencia falló", "code": "internal_error"}
    result = run_chat_image_generation(
        USER,
        CONV,
        "cambiale el color",
        HISTORY_AFTER_FLYER,
        plan_id="elite",
    )
    assert result["ok"] is False
    mock_ref.assert_called_once()
    mock_gen.assert_not_called()
    prompt = mock_ref.call_args.kwargs["prompt"]
    low = prompt.lower()
    assert "same subject" in low or "misma imagen" in low
    assert "cambiale el color" in low or "user request" in low
    assert "hay un problema" not in low


HISTORY_AFTER_CASTLE = [
    {"role": "user", "content": "hazme un castillo"},
    {"role": "assistant", "content": "Listo. Aqui esta tu imagen generada."},
]


def test_any_subject_background_followup_is_same_image_edit():
    msg = "oye pero quiero que salga ese castillo con un fondo amarillo"
    assert wants_image_reference_edit(msg) is True
    assert parse_followup_image_prompt(msg, HISTORY_AFTER_CASTLE) == msg
    assert should_take_direct_image_path(msg, HISTORY_AFTER_CASTLE) is True
    from app.services.copy_quality import user_asks_for_on_image_copy, user_requests_background_change

    assert user_requests_background_change(msg) is True
    assert user_asks_for_on_image_copy(msg) is False
    merged = effective_user_prompt(msg, HISTORY_AFTER_CASTLE)
    assert "castillo" in merged.lower()
    assert "fondo amarillo" in merged.lower()
    assert "Ajuste sobre la misma imagen" in merged


def test_ese_mismo_followup_is_same_image_edit():
    msg = "ese mismo con un fondo azul"
    assert wants_image_reference_edit(msg) is True
    assert parse_followup_image_prompt(msg, HISTORY_AFTER_FLYER) == msg
    assert user_requests_prior_reference(msg) is True


@patch("app.services.gemini_images.generate_image")
@patch("app.services.image_reference_generator.generate_image_with_reference")
def test_scene_followup_uses_reference_and_adds_no_copy(mock_ref: MagicMock, mock_gen: MagicMock):
    register_text_chat_image(USER, CONV, PNG, "image/png")
    register_text_chat_image_url(USER, CONV, "https://example.com/castle.png", prompt="hazme un castillo")
    mock_ref.return_value = {"ok": True, "url": "https://example.com/castle-yellow.png"}
    msg = "quiero que salga ese mismo con un fondo amarillo"
    result = run_chat_image_generation(USER, CONV, msg, HISTORY_AFTER_CASTLE, plan_id="elite")
    assert result["ok"] is True
    mock_ref.assert_called_once()
    mock_gen.assert_not_called()
    prompt = str(mock_ref.call_args.kwargs.get("prompt") or "")
    low = prompt.lower()
    assert "same subject" in low
    assert "fondo amarillo" in low or "user request" in low
    assert "hay un problema" not in low
    assert "textos exactos" not in low


def test_ced_logo_on_last_castle_does_not_inherit_old_phrase():
    from app.services.chat_intents import visual_episode_history
    from app.services.copy_quality import (
        build_reference_logo_on_scene_prompt,
        is_ced_wordmark_only_request,
    )
    from app.services.image_text_ritual import locked_overlay_lines

    old_and_new = [
        {"role": "user", "content": 'hazme un flyer que diga "Credibilidad ahora"'},
        {"role": "assistant", "content": "Listo. Aqui esta tu imagen generada."},
        {"role": "user", "content": "hazme un castillo digital con montanas y un lobo"},
        {"role": "assistant", "content": "Listo. Aqui esta tu imagen generada."},
    ]
    msg = "el castillo que acabas de generar, ponle el logo de CED redondo que diga CED"
    assert is_ced_wordmark_only_request(msg) is True
    assert wants_image_reference_edit(msg) is True
    assert locked_overlay_lines(msg, old_and_new) == ["CED"]
    assert "Credibilidad" not in "".join(locked_overlay_lines(msg, old_and_new))
    episode = visual_episode_history(old_and_new)
    assert "castillo" in episode[0]["content"]
    assert "flyer" not in episode[0]["content"].lower()
    logo = build_reference_logo_on_scene_prompt(msg).lower()
    assert "attached" in logo
    assert "circular" in logo or "ced" in logo
    assert "never expand" in logo
    assert "congregación evangélica" not in logo
    assert "congregacion evangelica" not in logo
    assert "do not replace" in logo or "exact same scene" in logo


@patch("app.services.gemini_images.generate_image")
@patch("app.services.image_reference_generator.generate_image_with_reference")
def test_ced_logo_edit_keeps_castle_reference(mock_ref: MagicMock, mock_gen: MagicMock):
    register_text_chat_image(USER, CONV, PNG, "image/png")
    register_text_chat_image_url(
        USER, CONV, "https://example.com/castle.png", prompt="castillo digital lobo montanas"
    )
    mock_ref.return_value = {"ok": True, "url": "https://example.com/castle-ced.png"}
    history = [
        {"role": "user", "content": 'flyer que diga "frase vieja del otro chat"'},
        {"role": "assistant", "content": "Listo. Aqui esta tu imagen generada."},
        {"role": "user", "content": "hazme un castillo digital con un lobo"},
        {"role": "assistant", "content": "Listo. Aqui esta tu imagen generada."},
    ]
    msg = "el castillo que acabas de generar necesito el logo de CED redondo"
    result = run_chat_image_generation(USER, CONV, msg, history, plan_id="elite")
    assert result["ok"] is True
    mock_ref.assert_called_once()
    prompt = str(mock_ref.call_args.kwargs.get("prompt") or "")
    low = prompt.lower()
    assert "frase vieja" not in low
    assert "congregación" not in low
    assert "ced" in low
    assert "attached" in low or "same scene" in low


def test_newer_user_image_beats_old_conversation_image():
    from app.services.publish_image_context import (
        clear_session_image,
        get_last_uploaded_image_for_session,
    )

    clear_session_image(USER, "old-chat")
    clear_session_image(USER, CONV)
    register_text_chat_image(USER, "old-chat", PNG, "image/png")
    register_text_chat_image_url(USER, "old-chat", "https://example.com/old-flyer.png", prompt="flyer viejo")
    register_text_chat_image(USER, CONV, PNG, "image/png")
    register_text_chat_image_url(USER, CONV, "https://example.com/castle.png", prompt="castillo nuevo")
    row = get_last_uploaded_image_for_session(USER, "old-chat")
    assert row is not None
    assert "castle" in str(row.get("url") or "") or row.get("prompt") == "castillo nuevo"


def test_ideation_hallucination_is_stripped_not_generated():
    reply, attachment = salvage_image_turn(
        USER,
        CONV,
        "dame una idea de flyer de Restorate",
        [],
        'generate_image({"prompt": "un gato espacial"})\nListo, aquí está tu imagen.',
        None,
    )
    assert attachment is None
    assert "generate_image" not in reply
    assert "gato espacial" not in reply.lower() or "idea" in reply.lower()


def test_creatine_correction_is_new_image_not_reference_edit():
    msg = (
        "mejor especifica esa imagen que queria: un hombre musculoso "
        "con un envase de creatina en la mano"
    )
    assert is_image_subject_correction(msg) is True
    assert wants_image_reference_edit(msg) is False
    register_text_chat_image(USER, CONV, PNG, "image/png")
    assert (
        should_use_reference_generation(
            msg,
            [
                {"role": "user", "content": "genera un hombre musculoso con un bote de creatina"},
                {"role": "assistant", "content": "Listo. Aqui esta tu imagen generada."},
            ],
            user_id=USER,
            conversation_id=CONV,
        )
        is False
    )


def test_color_tweak_still_uses_reference():
    assert is_image_subject_correction("cambiale el color") is False
    assert wants_image_reference_edit("cambiale el color") is True


ACTIVIZE_THREAD = [
    {
        "role": "user",
        "content": (
            "hola ced quiero generar una imagen de una persona con un frazco "
            "de activize en la mano pero quiero que el frasco sea el original"
        ),
    },
    {"role": "assistant", "content": "Listo. Aquí está tu imagen generada."},
    {
        "role": "user",
        "content": "ok pero ahora a esa misma foto ponle un fondo azul",
    },
    {"role": "assistant", "content": "Listo. Aquí está tu imagen con los cambios pedidos."},
    {
        "role": "user",
        "content": "ok perfecto a esa misma foto omle el logo de pm arriba a la isquierda en la exquina",
    },
    {"role": "assistant", "content": "Listo. Aquí está tu imagen con los cambios pedidos."},
]


def test_omle_pmle_logo_routes_to_same_image_edit():
    from app.services.chat_intents import is_simple_photo_edit_request
    from app.services.marketing_creative import resolve_image_creation_from_text

    omle = "ok perfecto a esa misma foto omle el logo de pm arriba a la isquierda en la exquina"
    pmle = "ok perfecto a esa misma imagen pmle el logo de pm arriba a la isquierda en la exquina"
    assert wants_image_reference_edit(omle) is True
    assert wants_image_reference_edit(pmle) is True
    assert user_requests_prior_reference(omle) is True
    assert is_simple_photo_edit_request(omle) is True
    assert should_take_direct_image_path(omle, ACTIVIZE_THREAD) is True
    assert should_take_direct_image_path(pmle, ACTIVIZE_THREAD) is True
    assert resolve_image_creation_from_text(omle, ACTIVIZE_THREAD) is None


def test_fondo_azul_is_edit_not_marketing_creativo():
    from app.services.marketing_creative import resolve_image_creation_from_text

    msg = "ok pero ahora a esa misma foto ponle un fondo azul"
    assert wants_image_reference_edit(msg) is True
    assert should_take_direct_image_path(msg, ACTIVIZE_THREAD[:2]) is True
    creation = resolve_image_creation_from_text(msg, ACTIVIZE_THREAD[:2])
    assert creation is None
    merged = effective_user_prompt(msg, ACTIVIZE_THREAD[:2])
    assert "activize" in merged.lower()
    assert "fondo azul" in merged.lower()
    assert "creativo —" not in merged.lower()


def test_from_scratch_composes_activize_blue_and_pm_logo():
    from app.services.chat_intents import (
        compose_visual_thread_brief,
        user_requests_from_scratch_compose,
    )

    msg = "ok genera esa desde cero asi con todo esos detalles"
    assert user_requests_from_scratch_compose(msg) is True
    assert should_take_direct_image_path(msg, ACTIVIZE_THREAD) is True
    register_text_chat_image(USER, CONV, PNG, "image/png")
    assert (
        should_use_reference_generation(
            msg,
            ACTIVIZE_THREAD,
            user_id=USER,
            conversation_id=CONV,
        )
        is False
    )
    brief = compose_visual_thread_brief(msg, ACTIVIZE_THREAD) or ""
    low = brief.lower()
    assert "activize" in low
    assert "fondo azul" in low
    assert "logo de pm" in low
    merged = effective_user_prompt(msg, ACTIVIZE_THREAD)
    assert "activize" in merged.lower()
    assert "fondo azul" in merged.lower()
    assert "logo de pm" in merged.lower()


def test_ced_corner_badge_prompt_does_not_paint_user_request():
    from app.services.copy_quality import build_reference_logo_on_scene_prompt

    msg = (
        "quiero que esa misma imagen tenga el logo arriba en un cuadrito "
        "en la esquina derecha azul cian y en ese azul cian le pongas CED"
    )
    prompt = build_reference_logo_on_scene_prompt(msg)
    low = prompt.lower()
    assert "user request" not in low
    assert "apply this change" not in low
    assert "white background" in low or "white canvas" in low
    assert "top-right" in low or "corner" in low
    assert "cyan" in low
    assert "circular ced logo in the center" not in low
    assert "CED" in prompt


def test_new_castle_with_ced_and_phrase_is_not_a_reference_edit():
    from app.services.chat_intents import (
        user_requests_new_image_piece,
        wants_image_reference_edit,
    )
    from app.services.copy_quality import (
        build_reference_scene_edit_prompt,
        is_ced_wordmark_only_request,
    )

    msg = (
        "genera una imagen con un fondo totalmente oscuro con un castillo digital "
        "y en la puerta el logo redondo CED y abajo inevitablemente el tiempo "
        "va a pasar no te dediques a perderlo"
    )
    history = [
        {"role": "user", "content": "genera un flyer con un reloj de arena"},
        {"role": "assistant", "content": "Listo. Aquí está tu imagen generada."},
    ]
    assert is_ced_wordmark_only_request(msg) is False
    assert user_requests_new_image_piece(msg, history) is True
    assert wants_image_reference_edit(msg) is False
    prompt = build_reference_scene_edit_prompt(msg)
    assert "apply this change" not in prompt.lower()
    assert "user request" not in prompt.lower()


def test_safe_caption_never_leaks_edit_prompt():
    from app.services.copy_quality import safe_image_display_caption

    leak = (
        "EDIT the attached image. Keep the EXACT same subject "
        "(same castle/building/person/object, same geometry, same circular C"
    )
    assert safe_image_display_caption(leak, edited=True) == "Imagen editada"
    assert "EDIT" not in safe_image_display_caption(leak)
    assert safe_image_display_caption("Flyer — DUGLE STUDIO") == "Flyer — DUGLE STUDIO"


@patch("app.services.gemini_images.generate_image")
@patch("app.services.image_reference_generator.generate_image_with_reference")
def test_activize_fondo_azul_reply_is_not_creativo(mock_ref: MagicMock, mock_gen: MagicMock):
    register_text_chat_image(USER, CONV, PNG, "image/png")
    register_text_chat_image_url(USER, CONV, "https://example.com/activize.png", prompt="activize")
    mock_ref.return_value = {
        "ok": True,
        "url": "https://example.com/activize-blue.png",
        "caption": (
            "EDIT the attached image. Keep the EXACT same subject "
            "(same castle/building/person/object"
        ),
    }
    msg = "ok pero ahora a esa misma foto ponle un fondo azul"
    result = run_chat_image_generation(USER, CONV, msg, ACTIVIZE_THREAD[:2], plan_id="elite")
    assert result["ok"] is True
    mock_ref.assert_called_once()
    assert "creativo" not in str(result.get("reply") or "").lower()
    assert "EDIT the attached" not in str(result.get("caption") or "")
    assert result["caption"] == "Imagen editada"
