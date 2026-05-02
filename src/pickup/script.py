"""Extract and tokenize text from a script PDF.

Returns a flat list of `ScriptToken` in reading order. Repeated headers/footers
are detected on multi-page PDFs and stripped before tokenization. Tokens whose
normalized key is empty (pure punctuation) are dropped.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pdfplumber

from pickup import normalize
from pickup.errors import ScriptParseError
from pickup.models import ScriptToken

_HEADER_FOOTER_MIN_PAGES = 3
_HEADER_FOOTER_THRESHOLD = 0.5


def extract(pdf_path: Path) -> list[ScriptToken]:
    """Open *pdf_path* and return its tokens in reading order."""
    if not pdf_path.exists():
        raise ScriptParseError(f"PDF not found: {pdf_path}")

    try:
        with pdfplumber.open(pdf_path) as pdf:
            page_texts = [(p.extract_text() or "") for p in pdf.pages]
    except Exception as exc:
        raise ScriptParseError(f"Could not read PDF: {pdf_path} ({exc})") from exc

    cleaned = _strip_repeated_lines(page_texts)
    tokens: list[ScriptToken] = []
    for page_num, text in enumerate(cleaned, start=1):
        offset = 0
        for raw in text.split():
            k = normalize.key(raw)
            if k:
                tokens.append(ScriptToken(text=raw, key=k, page=page_num, char_offset=offset))
            offset += len(raw) + 1

    if not tokens:
        raise ScriptParseError(f"No text extracted from PDF: {pdf_path}")

    return tokens


def _strip_repeated_lines(page_texts: list[str]) -> list[str]:
    """Remove first/last lines that repeat across most pages."""
    if len(page_texts) < _HEADER_FOOTER_MIN_PAGES:
        return page_texts

    lines_per_page = [[ln for ln in t.splitlines() if ln.strip()] for t in page_texts]
    candidates: Counter[str] = Counter()
    for lines in lines_per_page:
        if lines:
            candidates[lines[0]] += 1
            if len(lines) > 1:
                candidates[lines[-1]] += 1
    threshold = _HEADER_FOOTER_THRESHOLD * len(page_texts)
    repeated = {line for line, n in candidates.items() if n > threshold}

    return ["\n".join(ln for ln in lines if ln not in repeated) for lines in lines_per_page]
