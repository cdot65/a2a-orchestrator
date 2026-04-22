---
title: Quick Start
---

# Quick Start

## 1. Start every agent

```bash
make run-all
```

All four agents start in the foreground. Logs are interleaved; `Ctrl-C` stops them.

## 2. Confirm the agent card

```bash
curl -s http://localhost:8000/.well-known/agent-card.json | jq .
```

You should see the orchestrator advertising a single skill `orchestrate`.

## 3. Send a streaming A2A request

```bash
curl -N -X POST http://localhost:8000/ \
  -H 'content-type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
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

`-N` disables curl's output buffering so you see streamed status updates as they arrive.

The orchestrator will:

1. Discover the three peer agents.
2. Plan: `recipe-gen.generate_recipe("a vegan ramen recipe")`.
3. Dispatch and stream the agent's progress back.
4. Synthesize a natural-language summary referencing the structured recipe.

The generated recipe lands in `./recipes/<slug>.json` and `./recipes/<slug>.md`.

## 4. Try the OpenAI-compat surface

```bash
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{
    "model": "a2a-orchestrator",
    "messages": [{"role": "user", "content": "Give me a vegan ramen recipe"}],
    "stream": false
  }' | jq .
```

Set `"stream": true` to get SSE chunks (`text/event-stream`) terminated by `data: [DONE]`.

## 5. Drive a multi-step request

The planner happily chains steps. Example:

```bash
curl -N -X POST http://localhost:8000/ \
  -H 'content-type: application/json' \
  -d '{
    "jsonrpc":"2.0","id":"1","method":"message/stream",
    "params":{"message":{"role":"user","messageId":"m1",
      "parts":[{"kind":"text","text":"Parse https://www.recipetineats.com/vegan-ramen/ and tell me what ingredients I would need."}]
    }}
  }'
```

The plan will be roughly: `recipe-url.parse_recipe_url("https://...")` → synthesis. The synthesizer extracts the ingredient list from the structured artifact in its final reply.

## What's next

- [Configuration](configuration.md) — every env var the project respects.
- [Architecture: Orchestration Loop](../architecture/orchestration-loop.md) — what actually happens between request and response.
- [API Reference: curl Examples](../api/curl-examples.md) — the full set of curl recipes.
