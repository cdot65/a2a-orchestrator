---
title: Home
---

<div class="hero" markdown>

# A2A Orchestrator

**Reference implementation of an A2A-protocol orchestrator with Claude planning + synthesis**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-%3E%3D3.12-3776ab.svg)](https://www.python.org/)
[![A2A Protocol](https://img.shields.io/badge/protocol-A2A-7e57c2.svg)](https://github.com/google/agent-to-agent)

</div>

---

A2A Orchestrator is a small, end-to-end reference for building agent fan-outs over the **Agent-to-Agent (A2A)** protocol. One coordinator, three specialists, all served as A2A-compliant agents:

- The **orchestrator** discovers peer agents at startup, asks Claude Haiku to plan a sequence of skill calls, dispatches each step over A2A streaming, and streams back a synthesized natural-language answer.
- The **recipe-url** agent fetches a URL, extracts the main text, and emits a structured `Recipe` via Claude tool-use.
- The **recipe-gen** agent generates a fresh `Recipe` from a freeform prompt.
- The **shell** agent runs commands inside a Docker sandbox with a read-only `/work` mount (local-only — excluded from the k8s deployment).

The orchestrator also exposes an **OpenAI-compatible `/v1/chat/completions`** endpoint, so any OpenAI client can drive the full A2A fan-out by pointing at it.

---

## What's Inside

<div class="grid cards" markdown>

-   :material-robot:{ .lg .middle } **A2A Agents**

    ---

    Four `Executor` implementations served by `A2AStarletteApplication`. Each agent advertises a card at `/.well-known/agent-card.json` and accepts streaming JSON-RPC over `POST /`.

    [:octicons-arrow-right-24: Agents](agents/overview.md)

-   :material-graph-outline:{ .lg .middle } **Plan → Dispatch → Synthesize**

    ---

    Claude Haiku produces a JSON plan via tool-use. The orchestrator substitutes `{{step_N.output}}` placeholders, dispatches each step, and streams a final synthesis.

    [:octicons-arrow-right-24: Orchestration Loop](architecture/orchestration-loop.md)

-   :material-broadcast:{ .lg .middle } **Streaming Throughout**

    ---

    Status updates and artifact events flow over A2A streams. The orchestrator forwards every child-agent event as a status message so callers see progress live.

    [:octicons-arrow-right-24: Streaming](architecture/streaming.md)

-   :material-api:{ .lg .middle } **OpenAI-Compatible API**

    ---

    `POST /v1/chat/completions` with `stream=true|false` lets any OpenAI SDK call the orchestrator. Multi-turn history is reconstructed from the `messages` array.

    [:octicons-arrow-right-24: OpenAI Compat](api/openai-compat.md)

</div>

---

## Platform Bits

<div class="grid cards" markdown>

-   :material-radar:{ .lg .middle } **Discovery**

    ---

    `A2A_DISCOVERY_PORTS` for localhost or `A2A_DISCOVERY_URLS` for in-cluster service URLs. Cards are fetched in parallel and the discoverer rewrites `card.url` to the URL it actually reached.

    [:octicons-arrow-right-24: Discovery](architecture/discovery.md)

-   :material-history:{ .lg .middle } **Server-Side History**

    ---

    The orchestrator caches the last 20 turns per `contextId` in-memory, so repeat A2A sessions don't have to re-send transcripts.

    [:octicons-arrow-right-24: History](architecture/history.md)

-   :material-speedometer:{ .lg .middle } **Per-IP Rate Limit**

    ---

    Custom Starlette middleware with the `limits` package's moving-window strategy enforces limits over **all** routes — including the mounted A2A sub-app. Tunable via `RATE_LIMIT`.

    [:octicons-arrow-right-24: Rate Limiting](architecture/rate-limiting.md)

-   :material-docker:{ .lg .middle } **Container + K8s**

    ---

    Single Dockerfile + image, three deployments (orchestrator + two stateless agents). Traefik IngressRoute example for TLS termination on Talos.

    [:octicons-arrow-right-24: Kubernetes](deployment/kubernetes.md)

</div>

---

## Get Started

<div class="grid cards" markdown>

-   :material-download:{ .lg .middle } **Install**

    ---

    `uv` setup, Anthropic key, optional Docker for the shell agent.

    [:octicons-arrow-right-24: Installation](getting-started/installation.md)

-   :material-rocket-launch:{ .lg .middle } **Quick Start**

    ---

    `make run-all`, then `curl` your first orchestrated request.

    [:octicons-arrow-right-24: Quick Start](getting-started/quick-start.md)

-   :material-cog:{ .lg .middle } **Configure**

    ---

    Ports, model, discovery, rate limit, recipe directory.

    [:octicons-arrow-right-24: Configuration](getting-started/configuration.md)

-   :material-book-open-variant:{ .lg .middle } **Architecture**

    ---

    A2A surface, planner schema, dispatch loop, streaming model.

    [:octicons-arrow-right-24: Architecture](architecture/overview.md)

</div>
