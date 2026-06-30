"""Live pricing — floor costs + quote premium on every trade and material.

All customer-facing catalog prices flow through :func:`customer_price`.
Floor (internal) costs never include the competitive premium.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shop_pricing import (
    CUSTOMER_QUOTE_PER_SQFT,
    FLOOR_PRICE_PER_SQFT,
    LABOR_PER_SQFT,
    MATERIAL_PER_SQFT,
    QUOTE_PREMIUM_PERCENT,
    customer_multiplier,
)

from component_pricing import (
    deck_floor_from_benchmark,
    mat_labor_split,
    sum_components_floor,
)

_LIVE_PRICES_PATH = Path(__file__).resolve().parent / "live_prices.json"


def customer_price(floor_cost: float) -> float:
    """Customer quote price: floor + competitive premium (all trades/materials)."""
    return round(float(floor_cost) * customer_multiplier(), 2)


def floor_price(customer_cost: float) -> float:
    """Reverse: customer catalog price → floor."""
    return round(float(customer_cost) / customer_multiplier(), 2)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_live_overrides(path: Path | None = None) -> dict[str, Any]:
    """Load optional price overrides from live_prices.json."""
    p = path or _LIVE_PRICES_PATH
    if not p.is_file():
        return {"updated_at": None, "overrides": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("overrides", {})
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"updated_at": None, "overrides": {}}


def save_live_overrides(
    overrides: dict[str, Any],
    *,
    path: Path | None = None,
    sources: list[str] | None = None,
) -> Path:
    p = path or _LIVE_PRICES_PATH
    payload = {
        "updated_at": _now_iso(),
        "quote_premium_percent": QUOTE_PREMIUM_PERCENT,
        "sources": sources or ["trade_catalog"],
        "overrides": overrides,
    }
    p.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return p


def _override_floor(overrides: dict[str, Any], key: str, default: float) -> float:
    raw = overrides.get(key)
    if isinstance(raw, dict) and "floor" in raw:
        return float(raw["floor"])
    if isinstance(raw, (int, float)):
        return float(raw)
    return default


def trade_floor_sqft(trade: str, overrides: dict[str, Any] | None = None) -> float:
    """All-in floor $/sqft — deck from benchmark; garage/addition from components."""
    ov = overrides or {}

    # Explicit override wins
    raw = ov.get(f"{trade}_floor_sqft")
    if isinstance(raw, (int, float)):
        return float(raw)

    if trade == "deck":
        return deck_floor_from_benchmark(ov)

    if trade in ("garage", "addition", "covered porch"):
        total, _ = sum_components_floor(trade, ov)
        return total

    return FLOOR_PRICE_PER_SQFT


def trade_component_breakdown(
    trade: str,
    overrides: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Per-line floor $/sqft for garage/addition/deck (internal use)."""
    _, rows = sum_components_floor(trade, overrides)
    return rows


def pricing_summary(overrides: dict[str, Any] | None = None) -> dict[str, float]:
    """Current all-in rates after overrides and premium."""
    ov = overrides or {}
    deck_floor = trade_floor_sqft("deck", ov)
    garage_floor = trade_floor_sqft("garage", ov)
    addition_floor = trade_floor_sqft("addition", ov)
    garage_mat, garage_lab = mat_labor_split("garage", ov)
    add_mat, add_lab = mat_labor_split("addition", ov)
    return {
        "deck_floor_sqft": deck_floor,
        "deck_customer_sqft": customer_price(deck_floor),
        "garage_floor_sqft": garage_floor,
        "garage_customer_sqft": customer_price(garage_floor),
        "garage_material_sqft": garage_mat,
        "garage_labor_sqft": garage_lab,
        "addition_floor_sqft": addition_floor,
        "addition_customer_sqft": customer_price(addition_floor),
        "addition_material_sqft": add_mat,
        "addition_labor_sqft": add_lab,
        "premium_percent": QUOTE_PREMIUM_PERCENT,
        "material_floor_sqft": _override_floor(ov, "material_sqft", MATERIAL_PER_SQFT),
        "labor_floor_sqft": _override_floor(ov, "labor_sqft", LABOR_PER_SQFT),
    }
