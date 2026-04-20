from unittest.mock import MagicMock

import pytest

from a2a_orchestrator.common.claude import call_with_schema, stream_text


def _fake_tool_response(tool_name: str, tool_input: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.input = tool_input
    msg = MagicMock()
    msg.content = [block]
    return msg


def test_call_with_schema_returns_tool_input(monkeypatch):
    client = MagicMock()
    client.messages.create.return_value = _fake_tool_response("emit_result", {"title": "t", "n": 1})

    result = call_with_schema(
        client,
        system="you structure data",
        user="make a result",
        tool_name="emit_result",
        tool_description="emit the structured result",
        schema={"type": "object", "properties": {"title": {"type": "string"}}},
    )

    assert result == {"title": "t", "n": 1}

    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-haiku-4-5-20251001"
    assert kwargs["tool_choice"] == {"type": "tool", "name": "emit_result"}
    assert kwargs["tools"][0]["name"] == "emit_result"


def test_call_with_schema_raises_on_missing_tool_use():
    client = MagicMock()
    empty = MagicMock()
    empty.content = []
    client.messages.create.return_value = empty

    with pytest.raises(RuntimeError, match="no tool_use"):
        call_with_schema(
            client,
            system="s",
            user="u",
            tool_name="t",
            tool_description="d",
            schema={"type": "object"},
        )


async def test_stream_text_yields_chunks(monkeypatch):
    class _FakeStream:
        def __init__(self):
            self.text_stream = self._iter()

        async def _iter(self):
            for c in ["Hello ", "world"]:
                yield c

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    client = MagicMock()
    client.messages.stream.return_value = _FakeStream()

    chunks = []
    async for c in stream_text(client, system="s", user="u"):
        chunks.append(c)
    assert chunks == ["Hello ", "world"]
