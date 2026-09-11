"""SSRF: decode/fetch no debe ir a localhost, metadata ni LAN."""

from __future__ import annotations

import pytest

from app.services.safe_http_fetch import UnsafeUrlError, assert_public_http_url


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/secret",
        "http://localhost/x",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.4/img.png",
        "http://192.168.1.10/a",
        "http://[::1]/x",
        "file:///etc/passwd",
        "ftp://example.com/a",
        "http://user:pass@example.com/a",
        "http://metadata.google.internal/",
    ],
)
def test_assert_public_http_url_rejects_private(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        assert_public_http_url(url)


def test_decode_image_data_rejects_localhost() -> None:
    from app.services.publish_media import decode_image_data

    with pytest.raises(ValueError, match="no permitida"):
        decode_image_data("http://127.0.0.1/x.png")
