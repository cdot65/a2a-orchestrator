"""Exercise each deployed endpoint and validate responses against the OpenAPI schemas."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
from jsonschema import Draft202012Validator

BASE = "http://localhost:18000"
SPECS_DIR = Path("/Users/cdot/development/cdot65/a2a-orchestrator/docs/openapi")

# Load orchestrator OpenAPI (has A2A + OpenAI-compat paths + schemas)
ORCH_SPEC = json.loads((SPECS_DIR / "orchestrator.openapi.json").read_text())
SCHEMAS = ORCH_SPEC["components"]["schemas"]


PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{PASS if ok else FAIL} {name}{': ' + detail if detail else ''}")


def validate_against(instance, schema_name: str, test_name: str) -> bool:
    """Validate instance against a named component schema, handling $defs inline."""
    schema = SCHEMAS.get(schema_name)
    if schema is None:
        record(test_name, False, f"unknown schema {schema_name}")
        return False
    # Compose a root schema that carries all component schemas so $refs resolve.
    root = {
        **schema,
        "$defs": SCHEMAS,
    }
    # Rewrite #/components/schemas/X → #/$defs/X within this validator
    root_str = json.dumps(root).replace("#/components/schemas/", "#/$defs/")
    root = json.loads(root_str)
    try:
        Draft202012Validator(root).validate(instance)
        record(test_name, True, f"matches {schema_name}")
        return True
    except Exception as e:
        record(test_name, False, f"schema {schema_name} violated: {str(e).splitlines()[0]}")
        return False


# ---------- 1. Discovery / metadata ----------

print("\n== Discovery / metadata ==\n")

r = httpx.get(f"{BASE}/.well-known/agent-card.json", timeout=10)
record("GET /.well-known/agent-card.json → 200", r.status_code == 200, f"HTTP {r.status_code}")
if r.status_code == 200:
    card = r.json()
    validate_against(card, "AgentCard", "AgentCard schema conforms")
    record(
        "AgentCard name + skill",
        card.get("name") == "orchestrator"
        and any(s.get("id") == "orchestrate" for s in card.get("skills", [])),
        f"name={card.get('name')!r}",
    )

r = httpx.get(f"{BASE}/openapi.json", timeout=10)
record("GET /openapi.json → 200", r.status_code == 200)
if r.status_code == 200:
    spec = r.json()
    has_a2a = "/" in spec.get("paths", {})
    has_v1 = "/v1/chat/completions" in spec.get("paths", {})
    record(
        "/openapi.json includes A2A + OpenAI-compat paths",
        has_a2a and has_v1,
        f"A2A={has_a2a} v1={has_v1}",
    )

r = httpx.get(f"{BASE}/v1/openapi.json", timeout=10)
record("GET /v1/openapi.json → 200", r.status_code == 200)
if r.status_code == 200:
    v1_spec = r.json()
    record(
        "/v1/openapi.json is FastAPI-auto",
        "/v1/chat/completions" in v1_spec.get("paths", {}),
    )

# ---------- 2. OpenAI — GET /v1/models ----------

print("\n== OpenAI — /v1/models ==\n")

r = httpx.get(f"{BASE}/v1/models", timeout=10)
record("GET /v1/models → 200", r.status_code == 200)
if r.status_code == 200:
    models = r.json()
    record(
        "models list shape",
        models.get("object") == "list" and isinstance(models.get("data"), list),
    )
    ids = [m.get("id") for m in models.get("data", [])]
    record("a2a-orchestrator model listed", "a2a-orchestrator" in ids, f"ids={ids}")

# ---------- 3. OpenAI — /v1/chat/completions non-streaming ----------

print("\n== OpenAI — /v1/chat/completions (non-streaming) ==\n")

req_body = {
    "model": "a2a-orchestrator",
    "messages": [{"role": "user", "content": "Reply with exactly: pong"}],
    "stream": False,
}
r = httpx.post(f"{BASE}/v1/chat/completions", json=req_body, timeout=120)
record(
    "POST /v1/chat/completions (stream=false) → 200", r.status_code == 200, f"HTTP {r.status_code}"
)
if r.status_code == 200:
    cc = r.json()
    validate_against(cc, "ChatCompletionResponse", "ChatCompletionResponse schema")
    record(
        "response.object == chat.completion",
        cc.get("object") == "chat.completion",
        str(cc.get("object")),
    )
    choice = cc.get("choices", [{}])[0]
    content = choice.get("message", {}).get("content", "")
    record(
        "choice[0].message.content non-empty",
        bool(content),
        f"len={len(content)}",
    )
    record(
        "finish_reason present",
        choice.get("finish_reason") in ("stop", "length", "content_filter", None),
        f"finish_reason={choice.get('finish_reason')!r}",
    )
else:
    print("  body:", r.text[:400])

# ---------- 4. OpenAI — streaming SSE ----------

print("\n== OpenAI — /v1/chat/completions (streaming SSE) ==\n")

req_body_stream = {
    "model": "a2a-orchestrator",
    "messages": [{"role": "user", "content": "Say exactly: pong"}],
    "stream": True,
}

chunks = []
saw_done = False
first_delta_role = None
last_finish_reason = None
with httpx.stream("POST", f"{BASE}/v1/chat/completions", json=req_body_stream, timeout=120) as r:
    record("POST stream=true → 200", r.status_code == 200, f"HTTP {r.status_code}")
    record(
        "content-type: text/event-stream",
        "text/event-stream" in r.headers.get("content-type", ""),
        r.headers.get("content-type", ""),
    )
    if r.status_code == 200:
        for raw in r.iter_lines():
            if not raw:
                continue
            if not raw.startswith("data: "):
                continue
            payload = raw[len("data: ") :]
            if payload.strip() == "[DONE]":
                saw_done = True
                break
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError as e:
                record("SSE frame is JSON", False, str(e))
                continue
            chunks.append(obj)

record("saw [DONE] terminator", saw_done)
record("at least 1 chunk", len(chunks) >= 1, f"got {len(chunks)}")
if chunks:
    for c in chunks:
        validate_against(c, "ChatCompletionChunk", "chunk schema")
        break  # just validate shape on the first
    first_delta_role = chunks[0]["choices"][0]["delta"].get("role")
    record(
        "first chunk delta.role == assistant",
        first_delta_role == "assistant",
        f"role={first_delta_role!r}",
    )
    last_finish_reason = chunks[-1]["choices"][0]["finish_reason"]
    record(
        "final chunk finish_reason == stop",
        last_finish_reason == "stop",
        f"finish_reason={last_finish_reason!r}",
    )

# ---------- 5. A2A message/send non-streaming ----------

print("\n== A2A — message/send (non-streaming JSON-RPC) ==\n")

a2a_body = {
    "jsonrpc": "2.0",
    "id": "verify-1",
    "method": "message/send",
    "params": {
        "message": {
            "role": "user",
            "parts": [{"kind": "text", "text": "Reply briefly: hello"}],
            "messageId": "verify-msg-1",
        }
    },
}
r = httpx.post(f"{BASE}/", json=a2a_body, timeout=120)
record("POST / message/send → 200", r.status_code == 200, f"HTTP {r.status_code}")
if r.status_code == 200:
    resp = r.json()
    record(
        "jsonrpc == 2.0",
        resp.get("jsonrpc") == "2.0",
        str(resp.get("jsonrpc")),
    )
    record(
        "id echoed",
        resp.get("id") == "verify-1",
        str(resp.get("id")),
    )
    # Could be result (Task/Message) or error
    if "error" in resp:
        record("no JSON-RPC error", False, str(resp["error"])[:120])
    else:
        record("has result", "result" in resp)
        # Try to validate against SendMessageResponse
        validate_against(resp, "SendMessageResponse", "SendMessageResponse schema")
else:
    print("  body:", r.text[:400])

# ---------- 6. A2A message/stream ----------

print("\n== A2A — message/stream (SSE JSON-RPC) ==\n")

a2a_stream_body = {
    "jsonrpc": "2.0",
    "id": "verify-2",
    "method": "message/stream",
    "params": {
        "message": {
            "role": "user",
            "parts": [{"kind": "text", "text": "Say exactly: pong"}],
            "messageId": "verify-msg-2",
        }
    },
}

sse_frames = 0
saw_final = False
with httpx.stream("POST", f"{BASE}/", json=a2a_stream_body, timeout=180) as r:
    record("POST / message/stream → 200", r.status_code == 200, f"HTTP {r.status_code}")
    record(
        "content-type: text/event-stream",
        "text/event-stream" in r.headers.get("content-type", ""),
        r.headers.get("content-type", ""),
    )
    if r.status_code == 200:
        for raw in r.iter_lines():
            if not raw.startswith("data: "):
                continue
            payload = raw[len("data: ") :]
            try:
                obj = json.loads(payload)
            except Exception:
                continue
            sse_frames += 1
            # Each frame should be a SendStreamingMessageResponse per spec
            if sse_frames <= 3:
                validate_against(obj, "SendStreamingMessageResponse", f"frame #{sse_frames} schema")
            # Detect final event
            result = obj.get("result", {})
            if isinstance(result, dict) and result.get("final") is True:
                saw_final = True
            if sse_frames > 200:
                break

record(f"received {sse_frames} SSE frames", sse_frames > 0)
record("saw a final=true event", saw_final)

# ---------- 7. Error paths ----------

print("\n== Error paths ==\n")

r = httpx.post(
    f"{BASE}/v1/chat/completions", json={"model": "a2a-orchestrator", "messages": []}, timeout=10
)
record("empty messages → 400", r.status_code == 400, f"HTTP {r.status_code}")

r = httpx.post(
    f"{BASE}/v1/chat/completions",
    content=b"not-json",
    headers={"content-type": "application/json"},
    timeout=10,
)
record("invalid JSON → 4xx", 400 <= r.status_code < 500, f"HTTP {r.status_code}")

# ---------- Summary ----------

print("\n== Summary ==\n")
total = len(results)
passed = sum(1 for _, ok, _ in results if ok)
print(f"{passed}/{total} checks passed")
failed = [(n, d) for n, ok, d in results if not ok]
if failed:
    print("\nFailed:")
    for n, d in failed:
        print(f"  - {n}: {d}")
    sys.exit(1)
