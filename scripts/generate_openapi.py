"""Generate OpenAPI 3.1 specs for all four A2A agents."""

import copy
import json
import pathlib

from a2a.types import (
    AgentCard,
    AgentSkill,
    Artifact,
    JSONRPCErrorResponse,
    Message,
    Part,
    Role,
    SendMessageRequest,
    SendMessageResponse,
    SendMessageSuccessResponse,
    SendStreamingMessageRequest,
    SendStreamingMessageResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from fastapi import FastAPI

from a2a_orchestrator.orchestrator.executor import build_card as orch_build_card
from a2a_orchestrator.orchestrator.openai_compat import router as openai_router
from a2a_orchestrator.recipe_gen.executor import build_card as gen_build_card
from a2a_orchestrator.recipe_url.executor import build_card as url_build_card
from a2a_orchestrator.shell.executor import build_card as shell_build_card

OUT_DIR = pathlib.Path(__file__).parent.parent / "docs" / "openapi"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rewrite_refs(obj: object) -> object:
    """Recursively rewrite '#/$defs/Foo' -> '#/components/schemas/Foo'."""
    if isinstance(obj, dict):
        return {
            k: (
                v.replace("#/$defs/", "#/components/schemas/")
                if k == "$ref" and isinstance(v, str)
                else _rewrite_refs(v)
            )
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_rewrite_refs(item) for item in obj]
    return obj


def _collect_schemas() -> dict:
    """Collect JSON schemas from all relevant a2a-sdk Pydantic models."""
    pydantic_models = [
        AgentCard,
        AgentSkill,
        Message,
        TextPart,
        Part,
        SendMessageRequest,
        SendMessageSuccessResponse,
        SendMessageResponse,
        SendStreamingMessageRequest,
        SendStreamingMessageResponse,
        Task,
        TaskStatus,
        TaskStatusUpdateEvent,
        TaskArtifactUpdateEvent,
        Artifact,
        JSONRPCErrorResponse,
    ]

    schemas: dict = {}

    for model in pydantic_models:
        raw = model.model_json_schema()
        # Hoist any inline $defs into the top-level schemas dict so we can
        # reference them with $ref later.
        for name, defn in raw.pop("$defs", {}).items():
            if name not in schemas:
                schemas[name] = defn
        schemas[model.__name__] = raw

    # Rewrite all internal '#/$defs/...' refs to '#/components/schemas/...'
    schemas = _rewrite_refs(schemas)

    # Add Role and TaskState enums manually (they are Python enums, not Pydantic models)
    schemas["Role"] = {
        "title": "Role",
        "type": "string",
        "enum": [e.value for e in Role],
        "description": "The role of the message sender.",
    }
    schemas["TaskState"] = {
        "title": "TaskState",
        "type": "string",
        "enum": [e.value for e in TaskState],
        "description": "The lifecycle state of a task.",
    }

    return schemas


def _make_jsonrpc_post_operation(schemas: dict) -> dict:  # noqa: ARG001
    """Build the POST / operation covering message/send and message/stream."""
    return {
        "summary": "A2A JSON-RPC endpoint",
        "description": (
            "Accepts JSON-RPC 2.0 requests. Primary methods:\n"
            "- `message/send` — send a message and receive a single response\n"
            "- `message/stream` — send a message and receive an SSE stream\n\n"
            "Additional methods (not fully described here): `tasks/get`, `tasks/cancel`."
        ),
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "oneOf": [
                            {"$ref": "#/components/schemas/SendMessageRequest"},
                            {"$ref": "#/components/schemas/SendStreamingMessageRequest"},
                        ],
                        "discriminator": {
                            "propertyName": "method",
                            "mapping": {
                                "message/send": ("#/components/schemas/SendMessageRequest"),
                                "message/stream": (
                                    "#/components/schemas/SendStreamingMessageRequest"
                                ),
                            },
                        },
                    }
                }
            },
        },
        "responses": {
            "200": {
                "description": (
                    "Successful response. Content-Type is `application/json` for "
                    "`message/send`, or `text/event-stream` (SSE) for `message/stream`."
                ),
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/SendMessageResponse"},
                        "examples": {
                            "message_send": {
                                "summary": "message/send success",
                                "value": {
                                    "jsonrpc": "2.0",
                                    "id": "1",
                                    "result": {
                                        "id": "task-abc",
                                        "status": {"state": "completed"},
                                        "artifacts": [
                                            {
                                                "parts": [
                                                    {
                                                        "kind": "text",
                                                        "text": "Done!",
                                                    }
                                                ]
                                            }
                                        ],
                                    },
                                },
                            }
                        },
                    },
                    "text/event-stream": {
                        "schema": {
                            "type": "string",
                            "description": (
                                "Server-Sent Events stream. Each event's `data` field "
                                "contains a JSON-serialised `SendStreamingMessageResponse`."
                            ),
                        }
                    },
                },
            },
            "default": {
                "description": "JSON-RPC error",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/JSONRPCErrorResponse"}
                    }
                },
            },
        },
    }


