"""Pickup CLI: PDF + audio in, Pro Tools markers out."""

from __future__ import annotations

from pathlib import Path

import typer
from dotenv import load_dotenv

from pickup import align, ptx, script, transcribe
from pickup.errors import PickupError
from pickup.models import Discrepancy

_TAGS = {
    "substitution": "[SUB]",
    "omission": "[OMIT]",
    "omission_long": "[OMIT LONG PASSAGE]",
    "addition": "[ADD]",
    "rephrasing": "[REPHRASE]",
}

app = typer.Typer(add_completion=False)


@app.command()
def main(
    script_pdf: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    audio_file: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    output: Path = typer.Option(Path("markers.ptx"), "--output", "-o"),
) -> None:
    """Compare SCRIPT_PDF against AUDIO_FILE and write a Pro Tools .ptx."""
    load_dotenv()

    try:
        typer.echo(f"Extracting script from {script_pdf}...")
        tokens = script.extract(script_pdf)

        typer.echo(f"Transcribing {audio_file} (cached after first run)...")
        words = transcribe.run(audio_file)

        typer.echo("Aligning...")
        discrepancies = align.diff(tokens, words)

        markers = [_to_marker(d) for d in discrepancies]
        n = ptx.write_ptx(markers, output)
    except PickupError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from None

    typer.echo(f"Wrote {n} markers to {output}")


def _to_marker(d: Discrepancy) -> tuple[str, float, str]:
    expected = d.expected.replace('"', "'")
    actual = d.actual.replace('"', "'")
    s_ctx = d.script_context.replace('"', "'")
    t_ctx = d.transcript_context.replace('"', "'")

    if d.category == "rephrasing":
        body = f'Expected: "{expected}"\nHeard: "{actual}"'
    elif d.category == "addition":
        body = (
            f'Added: "{actual}"\n'
            f'Expected: "...{_splice(s_ctx, "")}..."\n'
            f'Heard: "...{_splice(t_ctx, actual)}..."'
        )
    elif d.category in ("omission", "omission_long"):
        body = (
            f'Omitted: "{expected}"\n'
            f'Expected: "...{_splice(s_ctx, expected)}..."\n'
            f'Heard: "...{_splice(t_ctx, "")}..."'
        )
    else:  # substitution
        body = (
            f'Substituted: "{expected}" → "{actual}"\n'
            f'Expected: "...{_splice(s_ctx, expected)}..."\n'
            f'Heard: "...{_splice(t_ctx, actual)}..."'
        )

    return (_TAGS[d.category], d.time_seconds, body)


def _splice(context: str, content: str) -> str:
    """Replace the ` … ` placeholder in *context* with *content* (or with a single space)."""
    if " … " in context:
        replacement = f" {content} " if content else " "
        return context.replace(" … ", replacement, 1).strip()
    return f"{content} {context}".strip() if content else context
