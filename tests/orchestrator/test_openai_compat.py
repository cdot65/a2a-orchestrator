"""Tests for the OpenAI-compatible chat completions endpoint."""

from __future__ import annotations

import json
from unittest.mock import patch

from a2a.types import TaskState
from fastapi import FastAPI
from fastapi.testclient import TestClient

from a2a_orchestrator.common.a2a_helpers import status_event, text_update
from a2a_orchestrator.orchestrator.openai_compat import router

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


async def _fake_execute_ok(self, context, event_queue):
    await event_queue.enqueue_event(
        text_update(task_id=context.task_id, context_id=context.context_id, text="hello ")
    )
    await event_queue.enqueue_event(
        text_update(task_id=context.task_id, context_id=context.context_id, text="world")
    )
    await event_queue.enqueue_event(
        status_event(
            task_id=context.task_id,
            context_id=context.context_id,
            state=TaskState.completed,
            final=True,
        )
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_models():
    client = TestClient(_make_app())
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    assert len(data["data"]) == 1
    assert data["data"][0]["id"] == "a2a-orchestrator"
    assert data["data"][0]["object"] == "model"
    assert "created" in data["data"][0]
    assert data["data"][0]["owned_by"] == "a2a-orchestrator"


def test_chat_completions_nonstreaming():
    with patch(
        "a2a_orchestrator.orchestrator.openai_compat.OrchestratorExecutor.execute",
        _fake_execute_ok,
    ):
        client = TestClient(_make_app())
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "a2a-orchestrator",
                "messages": [{"role": "user", "content": "say hello"}],
                "stream": False,
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["object"] == "chat.completion"
    assert len(data["choices"]) == 1
    choice = data["choices"][0]
    assert choice["message"]["role"] == "assistant"
    assert "hello " in choice["message"]["content"]
    assert "world" in choice["message"]["content"]
    assert "usage" in data


def test_chat_completions_streaming():
    with patch(
        "a2a_orchestrator.orchestrator.openai_compat.OrchestratorExecutor.execute",
        _fake_execute_ok,
    ):
        client = TestClient(_make_app())
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "a2a-orchestrator",
                "messages": [{"role": "user", "content": "say hello"}],
                "stream": True,
            },
        )
    assert resp.status_code == 200

    raw = resp.text
    frames = [line for line in raw.splitlines() if line.startswith("data: ")]
    assert frames, "Expected SSE data frames"

    # Last frame must be [DONE]
    assert frames[-1] == "data: [DONE]"

    # Parse JSON frames (all except [DONE])
    chunks = []
    for frame in frames[:-1]:
        payload = frame[len("data: "):]
        chunks.append(json.loads(payload))

    assert all(c["object"] == "chat.completion.chunk" for c in chunks)

    # At least one chunk contains "hello" or "world"
    all_content = "".join(
        c["choices"][0]["delta"].get("content", "") or ""
        for c in chunks
    )
    assert "hello" in all_content or "world" in all_content

    # Final non-[DONE] chunk has finish_reason="stop"
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"

    # First content chunk has role="assistant"
    content_chunks = [
        c for c in chunks if c["choices"][0]["delta"].get("content")
    ]
    assert content_chunks[0]["choices"][0]["delta"]["role"] == "assistant"


def test_chat_completions_empty_messages_returns_400():
    client = TestClient(_make_app())
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "a2a-orchestrator",
            "messages": [],
            "stream": False,
        },
    )
    assert resp.status_code == 400


def test_chat_completions_no_user_message_returns_400():
    client = TestClient(_make_app())
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "a2a-orchestrator",
            "messages": [{"role": "system", "content": "you are helpful"}],
            "stream": False,
        },
    )
    assert resp.status_code == 400
