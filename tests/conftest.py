"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """A 5-page PDF with a known body, a repeated header, and a repeated footer.

    The page-number footer varies per page, so it should NOT be stripped by the
    header/footer heuristic — its tokens leak through (documented in tests).
    """
    path = tmp_path / "sample.pdf"
    c = canvas.Canvas(str(path), pagesize=letter)
    pages = [
        "Chapter one. The quick brown fox jumps over the lazy dog.",
        "She sells seashells by the seashore on a sunny afternoon.",
        "Peter Piper picked a peck of pickled peppers in the garden.",
        "How much wood would a woodchuck chuck if a woodchuck could chuck wood.",
        "All work and no play makes Jack a dull boy and not much else.",
    ]
    for i, body in enumerate(pages, start=1):
        c.setFont("Helvetica", 10)
        c.drawString(72, 750, "Sample Script — Draft 1")
        c.setFont("Helvetica", 12)
        c.drawString(72, 700, body)
        c.setFont("Helvetica", 9)
        c.drawString(72, 50, f"Page {i}")
        c.drawString(72, 30, "Confidential")
        c.showPage()
    c.save()
    return path
