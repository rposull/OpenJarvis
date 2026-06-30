#!/usr/bin/env python3
"""Seed a southern NH GC cost catalog for deck, garage, and addition quotes.

Customer quotes: one all-in $/sqft line (no material/labor split on the PDF).
Internal mat/labor math lives in shop_pricing.py for lead reports only.

Run once before lead scans::

    uv run python examples/southern_nh_gc/seed_cost_catalog.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from openjarvis.construction.store import ConstructionStore

from shop_pricing import (
    LABOR_PER_CREW_DAY,
    LABOR_PER_SQFT,
    MATERIAL_PER_SQFT,
    PRICE_PER_SQFT,
    REFERENCE_CREW_DAYS,
    REFERENCE_DECK_SQFT,
)

# Customer-facing catalog items (quotes use all-in lines only)
DEFAULT_ITEMS: list[tuple[str, str, str, float]] = [
    # (name, category, unit, unit_cost)
    ("deck installed all-in", "labor", "sqft", round(PRICE_PER_SQFT, 2)),
    ("garage built all-in", "labor", "sqft", round(PRICE_PER_SQFT, 2)),
    ("addition built all-in", "labor", "sqft", round(PRICE_PER_SQFT, 2)),
    ("covered porch all-in", "labor", "sqft", round(PRICE_PER_SQFT, 2)),
    # Optional extras (separate lines only when scoped in the job)
    ("deck stairs", "labor", "each", 1200.0),
    ("composite upgrade", "material", "sqft", 15.0),
    ("permit fee allowance", "other", "each", 450.0),
    ("dumpster 20yd", "equipment", "each", 550.0),
]

# Internal reference costs — not for customer quote_create line items
INTERNAL_ITEMS: list[tuple[str, str, str, float]] = [
    ("_internal deck material", "material", "sqft", round(MATERIAL_PER_SQFT, 2)),
    ("_internal deck labor", "labor", "sqft", round(LABOR_PER_SQFT, 2)),
]


@click.command()
def main() -> None:
    """Load default GC unit costs into the construction store."""
    store = ConstructionStore()

    for name, category, unit, unit_cost in DEFAULT_ITEMS + INTERNAL_ITEMS:
        store.add_cost_item(name, unit_cost, category=category, unit=unit)

    items = store.search_cost_items()
    click.echo(f"Seeded {len(items)} cost catalog items.")
    click.echo(
        f"Customer quote rate: ${PRICE_PER_SQFT:.2f}/sqft all-in (single line)\n"
        f"Internal reference ({REFERENCE_DECK_SQFT} sqft / {REFERENCE_CREW_DAYS} days):\n"
        f"  Material: ${MATERIAL_PER_SQFT:.2f}/sqft | Labor: ${LABOR_PER_SQFT:.2f}/sqft\n"
        f"  Labor billing: ~${LABOR_PER_CREW_DAY:,.0f}/crew-day"
    )


if __name__ == "__main__":
    main()
