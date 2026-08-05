"""Strategy engine, market filters, ppm scorer tests."""

from __future__ import annotations

from trading_research.config.settings import Settings
from trading_research.core_types import LONG, RankedAsset, TradePlan
from trading_research.execution.exit_engine import check_exits, init_trade_meta
from trading_research.core_types import PaperTrade
from trading_research.selection.market_filters import evaluate_market_filters
from trading_research.selection.ppm_scorer import score_opportunity
from trading_research.strategy_engine.registry import StrategyRegistry, get_registry
from trading_research.scanner.base import Candle


def _candles(n=80, vol=1000.0, trend=0.02):
    out = []
    p = 100.0
    for i in range(n):
        p += trend
        out.append(Candle(ts=i, open=p, high=p + 0.5, low=p - 0.5, close=p, volume=vol))
    return out


def _ranked(spread=0.001):
    return RankedAsset(
        symbol="BTC-USD", market="crypto", score=0.8, rank=1,
        snapshot={"spread_pct": spread},
        components={"trend": 0.7, "volume": 0.8},
    )


def _plan():
    return TradePlan(
        symbol="BTC-USD", market="crypto", side=LONG,
        entry=100.0, stop=98.0, tp1=103.0, tp2=105.0,
        position_size=10.0, risk_amount=20.0, reward_amount=30.0,
        risk_reward=1.5, max_hold_bars=12, model_agreement=3,
        reason="test", invalidation="stop 98",
    )


def test_registry_toggle():
    reg = StrategyRegistry()
    assert reg.is_enabled("momentum_breakout_scalp")
    reg.set_enabled("momentum_breakout_scalp", False)
    assert not reg.is_enabled("momentum_breakout_scalp")


def test_market_filter_rejects_wide_spread():
    fr = evaluate_market_filters(_ranked(spread=0.05), _candles(), _plan(), settings=Settings())
    assert fr.passed is False
    assert any("spread" in r for r in fr.reasons_fail)


def test_ppm_scorer_returns_positive_score():
    info = score_opportunity(_plan(), _ranked(), _candles(), settings=Settings())
    assert info["ppm_score"] > 0
    assert info["expected_hold_minutes"] > 0


def test_exit_engine_loss_cut_before_max_hold():
    s = Settings(option_loss_cut_bars=8, option_win_max_hold_bars=32)
    t = PaperTrade(
        symbol="X", market="crypto", side=LONG, qty=2,
        entry_price=0.50, stop=0.33, tp1=0.65, tp2=0.90, kind="option",
        meta={"action": "buy", "right": "call", "max_hold_bars": 32},
    )
    init_trade_meta(t, s)
    t.bars_held = 8
    actions = check_exits(t, high=0.49, low=0.48, last=0.48, atr=0.0, settings=s)
    assert len(actions) == 1
    assert actions[0].reason == "loss_cut"


def test_exit_engine_winner_time_take_not_max_hold():
    s = Settings(
        option_loss_cut_bars=8,
        option_win_max_hold_bars=10,
        option_trail_min_upnl_usd=999.0,
    )
    t = PaperTrade(
        symbol="X", market="crypto", side=LONG, qty=2,
        entry_price=0.50, stop=0.33, tp1=0.65, tp2=0.90, kind="option",
        meta={"action": "buy", "right": "put", "max_hold_bars": 10},
    )
    init_trade_meta(t, s)
    t.bars_held = 10
    actions = check_exits(t, high=0.55, low=0.52, last=0.54, atr=0.0, settings=s)
    assert len(actions) == 1
    assert actions[0].reason == "time_take"


def test_exit_engine_oj_skips_time_take_and_loss_cut():
    s = Settings(option_loss_cut_bars=1, option_win_max_hold_bars=1)
    t = PaperTrade(
        symbol="SPY",
        market="stock",
        side=LONG,
        qty=1,
        entry_price=0.76,
        stop=0.38,
        tp1=1.2,
        tp2=1.8,
        kind="option",
        meta={
            "action": "buy",
            "right": "call",
            "oj_strategy": "oj_0dte",
            "underlying": 763.39,
            "oj_underlying_stop": 760.9,
            "oj_underlying_tp1": 764.64,
            "oj_underlying_tp2": 765.88,
            "oj_underlying_tp3": 767.13,
            "max_hold_bars": 1,
        },
    )
    init_trade_meta(t, s)
    t.bars_held = 99
    # Premium path would time_take; OJ without underlying must hold.
    assert check_exits(t, high=0.80, low=0.70, last=0.78, atr=0.0, settings=s) == []
    # Underlying TP1 touch is a suggestion only — no sell.
    actions = check_exits(
        t,
        high=0.80,
        low=0.70,
        last=0.78,
        atr=0.0,
        settings=s,
        underlying_high=765.0,
        underlying_low=763.0,
        underlying_last=764.7,
        bar_hm=1000,
    )
    assert actions == []
    assert int(t.meta.get("oj_tp_hit") or 0) == 1


