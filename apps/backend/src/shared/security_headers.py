"""Security response headers (security.md §64, ADR-0036).

The first middleware in this codebase. Applies a fixed set of
architecture-independent headers to every response, plus a strict
Content-Security-Policy on every path except the interactive-docs ones
(`/docs`, `/redoc`, `/openapi.json`), which FastAPI serves by default
and which load their own JS/CSS from a CDN — a strict CSP there would
break them rather than protect anything, since this backend is a JSON
API, not the browser-rendered "deployed frontend architecture" security.
md §64 is actually about. See ADR-0036 Decision 1 for the full reasoning
and why CSP specifically needed a documented judgment call while the
other four headers did not.
"""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_DOCS_PATHS = frozenset({"/docs", "/redoc", "/openapi.json"})

_FIXED_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
}

_STRICT_CSP = "default-src 'none'; frame-ancestors 'none'"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for name, value in _FIXED_HEADERS.items():
            response.headers[name] = value
        if request.url.path not in _DOCS_PATHS:
            response.headers["Content-Security-Policy"] = _STRICT_CSP
        return response
