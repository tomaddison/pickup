# Pickup

[![CI](https://github.com/tomaddison/pickup/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/tomaddison/pickup/actions/workflows/ci.yml)

Command line tool for comparing a recorded performance against its source script. Outputs a Pro Tools
session (`.ptx`) containing one marker per discrepancy, ready to import session data from.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Copy `.env.example` to `.env` and fill in your ElevenLabs key:

```bash
cp .env.example .env
# then edit .env: ELEVENLABS_API_KEY=sk_...
```

## Use

```bash
pickup script.pdf recording.wav
```

Writes `markers.ptx` in the current directory. Override with `-o path.ptx`.

The Scribe transcript is cached as `recording.wav.scribe.json` next to the
audio file; re-runs are free and instant.

In Pro Tools: **File > Import > Session Data**, select `markers.ptx`, check
**Ruler Markers / Memory Locations**, OK.

## Marker formatting

Each discrepancy becomes one marker. The marker **name** is a short tag and the detail goes in the **comment** section.

| Tag                   | Meaning                                                                   |
| --------------------- | ------------------------------------------------------------------------- |
| `[SUB]`               | One word in the script was replaced by a different word in the recording. |
| `[OMIT]`              | A short run of words from the script was skipped.                         |
| `[OMIT LONG PASSAGE]` | Five or more contiguous script words were skipped.                        |
| `[ADD]`               | The reader said word(s) that weren't in the script.                       |
| `[REPHRASE]`          | A multi-word phrase was reworded (different word count).                  |

Each comment is a small block. The action on top, then the script vs.
performance with surrounding context so you can locate the moment quickly.

**`[SUB]`** : substitution:

```
Substituted: "awesome" → "great"
Expected: "...life, and be my most awesome self. Sounds simple, right? Yet..."
Heard: "...life and be my most great self. Sounds simple, right? Yet..."
```

**`[ADD]`** : added word(s):

```
Added: "the"
Expected: "...it through the day, all while saying to ourselves, 'What..."
Heard: "...it through the day. All the while saying to ourselves, 'What..."
```

**`[OMIT]` / `[OMIT LONG PASSAGE]`** : skipped word(s):

```
Omitted: "very"
Expected: "...he was very tired and..."
Heard: "...he was tired and..."
```

**`[REPHRASE]`** : phrase reworded (no surrounding context, since the change
is the whole point):

```
Expected: "I am"
Heard: "I'm"
```

Marker timestamps land on the first transcript word in the discrepancy (for
substitutions, additions, and rephrases) or on the next spoken word after the
gap (for omissions).

## How it works

- **Script extraction**: `pdfplumber` reads the PDF. Any
  line that appears on more than half the pages is treated as a header or
  footer and removed before the page is tokenised into words.
- **Transcription**: ElevenLabs Scribe returns each word with a start and end
  time. Its full JSON response is saved alongside the audio file, so the
  second run on the same file reads the cache instead of calling the API.
- **Normalisation**: both sides are lowercased, stripped of punctuation, and
  passed through a small contraction map ("can't" → "cannot", etc.) so that
  the script and the spoken word match on meaning rather than surface form.
- **Alignment**: Python's `difflib.SequenceMatcher` diffs the two word
  lists. Every insertion, deletion
  and replacement is classified as a substitution, omission, addition,
  or rephrase, and tagged with the timestamp of the affected word.
- **Pro Tools writer**: a `.ptx` is a Pro Tools session file. It has a
  20-byte plain header followed by an XOR-scrambled body. The format isn't
  publicly documented, so the writer is reverse-engineered from the
  open-source ptformat reader. Pickup ships a session template containing a
  single placeholder marker as package data. At write time it decrypts the
  template, swaps the placeholder for one record per discrepancy, updates
  the byte-offset pointers elsewhere in the file to account for the new
  block being a different size, re-encrypts, and writes the result.

## Development

```bash
pip install -e ".[dev]"
pytest         # 59 tests, run from cached fixtures
ruff check .   # lint
mypy           # strict type-check
```
