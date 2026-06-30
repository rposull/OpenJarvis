"""All trades and materials — floor unit costs (southern NH GC).

Customer-facing sell prices are computed by :mod:`live_pricing` (floor + premium).
Override any key in ``live_prices.json`` → ``overrides`` to update live costs.
"""

from __future__ import annotations

from typing import Any

from component_pricing import mat_labor_split
from live_pricing import customer_price, trade_floor_sqft
from shop_pricing import LABOR_PER_SQFT, MATERIAL_PER_SQFT

# (name, category, unit, floor_unit_cost)
# Categories: material | labor | equipment | subcontract | other

SHARED_MATERIALS: list[tuple[str, str, str, float]] = [
    ("pressure treated decking", "material", "sqft", 3.25),
    ("composite decking", "material", "sqft", 6.50),
    ("deck framing lumber package", "material", "sqft", 4.75),
    ("deck footings", "material", "each", 85.0),
    ("deck railing linear", "material", "lf", 42.0),
    ("fasteners and hardware", "material", "sqft", 1.50),
    ("concrete mix yard", "material", "yd", 165.0),
    ("garage slab 4in", "material", "sqft", 9.50),
    ("garage framing package", "material", "sqft", 14.0),
    ("roof shingles", "material", "sqft", 3.85),
    ("housewrap", "material", "sqft", 0.45),
    ("insulation r21", "material", "sqft", 2.80),
    ("drywall hung taped", "material", "sqft", 3.50),
    ("vinyl siding", "material", "sqft", 5.25),
    ("windows standard", "material", "each", 450.0),
    ("composite upgrade", "material", "sqft", 15.0),
    ("glass railing upgrade", "material", "lf", 95.0),
]

SHARED_LABOR: list[tuple[str, str, str, float]] = [
    ("carpenter labor", "labor", "hour", 72.0),
    ("lead carpenter labor", "labor", "hour", 85.0),
    ("general labor", "labor", "hour", 55.0),
    ("demo labor", "labor", "hour", 65.0),
    ("concrete labor", "labor", "hour", 68.0),
    ("roofing labor", "labor", "sqft", 4.25),
    ("siding labor", "labor", "sqft", 3.75),
]

SHARED_EQUIPMENT: list[tuple[str, str, str, float]] = [
    ("dumpster 20yd", "equipment", "each", 550.0),
    ("excavator mini day", "equipment", "day", 450.0),
    ("concrete pump", "equipment", "each", 650.0),
]

SHARED_OTHER: list[tuple[str, str, str, float]] = [
    ("permit fee allowance", "other", "each", 450.0),
    ("site protection misc", "other", "each", 250.0),
    ("dig safe locate", "other", "each", 75.0),
]

# Subcontract allowances (floor — customer quote uses customer_price)
SUBCONTRACT_TRADES: list[tuple[str, str, str, float]] = [
    ("electrical rough-in allowance", "subcontract", "each", 2200.0),
    ("plumbing rough allowance", "subcontract", "each", 1800.0),
    ("hvac allowance", "subcontract", "each", 3500.0),
    ("garage door installed", "subcontract", "each", 1800.0),
]

# Internal mat/labor from component sums (garage/addition higher $/sqft than deck)
def _internal_packages(overrides: dict[str, Any]) -> list[tuple[str, str, str, float]]:
    deck_mat, deck_lab = mat_labor_split("deck", overrides)
    gar_mat, gar_lab = mat_labor_split("garage", overrides)
    add_mat, add_lab = mat_labor_split("addition", overrides)
    return [
        ("_internal deck material", "material", "sqft", deck_mat or MATERIAL_PER_SQFT),
        ("_internal deck labor", "labor", "sqft", deck_lab or LABOR_PER_SQFT),
        ("_internal garage material", "material", "sqft", gar_mat),
        ("_internal garage labor", "labor", "sqft", gar_lab),
        ("_internal addition material", "material", "sqft", add_mat),
        ("_internal addition labor", "labor", "sqft", add_lab),
    ]


INTERNAL_LABOR_PACKAGES: list[tuple[str, str, str, float]] = []

# Flat add-ons (floor)
FLAT_ADDONS: list[tuple[str, str, str, float]] = [
    ("deck stairs", "labor", "each", 1200.0),
    ("hot tub deck reinforcement", "labor", "each", 850.0),
    ("addition roof tie-in", "labor", "sqft", 22.0),
]


def _item_floor(
    name: str,
    default: float,
    overrides: dict[str, Any],
) -> float:
    raw = overrides.get(name)
    if isinstance(raw, dict) and "floor" in raw:
        return float(raw["floor"])
    if isinstance(raw, (int, float)):
        return float(raw)
    return default


def build_catalog_items(
    overrides: dict[str, Any] | None = None,
) -> tuple[list[tuple[str, str, str, float]], list[tuple[str, str, str, float]]]:
    """Return (customer_items, internal_items) for ConstructionStore.

    Every customer item uses live floor cost + quote premium.
    Internal items stay at floor for margin math.
    """
    ov = overrides or {}
    customer: list[tuple[str, str, str, float]] = []
    internal: list[tuple[str, str, str, float]] = []

    # All-in packages per trade (primary quote line)
    for trade, catalog_name in (
        ("deck", "deck installed all-in"),
        ("garage", "garage built all-in"),
        ("addition", "addition built all-in"),
        ("covered porch", "covered porch all-in"),
    ):
        floor_sqft = trade_floor_sqft(trade, ov)
        customer.append((catalog_name, "labor", "sqft", customer_price(floor_sqft)))

    # Materials, labor, equipment, subs — premium on every sell line
    for group in (
        SHARED_MATERIALS,
        SHARED_LABOR,
        SHARED_EQUIPMENT,
        SHARED_OTHER,
        SUBCONTRACT_TRADES,
        FLAT_ADDONS,
    ):
        for name, category, unit, floor_cost in group:
            floor = _item_floor(name, floor_cost, ov)
            customer.append((name, category, unit, customer_price(floor)))

    for name, category, unit, floor_cost in _internal_packages(ov):
        internal.append((name, category, unit, floor_cost))

    return customer, internal


def all_trade_names() -> list[str]:
    return ["deck", "garage", "addition", "covered porch"]
