"""OpenAI-compatible chat completions endpoint for the orchestrator."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Literal
from uuid import uuid4

from a2a.types import TaskArtifactUpdateEvent, TaskStatusUpdateEvent
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from a2a_orchestrator.orchestrator.executor import OrchestratorExecutor

router = APIRouter()

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: Literal["stop", "length", "content_filter", None] = "stop"


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage


class ChatCompletionDelta(BaseModel):
    role: Literal["assistant"] | None = None
    content: str | None = None


class ChatCompletionChunkChoice(BaseModel):
    index: int
    delta: ChatCompletionDelta
    finish_reason: Literal["stop", "length", None] = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: list[ChatCompletionChunkChoice]


# ---------------------------------------------------------------------------
# Minimal RequestContext shim
# ---------------------------------------------------------------------------


class _MinimalContext:
    def __init__(self, task_id: str, context_id: str, user_input: str) -> None:
        self.task_id = task_id
        self.context_id = context_id
        self._user_input = user_input

    def get_user_input(self) -> str:
        return self._user_input


# ---------------------------------------------------------------------------
# Queue shim (mirrors InMemoryTaskStore event queue interface)
# ---------------------------------------------------------------------------


class _AsyncQueue:
    def __init__(self) -> None:
        self._q: asyncio.Queue[Any] = asyncio.Queue()

    async def enqueue_event(self, event: Any) -> None:
        await self._q.put(event)

    async def get(self) -> Any:
        return await self._q.get()


# ---------------------------------------------------------------------------
# Text extraction helper
# ---------------------------------------------------------------------------


def _extract_text_from_status_event(event: TaskStatusUpdateEvent) -> str | None:
    """Return text from event.status.message.parts[0].root.text, or None."""
    status = getattr(event, "status", None)
    if status is None:
        return None
    message = getattr(status, "message", None)
    if message is None:
        return None
    parts = getattr(message, "parts", [])
    for p in parts:
        root = getattr(p, "root", p)
        text = getattr(root, "text", None)
        if text:
            return text
    return None


def _extract_text_from_artifact_event(event: TaskArtifactUpdateEvent) -> str | None:
    artifact = getattr(event, "artifact", None)
    if artifact is None:
        return None
    parts = getattr(artifact, "parts", [])
    for p in parts:
        root = getattr(p, "root", p)
        text = getattr(root, "text", None)
        if text:
            return text
    return None


# ---------------------------------------------------------------------------
# Core: run executor and collect text chunks
# ---------------------------------------------------------------------------


async def _collect_chunks(user_input: str) -> list[str]:
    """Run executor, drain queue, return list of text chunks."""
    task_id = uuid4().hex
    context_id = uuid4().hex
    ctx = _MinimalContext(task_id, context_id, user_input)
    queue = _AsyncQueue()

    executor_task = asyncio.create_task(OrchestratorExecutor().execute(ctx, queue))

    chunks: list[str] = []
    while True:
        event = await queue.get()
        final = getattr(event, "final", False)

        if isinstance(event, TaskStatusUpdateEvent):
            text = _extract_text_from_status_event(event)
            state = getattr(getattr(event, "status", None), "state", None)
            state_str = state.value if hasattr(state, "value") else str(state)
            # Only forward working-state text updates (not bare status messages)
            if state_str == "working" and text:
                chunks.append(text)
        elif isinstance(event, TaskArtifactUpdateEvent):
            text = _extract_text_from_artifact_event(event)
            if text:
                chunks.append(text)

        if final:
            break

    await executor_task
    return chunks


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/v1/models")
async def list_models() -> dict:
    return {
        "object": "list",
        "data": [
            {
                "id": "a2a-orchestrator",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "a2a-orchestrator",
            }
        ],
    }


@router.post(
    "/v1/chat/completions",
    response_model=ChatCompletionResponse,
    responses={
        200: {
            "description": (
                "When stream=false, returns a single ChatCompletionResponse "
                "(application/json). When stream=true, returns text/event-stream "
                "with one ChatCompletionChunk per data: frame, terminated by "
                "'data: [DONE]'."
            ),
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ChatCompletionResponse"},
                },
                "text/event-stream": {
                    "schema": {"$ref": "#/components/schemas/ChatCompletionChunk"},
                },
            },
        },
    },
)
async def chat_completions(request: ChatCompletionRequest):
    # Extract last user message
    user_content: str | None = None
    for msg in reversed(request.messages):
        if msg.role == "user":
            user_content = msg.content
            break

    if not user_content:
        raise HTTPException(status_code=400, detail="No user message found in messages.")

    completion_id = f"chatcmpl-{uuid4().hex}"
    created = int(time.time())
    model = request.model

    if request.stream:

        async def sse_gen():
            first = True
            task_id = uuid4().hex
            context_id = uuid4().hex
            ctx = _MinimalContext(task_id, context_id, user_content)
            queue = _AsyncQueue()

            executor_task = asyncio.create_task(OrchestratorExecutor().execute(ctx, queue))

            while True:
                event = await queue.get()
                final = getattr(event, "final", False)

                chunks_to_emit: list[str] = []

                if isinstance(event, TaskStatusUpdateEvent):
                    text = _extract_text_from_status_event(event)
                    state = getattr(getattr(event, "status", None), "state", None)
                    state_str = state.value if hasattr(state, "value") else str(state)
                    if state_str == "working" and text:
                        chunks_to_emit.append(text)
                elif isinstance(event, TaskArtifactUpdateEvent):
                    text = _extract_text_from_artifact_event(event)
                    if text:
                        chunks_to_emit.append(text)

                for text in chunks_to_emit:
                    delta = ChatCompletionDelta(
                        role="assistant" if first else None,
                        content=text,
                    )
                    first = False
                    chunk = ChatCompletionChunk(
                        id=completion_id,
                        created=created,
                        model=model,
                        choices=[
                            ChatCompletionChunkChoice(
                                index=0,
                                delta=delta,
                                finish_reason=None,
                            )
                        ],
                    )
                    yield f"data: {chunk.model_dump_json()}\n\n"

                if final:
                    break

            await executor_task

            # Final chunk with finish_reason=stop
            stop_chunk = ChatCompletionChunk(
                id=completion_id,
                created=created,
                model=model,
                choices=[
                    ChatCompletionChunkChoice(
                        index=0,
                        delta=ChatCompletionDelta(),
                        finish_reason="stop",
                    )
                ],
            )
            yield f"data: {stop_chunk.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(sse_gen(), media_type="text/event-stream")

    # Non-streaming
    chunks = await _collect_chunks(user_content)
    content = "".join(chunks)

    return ChatCompletionResponse(
        id=completion_id,
        created=created,
        model=model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatMessage(role="assistant", content=content),
                finish_reason="stop",
            )
        ],
        usage=ChatCompletionUsage(
            prompt_tokens=0,
            completion_tokens=len(content.split()),
            total_tokens=len(content.split()),
        ),
    )
