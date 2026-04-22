---
title: OpenAI-Compatible API
---

# OpenAI-Compatible API

The orchestrator exposes a subset of the OpenAI API so that any OpenAI client can drive the full A2A fan-out by pointing at it.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/models` | List models — always returns the single id `a2a-orchestrator` |
| POST | `/v1/chat/completions` | Chat completion (sync or SSE) |
| GET | `/v1/openapi.json` | FastAPI auto-generated spec for the `/v1/...` surface |
| GET | `/v1/docs` | Swagger UI |

## /v1/models

```bash
curl -s http://localhost:8000/v1/models | jq .
```

```json
{
  "object": "list",
  "data": [
    {
      "id": "a2a-orchestrator",
      "object": "model",
      "created": 1737123456,
      "owned_by": "a2a-orchestrator"
    }
  ]
}
```

The orchestrator does not gate on `request.model` — any string works. Use `a2a-orchestrator` for clarity.

## /v1/chat/completions

### Request

```json
{
  "model": "a2a-orchestrator",
  "messages": [
    {"role": "user", "content": "Give me a vegan ramen recipe."}
  ],
  "stream": false
}
```

| Field | Notes |
|---|---|
| `model` | Required, ignored value |
| `messages` | Required, must contain at least one `user` message |
| `stream` | Optional, defaults to `false` |
| `temperature`, `max_tokens` | Accepted but ignored — the orchestrator is the model |

### Multi-turn

Pass the full conversation in `messages`, exactly like the real OpenAI API. The endpoint flattens the array into a transcript string:

```
SYSTEM: ...
USER: prior question
ASSISTANT: prior answer
USER: follow-up
```

…and passes that to the orchestrator. Server-side history (the `_HISTORY` cache) is **not** used for OpenAI-compat requests — clients are responsible for tracking their own conversations.

### Non-streaming response

```json
{
  "id": "chatcmpl-<hex>",
  "object": "chat.completion",
  "created": 1737123456,
  "model": "a2a-orchestrator",
  "choices": [
    {
      "index": 0,
      "message": {"role": "assistant", "content": "..."},
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": <approx>,
    "total_tokens": <approx>
  }
}
```

`prompt_tokens` is always `0`. `completion_tokens` is a naive whitespace-split count of the response — not a real tokenization. Treat it as a rough hint, not a billing signal.

### Streaming response

With `"stream": true` the response is `text/event-stream`:

```
data: {"id":"chatcmpl-...", "object":"chat.completion.chunk", "choices":[{"index":0, "delta":{"role":"assistant","content":"Plan: 1) recipe-gen:generate_recipe"}, "finish_reason":null}]}

data: {"id":"chatcmpl-...", "choices":[{"index":0, "delta":{"content":"[generate_recipe] working: generating recipe"}, "finish_reason":null}]}

data: {"id":"chatcmpl-...", "choices":[{"index":0, "delta":{"content":"<recipe JSON>"}, "finish_reason":null}]}

data: {"id":"chatcmpl-...", "choices":[{"index":0, "delta":{"content":"Here's the recipe..."}, "finish_reason":null}]}

data: {"id":"chatcmpl-...", "choices":[{"index":0, "delta":{}, "finish_reason":"stop"}]}

data: [DONE]
```

Every interim status update from the orchestrator becomes a chunk, including the plan summary and each forwarded child-agent event. Clients that only care about the final answer can drop chunks until they see synthesis text — but most clients render everything as it arrives, which gives users live progress.

## Using with the OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-used",
)

stream = client.chat.completions.create(
    model="a2a-orchestrator",
    messages=[{"role": "user", "content": "Give me a vegan ramen recipe."}],
    stream=True,
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```
