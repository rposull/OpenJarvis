"""Market universe for multi-asset backtests."""

from __future__ import annotations

MARKETS: dict[str, list[str]] = {
    "stocks": ["SPY", "AAPL", "MSFT", "NVDA"],
    "indices": ["^GSPC", "^IXIC", "^DJI"],
    "fx": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDJPY=X"],
    "crypto": ["BTC-USD", "ETH-USD"],
    "commodities": ["GC=F", "CL=F", "SI=F"],
}

# Pairs trade: EUR/USD vs GBP/USD (run separately)
PAIR_SPECS: list[tuple[str, str, str]] = [
    ("fx", "EURUSD=X", "GBPUSD=X"),
]

ALL_TICKERS: list[str] = sorted({t for group in MARKETS.values() for t in group})

STRATEGY_NAMES: list[str] = [
    "trend_following",
    "mean_reversion",
    "support_resistance",
    "opening_range_breakout",
    "pullback_in_trend",
    "momentum",
    "pairs_mean_reversion",
    "carry_trade",
    "volatility_breakout",
    "systematic_trend_risk",
]
