"""Tests — economía y flujo piloto Video Edit (tokens por duración)."""

from __future__ import annotations

from app.domain.video_edit_economy import (
    MIN_BILLABLE_SECONDS,
    quote_render,
    quote_video_edit_pack,
    tokens_for_duration_seconds,
    tokens_for_usd,
)
from app.services.video_edit_pilot.timeline import (
    build_edit_timeline,
    build_sonilo_text_cues,
    evaluate_veo_transition,
    split_script_scenes,
)
from app.services.video_edit_pilot.tokens import (
    credit_tokens,
    debit_tokens,
    get_token_balance,
    record_render_attempt,
    reset_memory_for_tests,
    soft_cap_remaining,
)


def setup_function() -> None:
    reset_memory_for_tests()


def test_tokens_conversion_and_minimum_30s():
    assert tokens_for_usd(1) == 100
    assert tokens_for_usd(20) == 2000
    assert tokens_for_duration_seconds(12) == 30
    assert tokens_for_duration_seconds(30) == 30
    assert tokens_for_duration_seconds(45.2) == 46
    assert tokens_for_duration_seconds(60) == 60


def test_quote_margin_at_least_30_percent():
    q = quote_render(30)
    assert q["tokens"] == 30
    assert q["price_usd"] == 0.30
    assert q["margin_percent"] >= 30.0
    assert q["billable_seconds"] == MIN_BILLABLE_SECONDS


def test_pack_20_is_2000_tokens():
    pack = quote_video_edit_pack(20)
    assert pack["tokens"] == 2000
    assert pack["base_videos_30s"] == 66


def test_debit_and_soft_cap():
    uid = "user-video-edit-test"
    credit_tokens(uid, 100, reason="test")
    assert get_token_balance(uid) == 100
    out = debit_tokens(uid, 30, reason="render", duration_sec=30)
    assert out["ok"] is True
    assert out["balance_tokens"] == 70
    from app.domain.video_edit_economy import VIDEO_EDIT_SOFT_CAP_RENDERS_PER_DAY

    for _ in range(VIDEO_EDIT_SOFT_CAP_RENDERS_PER_DAY):
        record_render_attempt(uid)
    assert soft_cap_remaining(uid) == 0


def test_shotstack_edit_json_from_timeline():
    from app.services.video_edit_pilot.shotstack import timeline_to_shotstack_edit

    tl = build_edit_timeline(
        duration_sec=30,
        script="A.\n\nDespués B.\n\nCierre.",
        source_asset="upload://x.mp4",
        veo_enabled=False,
    )
    edit = timeline_to_shotstack_edit(
        source_url="https://example.com/v.mp4",
        timeline=tl,
        duration_sec=30,
    )
    assert edit["output"]["format"] == "mp4"
    clips = edit["timeline"]["tracks"][0]["clips"]
    assert len(clips) >= 1
    assert clips[0]["asset"]["src"] == "https://example.com/v.mp4"


def test_sonilo_cues_are_text_mode_max_5():
    scenes = split_script_scenes(
        "Escena 1: entra a la tienda.\n\nEscena 2: después paga.\n\nEscena 3: celebra.",
        duration_sec=45,
    )
    cues = build_sonilo_text_cues(scenes, max_cues=5)
    assert 3 <= len(cues) <= 5
    assert all(c["mode"] == "text_to_sfx" for c in cues)


def test_veo_off_by_default_even_with_hard_cut():
    scenes = split_script_scenes(
        "Estamos en la oficina.\n\nDespués, corte a la playa al atardecer.",
        duration_sec=40,
    )
    veo = evaluate_veo_transition(scenes, veo_enabled=False)
    assert veo["use_veo"] is False
    veo_on = evaluate_veo_transition(scenes, veo_enabled=True)
    assert veo_on["use_veo"] is True
    assert veo_on["tier"] == "veo-3.1-lite-720p"


def test_timeline_build():
    tl = build_edit_timeline(
        duration_sec=30,
        script="Intro.\n\nDespués el producto.\n\nCierre.",
        source_asset="upload://demo.mp4",
        veo_enabled=False,
    )
    assert tl["provider"] == "shotstack"
    assert tl["sonilo"]["mode"] == "text_to_sfx"
    assert tl["veo"]["use_veo"] is False


def test_plan_and_render_dry_run():
    from app.services.video_edit_pilot.service import plan_and_render

    uid = "user-render-dry"
    credit_tokens(uid, 200, reason="test")
    result = plan_and_render(
        uid,
        duration_sec=35,
        script="Escena A.\n\nEscena B con transición después.",
        source_asset="upload://clip.mp4",
    )
    assert result["ok"] is True
    assert result["tokens_charged"] == 35
    assert result["status"] == "dry_run"
    assert result["timeline"]["scenes"]
    assert get_token_balance(uid) == 165
