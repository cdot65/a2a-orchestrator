import re

import trafilatura


def _trafilatura_extract(html: str) -> str | None:
    return trafilatura.extract(html, include_comments=False, include_tables=False)


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_tags(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    return _WS_RE.sub(" ", text).strip()


def extract_main_text(html: str) -> str:
    text = _trafilatura_extract(html)
    if text and text.strip():
        return text.strip()
    return _strip_tags(html)
