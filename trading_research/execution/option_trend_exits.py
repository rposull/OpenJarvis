"""Trend-aligned profit brackets for option buys and sells."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from trading_research.config.settings import Settings, get_settings


def stop_premium_for_leg(
    *,
    entry: float,
    action: str,
    stop_frac: float,
) -> float:
    """Premium stop at *stop_frac* adverse move (e.g. 0.35 = 35% loss cap).

    When entry is floored at the $0.05 minimum premium, a naive ``max(0.05, …)``
    clamp pins stop to entry and causes instant stop-outs. Use a minimum risk
    distance so micro-premium trades still have room to reach trail activation.
    """
    action = action.lower()
    entry = float(entry)
    frac_dist = entry * float(stop_frac)
    min_risk = max(0.012, entry * 0.22)
    risk_dist = max(frac_dist, min_risk)
    if action == "buy":
        return round(max(0.01, entry - risk_dist), 2)
    return round(entry + risk_dist, 2)


def buy_profit_brackets(settings: Optional[Settings] = None) -> Tuple[float, float, float, float]:
    """Return entry, stop, tp1, tp2 for debit (buy) option legs."""
    s = settings or get_settings()
    entry = s.option_win_premium
    frac = float(getattr(s, "option_win_stop_frac", 0.35) or 0.35)
    stop = stop_premium_for_leg(entry=entry, action="buy", stop_frac=frac)
    if s.option_trend_profit_enabled:
        tp1 = s.option_win_tp1_premium
        tp2 = s.option_win_tp2_premium
    else:
        tp1 = tp2 = s.option_win_tp_premium
    return entry, stop, tp1, tp2


def sell_profit_brackets(settings: Optional[Settings] = None) -> Tuple[float, float, float, float]:
    """Return entry, stop, tp1, tp2 for credit (sell) option legs."""
    s = settings or get_settings()
    entry = s.option_win_premium
    frac = float(getattr(s, "option_win_stop_frac", 0.35) or 0.35)
    stop = stop_premium_for_leg(entry=entry, action="sell", stop_frac=frac)
    if s.option_trend_profit_enabled:
        tp1 = s.option_win_sell_tp1_premium
        tp2 = s.option_win_sell_tp2_premium
    else:
        tp1 = tp2 = s.option_win_stop_premium
    return entry, stop, tp1, tp2


def trend_exit_pct(settings: Optional[Settings] = None) -> float:
    """Fraction to exit at TP1; remainder trails to TP2."""
    s = settings or get_settings()
    if s.option_trend_profit_enabled:
        return min(1.0, max(0.25, s.tp1_exit_pct))
    return s.tp1_exit_pct


def _scaled_trend_brackets(
    entry: float,
    action: str,
    settings: Settings,
) -> Tuple[float, float, float]:
    """Stop / TP1 / TP2 from dynamic entry, scaled like fixed 0.50 reference tiers."""
    action = action.lower()
    frac = float(getattr(settings, "option_win_stop_frac", 0.35) or 0.35)
    stop = stop_premium_for_leg(entry=entry, action=action, stop_frac=frac)
    ref = max(0.01, float(settings.option_win_premium or 0.50))
    if action == "sell":
        if settings.option_trend_profit_enabled:
            tp1 = round(max(0.05, entry * (settings.option_win_sell_tp1_premium / ref)), 2)
            tp2 = round(max(0.05, entry * (settings.option_win_sell_tp2_premium / ref)), 2)
        else:
            tp1 = tp2 = round(max(0.05, entry * (settings.option_win_stop_premium / ref)), 2)
    else:
        if settings.option_trend_profit_enabled:
            tp1 = round(max(0.05, entry * (settings.option_win_tp1_premium / ref)), 2)
            tp2 = round(max(0.05, entry * (settings.option_win_tp2_premium / ref)), 2)
        else:
            tp1 = tp2 = round(max(0.05, entry * (settings.option_win_tp_premium / ref)), 2)
    return stop, tp1, tp2


def open_option_kwargs(
    *,
    action: str,
    right: str,
    strike: float,
    underlying_price: float,
    contracts: int,
    reason: str,
    settings: Optional[Settings] = None,
    atr: Optional[float] = None,
    symbol: Optional[str] = None,
    prefer_live_premium: bool = True,
) -> Dict[str, Any]:
    """Build ``PaperBroker.open_option`` kwargs with trend profit tiers.

    For stock underlyings, prefers the live ATM chain quote (strike nearest
    spot, mid of bid/ask) when available; otherwise ATR/fixed synthetic.
    """
    from trading_research.config.market_strategy import detect_market, is_stock_market
    from trading_research.execution.atm_option_quote import fetch_atm_option_quote
    from trading_research.execution.options import build_option_order

    s = settings or get_settings()
    action = action.lower()
    right = right.lower()

    live = None
    mkt = detect_market(symbol) if symbol else None
    if prefer_live_premium and symbol and is_stock_market(mkt or "stock"):
        try:
            live = fetch_atm_option_quote(
                symbol,
                right,
                spot=float(underlying_price) if underlying_price else None,
                prefer_0dte=True,
            )
        except Exception:
            live = None

    if live is not None and live.premium > 0:
        entry = float(live.premium)
        stop, tp1, tp2 = _scaled_trend_brackets(entry, action, s)
        return {
            "symbol": None,
            "right": right,
            "action": action,
            "strike": float(live.strike),
            "premium": entry,
            "underlying_price": float(live.underlying or underlying_price),
            "stop_premium": stop,
            "tp_premium": tp1,
            "tp2_premium": tp2,
            "contracts": contracts,
            "days_to_expiry": int(live.days_to_expiry),
            "reason": (
                f"{reason} | ATM {live.right} {live.strike:g} "
                f"prem ${entry:.2f} mid (bid {live.bid:.2f}/ask {live.ask:.2f}) "
                f"exp {live.expiration} · spot ${float(live.underlying or underlying_price):,.4f}"
            ),
            "live_quote": {
                "source": live.source,
                "expiration": live.expiration,
                "bid": live.bid,
                "ask": live.ask,
                "last": live.last,
                "strike": live.strike,
                "premium": entry,
            },
        }

    use_fixed = bool(s.option_win_use_fixed_premium)
    if not use_fixed and underlying_price > 0:
        atr_val = float(atr or 0) or underlying_price * 0.02
        setup = build_option_order(
            action=action,
            right=right,
            underlying_price=underlying_price,
            atr=atr_val,
            stop_frac=float(getattr(s, "option_win_stop_frac", 0.35) or 0.35),
            otm_pct=0.0,
            tp_mult=s.option_win_tp_mult,
        )
        entry = setup.est_premium
        stop, tp1, tp2 = _scaled_trend_brackets(entry, action, s)
        return {
            "symbol": None,
            "right": right,
            "action": action,
            "strike": setup.strike,
            "premium": entry,
            "underlying_price": underlying_price,
            "stop_premium": stop,
            "tp_premium": tp1,
            "tp2_premium": tp2,
            "contracts": contracts,
            "days_to_expiry": s.option_win_days_to_expiry,
            "reason": (
                f"{reason} | live prem ${entry:.2f} "
                f"(spot ${underlying_price:,.4f} atr ${atr_val:.4f})"
            ),
        }

    if action == "sell":
        entry, stop, tp1, tp2 = sell_profit_brackets(s)
    else:
        entry, stop, tp1, tp2 = buy_profit_brackets(s)
    return {
        "symbol": None,  # caller fills
        "right": right,
        "action": action,
        "strike": strike,
        "premium": entry,
        "underlying_price": underlying_price,
        "stop_premium": stop,
        "tp_premium": tp1,
        "tp2_premium": tp2,
        "contracts": contracts,
        "days_to_expiry": s.option_win_days_to_expiry,
        "reason": reason,
    }
