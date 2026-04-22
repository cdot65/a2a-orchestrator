"""Per-source-IP rate limiting that runs at the outer ASGI layer.

Unlike `slowapi.SlowAPIMiddleware`, this middleware enforces limits on ALL
requests, including those routed to a mounted Starlette sub-app (the A2A
surface). Backed by the `limits` package's moving-window strategy with
in-memory storage.

Usage:

    from starlette.middleware import Middleware
    app.add_middleware(build_rate_limit_middleware, limits=["1200/minute"])
"""

from __future__ import annotations

from typing import Any

from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp


def _client_key(request: Request) -> str:
    # Prefer X-Forwarded-For when behind a trusted proxy (Traefik IngressRoute
    # sets this). Fall back to the direct socket peer.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


class _GlobalRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, limits: list[str] | None = None) -> None:
        super().__init__(app)
        self._storage = MemoryStorage()
        self._strategy = MovingWindowRateLimiter(self._storage)
        self._limits = [parse(spec) for spec in (limits or ["1200/minute"])]

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        key = _client_key(request)
        for limit in self._limits:
            if not self._strategy.hit(limit, key):
                retry_after = 60
                # limits exposes the reset time via get_window_stats
                stats = self._strategy.get_window_stats(limit, key)
                if stats and stats.reset_time:
                    import time as _time

                    retry_after = max(1, int(stats.reset_time - _time.time()))
                return JSONResponse(
                    {
                        "error": {
                            "type": "rate_limit_exceeded",
                            "message": f"Rate limit exceeded: {limit}",
                        }
                    },
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )
        return await call_next(request)


def build_rate_limit_middleware(
    app: ASGIApp, limits: list[str] | None = None
) -> _GlobalRateLimitMiddleware:
    """Factory so `app.add_middleware(build_rate_limit_middleware, limits=...)` works."""
    return _GlobalRateLimitMiddleware(app, limits=limits)
