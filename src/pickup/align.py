"""Diff a script-token list against a transcript-word list and categorize the differences.

Uses stdlib `difflib.SequenceMatcher` over the two normalized key sequences with
`autojunk=False` (autojunk silently drops common tokens in long sequences and would
corrupt audiobook-length diffs). Each non-`equal` opcode becomes a `Discrepancy`.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from pickup.models import Category, Discrepancy, ScriptToken, TranscriptWord

CONTEXT_WINDOW = 5  # tokens either side of the diff slice
LONG_OMISSION_THRESHOLD = 5  # ≥ this many script tokens in one delete → omission_long


def diff(
    script_tokens: list[ScriptToken],
    transcript_words: list[TranscriptWord],
) -> list[Discrepancy]:
    """Return discrepancies in audio-time order. Empty inputs → empty list."""
    script_keys = [t.key for t in script_tokens]
    transcript_keys = [w.key for w in transcript_words]
    matcher = SequenceMatcher(a=script_keys, b=transcript_keys, autojunk=False)

    discrepancies: list[Discrepancy] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue

        category = _categorize(tag, i2 - i1, j2 - j1)
        time_seconds = _timestamp(tag, j1, transcript_words)
        expected = " ".join(t.text for t in script_tokens[i1:i2])
        actual = " ".join(w.text for w in transcript_words[j1:j2])
        script_context = _context([t.text for t in script_tokens], i1, i2)
        transcript_context = _context([w.text for w in transcript_words], j1, j2)

        discrepancies.append(
            Discrepancy(
                category=category,
                time_seconds=time_seconds,
                expected=expected,
                actual=actual,
                script_context=script_context,
                transcript_context=transcript_context,
            )
        )

    return discrepancies


def _categorize(tag: str, script_len: int, transcript_len: int) -> Category:
    if tag == "delete":
        return "omission_long" if script_len >= LONG_OMISSION_THRESHOLD else "omission"
    if tag == "insert":
        return "addition"
    # tag == "replace"
    return "substitution" if script_len == transcript_len else "rephrasing"


def _timestamp(tag: str, j1: int, transcript_words: list[TranscriptWord]) -> float:
    """When did this discrepancy happen in the audio?

    For insert/replace: the first transcript word in the slice.
    For delete (omission): the *next* transcript word — i.e. "around here, the reader
    skipped X." If the omission is at end-of-file, fall back to last word's end + 1ms,
    or 0.0 if the transcript is entirely empty.
    """
    if tag != "delete":
        return transcript_words[j1].start_seconds
    if j1 < len(transcript_words):
        return transcript_words[j1].start_seconds
    if transcript_words:
        return transcript_words[-1].end_seconds + 0.001
    return 0.0


def _context(items: list[str], i1: int, i2: int) -> str:
    """Surrounding text: `before … after`, where each side is up to CONTEXT_WINDOW words.

    Empty halves are dropped. Empty result if there is no surrounding text at all
    (e.g. a single-word input where the slice covers everything).
    """
    before = items[max(0, i1 - CONTEXT_WINDOW) : i1]
    after = items[i2 : i2 + CONTEXT_WINDOW]
    parts: list[str] = []
    if before:
        parts.append(" ".join(before))
    if after:
        parts.append(" ".join(after))
    return " … ".join(parts)
