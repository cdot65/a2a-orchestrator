# A2A Project — curl Reference

> See `docs/openapi/*.openapi.json` for full schemas.

Start all agents with `make run-all` (needs Docker for the shell agent).

## Port map

| Agent        | Port | Skill              |
|--------------|------|--------------------|
| orchestrator | 8000 | `orchestrate`      |
| recipe-url   | 8001 | `parse_recipe_url` |
| recipe-gen   | 8002 | `generate_recipe`  |
| shell        | 8003 | `run_shell`        |

---

## Discovery endpoints

### Agent Card

`GET /.well-known/agent-card.json` — returns the agent's identity, capabilities, and skills.

```bash
# orchestrator
curl -s http://localhost:8000/.well-known/agent-card.json \
  | jq '{name: .name, description: .description, skill: .skills[0].id}'

# recipe-url
curl -s http://localhost:8001/.well-known/agent-card.json \
  | jq '{name: .name, description: .description, skill: .skills[0].id}'

# recipe-gen
curl -s http://localhost:8002/.well-known/agent-card.json \
  | jq '{name: .name, description: .description, skill: .skills[0].id}'

# shell
curl -s http://localhost:8003/.well-known/agent-card.json \
  | jq '{name: .name, description: .description, skill: .skills[0].id}'
```

### Static OpenAPI spec

`GET /openapi.json` — the hand-authored OpenAPI 3.1 spec for each agent.

```bash
# orchestrator
curl -s http://localhost:8000/openapi.json | jq '.info.title'

# recipe-url
curl -s http://localhost:8001/openapi.json | jq '.info.title'

# recipe-gen
curl -s http://localhost:8002/openapi.json | jq '.info.title'

# shell
curl -s http://localhost:8003/openapi.json | jq '.info.title'
```

### FastAPI auto-generated OpenAPI (orchestrator only)

`GET /v1/openapi.json` — the FastAPI-generated spec covering only the OpenAI-compat surface (`/v1/models`, `/v1/chat/completions`).

```bash
curl -s http://localhost:8000/v1/openapi.json | jq '.paths | keys'
```

Swagger UI for the OpenAI-compat surface: `http://localhost:8000/v1/docs`

---

## A2A protocol — JSON-RPC on POST /

All four agents share the same JSON-RPC 2.0 envelope on `POST /`. The `method` field selects the operation. Required envelope fields:

| Field      | Value                                              |
|------------|----------------------------------------------------|
| `jsonrpc`  | `"2.0"`                                            |
| `id`       | any string or integer (echoed back in the response)|
| `method`   | `"message/send"` or `"message/stream"` etc.        |
| `params`   | `{ "message": { ... } }`                           |

The `message` object requires `role`, `parts`, and `messageId`. Parts are typed by `kind`: `"text"`, `"file"`, or `"data"`.

### message/send (non-streaming)

Returns a single JSON-RPC response. `result` is a `Task` object (with `id`, `contextId`, `status.state`, and optionally `artifacts`) or, in some agent implementations, a `Message` object.

#### orchestrator — skill: `orchestrate`

```bash
curl -s -X POST http://localhost:8000/ \
  -H 'content-type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-1",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "Give me a vegan ramen recipe."}],
        "messageId": "m1"
      }
    }
  }' | jq .
```

#### recipe-url — skill: `parse_recipe_url`

```bash
curl -s -X POST http://localhost:8001/ \
  -H 'content-type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-1",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "https://cookieandkate.com/vegan-ramen-recipe/"}],
        "messageId": "m1"
      }
    }
  }' | jq .
```

#### recipe-gen — skill: `generate_recipe`

```bash
curl -s -X POST http://localhost:8002/ \
  -H 'content-type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-1",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "A spicy miso ramen for 2 people"}],
        "messageId": "m1"
      }
    }
  }' | jq .
```

#### shell — skill: `run_shell`

```bash
curl -s -X POST http://localhost:8003/ \
  -H 'content-type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-1",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "ls /work"}],
        "messageId": "m1"
      }
    }
  }' | jq .
```

**Inspect the task state from any response:**

```bash
# pipe the above command and check state
... | jq '.result.status.state'
# expected: "completed" | "working" | "failed" | ...
```

---

### message/stream (streaming via SSE)

Use `curl -N` to disable output buffering. The server responds with `Content-Type: text/event-stream`. Each line is formatted as `data: <JSONRPCResponse>\n\n`, where the result is one of `TaskStatusUpdateEvent`, `TaskArtifactUpdateEvent`, `Task`, or `Message`. The final event has `result.final: true`.

#### orchestrator

```bash
curl -N -X POST http://localhost:8000/ \
  -H 'content-type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-2",
    "method": "message/stream",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "Give me a vegan ramen recipe."}],
        "messageId": "m1"
      }
    }
  }'
```