def test_exit_engine_oj_tp_break_sells_full():
    s = Settings()
    t = PaperTrade(
        symbol="SPY",
        market="stock",
        side=LONG,
        qty=1,
        entry_price=0.76,
        stop=0.38,
        tp1=1.2,
        tp2=1.8,
        kind="option",
        meta={
            "action": "buy",
            "right": "call",
            "oj_strategy": "oj_0dte",
            "underlying": 763.39,
            "oj_underlying_stop": 760.9,
            "oj_underlying_tp1": 764.64,
            "oj_underlying_tp2": 765.88,
            "oj_underlying_tp3": 767.13,
            "oj_tp_hit": 2,
        },
    )
    init_trade_meta(t, s)
    # Prior TP2 tagged; this bar breaks back through TP2 → full profit exit.
    actions = check_exits(
        t,
        high=0.9,
        low=0.7,
        last=0.75,
        atr=0.0,
        settings=s,
        underlying_high=766.0,
        underlying_low=765.5,
        underlying_last=765.6,
        bar_hm=1100,
    )
    assert len(actions) == 1
    assert actions[0].reason == "tp2_break"
    assert actions[0].qty_fraction == 1.0


def test_exit_engine_oj_hold_through_tp_to_eod():
    s = Settings()
    t = PaperTrade(
        symbol="QQQ",
        market="stock",
        side=LONG,
        qty=1,
        entry_price=0.99,
        stop=0.5,
        tp1=1.5,
        tp2=2.0,
        kind="option",
        meta={
            "action": "buy",
            "right": "call",
            "oj_strategy": "oj_0dte",
            "underlying": 713.65,
            "oj_underlying_stop": 710.64,
            "oj_underlying_tp1": 715.16,
            "oj_underlying_tp2": 716.66,
            "oj_underlying_tp3": 718.17,
        },
    )
    init_trade_meta(t, s)
    # Tag TP3 on this bar (no sell even though low is below TP3 — first touch).
    assert (
        check_exits(
            t,
            high=1.0,
            low=0.9,
            last=0.95,
            atr=0.0,
            settings=s,
            underlying_high=720.0,
            underlying_low=717.0,
            underlying_last=719.0,
            bar_hm=1115,
        )
        == []
    )
    assert int(t.meta.get("oj_tp_hit") or 0) == 3
    # Next bar still above TP3 — hold.
    assert (
        check_exits(
            t,
            high=1.1,
            low=1.0,
            last=1.05,
            atr=0.0,
            settings=s,
            underlying_high=722.0,
            underlying_low=719.0,
            underlying_last=721.0,
            bar_hm=1300,
        )
        == []
    )
    # EOD flats full size.
    actions = check_exits(
        t,
        high=1.2,
        low=1.1,
        last=1.15,
        atr=0.0,
        settings=s,
        underlying_high=724.0,
        underlying_low=723.0,
        underlying_last=723.5,
        bar_hm=1545,
    )
    assert len(actions) == 1
    assert actions[0].reason == "eod"


def test_exit_engine_oj_eod_flat():
    s = Settings()
    t = PaperTrade(
        symbol="NVDA",
        market="stock",
        side=LONG,
        qty=1,
        entry_price=0.34,
        stop=0.17,
        tp1=0.5,
        tp2=0.7,
        kind="option",
        meta={
            "action": "buy",
            "right": "put",
            "oj_strategy": "oj_0dte",
            "underlying": 210.0,
            "oj_underlying_stop": 213.3,
            "oj_underlying_tp1": 208.4,
            "oj_underlying_tp2": 206.8,
            "oj_underlying_tp3": 205.1,
        },
    )
    init_trade_meta(t, s)
    actions = check_exits(
        t,
        high=0.4,
        low=0.3,
        last=0.32,
        atr=0.0,
        settings=s,
        underlying_high=212.0,
        underlying_low=210.5,
        underlying_last=211.0,
        bar_hm=1545,
    )
    assert len(actions) == 1
    assert actions[0].reason == "eod"



