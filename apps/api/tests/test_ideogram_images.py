"""Tests — servicio Ideogram 4.0 (`generate_image_ideogram`), llamada HTTP aislada."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _fake_response(*, status_code=200, json_data=None, text="", content=b"", headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_data or {})
    resp.text = text
    resp.content = content
    resp.headers = headers or {}
    return resp


def _fake_client(*, post_response=None, get_response=None):
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    if post_response is not None:
        client.post = MagicMock(return_value=post_response)
    if get_response is not None:
        client.get = MagicMock(return_value=get_response)
    return client


def _settings(*, ideogram_api_key="ik-test-key"):
    return MagicMock(
        ideogram_api_key=ideogram_api_key,
        ideogram_rendering_speed="TURBO",
        ideogram_resolution="2048x2048",
    )


def test_generate_image_ideogram_success_returns_gemini_compatible_shape():
    from app.services import ideogram_images

    post_resp = _fake_response(
        json_data={
            "created": "2026-07-20T00:00:00Z",
            "response_type": "url",
            "data": [
                {
                    "url": "https://ideogram.ai/api/images/ephemeral/x.png",
                    "is_image_safe": True,
                    "seed": 42,
                    "prompt": "cartel que diga Hola",
                    "resolution": "2048x2048",
                }
            ],
        }
    )
    get_resp = _fake_response(content=b"PNG-BYTES", headers={"content-type": "image/png"})
    client = _fake_client(post_response=post_resp, get_response=get_resp)

    with (
        patch("app.services.ideogram_images.httpx.Client", return_value=client),
        patch("app.services.ideogram_images.get_settings", return_value=_settings()),
    ):
        result = ideogram_images.generate_image_ideogram(prompt='cartel que diga "Hola"')

    assert result["ok"] is True
    assert result["raw_bytes"] == b"PNG-BYTES"
    assert result["mime_type"] == "image/png"
    assert result["provider"] == "ideogram"
    assert result["model"] == "ideogram-v4-turbo"
    assert result["estimated_cost_usd"] == ideogram_images.IDEOGRAM_TURBO_COST_USD
    client.post.assert_called_once()
    _, kwargs = client.post.call_args
    assert kwargs["headers"]["Api-Key"] == "ik-test-key"
    assert kwargs["data"]["rendering_speed"] == "TURBO"


def test_generate_image_ideogram_missing_api_key():
    from app.services import ideogram_images

    with patch("app.services.ideogram_images.get_settings", return_value=_settings(ideogram_api_key="")):
        result = ideogram_images.generate_image_ideogram(prompt="algo")

    assert result["ok"] is False
    assert result["code"] == "config_error"


def test_generate_image_ideogram_empty_prompt():
    from app.services import ideogram_images

    result = ideogram_images.generate_image_ideogram(prompt="   ")
    assert result["ok"] is False
    assert result["code"] == "empty_prompt"


def test_generate_image_ideogram_safety_block_no_url():
    from app.services import ideogram_images

    post_resp = _fake_response(
        json_data={"data": [{"url": "", "is_image_safe": False, "seed": 1, "prompt": "x", "resolution": "2048x2048"}]}
    )
    client = _fake_client(post_response=post_resp)

    with (
        patch("app.services.ideogram_images.httpx.Client", return_value=client),
        patch("app.services.ideogram_images.get_settings", return_value=_settings()),
    ):
        result = ideogram_images.generate_image_ideogram(prompt="algo con marca protegida")

    assert result["ok"] is False
    assert result["code"] == "ideogram_safety_block"


def test_generate_image_ideogram_http_error_falls_gracefully():
    from app.services import ideogram_images

    post_resp = _fake_response(status_code=500, text="internal error")
    client = _fake_client(post_response=post_resp)

    with (
        patch("app.services.ideogram_images.httpx.Client", return_value=client),
        patch("app.services.ideogram_images.get_settings", return_value=_settings()),
    ):
        result = ideogram_images.generate_image_ideogram(prompt="algo")

    assert result["ok"] is False
    assert result["code"] == "ideogram_error"


def test_generate_image_ideogram_download_failure():
    from app.services import ideogram_images

    post_resp = _fake_response(
        json_data={"data": [{"url": "https://ideogram.ai/x.png", "is_image_safe": True, "seed": 1, "prompt": "x", "resolution": "2048x2048"}]}
    )
    get_resp = _fake_response(status_code=404, content=b"")
    client = _fake_client(post_response=post_resp, get_response=get_resp)

    with (
        patch("app.services.ideogram_images.httpx.Client", return_value=client),
        patch("app.services.ideogram_images.get_settings", return_value=_settings()),
    ):
        result = ideogram_images.generate_image_ideogram(prompt="algo")

    assert result["ok"] is False
    assert result["code"] == "ideogram_download_error"


def test_generate_image_ideogram_timeout():
    import httpx

    from app.services import ideogram_images

    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.post = MagicMock(side_effect=httpx.TimeoutException("timed out"))

    with (
        patch("app.services.ideogram_images.httpx.Client", return_value=client),
        patch("app.services.ideogram_images.get_settings", return_value=_settings()),
    ):
        result = ideogram_images.generate_image_ideogram(prompt="algo")

    assert result["ok"] is False
    assert result["code"] == "ideogram_timeout"