#### recipe-url

```bash
curl -N -X POST http://localhost:8001/ \
  -H 'content-type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-2",
    "method": "message/stream",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "https://cookieandkate.com/vegan-ramen-recipe/"}],
        "messageId": "m1"
      }
    }
  }'
```

#### recipe-gen

```bash
curl -N -X POST http://localhost:8002/ \
  -H 'content-type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-2",
    "method": "message/stream",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "A spicy miso ramen for 2 people"}],
        "messageId": "m1"
      }
    }
  }'
```

#### shell

```bash
curl -N -X POST http://localhost:8003/ \
  -H 'content-type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-2",
    "method": "message/stream",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "ls /work"}],
        "messageId": "m1"
      }
    }
  }'
```

---

### tasks/get

Look up a task by ID after dispatching with `message/send`. Replace `TASK_ID` with the value of `.result.id` from a prior `message/send` response.

```bash
# Replace TASK_ID with the id returned in the message/send result
curl -s -X POST http://localhost:8000/ \
  -H 'content-type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-3",
    "method": "tasks/get",
    "params": {"id": "TASK_ID"}
  }' | jq .
```

The same envelope works on ports 8001–8003 for their respective agents.

---

### tasks/cancel

Cancel a running or submitted task. Replace `TASK_ID` with the task ID to cancel. Returns an error (`-32002 TaskNotCancelableError`) if the task is already in a terminal state.

```bash
# Replace TASK_ID with the id of the task to cancel
curl -s -X POST http://localhost:8000/ \
  -H 'content-type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-4",
    "method": "tasks/cancel",
    "params": {"id": "TASK_ID"}
  }' | jq .
```

---

## OpenAI-compatible chat API — orchestrator only

The orchestrator exposes an OpenAI-compatible surface at `/v1/*`. No auth required for local dev.

### List models

```bash
curl -s http://localhost:8000/v1/models | jq '.data[0].id'
# returns: "a2a-orchestrator"
```

### Chat completion — non-streaming

Returns a `chat.completion` object. Key fields: `id`, `choices[0].message.content`, `usage`.

```bash
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{
    "model": "a2a-orchestrator",
    "messages": [
      {"role": "user", "content": "Give me a vegan ramen recipe"}
    ]
  }' | jq .
```

Extract just the reply text:

```bash
# (optional) extract reply content only
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{
    "model": "a2a-orchestrator",
    "messages": [
      {"role": "user", "content": "Give me a vegan ramen recipe"}
    ]
  }' | jq '.choices[0].message.content'
```

**Response shape:**

```json
{
  "id": "chatcmpl-<hex>",
  "object": "chat.completion",
  "created": 1700000000,
  "model": "a2a-orchestrator",
  "choices": [
    {
      "index": 0,
      "message": {"role": "assistant", "content": "..."},
      "finish_reason": "stop"
    }
  ],
  "usage": {"prompt_tokens": 0, "completion_tokens": 42, "total_tokens": 42}
}
```

### Chat completion — streaming

Pass `"stream": true`. The response is `text/event-stream`. Each line is `data: <chat.completion.chunk JSON>`. The stream ends with `data: [DONE]`.

```bash
curl -N -X POST http://localhost:8000/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{
    "model": "a2a-orchestrator",
    "messages": [
      {"role": "user", "content": "Give me a vegan ramen recipe"}
    ],
    "stream": true
  }'
```

Each `data:` frame (except the final `[DONE]`) is a `chat.completion.chunk` with `choices[0].delta.content` holding the text fragment. The last chunk before `[DONE]` has `choices[0].finish_reason: "stop"` and an empty delta.

### Multi-turn chat — client-managed history

The OpenAI-compat endpoint accepts the full `messages` array and feeds every turn (user + assistant + system) into the planner and synthesizer. Standard OpenAI-client behavior works: append the assistant's reply to `messages` before sending the next turn.

**Request:**

```bash
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{
    "model": "a2a-orchestrator",
    "messages": [
      {"role": "user", "content": "My favorite cuisine is Thai."},
      {"role": "assistant", "content": "Got it, Thai is your favorite."},
      {"role": "user", "content": "Based on that, recommend a dish I should try."}
    ]
  }'
```

**Response** (abridged):

```json
{
  "id": "chatcmpl-<hex>",
  "object": "chat.completion",
  "created": 1776712000,
  "model": "a2a-orchestrator",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Based on your love of Thai cuisine, I'd recommend trying **Pad Thai** — Thailand's most iconic stir-fried noodle dish! ..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {"prompt_tokens": 0, "completion_tokens": 187, "total_tokens": 187}
}
```

The model sees the full history on every turn, so prior context carries forward naturally.

---

