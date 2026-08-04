"""Phase 7 — Paper broker (PAPER TRADING ONLY).

Simulates an account that opens/closes positions from TradePlans, applies fees
and slippage, enforces risk rules via :class:`RiskManager`, checks stops/take-
profits on each market update, and exposes stats for the dashboard.

There is no network or order-routing code here by design: this broker can NEVER
place a real order.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from trading_research.config.market_strategy import detect_market
from trading_research.config.settings import Settings, get_settings
from trading_research.core_types import LONG, SHORT, PaperTrade, TradePlan
from trading_research.execution.exit_engine import (
    apply_partial,
    check_exits,
    init_trade_meta,
    is_oj_trade,
)
from trading_research.execution.option_premium import (
    bar_hm_ny,
    option_ohlc_from_bar,
    underlying_ohlc_from_bar,
)
from trading_research.execution.risk_manager import AccountState, RiskManager
from trading_research.storage import store


def _ohlc(data: Any) -> Tuple[float, float, float]:
    """Normalise a price update to (high, low, last)."""
    if isinstance(data, (int, float)):
        return float(data), float(data), float(data)
    if isinstance(data, dict):
        last = float(data.get("last", data.get("close", data.get("price"))))
        high = float(data.get("high", last))
        low = float(data.get("low", last))
        return high, low, last
    # Candle-like object.
    return float(data.high), float(data.low), float(data.close)


class PaperBroker:
    """An in-memory paper-trading account."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        *,
        starting_equity: float | None = None,
        spot_fee: float = 0.001,
        slippage: float = 0.0005,
        option_fee_per_contract: float = 0.65,
        risk: Optional[RiskManager] = None,
    ) -> None:
        self.s = settings or get_settings()
        self.s.assert_paper_only()  # hard guard
        self.risk = risk or RiskManager(self.s)
        self.spot_fee = spot_fee
        self.slippage = slippage
        self.option_fee = option_fee_per_contract
        start = (
            starting_equity if starting_equity is not None else self.s.starting_equity
        )
        self.state = AccountState(
            starting_equity=start,
            equity=start,
            cash=start,
        )
        self.positions: Dict[str, PaperTrade] = {}
        self.closed: List[PaperTrade] = []

    # ------------------------------------------------------------------
    def _has_open(self, symbol: str, side: str) -> bool:
        return any(
            t.symbol == symbol and t.side == side for t in self.positions.values()
        )

    def open_from_plan(
        self,
        plan: TradePlan,
        *,
        price: Optional[float] = None,
        log: bool = True,
        ignore_daily_limits: bool = False,
    ) -> Tuple[Optional[PaperTrade], str]:
        """Open a spot/crypto paper position from a TradePlan."""
        self.s.assert_paper_only()
        ok, reason = self.risk.can_open(
            self.state, ignore_daily_limits=ignore_daily_limits
        )
        if not ok:
            return None, reason
        if self.s.never_average_down and self._has_open(plan.symbol, plan.side):
            return None, "never average down (position already open)"

        raw_entry = price if price is not None else plan.entry
        entry = (
            raw_entry * (1 + self.slippage)
            if plan.side == LONG
            else raw_entry * (1 - self.slippage)
        )
        qty = plan.position_size if plan.position_size > 0 else self.risk.position_size(
            self.state.equity, entry, plan.stop, tp1=plan.tp1,
            return_pct=self.state.return_pct,
        )
        if qty <= 0:
            return None, "invalid position size"

        trade = PaperTrade(
            symbol=plan.symbol, market=plan.market, side=plan.side, qty=qty,
            entry_price=entry, stop=plan.stop, tp1=plan.tp1, tp2=plan.tp2,
            kind="spot", entry_reason=plan.reason,
            meta={
                "models": plan.models, "rr": plan.risk_reward,
                "invalidation": plan.invalidation,
                "max_hold_bars": plan.max_hold_bars,
                "profit_target_usd": plan.meta.get("profit_target_usd"),
                "strategy": plan.meta.get("strategy", "multi_model"),
                "ppm_score": plan.meta.get("ppm_score", plan.score),
                "confidence": plan.meta.get("confidence"),
                "confidence_pct": plan.meta.get("confidence_pct"),
                "atr": plan.meta.get("atr"),
            },
        )
        init_trade_meta(trade, self.s)
        self.positions[trade.id] = trade
        self.state.open_trades += 1
        if not ignore_daily_limits:
            self.risk.register_open(self.state)
        if log:
            store.log_trade({"event": "open", **trade.to_dict()}, self.s)
        return trade, "opened"

    def open_option(
        self, *, symbol: str, right: str, strike: float, premium: float,
        underlying_price: float, stop_premium: float, tp_premium: float,
        tp2_premium: float | None = None,
        action: str = "buy",
        contracts: Optional[int] = None, reason: str = "",
        days_to_expiry: Optional[int] = None, atr: float | None = None,
        max_hold_bars: int | None = None, log: bool = True,
        ignore_daily_limits: bool = False,
    ) -> Tuple[Optional[PaperTrade], str]:
        """Open a paper option: buy or sell calls/puts (defined-risk brackets)."""
        self.s.assert_paper_only()
        action = action.lower()
        right = right.lower()
        if action not in ("buy", "sell"):
            return None, f"invalid action {action!r} (use buy or sell)"
        if right not in ("call", "put"):
            return None, f"invalid right {right!r} (use call or put)"
        if premium <= 0:
            return None, "invalid premium"
        ok, reason_gate = self.risk.can_open(
            self.state, ignore_daily_limits=ignore_daily_limits
        )
        if not ok:
            return None, reason_gate
        if contracts is None:
            contracts = self.risk.option_contracts(
                self.state.equity,
                premium,
                stop_premium=stop_premium,
                action=action,
                strike=strike,
                right=right,
                cash=self.state.cash,
            )
        if contracts < 1:
            return None, "position too small for risk budget"

        pos_side = LONG if action == "buy" else SHORT
        if action == "buy":
            max_loss = (premium - stop_premium) * 100 * contracts
        else:
            max_loss = (stop_premium - premium) * 100 * contracts

        tp2 = tp2_premium if tp2_premium is not None else tp_premium
        from trading_research.config.market_strategy import settings_for_market

        mkt = detect_market(symbol)
        sym_s = settings_for_market(self.s, mkt)
        hold_bars = max_hold_bars or sym_s.option_win_max_hold_bars
        trade = PaperTrade(
            symbol=symbol, market=mkt, side=pos_side, qty=contracts,
            entry_price=premium, stop=stop_premium, tp1=tp_premium, tp2=tp2,
            kind="option", entry_reason=reason,
            meta={
                "action": action,
                "right": right,
                "strike": strike,
                "underlying": underlying_price,
                "days_to_expiry": days_to_expiry,
                "max_loss": max_loss,
                "atr": atr,
                "max_hold_bars": hold_bars,
                "strategy": "option_win_2c",
            },
        )
        init_trade_meta(trade, sym_s)
        if sym_s.option_trend_profit_enabled:
            from trading_research.execution.option_trend_exits import trend_exit_pct

            trade.meta["tp1_exit_pct"] = trend_exit_pct(sym_s)
        trade.meta["max_hold_bars"] = hold_bars
        self.positions[trade.id] = trade
        self.state.open_trades += 1
        if not ignore_daily_limits:
            self.risk.register_open(self.state)
        if log:
            store.log_trade({"event": "open", **trade.to_dict()}, self.s)
        return trade, "opened"

    # ------------------------------------------------------------------
    def update(self, prices: Dict[str, Any], *, log: bool = True) -> List[PaperTrade]:
        """Mark-to-market; partial TP, trailing stop, time exit via exit_engine."""
        self.risk.tick(self.state)
        closed_now: List[PaperTrade] = []
        for tid in list(self.positions.keys()):
            t = self.positions.get(tid)
            if t is None or t.symbol not in prices:
                continue
            if t.kind == "option":
                high, low, last = option_ohlc_from_bar(t, prices[t.symbol])
            else:
                high, low, last = _ohlc(prices[t.symbol])
            t.bars_held += 1
            atr = float(t.meta.get("atr") or 0.0)
            from trading_research.config.market_strategy import detect_market, settings_for_market

            exit_settings = settings_for_market(
                self.s, t.market or detect_market(t.symbol)
            )
            u_high = u_low = u_last = None
            hm = None
            if t.kind == "option" and is_oj_trade(t):
                u_high, u_low, u_last = underlying_ohlc_from_bar(prices[t.symbol])
                hm = bar_hm_ny(prices[t.symbol])
                if hm is None:
                    from datetime import datetime
                    from zoneinfo import ZoneInfo

                    now = datetime.now(ZoneInfo("America/New_York"))
                    hm = int(now.hour * 100 + now.minute)
            for action in check_exits(
                t,
                high=high,
                low=low,
                last=last,
                atr=atr,
                settings=exit_settings,
                underlying_high=u_high,
                underlying_low=u_low,
                underlying_last=u_last,
                bar_hm=hm,
            ):
                close_qty, fully = apply_partial(t, action)
                if close_qty <= 0:
                    continue
                pnl = self._leg_pnl(t, action.price, close_qty)
                self.state.equity += pnl
                self.state.cash += pnl
                t.pnl = (t.pnl or 0.0) + pnl
                if log:
                    store.log_trade({
                        "event": "partial" if not fully else "close",
                        "trade_id": t.id,
                        "qty": close_qty,
                        "price": action.price,
                        "reason": action.reason,
                        "pnl_leg": pnl,
                    }, self.s)
                if fully:
                    t.exit_price = action.price
                    t.exit_reason = action.reason
                    from trading_research.live.order_attribution import stamp_exit_channel

                    stamp_exit_channel(t, "session_tick")
                    t.status = "closed"
                    import time as _t
                    t.closed_at = _t.time()
                    self.positions.pop(t.id, None)
                    self.closed.append(t)
                    self.state.open_trades = max(0, self.state.open_trades - 1)
                    self.risk.register_close(self.state, t.pnl)
                    if log:
                        store.log_trade({"event": "close", **t.to_dict()}, self.s)
                    closed_now.append(t)
                    break
        return closed_now

    def _leg_pnl(self, t: PaperTrade, exit_price: float, qty: float) -> float:
        if t.kind == "option":
            if t.side == LONG:
                gross = (exit_price - t.entry_price) * 100.0 * qty
            else:
                gross = (t.entry_price - exit_price) * 100.0 * qty
            fee = self.option_fee * qty
        else:
            if t.side == LONG:
                gross = qty * (exit_price - t.entry_price)
            else:
                gross = qty * (t.entry_price - exit_price)
            fee = self.spot_fee * (qty * t.entry_price + qty * exit_price)
        return gross - fee

    def close_trade(
        self,
        trade_id: str,
        price: float,
        reason: str = "manual",
        *,
        exit_channel: Optional[str] = None,
        log: bool = True,
    ):
        t = self.positions.get(trade_id)
        if t is None:
            return None, "not found"
        self._close(t, price, reason, exit_channel=exit_channel, log=log)
        return t, "closed"

    def _close(
        self,
        t: PaperTrade,
        exit_price: float,
        reason: str,
        *,
        exit_channel: Optional[str] = None,
        log: bool = True,
    ) -> None:
        remaining = float(t.meta.get("qty_remaining", t.qty) or t.qty)
        if t.kind == "option":
            if t.side == LONG:
                gross = (exit_price - t.entry_price) * 100.0 * remaining
            else:
                gross = (t.entry_price - exit_price) * 100.0 * remaining
            fee = self.option_fee * remaining * 2
        else:
            if t.side == LONG:
                gross = t.qty * (exit_price - t.entry_price)
            else:
                gross = t.qty * (t.entry_price - exit_price)
            fee = self.spot_fee * (t.qty * t.entry_price + t.qty * exit_price)
        pnl = gross - fee
        t.exit_price = exit_price
        t.exit_reason = reason
        from trading_research.live.order_attribution import (
            classify_exit_channel,
            stamp_exit_channel,
        )

        stamp_exit_channel(
            t,
            exit_channel or classify_exit_channel(reason, meta=t.meta),
        )
        t.status = "closed"
        t.pnl = (t.pnl or 0.0) + pnl
        t.meta["qty_remaining"] = 0.0
        t.fees = fee
        import time as _t
        t.closed_at = _t.time()
        self.positions.pop(t.id, None)
        self.closed.append(t)
        self.state.open_trades = max(0, self.state.open_trades - 1)
        self.risk.register_close(self.state, pnl)
        if log:
            store.log_trade({"event": "close", **t.to_dict()}, self.s)

    # ------------------------------------------------------------------
    def activate_kill_switch(self, prices: Dict[str, Any]) -> List[PaperTrade]:
        """Emergency stop: flatten everything and block new trades."""
        self.s.kill_switch = True
        flattened: List[PaperTrade] = []
        for tid in list(self.positions.keys()):
            t = self.positions[tid]
            _, _, last = _ohlc(prices.get(t.symbol, t.entry_price))
            self._close(t, last, "kill_switch")
            flattened.append(t)
        return flattened

    def stats(self) -> Dict[str, Any]:
        from trading_research.profit_plan import daily_progress

        st = self.state
        out = {
            "starting_equity": st.starting_equity,
            "equity": round(st.equity, 2),
            "return_pct": round(st.return_pct, 2),
            "open_trades": len(self.positions),
            "total_trades": st.total_trades,
            "wins": st.wins,
            "losses": st.losses,
            "win_rate": round(st.win_rate, 3),
            "max_drawdown": round(st.max_drawdown, 4),
            "daily_pnl": round(st.daily_pnl, 2),
            "kill_switch": self.s.kill_switch,
            "cooldown_ticks": st.cooldown_ticks,
            "paper_trade": self.s.paper_trade,
            "live_trade": self.s.live_trade,
            "require_manual_confirm": self.s.require_manual_confirm,
        }
        out.update(daily_progress(st, self.s))
        return out
