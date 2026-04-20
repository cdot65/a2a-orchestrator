import asyncio
import logging
from typing import Any
from uuid import uuid4

import httpx
from a2a.types import (
    Artifact,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)

log = logging.getLogger(__name__)

AGENT_CARD_PATH = "/.well-known/agent-card.json"


def build_agent_card(
    *,
    name: str,
    description: str,
    url: str,
    skills: list[dict[str, Any]],
    version: str = "0.1.0",
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "url": url,
        "version": version,
        "capabilities": {"streaming": True},
        "authentication": {"schemes": ["none"]},
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": skills,
    }


async def _fetch_card(client: httpx.AsyncClient, base_url: str) -> dict[str, Any] | None:
    url = base_url.rstrip("/") + AGENT_CARD_PATH
    try:
        resp = await client.get(url, timeout=2.0)
    except httpx.HTTPError as e:
        log.warning("discovery failed for %s: %s", base_url, e)
        return None
    if resp.status_code != 200:
        log.warning("discovery non-200 for %s: %s", base_url, resp.status_code)
        return None
    try:
        return resp.json()
    except ValueError:
        log.warning("discovery: %s returned non-JSON", base_url)
        return None


async def discover_agents(base_urls: list[str]) -> list[dict[str, Any]]:
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *(_fetch_card(client, url) for url in base_urls),
            return_exceptions=True,
        )
    return [c for c in results if isinstance(c, dict)]


def _text_message(text: str) -> Message:
    return Message(
        role=Role.agent,
        parts=[Part(root=TextPart(text=text))],
        message_id=uuid4().hex,
    )


def status_event(
    *,
    task_id: str,
    context_id: str,
    state: TaskState,
    message: str = "",
    final: bool = False,
) -> TaskStatusUpdateEvent:
    return TaskStatusUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        status=TaskStatus(
            state=state,
            message=_text_message(message) if message else None,
        ),
        final=final,
    )


def text_update(*, task_id: str, context_id: str, text: str) -> TaskStatusUpdateEvent:
    """Interim streaming text forwarded via status message."""
    return TaskStatusUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        status=TaskStatus(state=TaskState.working, message=_text_message(text)),
        final=False,
    )


def artifact_event(
    *,
    task_id: str,
    context_id: str,
    mime_type: str,
    text: str,
    name: str | None = None,
) -> TaskArtifactUpdateEvent:
    part = Part(root=TextPart(text=text))
    return TaskArtifactUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        artifact=Artifact(
            artifact_id=uuid4().hex,
            name=name,
            parts=[part],
        ),
        last_chunk=True,
    )