## Multi-turn — A2A server-managed via `contextId`

When calling the A2A endpoint (`POST /`), include a stable `contextId` in `params.message.contextId`. The orchestrator stores the user + synthesized assistant text for each completed task and replays it into the planner/synthesizer on subsequent calls under the same `contextId`. History is capped at the last 20 turns per context.

The first response echoes the `contextId` you sent (or mints one if omitted) under `result.contextId`. Thread that value into every later turn.

### Turn 1 — establishes context

**Request:**

```bash
CTX="session-$(date +%s)"
curl -sS -X POST http://localhost:8000/ \
  -H 'content-type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": "t1",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "My favorite cuisine is Thai."}],
        "messageId": "m1",
        "contextId": "'"$CTX"'"
      }
    }
  }'
```

**Response** (abridged — `result.history` contains the full interleaved plan/dispatch/synthesis event stream; the final agent message is the synthesis):

```json
{
  "jsonrpc": "2.0",
  "id": "t1",
  "result": {
    "kind": "task",
    "id": "21ccf933-ad4a-420e-baf3-8674d6bffd27",
    "contextId": "session-1776712110",
    "status": {"state": "completed"},
    "history": [
      {"role": "user",  "kind": "message", "parts": [{"kind": "text", "text": "My favorite cuisine is Thai."}]},
      {"role": "agent", "kind": "message", "parts": [{"kind": "text", "text": "discovering"}]},
      {"role": "agent", "kind": "message", "parts": [{"kind": "text", "text": "planning"}]},
      {"role": "agent", "kind": "message", "parts": [{"kind": "text", "text": "Plan: 1) recipe-gen:generate_recipe"}]},
      {"role": "agent", "kind": "message", "parts": [{"kind": "text", "text": "[generate_recipe] working: generating recipe"}]},
      {"role": "agent", "kind": "message", "parts": [{"kind": "text", "text": "[generate_recipe] artifact received"}]},
      {"role": "agent", "kind": "message", "parts": [{"kind": "text", "text": "[generate_recipe] completed"}]},
      {"role": "agent", "kind": "message", "parts": [{"kind": "text", "text": "synthesizing"}]},
      {"role": "agent", "kind": "message", "parts": [{"kind": "text", "text": "# Pad Thai ..."}]}
    ]
  }
}
```

### Turn 2 — same `contextId`, model remembers

**Request:**

```bash
curl -sS -X POST http://localhost:8000/ \
  -H 'content-type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": "t2",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "Recommend another dish I should try."}],
        "messageId": "m2",
        "contextId": "'"$CTX"'"
      }
    }
  }'
```

**Response** (synthesized reply references Thai cuisine from turn 1 without it being in the turn-2 prompt):

```json
{
  "jsonrpc": "2.0",
  "id": "t2",
  "result": {
    "kind": "task",
    "id": "d4cc4918-2b7c-45cd-81d2-a6b04c97f982",
    "contextId": "session-1776712110",
    "status": {"state": "completed"},
    "history": [
      "... plan/dispatch events ...",
      {"role": "agent", "kind": "message", "parts": [{"kind": "text", "text": "# Tom Kha Gai (Thai Coconut Chicken Soup) — a wonderful next step in your Thai cooking journey after Pad Thai ..."}]}
    ]
  }
}
```

### Intra-cluster variant

If calling from inside the Kubernetes cluster (where the red-teaming target lives), swap the base URL for the Service DNS name:

```bash
BASE="http://orchestrator.a2a.svc.cluster.local:8000"
# same request bodies as above
```

### Red-team tooling config

For tools that accept a JSON config mapping response/request id fields:

```json
{
  "response_id_field": "result.contextId",
  "request_id_field": "params.message.contextId"
}
```

(Your tool must support dotted paths — the A2A envelope is nested. If it only handles flat top-level fields, use the OpenAI-compat endpoint with client-managed history instead.)

---

## Tips

- **Inspect task state:** `jq '.result.status.state'` on any A2A response. Valid states: `submitted`, `working`, `completed`, `failed`, `canceled`, `input-required`, `rejected`, `auth-required`, `unknown`.
- **Fail on HTTP errors:** add `--fail-with-body` to get the response body while still exiting non-zero on 4xx/5xx.
- **Unbuffered streaming:** `curl -N` is required for `message/stream` and `stream: true` — without it curl buffers the entire response.
- **No auth required:** all endpoints are unauthenticated in local dev.
- **Swagger UI:** `http://localhost:8000/v1/docs` (OpenAI-compat surface only).
- **JSON-RPC errors** are returned as HTTP 200 with `{"jsonrpc":"2.0","error":{"code":<N>,"message":"..."}}`. Notable codes: `-32001` task not found, `-32002` task not cancelable, `-32601` method not found.
