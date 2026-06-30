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

import sys
from datetime import datetime, timezone
from pathlib import Path

import click

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shop_pricing import (
    LABOR_PER_SQFT,
    MATERIAL_PER_SQFT,
    MIN_JOB_SIZE,
    PRICE_PER_SQFT,
    REFERENCE_CREW_DAYS,
    REFERENCE_DECK_SQFT,
    SQFT_PER_CREW_DAY,
    TARGET_PROFIT_DAY,
    TARGET_PROFIT_DAY_MAX,
    TARGET_PROFIT_DAY_MIN,
)

DEFAULT_TOWNS = (
    "Nashua, Manchester, Merrimack, Bedford, Londonderry, Derry, Salem, "
    "Hudson, Pelham, Windham, Amherst, Milford, Hollis"
)

DEFAULT_JOB_TYPES = "decks, garages, home additions"

DEFAULT_PRICE_PER_SQFT = round(PRICE_PER_SQFT)
DEFAULT_MIN_JOB_SIZE = MIN_JOB_SIZE
DEFAULT_TARGET_PROFIT_DAY = TARGET_PROFIT_DAY
DEFAULT_MARKUP_RATE = 0.0

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
    default=DEFAULT_MIN_JOB_SIZE,
    show_default=True,
    type=int,
    help="Skip leads with estimated contract value below this (USD).",
)
@click.option(
    "--price-per-sqft",
    default=DEFAULT_PRICE_PER_SQFT,
    show_default=True,
    type=float,
    help="Installed rate $/sqft (material + labor).",
)
@click.option(
    "--target-profit-day",
    default=DEFAULT_TARGET_PROFIT_DAY,
    show_default=True,
    type=int,
    help="Prefer leads estimated to yield this $/crew-day profit (500–1000).",
)
@click.option(
    "--markup-rate",
    default=DEFAULT_MARKUP_RATE,
    show_default=True,
    type=float,
    help="Markup %% on quote line items (0 when catalog is already sell price).",
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
    price_per_sqft: float,
    target_profit_day: int,
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
        f"**Pricing** (from real 144 sqft deck job):\n"
        f"  - Material: ${MATERIAL_PER_SQFT:.2f}/sqft\n"
        f"  - Labor: ${LABOR_PER_SQFT:.2f}/sqft\n"
        f"  - Total: ~${price_per_sqft:.0f}/sqft\n"
        f"**Productivity**: ~{SQFT_PER_CREW_DAY:.0f} sqft/crew-day "
        f"({REFERENCE_DECK_SQFT} sqft in {REFERENCE_CREW_DAYS} days)\n"
        f"**Labor income target**: ${TARGET_PROFIT_DAY_MIN}–${TARGET_PROFIT_DAY_MAX}/day "
        f"(reference job ~${TARGET_PROFIT_DAY}/day)\n"
        f"**Minimum job size**: ${min_job_size:,}\n"
        f"**Quote markup**: {markup_rate}%\n\n"
        "Follow your system workflow: recall prior leads, search sources, score leads.\n\n"
        "**For every hot lead (score 7+)**:\n"
        "1. Estimate sqft. **Customer quote** (`quote_create`): ONE all-in line only — "
        "`deck installed all-in`, `garage built all-in`, or `addition built all-in` "
        f"at ${price_per_sqft:.2f}/sqft. Do NOT split material and labor on the quote.\n"
        "2. **Internal breakdown** (lead report + memory_store only, not on quote): "
        f"material = sqft × ${MATERIAL_PER_SQFT:.2f}, labor = sqft × "
        f"${LABOR_PER_SQFT:.2f}, crew-days = sqft ÷ {SQFT_PER_CREW_DAY:.0f}, "
        "labor/day = labor ÷ days.\n"
        "3. quote_create with:\n"
        "   - ONE pricing line (all-in $/sqft)\n"
        "   - scope_of_work: detailed bullets — site prep, permits, footings, "
        "framing, decking/railing, cleanup, inspections (customize to the post)\n"
        "   - exclusions: electrical, plumbing, landscaping unless in scope\n"
        "   - estimated_timeline: crew-days on site\n"
        "   See examples/southern_nh_gc/scope_templates.py for deck/garage/addition templates.\n"
        "4. project_create, project_update_status to quoted.\n"
        f"5. {notify_instructions}\n\n"
        "Report sections: customer total + quote path; separate **Internal** line "
        "with mat/labor/days (for you only)."
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
        f"  Rate: ${price_per_sqft:.0f}/sqft | Min job: ${min_job_size:,}\n"
        f"  Profit target: ${target_profit_day}/day\n"
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
