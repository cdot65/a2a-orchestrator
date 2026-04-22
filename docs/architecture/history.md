---
title: Conversation History
---

# Conversation History

The orchestrator caches per-`contextId` conversation history in-memory so A2A clients can have multi-turn conversations without resending the full transcript on every request.

## Behavior

| Situation | What happens |
|---|---|
| First request with a new `contextId` | Empty history. Planner sees only `user_text`. |
| Subsequent request with the **same** `contextId` | Prior `USER:` / `ASSISTANT:` turns are prepended to the planner's input as a transcript. |
| Request with **no** `contextId` | History is neither read nor written. |
| History exceeds 20 turns | Oldest turns are dropped (FIFO). |

The cap (`_MAX_HISTORY_TURNS = 20`) bounds memory growth per context.

## Implementation

```python
_MAX_HISTORY_TURNS = 20
_HISTORY: dict[str, list[tuple[str, str]]] = {}

def _build_transcript(history, current_user_text):
    if not history:
        return current_user_text
    lines = [f"{role.upper()}: {text}" for role, text in history]
    lines.append(f"USER: {current_user_text}")
    return "\n\n".join(lines)
```

After synthesis completes:

```python
if ctx_id:
    turns = _HISTORY.setdefault(ctx_id, [])
    turns.append(("user", user_text))
    turns.append(("assistant", "".join(reply_parts)))
    if len(turns) > _MAX_HISTORY_TURNS:
        del turns[: len(turns) - _MAX_HISTORY_TURNS]
```

## Caveats

!!! warning "Process-local"
    `_HISTORY` is a module-level dict. It does **not** survive a restart, and it is **not** shared across replicas. Two orchestrator pods behind a load balancer will each build separate histories for the same `contextId`.

    For sticky sessions, route by `contextId` at the ingress layer, or move history to a shared store (Redis, Postgres). The current implementation deliberately skips this — it's the right complexity for a reference impl, not for a production multi-replica deploy.

## OpenAI-compat history

The OpenAI-compat endpoint takes a different approach: it expects the **client** to pass the full `messages` array on every request, exactly like the real OpenAI API. The endpoint flattens those messages into a transcript string and feeds it to `OrchestratorExecutor.execute()` with a brand-new `contextId` per request, so server-side history is unused for OpenAI-style flows.

This keeps the OpenAI-compat surface stateless and lets clients control history themselves.
