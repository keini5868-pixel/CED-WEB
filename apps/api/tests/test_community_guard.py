from app.services.community_guard import reject_reason, public_display_name
from app.services.community_forum import create_post, list_posts, reset_for_tests


def test_blocks_phone_and_whatsapp():
    assert reject_reason("escríbeme al +1 809 555 1212")
    assert reject_reason("te contacto por whatsapp")
    assert reject_reason("mi correo es a@b.com")


def test_allows_youtube_and_blocks_random_links():
    assert reject_reason("mira https://youtu.be/abc123 este guion") is None
    assert reject_reason("entra a https://bit.ly/x")


def test_blocks_fitline_price_spam():
    assert reject_reason("el precio de entrada es 99")


def test_display_name_is_first_word_only():
    assert public_display_name("Keini Castillo", "x@y.com") == "Keini"


def test_create_and_list_post_in_memory():
    reset_for_tests()
    created = create_post(
        "user-1",
        room="prompts",
        title="Apertura",
        body="Prompt corto para un reel de 15 segundos.",
        token="idea",
    )
    assert created["ok"] is True
    listed = list_posts("user-1", "prompts")
    assert listed["ok"] is True
    assert listed["posts"][0]["body"].startswith("Prompt corto")
