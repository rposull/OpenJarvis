"""Map underlying OHLC to option premium marks for paper simulation."""

from __future__ import annotations

from typing import Any, Optional, Tuple

from trading_research.core_types import LONG, PaperTrade

# Cap delta-proxy marks so volatile underlying bars cannot explode replay PnL.
_PREM_FLOOR_MULT = 0.05
_PREM_CEIL_MULT = 3.0


def _clamp_premium(entry_p: float, raw: float) -> float:
    lo = max(0.01, entry_p * _PREM_FLOOR_MULT)
    hi = max(lo, entry_p * _PREM_CEIL_MULT)
    return max(lo, min(hi, raw))


def _underlying_price(data: Any) -> float:
    if isinstance(data, (int, float)):
        return float(data)
    if isinstance(data, dict):
        return float(data.get("last", data.get("close", data.get("price", 0))))
    return float(data.close)


def estimate_premium(trade: PaperTrade, underlying: float) -> float:
    """Delta-proxy premium from underlying move since entry."""
    entry_u = float(trade.meta.get("underlying") or trade.entry_price)
    entry_p = trade.entry_price
    if entry_u <= 0:
        return entry_p
    # ~0.5 delta ATM: 1% underlying ≈ 12% premium change (tunable).
    pct = (underlying - entry_u) / entry_u
    right = trade.meta.get("right", "call")
    action = trade.meta.get("action", "buy")
    if action == "buy" and right == "call":
        return _clamp_premium(entry_p, entry_p * (1.0 + pct * 12.0))
    if action == "buy" and right == "put":
        return _clamp_premium(entry_p, entry_p * (1.0 - pct * 12.0))
    if action == "sell" and right == "call":
        return _clamp_premium(entry_p, entry_p * (1.0 - pct * 12.0))
    if action == "sell" and right == "put":
        return _clamp_premium(entry_p, entry_p * (1.0 + pct * 12.0))
    return entry_p


def option_ohlc_from_bar(trade: PaperTrade, bar: Any) -> Tuple[float, float, float]:
    """Return (high, low, last) premium for this underlying bar."""
    u_high, u_low, u_last = underlying_ohlc_from_bar(bar)
    entry_u = float(trade.meta.get("underlying") or u_last)
    entry_p = trade.entry_price
    right = trade.meta.get("right", "call")
    action = trade.meta.get("action", "buy")

    def _prem(u: float) -> float:
        if entry_u <= 0:
            return entry_p
        pct = (u - entry_u) / entry_u
        if action == "buy" and right == "call":
            return _clamp_premium(entry_p, entry_p * (1.0 + pct * 12.0))
        if action == "buy" and right == "put":
            return _clamp_premium(entry_p, entry_p * (1.0 - pct * 12.0))
        if action == "sell" and right == "call":
            return _clamp_premium(entry_p, entry_p * (1.0 - pct * 12.0))
        return _clamp_premium(entry_p, entry_p * (1.0 + pct * 12.0))

    p_at_high_u = _prem(u_high)
    p_at_low_u = _prem(u_low)
    # Premium high/low must reflect the bar's premium range (puts invert vs underlying).
    prem_high = max(p_at_high_u, p_at_low_u)
    prem_low = min(p_at_high_u, p_at_low_u)
    return prem_high, prem_low, _prem(u_last)


def underlying_ohlc_from_bar(bar: Any) -> Tuple[float, float, float]:
    """Return (high, low, last) underlying from a candle/bar."""
    if isinstance(bar, dict):
        u_high = float(bar.get("high", bar.get("last", 0)))
        u_low = float(bar.get("low", bar.get("last", 0)))
        u_last = _underlying_price(bar)
    else:
        u_high = float(bar.high)
        u_low = float(bar.low)
        u_last = float(bar.close)
    return u_high, u_low, u_last


def bar_hm_ny(bar: Any) -> Optional[int]:
    """HHMM in America/New_York when the bar carries a timestamp; else None."""
    ts = None
    if isinstance(bar, dict):
        ts = bar.get("ts") or bar.get("timestamp") or bar.get("time") or bar.get("t")
    else:
        ts = getattr(bar, "ts", None) or getattr(bar, "timestamp", None) or getattr(bar, "time", None)
    if ts is None:
        return None
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        if isinstance(ts, (int, float)):
            t = float(ts)
            if t > 1e12:
                t /= 1000.0 if t < 1e14 else 1e9
            dt = datetime.fromtimestamp(t, tz=ZoneInfo("America/New_York"))
        else:
            dt = pd_timestamp_to_ny(ts)
        return int(dt.hour * 100 + dt.minute)
    except Exception:
        return None


def pd_timestamp_to_ny(ts: Any):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    if hasattr(ts, "tz_convert"):
        return ts.tz_convert("America/New_York")
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("America/New_York"))
        return ts.astimezone(ZoneInfo("America/New_York"))
    return datetime.fromisoformat(str(ts)).astimezone(ZoneInfo("America/New_York"))
