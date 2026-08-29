"""Selección de Page/IG en Meta OAuth callback."""

from __future__ import annotations

from app.routers.meta import select_instagram_page_candidate


def test_select_prefers_preferred_ig_id_over_first_page() -> None:
    candidates = [
        {
            "page_id": "111",
            "ig_id": "17841408655184026",
            "ig_username": "keinicastillob",
        },
        {
            "page_id": "222",
            "ig_id": "17841438529982300",
            "ig_username": "ced.ev",
        },
    ]
    chosen = select_instagram_page_candidate(candidates)
    assert chosen is not None
    assert chosen["ig_id"] == "17841438529982300"
    assert chosen["page_id"] == "222"


def test_select_prefers_username_when_id_not_listed() -> None:
    candidates = [
        {"page_id": "1", "ig_id": "999", "ig_username": "other"},
        {"page_id": "2", "ig_id": "888", "ig_username": "@Ced.Ev"},
    ]
    chosen = select_instagram_page_candidate(
        candidates,
        preferred_ig_ids=frozenset(),
        preferred_usernames=frozenset({"ced.ev"}),
    )
    assert chosen is not None
    assert chosen["page_id"] == "2"


def test_select_falls_back_to_first_with_ig() -> None:
    candidates = [
        {"page_id": "1", "ig_id": "aaa", "ig_username": "first"},
        {"page_id": "2", "ig_id": "bbb", "ig_username": "second"},
    ]
    chosen = select_instagram_page_candidate(
        candidates,
        preferred_ig_ids=frozenset({"nope"}),
        preferred_usernames=frozenset({"nope"}),
    )
    assert chosen is not None
    assert chosen["page_id"] == "1"


def test_select_empty() -> None:
    assert select_instagram_page_candidate([]) is None
