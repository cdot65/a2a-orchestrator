import pytest


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
    monkeypatch.setenv("RECIPES_DIR", str(tmp_path / "recipes"))
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "workspace"))
    (tmp_path / "recipes").mkdir()
    (tmp_path / "workspace").mkdir()
    yield


def get_state(event):
    """Extract state string from a TaskStatusUpdateEvent (or None)."""
    status = getattr(event, "status", None)
    if status is None:
        return None
    state = getattr(status, "state", None)
    return state.value if hasattr(state, "value") else state


def get_text(event):
    """Extract text from a status event's message or from an artifact."""
    status = getattr(event, "status", None)
    if status and getattr(status, "message", None):
        parts = status.message.parts
        for p in parts:
            t = getattr(getattr(p, "root", p), "text", None)
            if t:
                return t
    artifact = getattr(event, "artifact", None)
    if artifact:
        for p in artifact.parts:
            t = getattr(getattr(p, "root", p), "text", None)
            if t:
                return t
    return None
