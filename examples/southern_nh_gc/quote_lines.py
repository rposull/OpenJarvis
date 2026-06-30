"""Helpers for quote_create line items per trade."""

from __future__ import annotations

from typing import Any

from component_pricing import mat_labor_split
from live_pricing import customer_price, trade_floor_sqft


def quote_items_for_trade(
    trade: str,
    sqft: float,
    *,
    town: str = "",
    overrides: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build quote_create ``items`` list for a trade.

  - **deck**: one all-in line (customer sees single bulk price)
  - **garage / addition / porch**: two lines — materials first, then labor
    """
    trade = trade.strip().lower()
    loc = f" — {town}" if town else ""
    sqft = float(sqft)

    if trade == "deck":
        rate = customer_price(trade_floor_sqft("deck", overrides))
        return [
            {
                "description": f"Deck construction{loc}",
                "catalog_item": "deck installed all-in",
                "quantity": sqft,
                "unit": "sqft",
                "unit_cost": rate,
            }
        ]

    mat_floor, lab_floor = mat_labor_split(trade, overrides)
    mat_rate = customer_price(mat_floor)
    lab_rate = customer_price(lab_floor)
    label = trade.replace("_", " ").title()

    if trade == "garage":
        mat_item, lab_item = "garage materials package", "garage labor package"
    elif trade == "addition":
        mat_item, lab_item = "addition materials package", "addition labor package"
    elif trade in ("covered porch", "porch"):
        mat_item, lab_item = "porch materials package", "porch labor package"
        label = "Covered porch"
    else:
        mat_item = f"{trade} materials package"
        lab_item = f"{trade} labor package"

    return [
        {
            "description": (
                f"{label} — materials{loc} "
                f"(slab, framing, roof, siding, windows, allowances)"
            ),
            "catalog_item": mat_item,
            "quantity": sqft,
            "unit": "sqft",
            "unit_cost": mat_rate,
        },
        {
            "description": (
                f"{label} — labor{loc} "
                f"(framing, roofing, siding, supervision)"
            ),
            "catalog_item": lab_item,
            "quantity": sqft,
            "unit": "sqft",
            "unit_cost": lab_rate,
        },
    ]
