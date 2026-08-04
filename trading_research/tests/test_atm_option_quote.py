"""ATM live premium selection for paper option entries."""

from __future__ import annotations

from datetime import date, datetime, timezone

from trading_research.config.settings import Settings
from trading_research.execution.atm_option_quote import (
    AtmOptionQuote,
    _mid_premium,
    _nearest_strike_row,
    _pick_expiration,
)
from trading_research.execution.option_trend_exits import open_option_kwargs


def test_mid_premium_prefers_bid_ask():
    assert _mid_premium({"bid": 1.0, "ask": 1.2, "lastPrice": 9.0}) == 1.1


def test_nearest_strike_to_spot():
    rows = [
        {"strike": 100, "bid": 1, "ask": 1.1, "lastPrice": 1},
        {"strike": 105, "bid": 2, "ask": 2.1, "lastPrice": 2},
        {"strike": 110, "bid": 0.5, "ask": 0.6, "lastPrice": 0.5},
    ]
    best = _nearest_strike_row(rows, 104.8)
    assert best is not None
    assert float(best["strike"]) == 105


def test_pick_expiration_prefers_0dte():
    today = date(2026, 8, 4)
    ts_today = int(datetime(2026, 8, 4, tzinfo=timezone.utc).timestamp())
    ts_next = int(datetime(2026, 8, 5, tzinfo=timezone.utc).timestamp())
    assert _pick_expiration([ts_next, ts_today], prefer_0dte=True, today=today) == ts_today


def test_open_option_kwargs_uses_live_atm(monkeypatch):
    q = AtmOptionQuote(
        symbol="SPY",
        right="call",
        strike=771.0,
        premium=1.055,
        bid=1.03,
        ask=1.08,
        last=1.51,
        underlying=771.33,
        expiration="2026-08-04",
        days_to_expiry=0,
    )
    monkeypatch.setattr(
        "trading_research.execution.atm_option_quote.fetch_atm_option_quote",
        lambda *a, **k: q,
    )
    s = Settings(option_win_use_fixed_premium=False)
    kw = open_option_kwargs(
        action="buy",
        right="call",
        strike=771.33,
        underlying_price=771.33,
        contracts=1,
        reason="test",
        settings=s,
        atr=2.0,
        symbol="SPY",
        prefer_live_premium=True,
    )
    assert kw["strike"] == 771.0
    assert kw["premium"] == 1.055
    assert kw["days_to_expiry"] == 0
    assert kw["live_quote"]["source"] == "yahoo"
    assert "ATM" in kw["reason"]
