"""Tests for pickup.align — hand-built fixtures, no PDFs or audio."""

from __future__ import annotations

import pytest

from pickup.align import diff
from pickup.models import ScriptToken, TranscriptWord


def _script(*words: str) -> list[ScriptToken]:
    """Build a script-token list. Keys are lowercased; positions are dummy."""
    return [ScriptToken(text=w, key=w.lower(), page=1, char_offset=i) for i, w in enumerate(words)]


def _transcript(*pairs: tuple[str, float]) -> list[TranscriptWord]:
    """Build a transcript word list from (text, start_seconds) pairs.

    end_seconds is start + 0.1 for each word; confidence is None.
    """
    return [TranscriptWord(text=t, key=t.lower(), start_seconds=s, end_seconds=s + 0.1) for t, s in pairs]


# --- happy paths -----------------------------------------------------------------


def test_all_equal_returns_empty() -> None:
    script = _script("the", "quick", "brown", "fox")
    transcript = _transcript(("the", 0.0), ("quick", 0.5), ("brown", 1.0), ("fox", 1.5))
    assert diff(script, transcript) == []


def test_substitution_same_length() -> None:
    script = _script("the", "quick", "brown", "fox")
    transcript = _transcript(("the", 0.0), ("quick", 0.5), ("red", 1.0), ("fox", 1.5))
    result = diff(script, transcript)
    assert len(result) == 1
    d = result[0]
    assert d.category == "substitution"
    assert d.expected == "brown"
    assert d.actual == "red"
    assert d.time_seconds == 1.0
    assert d.script_context == "the quick … fox"
    assert d.transcript_context == "the quick … fox"


def test_addition_inserts_words() -> None:
    script = _script("the", "fox")
    transcript = _transcript(("the", 0.0), ("quick", 0.5), ("brown", 1.0), ("fox", 1.5))
    result = diff(script, transcript)
    assert len(result) == 1
    d = result[0]
    assert d.category == "addition"
    assert d.expected == ""
    assert d.actual == "quick brown"
    assert d.time_seconds == 0.5


def test_short_omission() -> None:
    script = _script("the", "quick", "brown", "fox", "jumps")
    transcript = _transcript(("the", 0.0), ("fox", 0.5), ("jumps", 1.0))
    result = diff(script, transcript)
    assert len(result) == 1
    d = result[0]
    assert d.category == "omission"  # 2 words < threshold
    assert d.expected == "quick brown"
    assert d.actual == ""
    assert d.time_seconds == 0.5  # next transcript word's start


def test_long_omission_uses_omission_long_category() -> None:
    # Five-word omission should bump to omission_long.
    script = _script("the", "a", "b", "c", "d", "e", "fox")
    transcript = _transcript(("the", 0.0), ("fox", 1.0))
    result = diff(script, transcript)
    assert len(result) == 1
    d = result[0]
    assert d.category == "omission_long"
    assert d.expected == "a b c d e"
    assert d.time_seconds == 1.0


def test_rephrasing_unequal_lengths() -> None:
    script = _script("the", "ran", "fast", "through")
    transcript = _transcript(("the", 0.0), ("took", 0.5), ("off", 1.0), ("through", 1.5))
    result = diff(script, transcript)
    assert len(result) == 1
    d = result[0]
    # script slice = "ran fast" (2), transcript slice = "took off" (2) → equal
    assert d.category == "substitution"


def test_rephrasing_truly_unequal() -> None:
    script = _script("the", "ran", "through")
    transcript = _transcript(("the", 0.0), ("took", 0.5), ("off", 1.0), ("through", 1.5))
    result = diff(script, transcript)
    assert len(result) == 1
    assert result[0].category == "rephrasing"
    assert result[0].expected == "ran"
    assert result[0].actual == "took off"


# --- edges -----------------------------------------------------------------------


def test_substitution_at_start_of_file() -> None:
    script = _script("hello", "world")
    transcript = _transcript(("hi", 0.0), ("world", 0.5))
    result = diff(script, transcript)
    assert len(result) == 1
    d = result[0]
    assert d.category == "substitution"
    assert d.script_context == "world"  # no "before", only "after"
    assert d.transcript_context == "world"


def test_substitution_at_end_of_file() -> None:
    script = _script("hello", "world")
    transcript = _transcript(("hello", 0.0), ("earth", 0.5))
    result = diff(script, transcript)
    assert len(result) == 1
    d = result[0]
    assert d.script_context == "hello"  # no "after", only "before"
    assert d.transcript_context == "hello"


def test_omission_at_end_of_transcript_uses_fallback_timestamp() -> None:
    # Script trails off after transcript ends.
    script = _script("hello", "world", "extra", "tail")
    transcript = _transcript(("hello", 0.0), ("world", 0.5))
    result = diff(script, transcript)
    assert len(result) == 1
    d = result[0]
    assert d.category == "omission"
    assert d.expected == "extra tail"
    # j1 == len(transcript), so fallback: last word end_seconds + 0.001 = 0.6 + 0.001
    assert d.time_seconds == pytest.approx(0.601)


def test_empty_inputs_return_empty() -> None:
    assert diff([], []) == []


def test_empty_transcript_full_script_omission() -> None:
    script = _script("hello", "world")
    result = diff(script, [])
    assert len(result) == 1
    assert result[0].category == "omission"  # 2 words < threshold
    assert result[0].time_seconds == 0.0  # transcript is empty → fallback to 0


def test_empty_script_full_transcript_addition() -> None:
    transcript = _transcript(("hello", 0.0), ("world", 0.5))
    result = diff([], transcript)
    assert len(result) == 1
    assert result[0].category == "addition"
    assert result[0].actual == "hello world"
    assert result[0].time_seconds == 0.0


# --- ordering --------------------------------------------------------------------


def test_multiple_discrepancies_in_audio_time_order() -> None:
    script = _script("the", "quick", "brown", "fox", "jumps", "over", "lazy", "dog")
    transcript = _transcript(
        ("the", 0.0),
        ("slow", 0.5),  # sub for "quick"
        ("brown", 1.0),
        ("fox", 1.5),
        ("leaps", 2.0),  # sub for "jumps"
        ("over", 2.5),
        ("lazy", 3.0),
        ("dog", 3.5),
    )
    result = diff(script, transcript)
    times = [d.time_seconds for d in result]
    assert times == sorted(times), f"timestamps not monotonic: {times}"
    assert len(result) == 2
    assert result[0].expected == "quick"
    assert result[1].expected == "jumps"
