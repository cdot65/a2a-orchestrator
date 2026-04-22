---
title: A2A Surface
---

# A2A Surface

Every agent — orchestrator and specialists alike — exposes the same A2A surface.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/.well-known/agent-card.json` | Agent card discovery |
| POST | `/` | JSON-RPC entrypoint |

## Methods

The orchestrator advertises `streaming: true` in its card, so the canonical method is `message/stream`. Direct `message/send` (non-streaming) also works but provides no progress visibility.

### message/stream

Request body:

```json
{
  "jsonrpc": "2.0",
  "id": "<your request id>",
  "method": "message/stream",
  "params": {
    "message": {
      "role": "user",
      "parts": [{"kind": "text", "text": "<your request>"}],
      "messageId": "<unique per message>"
    },
    "contextId": "<optional — reuse to chain turns>"
  }
}
```

Response: a stream of JSON-RPC envelopes, one per A2A event. Each envelope's `result` is one of `TaskStatusUpdateEvent` or `TaskArtifactUpdateEvent`. The stream terminates on `final: true`.

### contextId chaining

Reusing the same `contextId` across requests engages the orchestrator's [server-side history cache](../architecture/history.md). Without it, every request starts fresh.

## Specialist-agent inputs

| Agent | Skill | Expected input |
|---|---|---|
| recipe-url | `parse_recipe_url` | An `http://` or `https://` URL |
| recipe-gen | `generate_recipe` | Freeform recipe-description text |
| shell | `run_shell` | A shell command string |

When the orchestrator dispatches to these agents, it sends the planner's `step.input` (after `{{step_N.output}}` substitution) as the message text.

## Errors

JSON-RPC error envelopes follow the standard shape. The orchestrator translates them into `RuntimeError`s in `dispatch_step()` and emits a `failed` terminal frame to the original caller.

| Terminal state | Reason |
|---|---|
| `failed` | Agent reported an error |
| `canceled` | Caller invoked `tasks/cancel` |
| `rejected` | Agent declined the request |
| `input-required` | Agent needs additional input mid-task |
| `auth-required` | Agent needs credentials |

The orchestrator treats `canceled`, `rejected`, `input-required`, and `auth-required` as terminal-non-completed errors — the dispatch loop aborts and surfaces a `failed` event with the relevant message.
