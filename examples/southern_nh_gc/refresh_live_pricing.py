#!/usr/bin/env python3
"""Refresh live pricing for all trades and materials, then reseed the catalog.

Run before lead scans or after updating ``live_prices.json``::

    uv run python examples/southern_nh_gc/refresh_live_pricing.py

Optional — pull commodity hints from the web (requires Ollama + Jarvis)::

    uv run python examples/southern_nh_gc/refresh_live_pricing.py --fetch-web
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from live_pricing import (
    load_live_overrides,
    pricing_summary,
    save_live_overrides,
)
from trade_catalog import build_catalog_items

from openjarvis.construction.store import ConstructionStore


def _fetch_web_price_hints() -> dict[str, dict[str, float | str]]:
    """Best-effort web refresh for key materials (optional)."""
    try:
        from openjarvis import Jarvis
    except ImportError as exc:
        raise click.ClickException(
            "openjarvis required for --fetch-web. Run: uv sync"
        ) from exc

    prompt = (
        "Search for current southern New Hampshire / New England ballpark "
        "2026 unit costs for a residential GC. Return ONLY valid JSON object "
        "with keys matching catalog items and {\"floor\": number, \"unit\": str}:\n"
        "- pressure treated decking (per sqft)\n"
        "- composite decking (per sqft)\n"
        "- carpenter labor (per hour)\n"
        "- concrete mix yard\n"
        "- garage door installed\n"
        "Use conservative contractor buy prices, not retail list. No markdown."
    )
    j = Jarvis()
    try:
        raw = j.ask(prompt, agent="orchestrator", tools=["web_search", "think"])
    finally:
        j.close()

    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        click.echo("Web fetch: no JSON in response; keeping existing overrides.")
        return {}
    try:
        data = json.loads(raw[start : end + 1])
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {}


def reseed_construction_store(overrides: dict | None = None) -> int:
    """Write all customer + internal catalog lines to ~/.openjarvis/construction.db."""
    store = ConstructionStore()
    customer, internal = build_catalog_items(overrides)
    for name, category, unit, unit_cost in customer + internal:
        store.add_cost_item(name, unit_cost, category=category, unit=unit)
    return len(customer) + len(internal)


@click.command()
@click.option(
    "--fetch-web",
    is_flag=True,
    help="Update overrides from web search (optional, needs Ollama).",
)
@click.option(
    "--show",
    is_flag=True,
    help="Print pricing summary only; do not write DB.",
)
def main(fetch_web: bool, show: bool) -> None:
    """Apply live prices + premium to every trade/material and reseed catalog."""
    live = load_live_overrides()
    overrides: dict = dict(live.get("overrides") or {})
    sources = list(live.get("sources") or [])

    if fetch_web:
        click.echo("Fetching live material/trade hints from web...")
        hints = _fetch_web_price_hints()
        if hints:
            overrides.update(hints)
            sources.append("web_search")

    summary = pricing_summary(overrides)
    click.echo(
        f"Live pricing (+{summary['premium_percent']:.0f}% premium on all customer items)\n"
        f"  Deck:    ${summary['deck_floor_sqft']:.2f} floor → "
        f"${summary['deck_customer_sqft']:.2f} quote /sqft\n"
        f"  Garage:  ${summary['garage_floor_sqft']:.2f} floor → "
        f"${summary['garage_customer_sqft']:.2f} quote /sqft\n"
        f"  Addition:${summary['addition_floor_sqft']:.2f} floor → "
        f"${summary['addition_customer_sqft']:.2f} quote /sqft"
    )

    if show:
        customer, internal = build_catalog_items(overrides)
        click.echo(f"\n{len(customer)} customer + {len(internal)} internal catalog lines")
        return

    path = save_live_overrides(overrides, sources=sources)
    click.echo(f"\nWrote {path}")

    n = reseed_construction_store(overrides)
    click.echo(f"Reseeded {n} items into construction store.")


if __name__ == "__main__":
    main()
