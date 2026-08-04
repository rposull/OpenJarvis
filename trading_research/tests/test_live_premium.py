"""Live ATR-based option premium entry tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from trading_research.config.settings import Settings
from trading_research.execution.option_trend_exits import open_option_kwargs
from trading_research.live import manual_orders
from trading_research.live.manual_orders import build_manual_order_kwargs, manual_orders_path
from trading_research.live.trade_display import live_spot_and_mark
from trading_research.core_types import LONG, PaperTrade
from trading_research.scanner.base import Candle


def _candles(closes: list[float]) -> list[Candle]:
    out = []
    for i, c in enumerate(closes):
        out.append(
            Candle(
                ts=i * 300,
                open=c - 0.1,
                high=c + 0.5,
                low=c - 0.5,
                close=c,
                volume=1000,
            )
        )
    return out


def test_dynamic_premium_uses_atr_not_fixed_half():
    s = Settings(option_win_use_fixed_premium=False, option_win_premium=0.50)
    closes = [100.0 + i * 0.2 for i in range(40)]
    candles = _candles(closes)
    from trading_research.live.manual_orders import _atr_from_candles

    atr = _atr_from_candles(candles)
    assert atr and atr > 0
    kw = open_option_kwargs(
        action="buy",
        right="call",
        strike=108.0,
        underlying_price=108.0,
        contracts=2,
        reason="test",
        settings=s,
        atr=atr,
    )
    assert kw["premium"] != 0.50
    assert kw["premium"] > 0.05
    assert kw["stop_premium"] < kw["premium"]
    assert "live prem" in kw["reason"]


def test_fixed_premium_when_flag_on():
    s = Settings(option_win_use_fixed_premium=True)
    kw = open_option_kwargs(
        action="buy",
        right="call",
        strike=100.0,
        underlying_price=100.0,
        contracts=2,
        reason="test",
        settings=s,
        atr=2.5,
    )
    assert kw["premium"] == 0.50


def test_dynamic_premium_when_atr_none_uses_spot_fallback():
    s = Settings(option_win_use_fixed_premium=False, option_win_premium=0.50)
    kw = open_option_kwargs(
        action="buy",
        right="call",
        strike=108.0,
        underlying_price=108.0,
        contracts=2,
        reason="test",
        settings=s,
        atr=None,
    )
    assert kw["premium"] != 0.50
    assert kw["premium"] > 0.05
    assert "live prem" in kw["reason"]
    assert "atr $2.1600" in kw["reason"]


def test_build_manual_order_kwargs_without_data_dir_uses_spot_fallback(monkeypatch):
    monkeypatch.setattr(
        "trading_research.config.market_strategy.read_trade_modes_toml",
        lambda: {"crypto_trade_mode": "options", "stock_trade_mode": "options"},
    )
    # Force synthetic ATR path (no live chain) for this unit test.
    monkeypatch.setattr(
        "trading_research.execution.atm_option_quote.fetch_atm_option_quote",
        lambda *a, **k: None,
    )
    s = Settings(option_win_use_fixed_premium=False, option_win_premium=0.50)
    candidate = {
        "symbol": "AAPL",
        "market": "stock",
        "direction": "long",
        "spot": 180.0,
        "pattern": "test",
        "reason": "unit",
    }
    kw = build_manual_order_kwargs(candidate, "buy", settings=s, data_dir=None)
    assert kw["premium"] != 0.50
    assert kw["premium"] > 0.05
    assert "live prem" in kw["reason"]


def test_process_manual_orders_passes_data_dir(monkeypatch, tmp_path):
    captured: dict = {}

    def fake_build(candidate, action, *, settings=None, data_dir=None):
        captured["data_dir"] = data_dir
        raise ValueError("capture_only")

    monkeypatch.setattr(
        "trading_research.config.market_strategy.read_trade_modes_toml",
        lambda: {"crypto_trade_mode": "spot_scalp", "stock_trade_mode": "options"},
    )

    monkeypatch.setattr(manual_orders, "build_manual_trade_payload", fake_build)
    monkeypatch.setattr(manual_orders, "_check_market_gates", lambda *a, **k: None)
    monkeypatch.setattr(manual_orders, "_check_win_prob_gate", lambda *a, **k: None)

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    path = manual_orders_path(data_dir)
    path.write_text(
        json.dumps(
            {
                "orders": [
                    {
                        "status": "pending",
                        "symbol": "BTC-USD",
                        "action": "buy",
                        "spot": 50000.0,
                        "market": "crypto",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    session = MagicMock()
    session.data_dir = data_dir
    session.s = Settings()
    session.candles_by = {}
    session.broker.positions = []

    manual_orders.process_manual_orders(session)
    assert captured["data_dir"] == data_dir


def test_live_spot_and_mark_without_bar_estimates_premium(monkeypatch):
    monkeypatch.setattr(
        "trading_research.live.trade_display._resolve_live_spot",
        lambda trade: 0.0,
    )
    trade = PaperTrade(
        symbol="NEAR-USD",
        market="crypto",
        side=LONG,
        qty=2,
        entry_price=0.50,
        stop=0.33,
        tp1=0.65,
        tp2=0.90,
        kind="option",
        meta={"action": "buy", "right": "put", "underlying": 2.0},
    )
    spot, mark = live_spot_and_mark(trade, bar=None)
    assert spot == 2.0
    assert mark == 0.50
