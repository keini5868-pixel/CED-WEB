from app.services.ced_sentinel_image_vision import (
    _parse_audit_json,
    should_vision_audit_request,
    vision_retry_brief_suffix,
)


def test_should_vision_audit_when_dark_background_and_copy():
    text = 'fondo oscuro con "EL TIEMPO VA A PASAR" en letras blancas'
    assert should_vision_audit_request(text) is True


def test_should_not_vision_audit_generic_scene():
    assert should_vision_audit_request("un gato en la playa al atardecer") is False


def test_parse_audit_json_strips_markdown_fence():
    raw = '```json\n{"pass": false, "issues": ["fondo blanco"]}\n```'
    data = _parse_audit_json(raw)
    assert data.get("pass") is False
    assert "fondo blanco" in data.get("issues", [""])[0]


def test_vision_retry_brief_suffix_includes_detail():
    suffix = vision_retry_brief_suffix("Borde morado en lugar de cian")
    assert "morado" in suffix.casefold()
    assert "QA visual" in suffix
