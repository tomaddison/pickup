"""Transcribe an audio file with ElevenLabs Scribe, with on-disk caching.

The raw Scribe response is cached as JSON next to the audio file. Re-runs
parse the cache instead of hitting the API, which matters because Scribe
calls cost money and audiobook chapters take minutes to transcribe.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from elevenlabs import ElevenLabs
from elevenlabs.core import ApiError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from pickup import normalize
from pickup.errors import TranscriptionError
from pickup.models import TranscriptWord

_MODEL_ID = "scribe_v2"
_LANGUAGE = "en"


def run(audio_path: Path, use_cache: bool = True) -> list[TranscriptWord]:
    """Transcribe *audio_path* and return its words. Uses cached JSON when present."""
    cache = _cache_path(audio_path)

    if use_cache and cache.exists():
        payload = json.loads(cache.read_text())
        return _parse_response(payload, source=str(cache))

    payload = _call_scribe(audio_path)
    cache.write_text(json.dumps(payload, indent=2))
    return _parse_response(payload, source=str(audio_path))


def _cache_path(audio_path: Path) -> Path:
    """`foo.m4a` → `foo.m4a.scribe.json` next to the audio."""
    return audio_path.with_suffix(audio_path.suffix + ".scribe.json")


def _is_transient(exc: BaseException) -> bool:
    """Retry only 429/5xx. 4xx are permanent (auth, validation, abuse) — retrying
    them wastes credits and can trip abuse detectors."""
    if isinstance(exc, ApiError):
        code = exc.status_code or 0
        return code == 429 or 500 <= code < 600
    return False


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, max=16),
    retry=retry_if_exception(_is_transient),
    reraise=True,
)
def _scribe_request(client: ElevenLabs, audio_path: Path) -> dict[str, Any]:
    """The HTTP call alone. ApiError escapes so tenacity can inspect the status."""
    with audio_path.open("rb") as f:
        response = client.speech_to_text.convert(
            model_id=_MODEL_ID,
            file=f,
            language_code=_LANGUAGE,
            timestamps_granularity="word",
        )
    payload: dict[str, Any] = response.model_dump(mode="json")
    return payload


def _call_scribe(audio_path: Path) -> dict[str, Any]:
    """Auth + error wrapping around `_scribe_request`."""
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise TranscriptionError("ELEVENLABS_API_KEY is not set (export it or add it to .env).")

    client = ElevenLabs(api_key=api_key)
    try:
        return _scribe_request(client, audio_path)
    except ApiError as exc:
        raise TranscriptionError(
            f"Scribe API error ({exc.status_code}): {_extract_message(exc.body)}"
        ) from exc


def _extract_message(body: Any) -> str:
    """Pull a human message out of an ElevenLabs error body, falling back to repr."""
    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, dict) and "message" in detail:
            return str(detail["message"])
        if isinstance(detail, str):
            return detail
    return str(body)


def _parse_response(payload: dict[str, Any], *, source: str) -> list[TranscriptWord]:
    """Convert a Scribe response dict into TranscriptWord list. Drops spacing/audio_event entries."""
    raw_words = payload.get("words") or []
    words: list[TranscriptWord] = []
    for w in raw_words:
        if w.get("type") != "word":
            continue
        start, end = w.get("start"), w.get("end")
        if start is None or end is None:
            continue
        text = w.get("text", "")
        words.append(
            TranscriptWord(
                text=text,
                key=normalize.key(text),
                start_seconds=float(start),
                end_seconds=float(end),
                confidence=w.get("logprob"),
            )
        )

    if not words:
        raise TranscriptionError(f"No words in transcript ({source}).")

    return words
