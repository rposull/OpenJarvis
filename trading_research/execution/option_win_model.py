"""Option win model — trend buys/sells with scaled profit along the move.

Buy call on bullish trend, buy put on bearish. When enabled, also sell put on
strong uptrends and sell call on strong downtrends (credit legs). Partial TP
at TP1, trail remainder to TP2 via exit_engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from trading_research.config.settings import Settings, get_settings
from trading_research.core_types import FLAT, LONG, SHORT
from trading_research.execution.option_trend_exits import open_option_kwargs
from trading_research.execution.options import should_use_options
from trading_research.models import indicators as ind


@dataclass
class OptionWinSignal:
    side: str
    symbol: str
    underlying_price: float
    atr: float
    spread_pct: float
    reason: str
    action: str = "buy"
    right: str = "call"


def _trend_scores(
    closes: Sequence[float],
    price: float,
    *,
    settings: Settings,
) -> Tuple[float, float, str]:
    """Score bullish vs bearish trend strength (0..1)."""
    ema9 = ind.last(ind.ema(closes, 9))
    ema21 = ind.last(ind.ema(closes, 21))
    ema50 = ind.last(ind.ema(closes, 50)) if settings.option_trend_use_ema50 else ema21
    if ema9 is None or ema21 is None or ema50 is None:
        return 0.0, 0.0, "missing EMAs"

    bull = 0.0
    bear = 0.0
    if ema9 > ema21:
        bull += 0.35
        if price > ema9:
            bull += 0.35
        elif price > ema21:
            bull += 0.15
        if settings.option_trend_use_ema50 and ema21 > ema50:
            bull += 0.15
    elif ema9 < ema21:
        bear += 0.35
        if price < ema9:
            bear += 0.35
        elif price < ema21:
            bear += 0.15
        if settings.option_trend_use_ema50 and ema21 < ema50:
            bear += 0.15

    # Momentum: last 5 bars vs prior 5
    if len(closes) >= 10:
        recent = sum(closes[-5:]) / 5
        prior = sum(closes[-10:-5]) / 5
        if prior > 0:
            mom = (recent - prior) / prior
            if mom > 0.002:
                bull += min(0.2, mom * 20)
            elif mom < -0.002:
                bear += min(0.2, abs(mom) * 20)

    tag = f"EMA9={ema9:.2f} EMA21={ema21:.2f}"
    return min(1.0, bull), min(1.0, bear), tag


def _leg_bias(action: str, right: str) -> str:
    """Market direction the leg profits from (LONG=up, SHORT=down)."""
    if (action == "buy" and right == "call") or (action == "sell" and right == "put"):
        return LONG
    return SHORT


def _pick_leg(
    bull: float,
    bear: float,
    *,
    settings: Settings,
    relaxed: bool,
    vol_ratio: float,
) -> Tuple[str, str, str]:
    """Return (action, right, reason) for the strongest trend leg."""
    floor = settings.option_trend_min_score
    min_score = floor if not relaxed else max(0.30, floor - 0.06)
    strong = settings.option_trend_strong_score

    if bull >= min_score and bull >= bear:
        if settings.option_trend_allow_sell and bull >= strong and vol_ratio >= 0.9:
            return "sell", "put", "strong uptrend -> sell put (profit on way up)"
        return "buy", "call", "bullish trend -> buy call (profit on way up)"
    if bear >= min_score:
        if settings.option_trend_allow_sell and bear >= strong and vol_ratio >= 0.9:
            return "sell", "call", "strong downtrend -> sell call (profit on way down)"
        return "buy", "put", "bearish trend -> buy put (profit on way down)"
    return "", "", "no trend"


def signal_from_candles(
    symbol: str,
    candles: Sequence,
    *,
    spread_pct: float = 0.005,
    settings: Optional[Settings] = None,
    relaxed: bool = False,
) -> OptionWinSignal:
    """Trend filter for directional option entry (buy and sell legs)."""
    s = settings or get_settings()
    if len(candles) < 30:
        return OptionWinSignal(FLAT, symbol, 0.0, 0.0, spread_pct, "insufficient bars")

    closes = [c.close for c in candles]
    price = closes[-1]
    a = ind.last(ind.atr(candles, 14)) or 0.0
    if a <= 0:
        return OptionWinSignal(FLAT, symbol, price, a, spread_pct, "missing ATR")

    vols = [c.volume for c in candles]
    recent = vols[-2] if len(vols) >= 2 else vols[-1]
    avg = sum(vols[-22:-2]) / 20 if len(vols) >= 22 else sum(vols) / max(1, len(vols))
    vol_ratio = recent / avg if avg > 0 else 1.0
    if s.option_win_volume_ratio > 0 and vol_ratio < s.option_win_volume_ratio:
        return OptionWinSignal(FLAT, symbol, price, a, spread_pct, "low volume")

    bull, bear, ema_tag = _trend_scores(closes, price, settings=s)
    action, right, reason = _pick_leg(
        bull, bear, settings=s, relaxed=relaxed, vol_ratio=vol_ratio
    )
    if not action:
        return OptionWinSignal(FLAT, symbol, price, a, spread_pct, "no trend")

    if s.option_chart_patterns_enabled:
        from trading_research.patterns.chart_patterns import best_pattern

        hit = best_pattern(candles)
        bias = _leg_bias(action, right)
        if hit:
            if hit.direction != bias and hit.strength >= s.option_pattern_block_strength:
                return OptionWinSignal(
                    FLAT, symbol, price, a, spread_pct,
                    f"pattern {hit.name} conflicts with {reason}",
                )
            reason = f"{reason} + {hit.name} ({hit.reason})"
        elif s.option_chart_patterns_required:
            return OptionWinSignal(
                FLAT, symbol, price, a, spread_pct, "no confirming chart pattern",
            )

    side = LONG if action == "buy" else SHORT
    ok, msg = should_use_options(
        directional=True,
        days_to_expiry=s.option_win_days_to_expiry,
        spread_pct=spread_pct,
    )
    if not ok:
        return OptionWinSignal(FLAT, symbol, price, a, spread_pct, msg)

    return OptionWinSignal(
        side, symbol, price, a, spread_pct, f"{reason} ({ema_tag})",
        action=action, right=right,
    )


_REVERSAL_PATTERNS = frozenset({"double_bottom", "double_top"})


def signal_from_pattern(
    symbol: str,
    candles: Sequence,
    *,
    spread_pct: float = 0.005,
    settings: Optional[Settings] = None,
) -> OptionWinSignal:
    """Pattern-first entry on breakouts and reversals (no trend floor required)."""
    s = settings or get_settings()
    if not s.option_chart_patterns_enabled:
        return OptionWinSignal(FLAT, symbol, 0.0, 0.0, spread_pct, "patterns disabled")
    if len(candles) < 30:
        return OptionWinSignal(FLAT, symbol, 0.0, 0.0, spread_pct, "insufficient bars")

    from trading_research.patterns.chart_patterns import best_pattern

    hit = best_pattern(candles)
    min_strength = s.option_live_pattern_min_strength
    if not hit or hit.strength < min_strength:
        return OptionWinSignal(FLAT, symbol, 0.0, 0.0, spread_pct, "no pattern")

    from trading_research.config.market_strategy import pattern_is_allowed

    if not pattern_is_allowed(hit.name, settings=s):
        return OptionWinSignal(
            FLAT, symbol, 0.0, 0.0, spread_pct,
            f"pattern {hit.name} not in allowed list",
        )

    if hit.name == "double_top" and hit.strength < s.double_top_min_strength:
        return OptionWinSignal(
            FLAT, symbol, 0.0, 0.0, spread_pct,
            f"double_top strength {hit.strength:.2f} < {s.double_top_min_strength:.2f}",
        )
    if hit.name == "bear_flag" and hit.strength < s.bear_flag_min_strength:
        return OptionWinSignal(
            FLAT, symbol, 0.0, 0.0, spread_pct,
            f"bear_flag strength {hit.strength:.2f} < {s.bear_flag_min_strength:.2f}",
        )

    closes = [c.close for c in candles]
    price = closes[-1]
    a = ind.last(ind.atr(candles, 14)) or 0.0
    if a <= 0:
        return OptionWinSignal(FLAT, symbol, price, a, spread_pct, "missing ATR")

    vols = [c.volume for c in candles]
    recent = vols[-2] if len(vols) >= 2 else vols[-1]
    avg = sum(vols[-22:-2]) / 20 if len(vols) >= 22 else sum(vols) / max(1, len(vols))
    vol_ratio = recent / avg if avg > 0 else 1.0
    if s.option_win_volume_ratio > 0 and vol_ratio < s.option_win_volume_ratio:
        return OptionWinSignal(FLAT, symbol, price, a, spread_pct, "low volume")

    bull, bear, ema_tag = _trend_scores(closes, price, settings=s)
    if hit.name in _REVERSAL_PATTERNS:
        from trading_research.execution.direction_confirmation import (
            evaluate_direction_confirmation,
        )

        gate_dir = "long" if hit.direction == LONG else "short"
        confirm = evaluate_direction_confirmation(
            symbol=symbol,
            pattern=hit.name,
            direction=gate_dir,
            candles=candles,
            settings=s,
            spread_pct=spread_pct,
            bull=bull,
            bear=bear,
        )
        if not confirm.confirmed:
            return OptionWinSignal(
                FLAT, symbol, price, a, spread_pct, confirm.fail_reason or "not confirmed",
            )
    elif hit.direction == LONG and bear > bull + 0.15 and hit.strength < 0.68:
        return OptionWinSignal(
            FLAT, symbol, price, a, spread_pct, "breakout vs bearish trend",
        )
    elif hit.direction != LONG and bull > bear + 0.15 and hit.strength < 0.68:
        return OptionWinSignal(
            FLAT, symbol, price, a, spread_pct, "breakdown vs bullish trend",
        )

    if hit.direction == LONG:
        action, right = "buy", "call"
        reason = f"pattern {hit.name} ({hit.reason})"
    elif s.option_trend_allow_sell and bear >= s.option_trend_strong_score:
        action, right = "sell", "call"
        reason = f"pattern {hit.name} breakdown ({hit.reason})"
    else:
        action, right = "buy", "put"
        reason = f"pattern {hit.name} ({hit.reason})"

    side = LONG if action == "buy" else SHORT
    ok, msg = should_use_options(
        directional=True,
        days_to_expiry=s.option_win_days_to_expiry,
        spread_pct=spread_pct,
    )
    if not ok:
        return OptionWinSignal(FLAT, symbol, price, a, spread_pct, msg)

    return OptionWinSignal(
        side, symbol, price, a, spread_pct, f"{reason} ({ema_tag})",
        action=action, right=right,
    )


def build_option_win_trade(
    sig: OptionWinSignal,
    *,
    settings: Optional[Settings] = None,
    contracts: Optional[int] = None,
):
    """Return kwargs for ``PaperBroker.open_option``."""
    s = settings or get_settings()
    if sig.side == FLAT:
        return None

    action = sig.action or ("buy" if sig.side == LONG else "sell")
    right = sig.right or ("call" if sig.side == LONG else "put")
    n = contracts or s.option_fixed_contracts

    kw = open_option_kwargs(
        action=action,
        right=right,
        strike=round(sig.underlying_price, 2),
        underlying_price=sig.underlying_price,
        contracts=n,
        reason=f"option_trend_{n}c: {action} {right}",
        settings=s,
        atr=sig.atr,
        symbol=sig.symbol,
        prefer_live_premium=True,
    )
    kw["symbol"] = sig.symbol
    kw["reason"] = sig.reason or kw["reason"]
    return kw
