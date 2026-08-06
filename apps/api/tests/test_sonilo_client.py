"""Tests Sonilo client: errores visibles + fail-fast en trial/billing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.video_edit_pilot import sonilo


def test_parse_trial_exhausted_402():
    resp = MagicMock()
    resp.status_code = 402
    resp.text = '{"code":"trial_exhausted","message":"You have used your 2 free trial calls"}'
    resp.reason_phrase = "Payment Required"
    resp.json.return_value = {
        "code": "trial_exhausted",
        "message": "You've used your 2 free trial calls",
    }
    err = sonilo._parse_api_error(resp)
    assert err["ok"] is False
    assert err["http_status"] == 402
    assert err["code"] == "trial_exhausted"
    assert "free trial" in err["message"].lower() or "trial" in err["message"].lower()


def test_resolve_fail_fast_on_text_trial(monkeypatch):
    monkeypatch.setattr(sonilo, "sonilo_configured", lambda: True)

    def fake_sfx(prompt: str, *, duration_sec: float = 2.0):
        return {
            "ok": False,
            "stage": "submit",
            "http_status": 402,
            "code": "trial_exhausted",
            "message": "trial done",
        }

    calls = {"n": 0}

    def counting_sfx(prompt: str, *, duration_sec: float = 2.0):
        calls["n"] += 1
        return fake_sfx(prompt, duration_sec=duration_sec)

    monkeypatch.setattr(sonilo, "generate_sfx_result", counting_sfx)
    cues = [
        {"prompt": "whoosh", "start": 1, "duration_sec": 2},
        {"prompt": "impact", "start": 5, "duration_sec": 2},
        {"prompt": "hit", "start": 9, "duration_sec": 2},
    ]
    out = sonilo.resolve_cues_to_audio_clips(cues, max_cues=4)
    assert out["ok"] == 0
    assert calls["n"] == 1  # fail-fast, no quemar 3 llamadas
    assert out["error"]["code"] == "trial_exhausted"
    assert "trial_exhausted" in (out["message"] or "")
    assert "sin clips" in (out["message"] or "").lower() or out["ok"] == 0
    assert out["errors"]


def test_resolve_video_sfx_success_skips_text(monkeypatch):
    monkeypatch.setattr(sonilo, "sonilo_configured", lambda: True)

    def fake_video(video_url: str, *, prompt: str | None = None):
        return {"ok": True, "url": "https://cdn.example/sfx.mp3", "task_id": "abc"}

    def boom_text(prompt: str, *, duration_sec: float = 2.0):
        raise AssertionError("text-to-sfx no debe llamarse si video-to-sfx ok")

    monkeypatch.setattr(sonilo, "generate_video_sfx_result", fake_video)
    monkeypatch.setattr(sonilo, "generate_sfx_result", boom_text)
    out = sonilo.resolve_cues_to_audio_clips(
        [{"prompt": "x", "start": 0, "duration_sec": 2}],
        video_url="https://cdn.example/source.mp4",
        script_hint="action cut",
    )
    assert out["ok"] == 1
    assert out["mode"] == "video_to_sfx"
    assert out["clips"][0]["asset"]["src"].endswith("sfx.mp3")