def _build_base_spec(schemas: dict) -> dict:
    """Build the shared a2a-protocol OpenAPI 3.1 spec."""
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "A2A Protocol",
            "version": "0.1.0",
            "description": (
                "Common OpenAPI 3.1 surface for all A2A-protocol agents in this repo. "
                "Each agent exposes a GET endpoint for its Agent Card and a POST "
                "JSON-RPC endpoint for task execution."
            ),
        },
        "servers": [
            {"url": "http://localhost:8000", "description": "A2A Orchestrator Agent"},
            {"url": "http://localhost:8001", "description": "A2A Recipe URL Parser Agent"},
            {"url": "http://localhost:8002", "description": "A2A Recipe Generator Agent"},
            {"url": "http://localhost:8003", "description": "A2A Shell Agent"},
        ],
        "paths": {
            "/.well-known/agent-card.json": {
                "get": {
                    "summary": "Agent Card",
                    "description": (
                        "Returns the static Agent Card describing this agent's capabilities."
                    ),
                    "responses": {
                        "200": {
                            "description": "Agent Card",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/AgentCard"}
                                }
                            },
                        }
                    },
                }
            },
            "/": {
                "post": _make_jsonrpc_post_operation(schemas),
            },
        },
        "components": {
            "schemas": schemas,
        },
    }


def _agent_spec(
    base: dict,
    *,
    server_url: str,
    server_description: str,
    title: str,
    card_example: dict,
    example_name: str,
) -> dict:
    """Clone base spec and customise for a single agent."""
    spec = copy.deepcopy(base)
    spec["info"]["title"] = title
    spec["servers"] = [{"url": server_url, "description": server_description}]
    spec["components"].setdefault("examples", {})[example_name] = {
        "summary": f"{title} Agent Card",
        "value": card_example,
    }
    return spec


# ---------------------------------------------------------------------------
# OpenAI-compat merge helpers (orchestrator only)
# ---------------------------------------------------------------------------


def _openai_compat_subschema() -> dict:
    """Build a throwaway FastAPI app to extract the OpenAI-compat OpenAPI schema."""
    temp = FastAPI(title="oai", version="0", docs_url=None, redoc_url=None)
    temp.include_router(openai_router)
    return temp.openapi()


def _merge_into_orchestrator(base: dict) -> dict:
    """Merge OpenAI-compat paths + schemas into the orchestrator spec."""
    sub = _openai_compat_subschema()
    base.setdefault("paths", {}).update(sub.get("paths", {}))
    base.setdefault("components", {}).setdefault("schemas", {}).update(
        sub.get("components", {}).get("schemas", {})
    )
    return base


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    schemas = _collect_schemas()
    base = _build_base_spec(schemas)

    # 1. Common protocol spec
    _write(OUT_DIR / "a2a-protocol.openapi.json", base)

    # 2. Agent-specific specs
    agents = [
        {
            "filename": "orchestrator.openapi.json",
            "server_url": "http://localhost:8000",
            "server_description": "A2A Orchestrator Agent",
            "title": "A2A Orchestrator Agent",
            "card": orch_build_card("http://localhost:8000"),
            "example_name": "OrchestratorAgentCard",
        },
        {
            "filename": "recipe-url.openapi.json",
            "server_url": "http://localhost:8001",
            "server_description": "A2A Recipe URL Parser Agent",
            "title": "A2A Recipe URL Parser Agent",
            "card": url_build_card("http://localhost:8001"),
            "example_name": "RecipeUrlAgentCard",
        },
        {
            "filename": "recipe-gen.openapi.json",
            "server_url": "http://localhost:8002",
            "server_description": "A2A Recipe Generator Agent",
            "title": "A2A Recipe Generator Agent",
            "card": gen_build_card("http://localhost:8002"),
            "example_name": "RecipeGenAgentCard",
        },
        {
            "filename": "shell.openapi.json",
            "server_url": "http://localhost:8003",
            "server_description": "A2A Shell Agent",
            "title": "A2A Shell Agent",
            "card": shell_build_card("http://localhost:8003"),
            "example_name": "ShellAgentCard",
        },
    ]

    for a in agents:
        spec = _agent_spec(
            base,
            server_url=a["server_url"],
            server_description=a["server_description"],
            title=a["title"],
            card_example=a["card"],
            example_name=a["example_name"],
        )
        if a["filename"] == "orchestrator.openapi.json":
            spec["info"]["description"] = (
                "A2A Orchestrator Agent. Exposes the A2A JSON-RPC protocol "
                "(POST /, GET /.well-known/agent-card.json) and an OpenAI-compatible "
                "chat API surface (GET /v1/models, POST /v1/chat/completions)."
            )
            spec = _merge_into_orchestrator(spec)
        _write(OUT_DIR / a["filename"], spec)

    print("Generated files:")
    for f in sorted(OUT_DIR.glob("*.json")):
        print(f"  {f}  ({f.stat().st_size:,} bytes)")


def _write(path: pathlib.Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")


if __name__ == "__main__":
    main()
