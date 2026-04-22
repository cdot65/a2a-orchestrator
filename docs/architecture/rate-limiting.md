---
title: Rate Limiting
---

# Rate Limiting

The orchestrator enforces per-source-IP rate limits. The implementation lives in `src/a2a_orchestrator/common/ratelimit.py`.

## Why a custom middleware

`slowapi.SlowAPIMiddleware` only sees requests routed through the FastAPI router. The orchestrator **mounts** the A2A `Starlette` sub-app at `/`, so `slowapi` would silently miss every JSON-RPC call to `POST /` — exactly the surface that drives expensive Claude fan-outs.

The custom middleware is registered at the **outer** ASGI layer with `app.add_middleware(...)`, so every request passes through it before routing — covering the OpenAI-compat router, the static OpenAPI handler, and the mounted A2A app uniformly.

## Configuration

| Variable | Default | Format |
|---|---|---|
| `RATE_LIMIT` | `1200/minute` | Comma-separated [`limits`](https://limits.readthedocs.io/) specs, e.g. `50/minute,5/second` |

When multiple limits are supplied, **all** must pass for the request to proceed.

The example k8s manifest sets `RATE_LIMIT=50/minute` to be conservative under the Anthropic Tier-4 ceiling, accounting for the ~3× fan-out per orchestrator request (plan + specialist + synthesize).

## Strategy

`MovingWindowRateLimiter` over `MemoryStorage` from the `limits` package. The moving-window strategy avoids the burstiness of fixed windows: a user can't make 50 requests at 12:00:59 then 50 more at 12:01:00.

## Source-IP detection

```python
def _client_key(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
```

When behind a trusted proxy (e.g., the example Traefik IngressRoute), the `X-Forwarded-For` header carries the real client IP and is preferred over the socket peer.

!!! warning "Trust the proxy, or don't"
    `X-Forwarded-For` is client-controllable when the orchestrator is exposed directly to the internet without a trusted proxy stripping/setting it. If you run without an ingress that normalizes XFF, remove the XFF preference or you will leak the rate limit to anyone who sets the header.

## Response on limit exceeded

```json
{
  "error": {
    "type": "rate_limit_exceeded",
    "message": "Rate limit exceeded: 50/minute"
  }
}
```

HTTP 429 with a `Retry-After` header derived from the moving-window reset time.

## Storage

In-memory only. Each replica has its own counter, which means:

- A 50/minute limit with 3 replicas behind a round-robin LB tolerates up to 150 req/min total per source IP.
- A restart resets all counters.

Move to Redis (`limits.storage.RedisStorage`) for cluster-wide enforcement. The middleware is a single line change — only the storage backend swaps.
