"""Per-trade floor $/sqft built from individual material + labor components.

Decks use the real 144 sqft benchmark (~$100.69/sqft all-in).

Garages and additions sum many line items (slab, framing, roof, siding,
windows, subs, etc.) — typically **above** deck $/sqft.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shop_pricing import FLOOR_PRICE_PER_SQFT, LABOR_PER_SQFT, MATERIAL_PER_SQFT


@dataclass(frozen=True)
class SqftComponent:
    """One cost layer attributed per sqft of building footprint."""

    key: str
    label: str
    category: str  # material | labor | subcontract | other
    floor_per_sqft: float


# Deck — validated against your 144 sqft job ($7k mat + $7.5k labor)
DECK_COMPONENTS: tuple[SqftComponent, ...] = (
    SqftComponent("decking material", "Decking material", "material", 18.0),
    SqftComponent("deck framing material", "Framing & hardware", "material", 12.5),
    SqftComponent("footings amortized", "Footings & concrete", "material", 8.5),
    SqftComponent("railing amortized", "Railing", "material", 9.61),
    SqftComponent("deck build labor", "Deck carpentry labor", "labor", 52.08),
)

# Garage — slab, structure, roof, siding, openings, subs (higher $/sqft than deck)
GARAGE_COMPONENTS: tuple[SqftComponent, ...] = (
    SqftComponent("slab material", "Concrete slab", "material", 10.0),
    SqftComponent("slab labor", "Concrete labor", "labor", 6.0),
    SqftComponent("framing material", "Wall & roof framing lumber", "material", 15.0),
    SqftComponent("framing labor", "Framing carpentry labor", "labor", 32.0),
    SqftComponent("roofing material", "Roof sheathing & shingles", "material", 4.5),
    SqftComponent("roofing labor", "Roofing labor", "labor", 6.0),
    SqftComponent("siding material", "Siding & trim material", "material", 6.5),
    SqftComponent("siding labor", "Siding installation labor", "labor", 8.0),
    SqftComponent("housewrap trim", "Housewrap, fascia, soffit", "material", 2.5),
    SqftComponent("windows amortized", "Windows (amortized)", "material", 3.0),
    SqftComponent("garage door amortized", "Garage door (amortized)", "subcontract", 4.0),
    SqftComponent("electrical amortized", "Electrical rough-in (amortized)", "subcontract", 5.5),
    SqftComponent("supervision", "Lead carpentry / supervision", "labor", 13.0),
    SqftComponent("permits misc", "Permits & site protection", "other", 3.0),
)

# Addition — foundation, envelope, tie-in, MEP allowances (highest $/sqft)
ADDITION_COMPONENTS: tuple[SqftComponent, ...] = (
    SqftComponent("foundation", "Foundation & frost walls", "material", 14.0),
    SqftComponent("foundation labor", "Foundation labor", "labor", 10.0),
    SqftComponent("framing material", "Floor & wall framing", "material", 18.0),
    SqftComponent("framing labor", "Framing labor", "labor", 28.0),
    SqftComponent("roof tie-in", "Roof tie-in & flashing", "labor", 10.0),
    SqftComponent("roofing material", "Roofing material", "material", 5.0),
    SqftComponent("roofing labor", "Roofing labor", "labor", 5.5),
    SqftComponent("insulation", "Insulation & air seal", "material", 3.5),
    SqftComponent("drywall", "Drywall material", "material", 2.5),
    SqftComponent("drywall labor", "Drywall hang & finish labor", "labor", 4.5),
    SqftComponent("siding material", "Exterior siding material", "material", 6.5),
    SqftComponent("siding labor", "Siding labor", "labor", 6.0),
    SqftComponent("windows amortized", "Windows (amortized)", "material", 4.5),
    SqftComponent("exterior doors", "Exterior doors (amortized)", "material", 2.5),
    SqftComponent("plumbing amortized", "Plumbing rough (amortized)", "subcontract", 4.5),
    SqftComponent("electrical amortized", "Electrical rough (amortized)", "subcontract", 5.5),
    SqftComponent("hvac amortized", "HVAC allowance (amortized)", "subcontract", 6.0),
    SqftComponent("supervision", "Lead carpentry / supervision", "labor", 10.0),
    SqftComponent("permits misc", "Permits & site protection", "other", 4.0),
)

PORCH_COMPONENTS: tuple[SqftComponent, ...] = (
    SqftComponent("porch framing", "Porch framing", "material", 10.0),
    SqftComponent("porch roof", "Porch roof", "material", 8.0),
    SqftComponent("porch labor", "Porch build labor", "labor", 38.0),
    SqftComponent("footings", "Footings", "material", 7.0),
)

TRADE_COMPONENTS: dict[str, tuple[SqftComponent, ...]] = {
    "deck": DECK_COMPONENTS,
    "garage": GARAGE_COMPONENTS,
    "addition": ADDITION_COMPONENTS,
    "covered porch": PORCH_COMPONENTS,
}


def _component_floor(
    overrides: dict[str, Any],
    trade: str,
    comp: SqftComponent,
) -> float:
    for key in (f"{trade}:{comp.key}", comp.key, f"{trade}_{comp.key}"):
        raw = overrides.get(key)
        if isinstance(raw, dict) and "floor" in raw:
            return float(raw["floor"])
        if isinstance(raw, (int, float)):
            return float(raw)
    return comp.floor_per_sqft


def sum_components_floor(
    trade: str,
    overrides: dict[str, Any] | None = None,
) -> tuple[float, list[dict[str, Any]]]:
    """Return (total floor $/sqft, per-component breakdown)."""
    ov = overrides or {}
    components = TRADE_COMPONENTS.get(trade, ())
    rows: list[dict[str, Any]] = []
    total = 0.0
    for comp in components:
        val = _component_floor(ov, trade, comp)
        total += val
        rows.append(
            {
                "key": comp.key,
                "label": comp.label,
                "category": comp.category,
                "floor_per_sqft": round(val, 2),
            }
        )
    return round(total, 2), rows


def mat_labor_split(
    trade: str,
    overrides: dict[str, Any] | None = None,
) -> tuple[float, float]:
    """Floor $/sqft: materials (incl. subs & allowances) vs labor."""
    ov = overrides or {}
    material = 0.0
    labor = 0.0
    for comp in TRADE_COMPONENTS.get(trade, ()):
        val = _component_floor(ov, trade, comp)
        if comp.category == "labor":
            labor += val
        else:
            # material, subcontract, other → materials bucket
            material += val
    return round(material, 2), round(labor, 2)


def material_labor_rows(
    trade: str,
    overrides: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Per-sqft material and labor rows with component detail (internal)."""
    ov = overrides or {}
    mat_total, lab_total = mat_labor_split(trade, ov)
    mat_rows = []
    lab_rows = []
    for comp in TRADE_COMPONENTS.get(trade, ()):
        val = _component_floor(ov, trade, comp)
        row = {"label": comp.label, "floor_per_sqft": round(val, 2)}
        if comp.category == "labor":
            lab_rows.append(row)
        else:
            mat_rows.append(row)
    return [
        {"type": "materials", "floor_per_sqft": mat_total, "components": mat_rows},
        {"type": "labor", "floor_per_sqft": lab_total, "components": lab_rows},
    ]


def deck_floor_from_benchmark(overrides: dict[str, Any] | None = None) -> float:
    """Prefer real job benchmark override; else sum deck components."""
    ov = overrides or {}
    raw = ov.get("deck_floor_sqft")
    if isinstance(raw, (int, float)):
        return float(raw)
    total, _ = sum_components_floor("deck", ov)
    return total
