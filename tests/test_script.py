"""Tests for pickup.script."""

from __future__ import annotations

from pathlib import Path

import pytest

from pickup.errors import ScriptParseError
from pickup.script import extract


def test_extract_happy_path(sample_pdf: Path) -> None:
    tokens = extract(sample_pdf)
    assert len(tokens) > 0
    assert tokens[0].key == "chapter"
    assert tokens[0].page == 1
    assert {t.page for t in tokens} == {1, 2, 3, 4, 5}


def test_repeated_header_stripped(sample_pdf: Path) -> None:
    tokens = extract(sample_pdf)
    keys = {t.key for t in tokens}
    # "Sample Script — Draft 1" appears on every page; should be removed wholesale.
    assert "sample" not in keys
    assert "draft" not in keys


def test_repeated_footer_stripped(sample_pdf: Path) -> None:
    tokens = extract(sample_pdf)
    keys = {t.key for t in tokens}
    assert "confidential" not in keys


def test_page_numbers_leak_through(sample_pdf: Path) -> None:
    # Per-page-varying footers fall below the >50% repetition threshold and pass through.
    tokens = extract(sample_pdf)
    keys = [t.key for t in tokens]
    assert "page" in keys


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ScriptParseError, match="not found"):
        extract(tmp_path / "nope.pdf")


def test_garbage_pdf_raises(tmp_path: Path) -> None:
    bogus = tmp_path / "bogus.pdf"
    bogus.write_bytes(b"not a pdf")
    with pytest.raises(ScriptParseError):
        extract(bogus)
