import asyncio
import logging
from typing import Any

import httpx

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


async def _fetch_card(client: httpx.AsyncClient, port: int) -> dict[str, Any] | None:
    url = f"http://localhost:{port}{AGENT_CARD_PATH}"
    try:
        resp = await client.get(url, timeout=2.0)
    except httpx.HTTPError as e:
        log.warning("discovery failed for port %d: %s", port, e)
        return None
    if resp.status_code != 200:
        log.warning("discovery non-200 for port %d: %s", port, resp.status_code)
        return None
    try:
        return resp.json()
    except ValueError:
        log.warning("discovery: port %d returned non-JSON", port)
        return None


async def discover_agents(ports: list[int]) -> list[dict[str, Any]]:
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *(_fetch_card(client, p) for p in ports),
            return_exceptions=True,
        )
    return [c for c in results if isinstance(c, dict)]
