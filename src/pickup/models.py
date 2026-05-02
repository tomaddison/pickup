"""Pydantic data models exchanged between modules."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Category = Literal["substitution", "omission", "omission_long", "addition", "rephrasing"]


class ScriptToken(BaseModel):
    """A single tokenized word from the source script PDF, in reading order."""

    text: str  # original surface form, used in CSV context
    key: str  # normalized form, used for matching
    page: int  # 1-indexed
    char_offset: int  # byte offset within the page's text


class TranscriptWord(BaseModel):
    """A single word from the Scribe transcript, with its audio time range."""

    text: str  # original spoken word as Scribe heard it
    key: str  # normalized form, used for matching
    start_seconds: float
    end_seconds: float
    confidence: float | None = None  # Scribe's logprob (negative; closer to 0 = more confident)


class Discrepancy(BaseModel):
    """A single difference between script and transcript, ready for CSV output."""

    category: Category
    time_seconds: float  # where in the audio this discrepancy lives
    expected: str  # script side (display form, joined with spaces)
    actual: str  # transcript side
    script_context: str  # surrounding script text (5 tokens either side, gap-marked with " … ")
    transcript_context: str  # surrounding transcript text, same shape
