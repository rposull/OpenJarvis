#!/usr/bin/env python3
"""Seed a southern NH GC cost catalog for deck, garage, and addition quotes.

Shop pricing (edit these constants to match your business)::

    $100/sqft all-in (material + labor) for decks, garages, and additions
    Target: $500–$1,000 profit per crew-day on site

Run once before lead scans::

    uv run python examples/southern_nh_gc/seed_cost_catalog.py
"""

from __future__ import annotations

import click

from openjarvis.construction.store import ConstructionStore

# --- Your shop rates (customer-facing) ---------------------------------------
PRICE_PER_SQFT = 100.0  # $/sqft installed, material + labor included
# Internal loaded cost for margin math (~42% gross margin at $100 sell)
INTERNAL_COST_PER_SQFT = 58.0
MARGIN_PER_SQFT = PRICE_PER_SQFT - INTERNAL_COST_PER_SQFT

# --- Catalog: sell-price packages + common add-ons ----------------------------
DEFAULT_ITEMS: list[tuple[str, str, str, float]] = [
    # (name, category, unit, unit_cost)
    # Primary packages — already at your $100/sqft sell rate (use markup 0)
    ("deck installed all-in", "labor", "sqft", PRICE_PER_SQFT),
    ("garage built all-in", "labor", "sqft", PRICE_PER_SQFT),
    ("addition shell all-in", "labor", "sqft", PRICE_PER_SQFT),
    ("covered porch all-in", "labor", "sqft", PRICE_PER_SQFT),
    # Deck add-ons (sell price, on top of base deck sqft when applicable)
    ("deck stairs", "labor", "each", 1200.0),
    ("composite upgrade", "material", "sqft", 15.0),
    ("glass railing upgrade", "material", "lf", 95.0),
    ("hot tub deck reinforcement", "labor", "each", 850.0),
    # Garage add-ons
    ("garage door installed", "material", "each", 1800.0),
    ("garage electrical rough-in", "material", "each", 2200.0),
    ("garage slab 4in", "material", "sqft", 9.50),
    # Addition finish add-ons
    ("drywall hung taped", "material", "sqft", 3.50),
    ("vinyl siding", "material", "sqft", 5.25),
    ("insulation r21", "material", "sqft", 2.80),
    # Job overhead (flat per project)
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
    daily_at_20_sqft = MARGIN_PER_SQFT * 20
    click.echo(f"Seeded {len(items)} cost catalog items.")
    click.echo(
        f"Pricing: ${PRICE_PER_SQFT:.0f}/sqft all-in | "
        f"~${MARGIN_PER_SQFT:.0f}/sqft margin | "
        f"~${daily_at_20_sqft:.0f}/day at 20 sqft/day on site"
    )


if __name__ == "__main__":
    main()
