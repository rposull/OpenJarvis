#!/usr/bin/env python3
"""Southern NH GC lead scan — find deck, garage, and addition jobs.

Run manually::

    uv run python examples/southern_nh_gc/refresh_live_pricing.py
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

from live_pricing import load_live_overrides, pricing_summary
from refresh_live_pricing import reseed_construction_store
from shop_pricing import (
    BUSINESS_GOAL,
    CUSTOMER_QUOTE_PER_SQFT,
    FLOOR_PRICE_PER_SQFT,
    LABOR_PER_SQFT,
    MATERIAL_PER_SQFT,
    MIN_JOB_SIZE,
    QUOTE_PREMIUM_PERCENT,
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

DEFAULT_PRICE_PER_SQFT = CUSTOMER_QUOTE_PER_SQFT
DEFAULT_MIN_JOB_SIZE = MIN_JOB_SIZE
DEFAULT_TARGET_PROFIT_DAY = TARGET_PROFIT_DAY
DEFAULT_QUOTE_PREMIUM = QUOTE_PREMIUM_PERCENT
DEFAULT_MARKUP_RATE = 0.0


def _load_gc_context() -> str:
    """Optional owner context (e.g. future ChatGPT export) for pricing judgment."""
    import json

    for path in (
        Path.home() / ".openjarvis" / "gc_context.json",
        _ROOT / "gc_context.json",
    ):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return (
                f"\n\n**Owner context** (from `{path}` — use for pricing judgment):\n"
                f"```json\n{json.dumps(data, indent=2)}\n```\n"
            )
        except (OSError, json.JSONDecodeError):
            continue
    return ""

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
    help="Customer quote rate $/sqft (includes competitive premium).",
)
@click.option(
    "--quote-premium",
    default=DEFAULT_QUOTE_PREMIUM,
    show_default=True,
    type=float,
    help="%% above floor rate baked into customer quotes (negotiation room).",
)
@click.option(
    "--floor-per-sqft",
    default=round(FLOOR_PRICE_PER_SQFT, 2),
    show_default=True,
    type=float,
    help="Never quote below this $/sqft without explicit approval.",
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
    "--refresh-pricing/--no-refresh-pricing",
    default=True,
    show_default=True,
    help="Reseed catalog from live_prices.json before scan (all trades/materials).",
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
    quote_premium: float,
    floor_per_sqft: float,
    target_profit_day: int,
    markup_rate: float,
    notify: str,
    refresh_pricing: bool,
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
    live = load_live_overrides()
    overrides: dict = dict(live.get("overrides") or {})
    if refresh_pricing:
        n = reseed_construction_store(overrides)
        click.echo(f"Live pricing: reseeded {n} catalog items (all trades + materials).")
    live_summary = pricing_summary(overrides)
    if price_per_sqft == DEFAULT_PRICE_PER_SQFT:
        price_per_sqft = live_summary["deck_customer_sqft"]

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

    owner_context = _load_gc_context()

    prompt = (
        f"Today is {today}. Run a full southern NH GC lead scan.\n\n"
        f"**Owner goal**: {BUSINESS_GOAL}\n"
        f"**Towns to prioritize**: {town_str}\n"
        f"**Job types**: {job_types}\n"
        f"**Customer quote rate (deck)**: ${price_per_sqft:.2f}/sqft "
        f"(~{quote_premium:.0f}% above ${floor_per_sqft:.2f}/sqft deck floor)\n"
        f"**Garage / addition quotes**: TWO lines on the customer PDF — "
        "**materials first**, then **labor** (use `garage materials package` + "
        "`garage labor package`, or addition equivalents). cost_lookup both rates. "
        "Never use deck all-in for garage/addition.\n"
        f"**Deck quotes**: ONE all-in line (`deck installed all-in`).\n"
        f"**Pricing rule**: Premium already in catalog. Negotiate down toward floor "
        "rates, not below, without owner approval.\n"
        f"**Productivity**: ~{SQFT_PER_CREW_DAY:.0f} sqft/crew-day "
        f"({REFERENCE_DECK_SQFT} sqft in {REFERENCE_CREW_DAYS} days)\n"
        f"**Labor income target**: ${TARGET_PROFIT_DAY_MIN}–${TARGET_PROFIT_DAY_MAX}/day "
        f"(floor reference ~${TARGET_PROFIT_DAY}/day)\n"
        f"**Minimum job size (floor)**: ${min_job_size:,}\n"
        f"**Quote markup**: {markup_rate}%\n"
        f"**Live catalog**: always `cost_lookup` before quoting — every trade, "
        "material, labor, equipment, and subcontract line includes the "
        f"+{quote_premium:.0f}% premium in the stored sell price.\n"
        f"{owner_context}\n"
        "Follow your system workflow: recall prior leads, search sources, score leads.\n\n"
        "**For every hot lead (score 7+)**:\n"
        "1. **Customer quote** (`quote_create`):\n"
        "   - **Deck**: ONE line — `deck installed all-in` × sqft\n"
        "   - **Garage / addition**: TWO lines — materials package × sqft, "
        "then labor package × sqft (materials line lists slab, framing, roof, "
        "siding, windows, door/electrical allowances in description)\n"
        "   - See `examples/southern_nh_gc/quote_lines.py` for structure\n"
        "2. **Internal** (report + memory): component breakdown per layer, floor "
        "mat/labor $/sqft, negotiation room, crew-days, labor/day\n"
        "3. quote_create must include detailed `scope_of_work`, `exclusions`, "
        "`estimated_timeline` (see scope_templates.py).\n"
        "4. project_create, project_update_status to quoted.\n"
        f"5. {notify_instructions}\n\n"
        "Report: customer quote total + path; **Internal** line with floor, "
        "negotiation room, mat/labor, days."
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
        f"  Quote: ${price_per_sqft:.2f}/sqft (+{quote_premium:.0f}% over "
        f"${floor_per_sqft:.2f} floor) | Min: ${min_job_size:,}\n"
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