def test_exit_engine_partial_tp():
    s = Settings(tp1_exit_pct=0.5, option_trail_full_position=False)
    t = PaperTrade(
        symbol="X", market="crypto", side=LONG, qty=10,
        entry_price=100, stop=98, tp1=103, tp2=105,
    )
    init_trade_meta(t, s)
    actions = check_exits(t, high=104, low=99, last=103, atr=1.0, settings=s)
    assert len(actions) == 1
    assert actions[0].reason == "take_profit_1"
    assert actions[0].qty_fraction == 0.5


def test_exit_engine_flat_premium_before_loss_cut():
    s = Settings(
        option_flat_premium_exit_bars=8,
        option_loss_cut_bars=8,
        option_min_entry_premium=0.07,
        option_win_max_hold_bars=99,
        option_trail_min_upnl_usd=999.0,
    )
    t = PaperTrade(
        symbol="X", market="crypto", side=LONG, qty=2,
        entry_price=0.05, stop=0.03, tp1=0.08, tp2=0.10, kind="option",
        meta={"action": "buy", "right": "put", "max_hold_bars": 99},
    )
    init_trade_meta(t, s)
    t.bars_held = 8
    actions = check_exits(t, high=0.054, low=0.051, last=0.052, atr=0.0, settings=s)
    assert len(actions) == 1
    assert actions[0].reason == "flat_premium"


def test_exit_engine_micro_premium_skips_loss_cut():
    s = Settings(
        option_flat_premium_exit_bars=0,
        option_loss_cut_bars=8,
        option_min_entry_premium=0.07,
        option_win_max_hold_bars=99,
        option_trail_min_upnl_usd=999.0,
    )
    t = PaperTrade(
        symbol="X", market="crypto", side=LONG, qty=2,
        entry_price=0.05, stop=0.03, tp1=0.08, tp2=0.10, kind="option",
        meta={"action": "buy", "right": "put", "max_hold_bars": 99},
    )
    init_trade_meta(t, s)
    t.bars_held = 20
    actions = check_exits(t, high=0.052, low=0.048, last=0.049, atr=0.0, settings=s)
    assert actions == []


def test_exit_engine_flat_premium_exit():
    s = Settings(
        option_flat_premium_exit_bars=12,
        option_loss_cut_bars=99,
        option_win_max_hold_bars=99,
        option_trail_min_upnl_usd=999.0,
    )
    t = PaperTrade(
        symbol="X", market="crypto", side=LONG, qty=2,
        entry_price=0.50, stop=0.33, tp1=0.65, tp2=0.90, kind="option",
        meta={"action": "buy", "right": "put", "max_hold_bars": 99},
    )
    init_trade_meta(t, s)
    t.bars_held = 12
    actions = check_exits(t, high=0.512, low=0.508, last=0.51, atr=0.0, settings=s)
    assert len(actions) == 1
    assert actions[0].reason == "flat_premium"


def test_exit_engine_stock_option_skips_flat_premium():
    """ETF/stock options must not flat_premium-exit even when global bars > 0."""
    s = Settings(
        option_flat_premium_exit_bars=8,
        option_loss_cut_bars=99,
        option_win_max_hold_bars=99,
        option_trail_min_upnl_usd=999.0,
    )
    for sym in ("SPY", "QQQ", "NVDA"):
        t = PaperTrade(
            symbol=sym, market="stock", side=LONG, qty=2,
            entry_price=2.50, stop=1.50, tp1=3.50, tp2=4.50, kind="option",
            meta={"action": "buy", "right": "call", "max_hold_bars": 99},
        )
        init_trade_meta(t, s)
        t.bars_held = 12
        actions = check_exits(t, high=2.52, low=2.48, last=2.51, atr=0.0, settings=s)
        assert actions == [], f"{sym} should not flat_premium-exit"


def test_exit_engine_strong_pattern_extra_grace():
    s = Settings(option_stop_grace_bars=3, option_stop_grace_strong_extra=1)
    t = PaperTrade(
        symbol="X", market="crypto", side=LONG, qty=2,
        entry_price=0.50, stop=0.33, tp1=0.65, tp2=0.90, kind="option",
        meta={
            "action": "buy",
            "direction_confirmed": True,
            "pattern_strength": 0.80,
        },
    )
    init_trade_meta(t, s)
    t.bars_held = 3
    actions = check_exits(t, high=0.49, low=0.34, last=0.35, atr=0.0, settings=s)
    assert actions == []
