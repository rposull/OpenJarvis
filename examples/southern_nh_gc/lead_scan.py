#!/usr/bin/env python3
"""Southern NH GC lead scan — find deck, garage, and addition jobs.

Run manually::

    uv run python examples/southern_nh_gc/seed_cost_catalog.py
    uv run python examples/southern_nh_gc/lead_scan.py

    uv run python examples/southern_nh_gc/lead_scan.py \\
        --towns "Nashua,Merrimack,Bedford" --min-job-size 8000 --notify push

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

LEAD_TOOLS = [
    "web_search",
    "http_request",
    "memory_store",
    "memory_search",
    "think",
    "cost_lookup",
    "project_create",
    "project_update_status",
    "quote_create",
    "notify_push",
    "notify_email",
]


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
    "--min-job-size",
    default=8000,
    show_default=True,
    type=int,
    help="Skip leads with estimated value below this (USD).",
)
@click.option(
    "--markup-rate",
    default=18.0,
    show_default=True,
    type=float,
    help="Markup %% applied when drafting ballpark quotes.",
)
@click.option(
    "--notify",
    type=click.Choice(["none", "push", "email", "both"], case_sensitive=False),
    default="push",
    show_default=True,
    help="Alert channel for hot leads (requires .env — see .env.example).",
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
    min_job_size: int,
    markup_rate: float,
    notify: str,
    model: str | None,
    engine_key: str | None,
    output: Path | None,
) -> None:
    """Scan the web for GC leads in southern New Hampshire."""
    town_list = [t.strip() for t in towns.split(",") if t.strip()]
    if not town_list:
        click.echo("Error: --towns must contain at least one town.", err=True)
        raise SystemExit(1)

    env_path = Path(__file__).resolve().parent / ".env"
    if notify != "none":
        try:
            from openjarvis.notifications import load_env_file

            load_env_file(env_path)
            load_env_file(Path.home() / ".openjarvis" / ".env")
        except ImportError:
            pass

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    town_str = ", ".join(town_list)

    notify_instructions = {
        "none": "Do not send outbound alerts.",
        "push": (
            "For each hot lead (score 7+), call notify_push with a short "
            "subject and 2–3 line summary including town, job type, and "
            "ballpark quote total."
        ),
        "email": (
            "For each hot lead (score 7+), call notify_email with subject "
            "'Hot lead: [town] [job type]' and the full lead summary."
        ),
        "both": (
            "For each hot lead (score 7+), call notify_push AND notify_email."
        ),
    }[notify]

    prompt = (
        f"Today is {today}. Run a full southern NH GC lead scan.\n\n"
        f"**Towns to prioritize**: {town_str}\n"
        f"**Job types**: {job_types}\n"
        f"**Minimum job size**: ${min_job_size:,} estimated — skip smaller leads\n"
        f"**Quote markup**: {markup_rate}% on subtotal when using quote_create\n\n"
        "Follow your system workflow: recall prior leads from memory, search "
        "homeowner and bid sources, score new opportunities, store each lead.\n\n"
        "**For every hot lead (score 7+)**:\n"
        "1. Use cost_lookup for unit costs, then quote_create with realistic "
        "quantities inferred from the post (deck sqft, garage size, addition "
        "scope). Title: 'Ballpark — [job type] — [town]'.\n"
        "2. project_create for the lead (status: lead), link the quote.\n"
        "3. project_update_status to 'quoted' after the quote is saved.\n"
        f"4. {notify_instructions}\n\n"
        "Produce the standard lead report including quote file paths for hot leads."
    )

    tools = list(LEAD_TOOLS)
    if notify == "none":
        tools = [t for t in tools if not t.startswith("notify_")]

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
            tools=tools,
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
        f"  Min job size: ${min_job_size:,}\n"
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
