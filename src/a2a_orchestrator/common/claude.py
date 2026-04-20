import os
from collections.abc import AsyncIterator

from anthropic import Anthropic, AsyncAnthropic

_DEFAULT_MAX_TOKENS = 2048


def get_client() -> Anthropic:
    return Anthropic()


def get_async_client() -> AsyncAnthropic:
    return AsyncAnthropic()


def _model() -> str:
    return os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")


def call_with_schema(
    client: Anthropic,
    *,
    system: str,
    user: str,
    tool_name: str,
    tool_description: str,
    schema: dict,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> dict:
    """One-shot Claude call with a forced tool. Returns the tool input dict."""
    msg = client.messages.create(
        model=_model(),
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        tools=[{
            "name": tool_name,
            "description": tool_description,
            "input_schema": schema,
        }],
        tool_choice={"type": "tool", "name": tool_name},
    )
    for block in msg.content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            return dict(block.input)
    raise RuntimeError(f"Claude response had no tool_use for {tool_name!r}")


async def stream_text(
    client: AsyncAnthropic,
    *,
    system: str,
    user: str,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> AsyncIterator[str]:
    """Stream plain text output from Claude."""
    async with client.messages.stream(
        model=_model(),
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        async for chunk in stream.text_stream:
            yield chunk
