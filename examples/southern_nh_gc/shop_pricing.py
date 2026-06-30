"""Reference pricing from actual jobs — edit when your rates change.

Benchmark job: 144 sqft deck — $7,000 material + $7,500 labor = $14,500 (~7 days).

Customer quotes are priced above competitive southern NH rates so you have
room to negotiate down while still hitting your floor (base rate) and savings goals.
"""

from __future__ import annotations

# Reference deck (your real numbers — negotiation floor)
REFERENCE_DECK_SQFT = 144
REFERENCE_MATERIAL_TOTAL = 7_000
REFERENCE_LABOR_TOTAL = 7_500
REFERENCE_CREW_DAYS = 7

MATERIAL_PER_SQFT = REFERENCE_MATERIAL_TOTAL / REFERENCE_DECK_SQFT  # ~48.61
LABOR_PER_SQFT = REFERENCE_LABOR_TOTAL / REFERENCE_DECK_SQFT  # ~52.08
FLOOR_PRICE_PER_SQFT = MATERIAL_PER_SQFT + LABOR_PER_SQFT  # ~100.69 — never go below

# Customer quotes: slightly above competitive (room to negotiate, fund house savings)
QUOTE_PREMIUM_PERCENT = 10.0
CUSTOMER_QUOTE_PER_SQFT = round(
    FLOOR_PRICE_PER_SQFT * (1 + QUOTE_PREMIUM_PERCENT / 100), 2
)  # ~110.76/sqft at 10%

# Back-compat alias
PRICE_PER_SQFT = FLOOR_PRICE_PER_SQFT

SQFT_PER_CREW_DAY = REFERENCE_DECK_SQFT / REFERENCE_CREW_DAYS  # ~20.6
LABOR_PER_CREW_DAY = LABOR_PER_SQFT * SQFT_PER_CREW_DAY  # ~$1,071/day at floor

MIN_JOB_SIZE = round(REFERENCE_DECK_SQFT * FLOOR_PRICE_PER_SQFT)  # $14,500 floor
TARGET_PROFIT_DAY_MIN = 500
TARGET_PROFIT_DAY_MAX = 1_000
TARGET_PROFIT_DAY = round(LABOR_PER_CREW_DAY)

BUSINESS_GOAL = (
    "Saving toward buying or building a house — protect margin; quote above market."
)


def customer_multiplier() -> float:
    return 1 + QUOTE_PREMIUM_PERCENT / 100


def premium_addon(base_price: float) -> float:
    """Apply quote premium to flat add-ons (stairs, permits, etc.)."""
    return round(base_price * customer_multiplier(), 2)


def internal_breakdown(sqft: float) -> dict[str, float]:
    """Material/labor split for your eyes only — never put on customer quotes."""
    days = max(sqft / SQFT_PER_CREW_DAY, 1.0)
    labor = sqft * LABOR_PER_SQFT
    floor = sqft * FLOOR_PRICE_PER_SQFT
    quote = sqft * CUSTOMER_QUOTE_PER_SQFT
    return {
        "sqft": sqft,
        "material": round(sqft * MATERIAL_PER_SQFT),
        "labor": round(labor),
        "floor_total": round(floor),
        "quote_total": round(quote),
        "negotiation_room": round(quote - floor),
        "crew_days": round(days, 1),
        "labor_per_day": round(labor / days),
        "premium_percent": QUOTE_PREMIUM_PERCENT,
    }
