#!/usr/bin/env python3
"""Seed a southern NH GC cost catalog for deck, garage, and addition quotes.

Benchmark: 144 sqft deck — $7,000 material + $7,500 labor (~7 crew-days).

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
    LABOR_PER_SQFT,
    LABOR_PER_CREW_DAY,
    MATERIAL_PER_SQFT,
    PRICE_PER_SQFT,
    REFERENCE_CREW_DAYS,
    REFERENCE_DECK_SQFT,
)

# --- Catalog: material + labor per sqft (from your 144 sqft deck) ------------
DEFAULT_ITEMS: list[tuple[str, str, str, float]] = [
    # (name, category, unit, unit_cost)
    # Deck — quote as two lines: material sqft + labor sqft
    ("deck material", "material", "sqft", round(MATERIAL_PER_SQFT, 2)),
    ("deck labor", "labor", "sqft", round(LABOR_PER_SQFT, 2)),
    # Garage / addition — same $/sqft split unless you tune separately
    ("garage material", "material", "sqft", round(MATERIAL_PER_SQFT, 2)),
    ("garage labor", "labor", "sqft", round(LABOR_PER_SQFT, 2)),
    ("addition material", "material", "sqft", round(MATERIAL_PER_SQFT, 2)),
    ("addition labor", "labor", "sqft", round(LABOR_PER_SQFT, 2)),
    # Convenience single-line package (same total $/sqft)
    ("deck installed all-in", "labor", "sqft", round(PRICE_PER_SQFT, 2)),
    # Add-ons
    ("deck stairs", "labor", "each", 1200.0),
    ("composite upgrade", "material", "sqft", 15.0),
    ("glass railing upgrade", "material", "lf", 95.0),
    ("garage door installed", "material", "each", 1800.0),
    ("garage electrical rough-in", "material", "each", 2200.0),
    ("permit fee allowance", "other", "each", 450.0),
    ("dumpster 20yd", "equipment", "each", 550.0),
    ("site protection misc", "material", "each", 250.0),
]


@click.command()
def main() -> None:
    """Load default GC unit costs into the construction store."""
    store = ConstructionStore()

    for name, category, unit, unit_cost in DEFAULT_ITEMS:
        store.add_cost_item(name, unit_cost, category=category, unit=unit)

    items = store.search_cost_items()
    click.echo(f"Seeded {len(items)} cost catalog items.")
    click.echo(
        f"Reference: {REFERENCE_DECK_SQFT} sqft deck in {REFERENCE_CREW_DAYS} days\n"
        f"  Material: ${MATERIAL_PER_SQFT:.2f}/sqft\n"
        f"  Labor:    ${LABOR_PER_SQFT:.2f}/sqft\n"
        f"  Total:    ${PRICE_PER_SQFT:.2f}/sqft\n"
        f"  Labor billing: ~${LABOR_PER_CREW_DAY:,.0f}/crew-day on site"
    )


if __name__ == "__main__":
    main()
