from pathlib import Path

from a2a_orchestrator.recipe_url.extract import extract_main_text

SAMPLE = Path(__file__).parent.parent / "fixtures" / "recipes" / "sample.html"


def test_extract_returns_readable_text():
    html = SAMPLE.read_text()
    text = extract_main_text(html)
    assert "Sample Chili" in text
    assert "Brown beef" in text


def test_extract_falls_back_to_raw_on_empty(monkeypatch):
    from a2a_orchestrator.recipe_url import extract as mod

    monkeypatch.setattr(mod, "_trafilatura_extract", lambda _html: None)
    html = "<html><body><p>Just a paragraph.</p></body></html>"
    text = extract_main_text(html)
    assert "Just a paragraph" in text
