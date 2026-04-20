from pathlib import Path

import httpx
import respx

from a2a_orchestrator.common.a2a_helpers import (
    build_agent_card,
    discover_agents,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "agent_cards"


def test_build_agent_card_has_expected_shape():
    card = build_agent_card(
        name="recipe-gen",
        description="Generate a recipe.",
        url="http://localhost:8002",
        skills=[
            {
                "id": "generate_recipe",
                "name": "generate_recipe",
                "description": "Generate a new recipe.",
                "tags": ["recipe"],
                "examples": ["a vegan soup"],
            }
        ],
    )
    assert card["name"] == "recipe-gen"
    assert card["url"] == "http://localhost:8002"
    assert card["capabilities"]["streaming"] is True
    assert card["authentication"]["schemes"] == ["none"]
    assert card["skills"][0]["id"] == "generate_recipe"


@respx.mock
async def test_discover_agents_returns_reachable_cards():
    sample = (FIXTURES / "recipe_url.json").read_text()
    respx.get("http://localhost:8001/.well-known/agent-card.json").mock(
        return_value=httpx.Response(200, text=sample)
    )
    respx.get("http://localhost:8002/.well-known/agent-card.json").mock(
        return_value=httpx.Response(500)
    )

    cards = await discover_agents([8001, 8002])

    assert len(cards) == 1
    assert cards[0]["name"] == "recipe-url"


@respx.mock
async def test_discover_agents_skips_connection_errors():
    respx.get("http://localhost:9999/.well-known/agent-card.json").mock(
        side_effect=httpx.ConnectError("boom")
    )

    cards = await discover_agents([9999])
    assert cards == []


@respx.mock
async def test_discover_agents_skips_non_json_body():
    respx.get("http://localhost:8001/.well-known/agent-card.json").mock(
        return_value=httpx.Response(200, text="not-json")
    )
    cards = await discover_agents([8001])
    assert cards == []
