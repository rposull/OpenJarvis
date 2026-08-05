"""Unified exit engine — stop, partial TP, trailing stop, time exit.

Shared by paper broker and backtester so simulation matches live paper logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from trading_research.config.settings import Settings, get_settings
from trading_research.core_types import LONG, PaperTrade
from trading_research.execution.winner_trail import ratchet_premium_trail, trail_stop_hit


@dataclass
class ExitAction:
    """One exit event (partial or full)."""

    qty_fraction: float   # 0..1 of *remaining* position
    price: float
    reason: str
    move_stop_to: Optional[float] = None
    activate_trailing: bool = False


def _meta(trade: PaperTrade) -> dict:
    return trade.meta


def _qty_remaining(trade: PaperTrade) -> float:
    return float(_meta(trade).get("qty_remaining", trade.qty))


def _stop_grace_bars(trade: PaperTrade, settings: Settings) -> int:
    """Bars to defer hard stop when direction confirmation was strong at entry."""
    meta_grace = trade.meta.get("stop_grace_bars")
    if meta_grace is not None:
        try:
            return max(0, int(meta_grace))
        except (TypeError, ValueError):
            pass
    if not trade.meta.get("direction_confirmed"):
        return 0
    strength = float(trade.meta.get("pattern_strength") or 0)
    if strength < 0.72:
        return 0
    grace = int(getattr(settings, "option_stop_grace_bars", 0) or 0)
    if strength >= 0.78:
        grace += int(getattr(settings, "option_stop_grace_strong_extra", 1) or 1)
    return grace


def _hard_stop_blocked(trade: PaperTrade, settings: Settings) -> bool:
    grace = _stop_grace_bars(trade, settings)
    if grace <= 0:
        return False
    if trade.meta.get("trailing_active"):
        return False
    return int(trade.bars_held or 0) < grace


def _is_micro_premium_option(trade: PaperTrade, settings: Settings) -> bool:
    floor = float(getattr(settings, "option_min_entry_premium", 0) or 0)
    if floor <= 0 or trade.kind != "option":
        return False
    return trade.entry_price <= floor


def _is_stock_option(trade: PaperTrade) -> bool:
    """ETF/equity options — flat_premium bleeds spread/fees; let runners hold."""
    if trade.kind != "option":
        return False
    from trading_research.config.market_strategy import detect_market, is_stock_market

    mkt = trade.market or detect_market(trade.symbol)
    return is_stock_market(mkt)


def _flat_premium_bars(trade: PaperTrade, settings: Settings) -> int:
    if _is_stock_option(trade):
        return 0
    bars = int(getattr(settings, "option_flat_premium_exit_bars", 0) or 0)
    if bars <= 0:
        return 0
    if _is_micro_premium_option(trade, settings):
        return max(4, bars // 2)
    return bars


def _is_losing_mark(trade: PaperTrade, mark: float) -> bool:
    """True when the position is underwater at this mark."""
    entry = trade.entry_price
    if entry <= 0:
        return False
    action = str(_meta(trade).get("action") or ("buy" if trade.side == LONG else "sell")).lower()
    if trade.kind == "option":
        if action == "buy":
            return mark < entry
        return mark > entry
    if trade.side == LONG:
        return mark < entry
    return mark > entry


def is_oj_trade(trade: PaperTrade) -> bool:
    """True for OJ 0DTE Pine paper trades — exits are EOD / SL / TP-break only."""
    m = _meta(trade)
    blob = " ".join(
        str(m.get(k) or "")
        for k in ("oj_strategy", "strategy", "chart_pattern", "entry_source", "entry_reason")
    ).lower()
    return "oj_0dte" in blob or "tradingview_oj" in blob


def _oj_under_level(trade: PaperTrade, key: str) -> Optional[float]:
    m = _meta(trade)
    aliases = {
        "sl": ("oj_underlying_stop", "oj_sl", "sl"),
        "tp1": ("oj_underlying_tp1", "oj_tp1", "tp1"),
        "tp2": ("oj_underlying_tp2", "oj_tp2", "tp2"),
        "tp3": ("oj_underlying_tp3", "oj_tp3", "tp3"),
    }
    for cand in aliases.get(key, (key,)):
        raw = m.get(cand)
        try:
            val = float(raw) if raw is not None else None
        except (TypeError, ValueError):
            val = None
        if val is not None and val > 0:
            return val
    levels = m.get("levels") if isinstance(m.get("levels"), dict) else {}
    lvl_key = "sl" if key == "sl" else key
    try:
        val = float(levels.get(lvl_key)) if levels.get(lvl_key) is not None else None
    except (TypeError, ValueError):
        val = None
    return val if val is not None and val > 0 else None


def _oj_mark_premium(trade: PaperTrade, under: float) -> float:
    from trading_research.execution.option_premium import estimate_premium

    return float(estimate_premium(trade, under))


def _oj_tp_level(trade: PaperTrade, hit: int) -> Optional[float]:
    if hit <= 0:
        return None
    key = {1: "tp1", 2: "tp2", 3: "tp3"}.get(int(hit))
    return _oj_under_level(trade, key) if key else None


def check_oj_underlying_exits(
    trade: PaperTrade,
    *,
    high: float,
    low: float,
    last: float,
    bar_hm: Optional[int] = None,
    settings: Optional[Settings] = None,
) -> List[ExitAction]:
    """OJ Pine exits: hold full size to EOD unless SL or a prior TP is broken.

    TP1/TP2/TP3 are suggestion milestones only — touching them never scales out.
    After a TP has been tagged on a prior bar, a break back through that level
    exits the full position for profit at that TP mark.
    """
    s = settings or get_settings()
    m = _meta(trade)
    right = str(m.get("right") or "call").lower()
    sl = _oj_under_level(trade, "sl")
    tp1 = _oj_under_level(trade, "tp1")
    tp2 = _oj_under_level(trade, "tp2")
    tp3 = _oj_under_level(trade, "tp3")
    if not sl or not tp1:
        return []

    eod_hm = int(getattr(s, "oj_eod_hm", 1545) or 1545)
    if bar_hm is not None and bar_hm >= eod_hm:
        return [ExitAction(1.0, _oj_mark_premium(trade, last), "eod")]

    try:
        prior_hit = int(m.get("oj_tp_hit") or 0)
    except (TypeError, ValueError):
        prior_hit = 0
    prior_hit = max(0, min(3, prior_hit))

    # Break of a previously tagged TP → full profit exit (never same-bar first touch).
    trail = _oj_tp_level(trade, prior_hit)
    if trail is not None:
        broken = (low < trail) if right != "put" else (high > trail)
        if broken:
            return [
                ExitAction(
                    1.0,
                    _oj_mark_premium(trade, trail),
                    f"tp{prior_hit}_break",
                )
            ]

    # Hard stop — only when no TP-break fired.
    if right == "put":
        if high >= sl:
            return [ExitAction(1.0, _oj_mark_premium(trade, sl), "sl")]
    elif low <= sl:
        return [ExitAction(1.0, _oj_mark_premium(trade, sl), "sl")]

    # Tag TP suggestions (no sell).
    hit = prior_hit
    if right == "put":
        if tp3 is not None and low <= tp3:
            hit = 3
        elif tp2 is not None and low <= tp2:
            hit = max(hit, 2)
        elif low <= tp1:
            hit = max(hit, 1)
    else:
        if tp3 is not None and high >= tp3:
            hit = 3
        elif tp2 is not None and high >= tp2:
            hit = max(hit, 2)
        elif high >= tp1:
            hit = max(hit, 1)
    if hit > prior_hit:
        m["oj_tp_hit"] = hit
        if hit >= 1:
            m["tp1_suggest"] = True
        if hit >= 2:
            m["tp2_suggest"] = True
        if hit >= 3:
            m["tp3_suggest"] = True
        if bar_hm is not None:
            m["oj_tp_hit_hm"] = int(bar_hm)
    return []


def init_trade_meta(trade: PaperTrade, settings: Optional[Settings] = None) -> None:
    """Initialize partial/trailing state on open."""
    s = settings or get_settings()
    m = _meta(trade)
    m.setdefault("qty_remaining", trade.qty)
    m.setdefault("tp1_filled", False)
    m.setdefault("oj_tp_hit", 0)
    m.setdefault("trailing_active", False)
    m.setdefault("peak_price", trade.entry_price)
    m.setdefault("trough_price", trade.entry_price)
    m["tp1_exit_pct"] = s.tp1_exit_pct
    m["trail_activate_r"] = s.trail_activate_r
    m["trail_atr_mult"] = s.trail_atr_mult


def update_trailing(
    trade: PaperTrade,
    high: float,
    low: float,
    atr: float,
    settings: Optional[Settings] = None,
) -> None:
    """Ratchet stop once trade is sufficiently profitable."""
    s = settings or get_settings()
    m = _meta(trade)
    entry = trade.entry_price
    risk = abs(entry - trade.stop) or entry * 0.01

    if trade.side == LONG:
        m["peak_price"] = max(float(m.get("peak_price", entry)), high)
        peak = float(m["peak_price"])
        profit_r = (peak - entry) / risk
        if not m.get("trailing_active") and profit_r >= s.trail_activate_r:
            m["trailing_active"] = True
            m["stop_moved_to_be"] = True
            trade.stop = max(trade.stop, entry)
        if m.get("trailing_active") and atr > 0:
            trail = peak - atr * s.trail_atr_mult
            trade.stop = max(trade.stop, trail)
    else:
        m["trough_price"] = min(float(m.get("trough_price", entry)), low)
        trough = float(m["trough_price"])
        profit_r = (entry - trough) / risk
        if not m.get("trailing_active") and profit_r >= s.trail_activate_r:
            m["trailing_active"] = True
            m["stop_moved_to_be"] = True
            trade.stop = min(trade.stop, entry)
        if m.get("trailing_active") and atr > 0:
            trail = trough + atr * s.trail_atr_mult
            trade.stop = min(trade.stop, trail)


def check_exits(
    trade: PaperTrade,
    *,
    high: float,
    low: float,
    last: float,
    atr: float = 0.0,
    settings: Optional[Settings] = None,
    underlying_high: Optional[float] = None,
    underlying_low: Optional[float] = None,
    underlying_last: Optional[float] = None,
    bar_hm: Optional[int] = None,
) -> List[ExitAction]:
    """Return ordered exit actions for this bar (may be empty)."""
    s = settings or get_settings()
    m = _meta(trade)
    actions: List[ExitAction] = []

    # OJ 0DTE: EOD / SL / prior-TP break only — TP touches are suggestions (no scale-out).
    if is_oj_trade(trade):
        u_h = underlying_high
        u_l = underlying_low
        u_c = underlying_last
        if u_h is None or u_l is None or u_c is None:
            return []
        return check_oj_underlying_exits(
            trade,
            high=float(u_h),
            low=float(u_l),
            last=float(u_c),
            bar_hm=bar_hm,
            settings=s,
        )

    # Evaluate exits at the stop in place *before* ratcheting on this bar's high.
    stop = trade.stop
    if trade.side == LONG:
        if low <= stop and not _hard_stop_blocked(trade, s):
            actions.append(ExitAction(1.0, stop, "stop"))
            return actions
        trail_full = bool(getattr(s, "option_trail_full_position", True))
        if not trail_full and not m.get("tp1_filled") and high >= trade.tp1:
            frac = float(m.get("tp1_exit_pct", s.tp1_exit_pct))
            actions.append(
                ExitAction(
                    frac,
                    trade.tp1,
                    "take_profit_1",
                    move_stop_to=trade.entry_price,
                    activate_trailing=True,
                )
            )
            return actions
        if m.get("tp1_filled") and high >= trade.tp2 and not m.get("trailing_active"):
            actions.append(ExitAction(1.0, trade.tp2, "take_profit_2"))
            return actions
    else:
        if high >= stop and not _hard_stop_blocked(trade, s):
            actions.append(ExitAction(1.0, stop, "stop"))
            return actions
        trail_full = bool(getattr(s, "option_trail_full_position", True))
        if not trail_full and not m.get("tp1_filled") and low <= trade.tp1:
            frac = float(m.get("tp1_exit_pct", s.tp1_exit_pct))
            actions.append(
                ExitAction(
                    frac,
                    trade.tp1,
                    "take_profit_1",
                    move_stop_to=trade.entry_price,
                    activate_trailing=True,
                )
            )
            return actions
        if m.get("tp1_filled") and low <= trade.tp2 and not m.get("trailing_active"):
            actions.append(ExitAction(1.0, trade.tp2, "take_profit_2"))
            return actions

    if trade.kind == "option":
        from trading_research.execution.quick_scalp import quick_scalp_partial_action

        scalp_action = quick_scalp_partial_action(trade, last=last, settings=s)
        if scalp_action is not None:
            actions.append(scalp_action)
            return actions

        ratchet_premium_trail(trade, high=high, low=low, last=last, cfg=s)
        if trail_stop_hit(trade, high=high, low=low):
            actions.append(ExitAction(1.0, trade.stop, "trailing_stop"))
            return actions

    flat_bars = _flat_premium_bars(trade, s)
    if (
        flat_bars > 0
        and trade.kind == "option"
        and trade.bars_held >= flat_bars
        and not m.get("trailing_active")
    ):
        entry = trade.entry_price
        if entry > 0:
            band = max(entry * 0.04, 0.02)
            # Flat exit only when mark shows profit — breakeven exits bleed spread/fees.
            action = str(m.get("action") or ("buy" if trade.side == LONG else "sell")).lower()
            if action == "buy":
                mark_profitable = last > entry
            else:
                mark_profitable = last < entry
            if abs(last - entry) <= band and mark_profitable:
                actions.append(ExitAction(1.0, last, "flat_premium"))
                return actions

    loss_cut = int(getattr(s, "option_loss_cut_bars", 8) or 8)
    if (
        not _is_micro_premium_option(trade, s)
        and _is_losing_mark(trade, last)
        and trade.bars_held >= loss_cut
    ):
        actions.append(ExitAction(1.0, last, "loss_cut"))
        return actions

    max_hold = int(m.get("max_hold_bars", s.scalp_max_hold_bars))
    if trade.bars_held >= max_hold and not _is_losing_mark(trade, last):
        actions.append(ExitAction(1.0, last, "time_take"))

    # Ratchet trailing stop for the next bar after exit checks.
    if atr > 0 and not actions:
        update_trailing(trade, high, low, atr, s)

    return actions


def apply_partial(
    trade: PaperTrade,
    action: ExitAction,
) -> Tuple[float, bool]:
    """Apply partial exit; return (closed_qty, is_fully_closed)."""
    m = _meta(trade)
    remaining = _qty_remaining(trade)
    close_qty = remaining * min(1.0, max(0.0, action.qty_fraction))
    if close_qty <= 0:
        return 0.0, False

    m["qty_remaining"] = remaining - close_qty
    if action.reason in ("take_profit_1", "tp1"):
        m["tp1_filled"] = True
    if action.reason in ("take_profit_2", "tp2"):
        m["tp2_filled"] = True
    if action.reason == "quick_scalp_partial":
        m["quick_scalp_filled"] = True
        m["tp1_filled"] = True
    if action.move_stop_to is not None:
        if trade.side == LONG:
            trade.stop = max(trade.stop, action.move_stop_to)
        else:
            trade.stop = min(trade.stop, action.move_stop_to)
    if action.activate_trailing:
        m["trailing_active"] = True

    fully = m["qty_remaining"] <= 1e-12
    if fully:
        m["qty_remaining"] = 0.0
    return close_qty, fully
