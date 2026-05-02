"""Tests for pickup.transcribe — never hit the real API."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from elevenlabs.core import ApiError

from pickup.errors import TranscriptionError
from pickup.transcribe import _cache_path, _is_transient, _parse_response, run


@pytest.fixture
def canned_response() -> dict:
    return json.loads((Path(__file__).parent / "fixtures" / "sample.scribe.json").read_text())


def test_cache_path_for_m4a(tmp_path: Path) -> None:
    audio = tmp_path / "chapter1.m4a"
    assert _cache_path(audio) == tmp_path / "chapter1.m4a.scribe.json"


def test_cache_path_for_wav(tmp_path: Path) -> None:
    audio = tmp_path / "chapter1.wav"
    assert _cache_path(audio) == tmp_path / "chapter1.wav.scribe.json"


def test_run_loads_from_cache(tmp_path: Path, canned_response: dict) -> None:
    audio = tmp_path / "chapter1.m4a"
    audio.write_bytes(b"")  # presence not required for cache hit
    _cache_path(audio).write_text(json.dumps(canned_response))

    words = run(audio, use_cache=True)

    assert len(words) == 9  # 17 entries minus 8 spacings
    assert words[0].text == "Introduction."
    assert words[0].key == "introduction"
    assert words[0].start_seconds == 4.94
    assert words[0].end_seconds == 5.679
    assert words[0].confidence == -0.1186


def test_parse_drops_spacing_and_audio_events() -> None:
    payload = {
        "words": [
            {"text": "hello", "start": 0.0, "end": 0.2, "type": "word", "logprob": -0.01},
            {"text": " ", "start": 0.2, "end": 0.21, "type": "spacing", "logprob": 0.0},
            {"text": "(laughter)", "start": 0.3, "end": 0.5, "type": "audio_event", "logprob": -0.5},
            {"text": "world", "start": 0.6, "end": 0.9, "type": "word", "logprob": -0.02},
        ]
    }
    words = _parse_response(payload, source="test")
    assert [w.text for w in words] == ["hello", "world"]


def test_parse_empty_words_raises() -> None:
    with pytest.raises(TranscriptionError, match="No words"):
        _parse_response({"words": []}, source="test")


def test_parse_words_with_no_timestamps_dropped() -> None:
    payload = {
        "words": [
            {"text": "hello", "start": 0.0, "end": 0.2, "type": "word", "logprob": -0.01},
            {"text": "ghost", "start": None, "end": None, "type": "word", "logprob": -0.5},
        ]
    }
    words = _parse_response(payload, source="test")
    assert [w.text for w in words] == ["hello"]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_is_transient_rejects_4xx(status: int) -> None:
    """4xx are permanent. Retrying them burned credits and tripped abuse detection once."""
    assert _is_transient(ApiError(status_code=status, body={})) is False


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_is_transient_accepts_429_and_5xx(status: int) -> None:
    assert _is_transient(ApiError(status_code=status, body={})) is True


def test_is_transient_rejects_unknown_exceptions() -> None:
    assert _is_transient(ValueError("nope")) is False
    assert _is_transient(TranscriptionError("nope")) is False


def test_run_missing_api_key_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    audio = tmp_path / "no_cache.m4a"
    audio.write_bytes(b"")
    # No cache exists → forced to attempt the API call → key check fires.
    with pytest.raises(TranscriptionError, match="ELEVENLABS_API_KEY"):
        run(audio, use_cache=True)
