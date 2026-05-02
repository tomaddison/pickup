"""Tests for pickup.normalize."""

from __future__ import annotations

import pytest

from pickup.normalize import CONTRACTIONS, key


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Hello", "hello"),
        ("HELLO", "hello"),
        ("hello,", "hello"),
        ("(world)", "world"),
        ("...", ""),
        ("--", ""),
        ("", ""),
        ("“hello”", "hello"),
        ("…end", "end"),
        ("long-term", "long term"),
        # Smart apostrophe should still hit the contraction map.
        ("don’t", "do not"),
        ("Don’t", "do not"),
    ],
)
def test_key_basic(raw: str, expected: str) -> None:
    assert key(raw) == expected


@pytest.mark.parametrize("contraction,expansion", list(CONTRACTIONS.items()))
def test_key_contractions(contraction: str, expansion: str) -> None:
    assert key(contraction) == expansion
    assert key(contraction.upper()) == expansion
