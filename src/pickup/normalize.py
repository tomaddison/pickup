"""Text normalization shared by script extraction and transcript alignment.

`key()` produces the form used for matching — case- and punctuation-insensitive,
with common contractions expanded so the script's "can't" matches the
transcript's "cannot" (or vice versa).
"""

from __future__ import annotations

import string

CONTRACTIONS: dict[str, str] = {
    "can't": "cannot",
    "won't": "will not",
    "it's": "it is",
    "don't": "do not",
    "i'm": "i am",
    "you're": "you are",
    "we're": "we are",
    "they're": "they are",
    "there's": "there is",
}

# Word-style PDFs are full of smart quotes, en/em dashes, and ellipses that
# string.punctuation doesn't cover. Strip them too.
_PUNCT = string.punctuation + "“”‘’–—…"


def key(word: str) -> str:
    """Return the matching key for a single token. Empty if nothing meaningful remains."""
    w = word.lower().strip(_PUNCT).strip()
    # Smart apostrophes survive .lower(); normalize before contraction lookup.
    w = w.replace("’", "'")
    if w in CONTRACTIONS:
        w = CONTRACTIONS[w]
    return w.replace("-", " ").strip()
