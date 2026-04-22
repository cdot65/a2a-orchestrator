---
title: curl Examples
---

# curl Examples

The repo also ships [`docs/curl-examples.md`](https://github.com/cdot65/a2a-orchestrator/blob/main/docs/curl-examples.md) with a longer set of recipes; this page covers the essentials.

## Discovery

```bash
curl -s http://localhost:8000/.well-known/agent-card.json | jq .
curl -s http://localhost:8001/.well-known/agent-card.json | jq .
curl -s http://localhost:8002/.well-known/agent-card.json | jq .
curl -s http://localhost:8003/.well-known/agent-card.json | jq .
```

## A2A streaming request to the orchestrator

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

`-N` disables curl buffering so streaming chunks land at your terminal as they arrive.

## A2A request with a contextId (multi-turn)

```bash
CTX=$(uuidgen)

# Turn 1
curl -N -X POST http://localhost:8000/ \
  -H 'content-type: application/json' \
  -d "{
    \"jsonrpc\":\"2.0\",\"id\":\"1\",\"method\":\"message/stream\",
    \"params\":{
      \"contextId\":\"${CTX}\",
      \"message\":{\"role\":\"user\",\"messageId\":\"m1\",
        \"parts\":[{\"kind\":\"text\",\"text\":\"Give me a vegan ramen recipe.\"}]
      }
    }
  }"

# Turn 2 — the orchestrator remembers turn 1 server-side
curl -N -X POST http://localhost:8000/ \
  -H 'content-type: application/json' \
  -d "{
    \"jsonrpc\":\"2.0\",\"id\":\"2\",\"method\":\"message/stream\",
    \"params\":{
      \"contextId\":\"${CTX}\",
      \"message\":{\"role\":\"user\",\"messageId\":\"m2\",
        \"parts\":[{\"kind\":\"text\",\"text\":\"Make it gluten-free.\"}]
      }
    }
  }"
```

## OpenAI-compat — non-streaming

```bash
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{
    "model": "a2a-orchestrator",
    "messages": [{"role": "user", "content": "Give me a vegan ramen recipe"}],
    "stream": false
  }' | jq .
```

## OpenAI-compat — streaming

```bash
curl -N -X POST http://localhost:8000/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{
    "model": "a2a-orchestrator",
    "messages": [{"role": "user", "content": "Give me a vegan ramen recipe"}],
    "stream": true
  }'
```

Each `data: {...}` line is a `ChatCompletionChunk`. The stream ends with `data: [DONE]`.

## Hitting a specialist directly

The recipe-url agent expects a URL as its message text:

```bash
curl -N -X POST http://localhost:8001/ \
  -H 'content-type: application/json' \
  -d '{
    "jsonrpc":"2.0","id":"1","method":"message/stream",
    "params":{"message":{"role":"user","messageId":"m1",
      "parts":[{"kind":"text","text":"https://www.recipetineats.com/vegan-ramen/"}]
    }}
  }'
```

## OpenAPI specs

```bash
curl -s http://localhost:8000/openapi.json | jq '.paths | keys'
curl -s http://localhost:8000/v1/openapi.json | jq '.paths | keys'
```

Open the Swagger UI:

```
http://localhost:8000/v1/docs
```
