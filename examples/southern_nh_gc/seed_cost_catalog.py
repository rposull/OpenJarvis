#!/usr/bin/env python3
"""Seed a southern NH GC cost catalog for deck, garage, and addition quotes.

Run once before lead scans (or after resetting ~/.openjarvis/construction.db)::

    uv run python examples/southern_nh_gc/seed_cost_catalog.py

Adjust unit costs to match your shop rates. The lead scanner uses these via
``cost_lookup`` when drafting ballpark quotes with ``quote_create``.
"""

from __future__ import annotations

import click

from openjarvis.construction.store import ConstructionStore

# Ballpark southern NH rates — edit to match your pricing.
DEFAULT_ITEMS: list[tuple[str, str, str, float]] = [
    # (name, category, unit, unit_cost)
    # Labor
    ("carpenter labor", "labor", "hour", 72.0),
    ("lead carpenter labor", "labor", "hour", 85.0),
    ("general labor", "labor", "hour", 55.0),
    ("demo labor", "labor", "hour", 65.0),
    ("concrete labor", "labor", "hour", 68.0),
    # Decks
    ("pressure treated decking", "material", "sqft", 3.25),
    ("composite decking", "material", "sqft", 6.50),
    ("deck railing linear", "material", "lf", 42.0),
    ("deck footings", "material", "each", 85.0),
    ("deck framing lumber package", "material", "sqft", 4.75),
    ("deck stairs", "material", "each", 650.0),
    # Garages
    ("garage slab 4in", "material", "sqft", 9.50),
    ("garage framing package", "material", "sqft", 14.0),
    ("garage door installed", "material", "each", 1800.0),
    ("garage electrical rough-in", "material", "each", 2200.0),
    # Additions
    ("addition framing", "material", "sqft", 18.0),
    ("addition roof tie-in", "material", "sqft", 22.0),
    ("insulation r21", "material", "sqft", 2.80),
    ("drywall hung taped", "material", "sqft", 3.50),
    ("vinyl siding", "material", "sqft", 5.25),
    # Shared
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


if __name__ == "__main__":
    main()
