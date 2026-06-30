#!/usr/bin/env python3
"""Southern NH GC lead scan — find deck, garage, and addition jobs.

Run manually::

    uv run python examples/southern_nh_gc/lead_scan.py

    uv run python examples/southern_nh_gc/lead_scan.py \\
        --towns "Nashua,Merrimack,Bedford" --output ~/leads-today.md

Schedule (weekdays + Saturday 6 AM local — adjust cron for your timezone)::

    jarvis scheduler create "Southern NH GC lead scan" \\
        --type cron --value "0 11 * * 1-6"
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import click

DEFAULT_TOWNS = (
    "Nashua, Manchester, Merrimack, Bedford, Londonderry, Derry, Salem, "
    "Hudson, Pelham, Windham, Amherst, Milford, Hollis"
)

DEFAULT_JOB_TYPES = "decks, garages, home additions"


@click.command()
@click.option(
    "--towns",
    default=DEFAULT_TOWNS,
    show_default=True,
    help="Comma-separated southern NH towns to prioritize.",
)
@click.option(
    "--job-types",
    default=DEFAULT_JOB_TYPES,
    show_default=True,
    help="Job types to search for.",
)
@click.option(
    "--model",
    default=None,
    help="Model to use (e.g. qwen3:8b).",
)
@click.option(
    "--engine",
    "engine_key",
    default=None,
    help="Engine backend (e.g. ollama).",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=None,
    help="Optional file to save the lead report.",
)
def main(
    towns: str,
    job_types: str,
    model: str | None,
    engine_key: str | None,
    output: Path | None,
) -> None:
    """Scan the web for GC leads in southern New Hampshire."""
    town_list = [t.strip() for t in towns.split(",") if t.strip()]
    if not town_list:
        click.echo("Error: --towns must contain at least one town.", err=True)
        raise SystemExit(1)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    town_str = ", ".join(town_list)

    prompt = (
        f"Today is {today}. Run a full southern NH GC lead scan.\n\n"
        f"**Towns to prioritize**: {town_str}\n"
        f"**Job types**: {job_types}\n\n"
        "Follow your system workflow: recall prior leads from memory, search "
        "homeowner and bid sources, score new opportunities, store each lead, "
        "and produce the standard lead report with hot leads (7+), warm leads, "
        "municipal bids, and follow-ups due."
    )

    try:
        from openjarvis import Jarvis

        kwargs: dict[str, str | None] = {}
        if model:
            kwargs["model"] = model
        if engine_key:
            kwargs["engine_key"] = engine_key

        j = Jarvis(**kwargs)  # type: ignore[arg-type]
    except Exception as exc:
        click.echo(
            f"Error: Could not initialize Jarvis: {exc}\n\n"
            "Make sure an inference engine is running (e.g. `ollama serve`) "
            "and openjarvis is installed (`uv sync`).",
            err=True,
        )
        raise SystemExit(1) from exc

    try:
        response = j.ask(
            prompt,
            agent="operative",
            tools=["web_search", "http_request", "memory_store", "memory_search", "think"],
        )
    except Exception as exc:
        click.echo(f"Error during lead scan: {exc}", err=True)
        raise SystemExit(1) from exc
    finally:
        j.close()

    header = (
        f"\n{'=' * 60}\n"
        f"  Southern NH GC Lead Scan — {today}\n"
        f"  Towns: {town_str}\n"
        f"  Focus: {job_types}\n"
        f"{'=' * 60}\n"
    )
    click.echo(header)
    click.echo(response)
    click.echo(f"\n{'=' * 60}")

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(f"{header}\n{response}\n", encoding="utf-8")
        click.echo(f"\nSaved to {output}")


if __name__ == "__main__":
    main()
