---
title: Streaming
---

# Streaming

Streaming is end-to-end: from the original client all the way through every dispatched child-agent call and Claude's synthesis stream.

## Three event shapes

The orchestrator only ever emits two A2A event types:

| Event | When |
|---|---|
| `TaskStatusUpdateEvent(state=working, message=<text>)` | Stage markers (`discovering`, `planning`, `synthesizing`), plan summary, every text update forwarded from a child agent, every Claude synthesis chunk |
| `TaskStatusUpdateEvent(state=working, no message)` | Quiet stage marker (rare — most stages include a message) |
| `TaskStatusUpdateEvent(state=completed/failed/canceled, final=true)` | Terminal |

It does **not** emit `TaskArtifactUpdateEvent`. The structured outputs from child agents are surfaced through the synthesizer's natural-language summary instead. This keeps the streaming surface uniform — callers receive a single stream of text.

## Helpers

```python
# Status with no text — pure stage marker
status_event(task_id=..., context_id=..., state=TaskState.working, message="planning")

# Interim text update during 'working'
text_update(task_id=..., context_id=..., text="...")

# Final structured artifact (used by specialist agents, not the orchestrator)
artifact_event(task_id=..., context_id=..., mime_type="application/json", text=recipe.model_dump_json())
```

All three are in `common.a2a_helpers`.

## Forwarding child-agent events

In `dispatch_step()`:

```python
async for wrapper in client.send_message_streaming(request):
    if isinstance(wrapper.root, JSONRPCErrorResponse):
        raise RuntimeError(...)
    event = wrapper.root.result

    if isinstance(event, TaskStatusUpdateEvent):
        # Forward as text update with the child's skill name as a label
        await on_event(("text", f"[{skill}] {state_str}: {msg_text}".rstrip(": ")))
        if state_str == "failed":
            raise RuntimeError(...)
    elif isinstance(event, TaskArtifactUpdateEvent):
        # Capture the artifact text — the orchestrator returns the LAST one
        for p in event.artifact.parts:
            if t := getattr(getattr(p, "root", p), "text", None):
                final_artifact_text = t
                await on_event(("text", f"[{skill}] artifact received"))
```

The `[skill]` prefix lets clients group multi-step output without parsing structured fields. In practice, a streaming request looks like:

```
Plan: 1) recipe-url:parse_recipe_url
[parse_recipe_url] working: fetching
[parse_recipe_url] working: extracting
[parse_recipe_url] working: structuring
[parse_recipe_url] artifact received
[parse_recipe_url] completed
Synthesizing...
Here's what I extracted from the page: ...
```

## OpenAI-compat SSE adapter

The OpenAI-compat endpoint translates A2A events into OpenAI-style chunks. See `orchestrator/openai_compat.py:sse_gen`:

- Each forwarded text update becomes a `ChatCompletionChunk` with `delta.content = <text>`.
- The first chunk additionally carries `delta.role = "assistant"`.
- A final chunk with `finish_reason = "stop"` and an empty delta is emitted before the terminal `data: [DONE]` line.
- Artifact events are also flattened into `delta.content` so OpenAI clients see structured-recipe JSON inline.

Non-streaming requests go through `_collect_chunks()`, which drains the same queue and joins everything into one `ChatCompletionResponse.choices[0].message.content`.
