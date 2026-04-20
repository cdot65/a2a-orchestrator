import json

from a2a_orchestrator.common.logging import configure_logging, get_logger


def test_configure_logging_pretty_smoke(monkeypatch, capsys):
    monkeypatch.setenv("LOG_FORMAT", "pretty")
    configure_logging(agent_name="test-agent")
    log = get_logger("test-agent")
    log.info("hello", task_id="abc")
    out = capsys.readouterr().out
    assert "hello" in out


def test_configure_logging_json(monkeypatch, capsys):
    monkeypatch.setenv("LOG_FORMAT", "json")
    configure_logging(agent_name="test-agent")
    log = get_logger("test-agent")
    log.info("hello", task_id="abc", count=3)
    line = capsys.readouterr().out.strip().splitlines()[-1]
    data = json.loads(line)
    assert data["event"] == "hello"
    assert data["task_id"] == "abc"
    assert data["count"] == 3
    assert data["agent"] == "test-agent"
