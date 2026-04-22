---
title: Discovery
---

# Discovery

The orchestrator does not maintain a registry. It discovers peer agents by fetching their cards on every request.

## Configuration

| Variable | Format | Wins |
|---|---|---|
| `A2A_DISCOVERY_URLS` | `http://recipe-url.a2a.svc.cluster.local:8001,http://recipe-gen.a2a.svc.cluster.local:8002` | If present, used exclusively |
| `A2A_DISCOVERY_PORTS` | `8001,8002,8003` | Used only when `A2A_DISCOVERY_URLS` is unset; expanded to `http://localhost:PORT` |

## Implementation

`common.a2a_helpers.discover_agents()` fans out concurrently:

```python
async def discover_agents(base_urls: list[str]) -> list[dict[str, Any]]:
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *(_fetch_card(client, url) for url in base_urls),
            return_exceptions=True,
        )
    return [c for c in results if isinstance(c, dict)]
```

Each fetch:

1. `GET <base_url>/.well-known/agent-card.json` with a 2-second timeout.
2. Parses the JSON.
3. **Overwrites `card["url"]`** with the URL the discoverer actually reached, not the value the agent advertises.

The URL rewrite matters in any non-localhost deployment. A pod started with `RECIPE_URL_PORT=8001` has no idea what its in-cluster service URL is — its `build_card()` only knows `http://localhost:8001`. Without the rewrite, the orchestrator would try to dispatch to `http://localhost:8001` from inside its own pod, which is wrong.

## Failure handling

A failed `GET` (network error, non-200, non-JSON) is logged as a `WARNING` and silently dropped from the result list. The planner then sees a smaller capability set and adapts. There is **no** retry loop.

If discovery returns zero agents, the planner is still invoked with an empty capability list. Claude usually emits an empty plan, after which the synthesizer answers from its own knowledge.

## When discovery runs

Discovery happens at the start of **every** orchestrator task, not at process start. This makes the orchestrator robust to:

- Peer agents being scaled up or down between requests.
- A peer agent restarting (no need to restart the orchestrator).
- Adding a new agent — the next request picks it up automatically (if it's in `A2A_DISCOVERY_URLS`).

The cost is one HTTP round-trip per peer per task, with a 2-second per-peer timeout cap. For three peers on the same cluster network, this is sub-millisecond in practice.
