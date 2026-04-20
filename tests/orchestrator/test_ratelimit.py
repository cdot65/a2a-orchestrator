"""Verify the global rate-limit middleware covers direct routes AND mounted sub-apps."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse as SJSONResponse
from starlette.routing import Route

from a2a_orchestrator.common.ratelimit import build_rate_limit_middleware


def _build_app(limits: list[str]) -> FastAPI:
    app = FastAPI()

    @app.get("/ping")
    def _ping() -> dict:
        return {"ok": True}

    app.add_middleware(build_rate_limit_middleware, limits=limits)
    return app


def test_rate_limit_triggers_429_on_direct_route():
    app = _build_app(["2/minute"])
    client = TestClient(app)
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    r = client.get("/ping")
    assert r.status_code == 429
    body = r.json()
    assert body["error"]["type"] == "rate_limit_exceeded"
    assert "Retry-After" in r.headers


def test_rate_limit_covers_mounted_sub_app():
    async def _sub_handler(_request):
        return SJSONResponse({"sub": True})

    sub_app = Starlette(routes=[Route("/", _sub_handler)])

    app = _build_app(["2/minute"])
    app.mount("/sub", sub_app)
    client = TestClient(app)

    assert client.get("/ping").status_code == 200
    assert client.get("/sub/").status_code == 200
    r = client.get("/sub/")
    assert r.status_code == 429


def test_rate_limit_uses_xff_header_when_present():
    app = _build_app(["1/minute"])
    client = TestClient(app)

    # Two different X-Forwarded-For clients get their own buckets.
    assert client.get("/ping", headers={"X-Forwarded-For": "10.0.0.1"}).status_code == 200
    assert client.get("/ping", headers={"X-Forwarded-For": "10.0.0.2"}).status_code == 200
    # Third hit from 10.0.0.1 should now be 429.
    r = client.get("/ping", headers={"X-Forwarded-For": "10.0.0.1"})
    assert r.status_code == 429
