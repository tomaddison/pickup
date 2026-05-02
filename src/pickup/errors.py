"""Typed exceptions raised at module boundaries; caught by cli.py for friendly output."""


class PickupError(Exception):
    """Base for all Pickup-raised errors."""


class ScriptParseError(PickupError):
    """The script PDF could not be opened, read, or yielded zero tokens."""


class TranscriptionError(PickupError):
    """The Scribe call failed, the API key is missing, or the response had no words."""
