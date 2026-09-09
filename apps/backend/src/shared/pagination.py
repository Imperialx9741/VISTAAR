"""Shared pagination helpers, matching docs/05-api/api-contracts.md §50
(Pagination) exactly:

    Request:  ?page=1&page_size=20
    Response: {"data": {"items": [...], "pagination": {
                 "page": 1, "page_size": 20, "total": 100, "total_pages": 5
               }}, "error": null, "request_id": "..."}

This is the first list endpoint this codebase builds (Phase 16, ADR-0023
— Search Rides / Search Penalties), so this belongs in shared/ rather
than inside modules/ride or modules/penalty: every future list endpoint
needs the identical request/response shape, the same "first module to
need it belongs in shared/" reasoning shared/api_envelope.py's own
docstring already states.

`max_page_size` (server-configured per §50: "Maximum page size should be
server-configured") is passed in by the caller — core.config.settings.
MAX_PAGE_SIZE — rather than hardcoded here, so this module stays
free of any dependency on core.config (shared/ modules take their
configuration as parameters, not by importing settings directly, mirroring
shared/outbox_publisher.py's own constructor-injection shape).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")

_MIN_PAGE = 1
_MIN_PAGE_SIZE = 1


@dataclass(slots=True, frozen=True)
class PageParams:
    """Validated, clamped pagination request. `page` below 1 clamps to 1;
    `page_size` below 1 clamps to 1, above `max_page_size` clamps to
    `max_page_size` — a client-supplied out-of-range value is corrected,
    not rejected, since api-contracts.md documents no VALIDATION_FAILED
    behavior for pagination params specifically (unlike a genuinely
    invalid filter field)."""

    page: int
    page_size: int

    @staticmethod
    def clamp(*, page: int, page_size: int, max_page_size: int) -> PageParams:
        return PageParams(
            page=max(_MIN_PAGE, page),
            page_size=min(max(_MIN_PAGE_SIZE, page_size), max_page_size),
        )

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def pagination_envelope(
    items: list[dict[str, Any]], *, params: PageParams, total: int
) -> dict[str, Any]:
    total_pages = (total + params.page_size - 1) // params.page_size if total else 0
    return {
        "items": items,
        "pagination": {
            "page": params.page,
            "page_size": params.page_size,
            "total": total,
            "total_pages": total_pages,
        },
    }
