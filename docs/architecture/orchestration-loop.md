---
title: Orchestration Loop
---

# Orchestration Loop

`OrchestratorExecutor.execute()` in `src/a2a_orchestrator/orchestrator/executor.py` is the heart of the system. Every incoming A2A request — whether direct over `POST /` or via the OpenAI-compat shim — runs through it.

## Phases

```mermaid
flowchart TB
    Start([context.execute]) --> Hist[load history for contextId]
    Hist --> Disc[discover peer agents]
    Disc --> Plan[Claude tool-use → PlanStep[]]
    Plan --> Loop{for each step}
    Loop -->|substitute placeholders| Disp[dispatch to peer agent]
    Disp -->|forward events| Loop
    Loop -->|done| Synth[Claude streaming synthesis]
    Synth --> Save[append turn to history]
    Save --> End([emit completed])
```

## 1. History replay

```python
ctx_id = context.context_id
history = list(_HISTORY.get(ctx_id, [])) if ctx_id else []
planner_input = _build_transcript(history, user_text) if history else user_text
```

If the caller reuses a `contextId` across A2A requests, the orchestrator prepends prior `USER:` / `ASSISTANT:` turns to the planner's input. See [Conversation History](history.md).

## 2. Discovery

Run on **every** task — not cached at process start. This keeps the orchestrator resilient to peer agents being scaled up or down between requests.

```python
urls_env = os.environ.get("A2A_DISCOVERY_URLS", "").strip()
if urls_env:
    base_urls = [u.strip() for u in urls_env.split(",") if u.strip()]
else:
    ports = [...]
    base_urls = [f"http://localhost:{p}" for p in ports]
cards = await discover_agents(base_urls)
```

See [Discovery](discovery.md) for the parallel-fetch + URL-rewrite logic.

## 3. Planning

`build_plan(planner_input, cards)` formats the discovered cards into a capability listing and asks Claude to emit a structured plan via tool-use:

```python
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "agent": {"type": "string"},
                    "skill": {"type": "string"},
                    "input": {"type": "string"},
                },
                "required": ["agent", "skill", "input"],
            },
        }
    },
    "required": ["steps"],
}
```

The planner's `system` prompt explicitly tells Claude to:

- Use **only** agents from the supplied capability list.
- Reference prior step outputs with `{{step_N.output}}` placeholders (1-indexed).
- Emit an empty plan if no agent is needed (the synthesizer can still answer).

The plan summary (`Plan: 1) recipe-gen:generate_recipe; ...`) is forwarded to the caller as a status text update before any dispatch happens.

## 4. Dispatch

Each `PlanStep` is dispatched **sequentially** (the project deliberately keeps the loop simple — parallel fan-out within a single request would need additional book-keeping). Before dispatch, placeholders are substituted from the `step_outputs` dict:

```python
resolved_input = substitute_placeholders(step.input, step_outputs)
```

`dispatch_step()` opens an `httpx.AsyncClient`, builds an `A2AClient` against the peer's URL (the URL the discoverer rewrote — not the agent's self-advertised URL), and consumes its streaming response. Every text-bearing event is forwarded to the original caller via `_on_event`. The **last** `TaskArtifactUpdateEvent` with text wins and is stored in `step_outputs[idx]`.

If a step fails, the orchestrator emits a final `TaskStatusUpdateEvent` with `state=failed` and `message=f"step {idx}: {e}"` and returns. No subsequent steps are attempted.

## 5. Synthesis

```python
async for chunk in synthesize(planner_input, step_outputs=step_outputs):
    reply_parts.append(chunk)
    await event_queue.enqueue_event(text_update(...))
```

`synthesize()` builds a user message containing the original request and every step's output, then streams Claude's reply chunk-by-chunk. Each chunk goes back to the caller as a `working`-state text update.

## 6. History append + final

After synthesis completes:

```python
if ctx_id:
    turns = _HISTORY.setdefault(ctx_id, [])
    turns.append(("user", user_text))
    turns.append(("assistant", "".join(reply_parts)))
    if len(turns) > _MAX_HISTORY_TURNS:
        del turns[: len(turns) - _MAX_HISTORY_TURNS]
```

Then the terminal `TaskStatusUpdateEvent` with `state=completed` and `final=true` is emitted.

## Cancellation

`OrchestratorExecutor.cancel()` simply emits a final `state=canceled` event. Long-running child-agent calls are not interrupted — they finish in the background; their outputs are dropped.
