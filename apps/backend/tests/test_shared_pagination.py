"""Unit tests for shared/pagination.py (Phase 16, ADR-0023) — pure
logic, no database required."""

from __future__ import annotations

from shared.pagination import PageParams, pagination_envelope


def test_clamp_uses_the_requested_page_and_page_size_when_in_range() -> None:
    params = PageParams.clamp(page=2, page_size=10, max_page_size=100)
    assert params.page == 2
    assert params.page_size == 10


def test_clamp_floors_page_below_one() -> None:
    params = PageParams.clamp(page=0, page_size=10, max_page_size=100)
    assert params.page == 1

    params = PageParams.clamp(page=-5, page_size=10, max_page_size=100)
    assert params.page == 1


def test_clamp_floors_page_size_below_one() -> None:
    params = PageParams.clamp(page=1, page_size=0, max_page_size=100)
    assert params.page_size == 1


def test_clamp_caps_page_size_at_the_server_configured_max() -> None:
    params = PageParams.clamp(page=1, page_size=999999, max_page_size=100)
    assert params.page_size == 100


def test_offset_is_zero_on_page_one() -> None:
    params = PageParams.clamp(page=1, page_size=20, max_page_size=100)
    assert params.offset == 0


def test_offset_advances_by_page_size_per_page() -> None:
    params = PageParams.clamp(page=3, page_size=20, max_page_size=100)
    assert params.offset == 40


def test_pagination_envelope_shape_matches_api_contracts_section_50() -> None:
    params = PageParams.clamp(page=2, page_size=20, max_page_size=100)
    envelope = pagination_envelope([{"id": 1}], params=params, total=45)

    assert envelope == {
        "items": [{"id": 1}],
        "pagination": {"page": 2, "page_size": 20, "total": 45, "total_pages": 3},
    }


def test_pagination_envelope_total_pages_is_zero_when_total_is_zero() -> None:
    params = PageParams.clamp(page=1, page_size=20, max_page_size=100)
    envelope = pagination_envelope([], params=params, total=0)

    assert envelope["pagination"]["total_pages"] == 0


def test_pagination_envelope_rounds_total_pages_up() -> None:
    params = PageParams.clamp(page=1, page_size=20, max_page_size=100)
    envelope = pagination_envelope([], params=params, total=21)

    assert envelope["pagination"]["total_pages"] == 2
