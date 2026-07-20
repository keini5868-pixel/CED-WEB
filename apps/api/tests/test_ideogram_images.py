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
    assert result["num_images_requested"] == 1
    assert result["num_images_returned"] == 1
    assert result["wallet_unit_cost_usd"] == ideogram_images.IDEOGRAM_WALLET_COST_USD
    client.post.assert_called_once()
    _, kwargs = client.post.call_args
    assert kwargs["headers"]["Api-Key"] == "ik-test-key"
    # Debe ir como multipart/form-data real (Ideogram rechaza urlencoded con 415) —
    # httpx solo codifica como multipart si los campos van en `files=`.
    assert "data" not in kwargs or not kwargs.get("data")
    assert kwargs["files"]["rendering_speed"] == (None, "TURBO")
    assert kwargs["files"]["num_images"] == (None, "1")
    assert kwargs["files"]["text_prompt"] == (None, 'cartel que diga "Hola"')


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


def test_generate_image_ideogram_warns_but_uses_first_when_api_returns_many():
    """Si Ideogram devolviera N>1, solo usamos data[0] (no descargamos el resto)."""
    from app.services import ideogram_images

    entries = [
        {
            "url": f"https://ideogram.ai/api/images/ephemeral/{i}.png",
            "is_image_safe": True,
            "seed": i,
            "prompt": "x",
            "resolution": "2048x2048",
        }
        for i in range(5)
    ]
    post_resp = _fake_response(json_data={"data": entries})
    get_resp = _fake_response(content=b"ONLY-FIRST", headers={"content-type": "image/png"})
    client = _fake_client(post_response=post_resp, get_response=get_resp)

    with (
        patch("app.services.ideogram_images.httpx.Client", return_value=client),
        patch("app.services.ideogram_images.get_settings", return_value=_settings()),
    ):
        result = ideogram_images.generate_image_ideogram(prompt='frase "tiempo"')

    assert result["ok"] is True
    assert result["num_images_returned"] == 5
    assert result["num_images_requested"] == 1
    assert result["raw_bytes"] == b"ONLY-FIRST"
    assert result["provider_request_cost_usd"] == round(ideogram_images.IDEOGRAM_TURBO_COST_USD * 5, 4)
    client.get.assert_called_once_with("https://ideogram.ai/api/images/ephemeral/0.png")


def test_generate_image_ideogram_retries_without_num_images_on_400():
    from app.services import ideogram_images

    bad = _fake_response(status_code=400, text='{"error":"Unknown field num_images"}')
    good = _fake_response(
        json_data={
            "data": [
                {
                    "url": "https://ideogram.ai/api/images/ephemeral/ok.png",
                    "is_image_safe": True,
                    "seed": 1,
                    "prompt": "x",
                    "resolution": "2048x2048",
                }
            ]
        }
    )
    get_resp = _fake_response(content=b"PNG", headers={"content-type": "image/png"})
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.post = MagicMock(side_effect=[bad, good])
    client.get = MagicMock(return_value=get_resp)

    with (
        patch("app.services.ideogram_images.httpx.Client", return_value=client),
        patch("app.services.ideogram_images.get_settings", return_value=_settings()),
    ):
        result = ideogram_images.generate_image_ideogram(prompt="algo")

    assert result["ok"] is True
    assert client.post.call_count == 2
    second_files = client.post.call_args_list[1].kwargs["files"]
    assert "num_images" not in second_files
