"""Manual paper orders from the Trading UI — PAPER ONLY."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from trading_research.config.market_strategy import (
    count_positions_by_market,
    is_stock_market,
    market_max_open_reason,
    read_chart_strategy_toml,
    read_crypto_strategy_toml,
    read_scout_strategy_toml,
    settings_for_market,
    trade_kind_for_market,
    trade_mode_reject_reason,
    with_broker_max_open,
    stock_symbol_allowed,
    stocks_paused_reason,
    stocks_require_alpaca_quote,
)
from trading_research.config.settings import Settings, get_settings
from trading_research.core_types import TradePlan
from trading_research.execution.option_trend_exits import open_option_kwargs
from trading_research.execution.paper_broker import PaperBroker
from trading_research.execution.spot_scalp import (
    build_spot_scalp_plan,
    spot_max_hold_bars,
    spot_side_from_direction,
)
from trading_research.learning.session_learner import SessionLearner
from trading_research.live.ledger import load_ledger, record_buy, record_sell, save_ledger
from trading_research.live.session_persistence import load_snapshot, restore_session, save_snapshot
from trading_research.live.hot_win_prob import win_prob_gate_reason
from trading_research.live.trade_ledger_sync import sync_trade_ledger_file


def manual_orders_path(data_dir: Path) -> Path:
    return data_dir / "manual_paper_orders.json"


def is_live_session_running(data_dir: Path) -> bool:
    """True when live_session.pid points to a live process."""
    pid_path = data_dir / "live_session.pid"
    if not pid_path.is_file():
        return False
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except ValueError:
        return False
    if sys.platform == "win32":
        r = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        return str(pid) in (r.stdout or "")
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


_STOCK_EXCHANGES = frozenset({"NASDAQ", "NYSE", "AMEX", "OTC", "BATS", "ARCA"})


def infer_market(symbol: str, market: Optional[str] = None) -> str:
    """Classify symbol as stock or crypto for paper orders."""
    raw = (symbol or "").strip().upper()
    # Pair suffix wins over stale PaperTrade.market labels on legacy snapshots.
    if any(raw.endswith(q) for q in ("-USD", "-USDC", "-EUR", "-GBP")):
        return "crypto"
    if ":" in raw:
        exchange = raw.split(":", 1)[0]
        if exchange in _STOCK_EXCHANGES:
            return "stock"
        return "crypto"
    if market:
        m = str(market).lower()
        if m in ("stock", "stocks"):
            return "stock"
        if m == "crypto":
            return "crypto"
    if "-" in raw:
        return "crypto"
    if re.fullmatch(r"[A-Z]{1,5}", raw):
        return "stock"
    return "crypto"


def normalize_internal_symbol(symbol: str, market: Optional[str] = None) -> str:
    """Map TradingView tickers to internal paper-trade symbols."""
    raw = (symbol or "").strip().upper()
    mkt = infer_market(raw, market)
    if ":" in raw:
        return raw.split(":", 1)[1]
    if mkt == "stock":
        return raw
    return raw


def resolve_spot_price(
    symbol: str,
    market: str,
    price: Optional[float] = None,
    *,
    settings: Optional[Settings] = None,
) -> float:
    """Use alert/UI price, Alpaca quote for stocks, or a safe fallback."""
    if price is not None and float(price) > 0:
        return float(price)
    mkt = (market or "crypto").lower()
    internal = normalize_internal_symbol(symbol, mkt)
    if mkt == "stock":
        from trading_research.live.stock_quotes import fetch_stock_price

        quote = fetch_stock_price(internal, settings=settings)
        if quote and quote > 0:
            return quote
        s = settings or get_settings()
        if s.has_alpaca_credentials():
            raise ValueError(
                f"Alpaca quote unavailable for stock {internal} (no $100 fallback when keys are set)"
            )
        if stocks_require_alpaca_quote():
            raise ValueError(
                f"Alpaca quote unavailable for stock {internal}; set APCA_API_KEY_ID / APCA_API_SECRET_KEY"
            )
        try:
            from trading_research.jarvis_locked import read_strategy_toml

            if bool((read_strategy_toml().get("live_pricing") or {}).get("require_live_quote")):
                return 0.0
        except Exception:
            pass
        return 100.0
    from trading_research.live.crypto_quotes import resolve_crypto_spot

    live = resolve_crypto_spot(internal, candidate_spot=price, settings=settings)
    if live and live > 0:
        return live
    try:
        from trading_research.jarvis_locked import read_strategy_toml

        if bool((read_strategy_toml().get("live_pricing") or {}).get("require_live_quote")):
            return 0.0
    except Exception:
        pass
    return 1.0


def leg_from_hot(direction: str, action: str) -> Tuple[str, str]:
    """Map scanner direction + UI action to option leg (action, right)."""
    direction = (direction or "long").lower()
    action = (action or "buy").lower()
    if direction in ("long", "bullish", "up"):
        return ("buy", "call") if action == "buy" else ("sell", "put")
    return ("buy", "put") if action == "buy" else ("sell", "call")


def _base_asset(symbol: str) -> str:
    sym = (symbol or "").strip().upper()
    for q in ("-USDC", "-USD", "-EUR", "-GBP"):
        if sym.endswith(q):
            return sym[: -len(q)]
    return sym


def dedupe_setups_by_base(setups: List[Dict]) -> List[Dict]:
    """Keep highest-confidence setup per base asset (e.g. BTC-USD vs BTC-USDC).

    Callers should sort by confidence descending first; first row per base wins.
    """
    seen: set[str] = set()
    out: List[Dict] = []
    for setup in setups:
        sym = str(setup.get("symbol") or "").strip().upper()
        if not sym:
            continue
        base = _base_asset(sym)
        if base in seen:
            continue
        seen.add(base)
        out.append(setup)
    return out


def prune_stale_failed_orders(data_dir: Path, *, max_age_hours: float = 24.0) -> int:
    """Remove failed manual orders older than max_age_hours. Returns count pruned."""
    path = manual_orders_path(data_dir)
    if not path.is_file():
        return 0
    orders = _load_queue(path)
    if not orders:
        return 0
    cutoff = time.time() - max_age_hours * 3600.0
    kept: List[Dict[str, Any]] = []
    pruned = 0
    for order in orders:
        if order.get("status") == "failed":
            ts = float(order.get("created_at") or order.get("failed_at") or 0)
            if ts > 0 and ts < cutoff:
                pruned += 1
                continue
        kept.append(order)
    if pruned:
        _save_queue(path, kept)
    return pruned


def _scout_confidence_pct(candidate: Mapping[str, Any]) -> Optional[float]:
    raw = candidate.get("scout_confidence")
    if raw is None:
        raw = candidate.get("confidence")
    if raw is None:
        return None
    val = float(raw)
    return val * 100.0 if val <= 1.0 else val


def is_news_scout_setup(setup: Mapping[str, Any]) -> bool:
    """True for headlines from news_media_scout (not chart pattern scouts)."""
    kind = str(setup.get("kind") or "").lower()
    agent = str(setup.get("scout_agent") or setup.get("source") or "").lower()
    return kind == "news" or agent == "news_media_scout"


def build_scout_candidate(setup: Dict[str, Any]) -> Dict[str, Any]:
    """Map a market_scout_feed setup row to a paper-order candidate."""
    from trading_research.learning.model_store import load_model_learning
    from trading_research.learning.trade_outcome_learning import apply_learned_flip_to_setup

    news_row = is_news_scout_setup(setup)
    if news_row:
        setup = dict(setup)
        setup["direction"] = "long"
    else:
        setup = apply_learned_flip_to_setup(setup, load_model_learning())
    sym = str(setup.get("symbol") or "").strip().upper()
    direction = str(setup.get("direction") or "long").lower()
    conf = float(setup.get("confidence") or 0.0)
    spot = float(setup.get("spot") or 0.0)
    pattern = str(setup.get("pattern") or "scout_setup")
    mkt = infer_market(sym, setup.get("market"))
    row: Dict[str, Any] = {
        "symbol": sym,
        "direction": direction,
        "pattern": pattern,
        "spot": spot,
        "spot_fmt": setup.get("spot_fmt") or "",
        "reason": str(setup.get("label") or "market scout setup"),
        "market": mkt,
        "scout_confidence": conf,
        "confidence": conf,
        "strength": conf,
        "tools": list(setup.get("tools") or []),
    }
    for key in (
        "conviction_pct",
        "chart_tools",
        "sr_context",
        "fvg_context",
        "repeat_score",
        "has_sr",
        "has_fvg",
        "has_fib",
        "fib_context",
        "win_rate_prior",
        "symbol_math",
        "symbol_math_score",
        "symbol_math_pass",
    ):
        if setup.get(key) is not None:
            row[key] = setup[key]
    return row


def find_hot_candidate(symbol: str, data_dir: Path) -> Optional[Dict[str, Any]]:
    hot_path = data_dir / "breakout_hot.json"
    if not hot_path.is_file():
        return None
    try:
        data = json.loads(hot_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    sym_u = symbol.upper()
    for row in data.get("candidates") or []:
        if str(row.get("symbol", "")).upper() == sym_u:
            return dict(row)
    return None


def build_alert_candidate(
    symbol: str,
    *,
    market: str = "crypto",
    price: Optional[float] = None,
    direction: str = "long",
    tradingview_symbol: str = "",
    settings: Optional[Settings] = None,
    pattern: str = "tradingview_alert",
    entry_kind: str = "",
) -> Dict[str, Any]:
    """Synthetic scanner row for TradingView alerts outside the hot list."""
    sym = normalize_internal_symbol(symbol, market)
    mkt = infer_market(symbol, market)
    spot = resolve_spot_price(sym, mkt, price, settings=settings)
    pat = (pattern or "tradingview_alert").strip() or "tradingview_alert"
    reason = f"TradingView alert {tradingview_symbol or sym}"
    if entry_kind:
        reason = f"{reason} ({entry_kind})"
    return {
        "symbol": sym,
        "direction": direction,
        "pattern": pat,
        "spot": spot,
        "spot_fmt": f"${spot:,.2f}" if mkt == "stock" else f"{spot:.6f}",
        "reason": reason,
        "market": mkt,
        "entry_kind": entry_kind or "",
    }


def resolve_order_candidate(
    symbol: str,
    data_dir: Path,
    *,
    market: str = "crypto",
    price: Optional[float] = None,
    direction: str = "long",
    tradingview_symbol: str = "",
    settings: Optional[Settings] = None,
    pattern: Optional[str] = None,
    entry_kind: str = "",
) -> Dict[str, Any]:
    """Hot scanner row if available, else synthetic alert candidate."""
    internal = normalize_internal_symbol(symbol, market)
    # Trusted OJ / TV indicator entries should not inherit unrelated hot-list rows.
    if pattern in ("oj_0dte", "tradingview_oj"):
        return build_alert_candidate(
            internal,
            market=market,
            price=price,
            direction=direction,
            tradingview_symbol=tradingview_symbol,
            settings=settings,
            pattern=pattern or "oj_0dte",
            entry_kind=entry_kind,
        )
    found = find_hot_candidate(internal, data_dir) or find_hot_candidate(symbol, data_dir)
    if found:
        return found
    return build_alert_candidate(
        internal,
        market=market,
        price=price,
        direction=direction,
        tradingview_symbol=tradingview_symbol,
        settings=settings,
        pattern=pattern or "tradingview_alert",
        entry_kind=entry_kind,
    )


def _atr_from_candles(candles: list) -> Optional[float]:
    if len(candles) < 20:
        return None
    from trading_research.models import indicators as ind

    series = ind.atr(candles)
    val = ind.last(series)
    return float(val) if val and val > 0 else None


def _atr_for_entry(
    *,
    spot: float,
    candles: list,
    symbol: str,
    settings: Settings,
    data_dir: Path,
) -> float:
    """ATR from history when available; else quick live fetch or spot proxy."""
    atr_val = _atr_from_candles(candles)
    if atr_val and atr_val > 0:
        return atr_val
    if len(candles) < 20:
        try:
            from trading_research.scanner.base import HttpClient
            from trading_research.scanner.candle_provider import fetch_crypto_candles
            from trading_research.scanner.market_scanner import bar_seconds

            http = HttpClient()
            gran = settings.crypto_candle_granularity
            secs = bar_seconds(gran)
            quick = fetch_crypto_candles(
                settings,
                http,
                symbol,
                gran=gran,
                end=int(__import__("time").time()),
                total_bars=40,
                secs=secs,
            )
            atr_val = _atr_from_candles(quick)
            if atr_val and atr_val > 0:
                return atr_val
        except Exception:
            pass
    return max(spot * 0.02, 0.05)


def build_manual_spot_plan(
    candidate: Dict[str, Any],
    action: str,
    *,
    settings: Optional[Settings] = None,
    data_dir: Optional[Path] = None,
) -> TradePlan:
    """Build a spot scalp TradePlan from a hot/scout candidate (crypto only)."""
    s = settings or get_settings()
    s.assert_paper_only()
    sym = str(candidate.get("symbol") or "").strip().upper()
    mkt = candidate.get("market") or infer_market(sym)
    reject = trade_mode_reject_reason(mkt, "spot")
    if reject:
        raise ValueError(reject)
    direction = str(candidate.get("direction") or "long")
    side = spot_side_from_direction(direction, action)
    spot = resolve_spot_price(
        sym,
        mkt,
        float(candidate.get("spot") or 0) or None,
        settings=s,
    )
    if spot <= 0:
        raise ValueError("candidate missing spot price")

    atr_val: Optional[float] = None
    if data_dir is not None:
        from trading_research.execution.entry_bar_meta import load_candles_for_symbol

        candles = load_candles_for_symbol(sym, data_dir=Path(data_dir))
        atr_val = _atr_for_entry(
            spot=spot,
            candles=candles,
            symbol=sym,
            settings=s,
            data_dir=Path(data_dir),
        )
        if str(mkt).lower() in ("crypto",):
            from trading_research.live.crypto_quotes import fetch_crypto_spot

            live = fetch_crypto_spot(sym, settings=s)
            if live and live > 0:
                spot = live
            elif candles:
                spot = float(candles[-1].close)
    elif spot > 0:
        atr_val = max(spot * 0.02, 0.05)

    pattern = candidate.get("pattern") or "pattern"
    reason = f"manual_spot_{side}: {pattern} ({candidate.get('reason', '')})"
    crypto_cfg = read_crypto_strategy_toml()
    hold = spot_max_hold_bars(s, crypto_cfg=crypto_cfg)
    return build_spot_scalp_plan(
        symbol=sym,
        side=side,
        entry=spot,
        atr=atr_val or max(spot * 0.02, 0.05),
        settings=s,
        reason=reason,
        max_hold_bars=hold,
        meta={
            "chart_pattern": pattern,
            "market": mkt,
            "confidence": candidate.get("scout_confidence") or candidate.get("confidence"),
            "confidence_pct": candidate.get("scout_confidence") or candidate.get("confidence"),
        },
    )


def build_manual_order_kwargs(
    candidate: Dict[str, Any],
    action: str,
    *,
    settings: Optional[Settings] = None,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Build PaperBroker.open_option kwargs from a hot/scout candidate."""
    s = settings or get_settings()
    s.assert_paper_only()
    sym = str(candidate.get("symbol") or "").strip().upper()
    mkt = candidate.get("market") or infer_market(sym)
    reject = trade_mode_reject_reason(mkt, "option")
    if reject:
        raise ValueError(reject)
    direction = str(candidate.get("direction") or "long")
    leg_action, right = leg_from_hot(direction, action)
    spot = resolve_spot_price(
        sym,
        mkt,
        float(candidate.get("spot") or 0) or None,
        settings=s,
    )
    if spot <= 0:
        raise ValueError("candidate missing spot price")

    atr_val: Optional[float] = None
    candles: list = []
    if data_dir is not None:
        from trading_research.execution.entry_bar_meta import load_candles_for_symbol

        candles = load_candles_for_symbol(sym, data_dir=Path(data_dir))
        atr_val = _atr_for_entry(
            spot=spot,
            candles=candles,
            symbol=sym,
            settings=s,
            data_dir=Path(data_dir),
        )
        if str(mkt).lower() in ("crypto",):
            from trading_research.live.crypto_quotes import fetch_crypto_spot

            live = fetch_crypto_spot(sym, settings=s)
            if live and live > 0:
                spot = live
            elif candles:
                spot = float(candles[-1].close)
    elif spot > 0:
        atr_val = max(spot * 0.02, 0.05)

    pattern = candidate.get("pattern") or "pattern"
    reason = f"manual_{leg_action}_{right}: {pattern} ({candidate.get('reason', '')})"
    kw = open_option_kwargs(
        action=leg_action,
        right=right,
        strike=round(spot, 2),
        underlying_price=spot,
        contracts=s.option_fixed_contracts,
        reason=reason,
        settings=s,
        atr=atr_val,
        symbol=sym,
        prefer_live_premium=True,
    )
    kw["symbol"] = sym
    kw["chart_pattern"] = str(pattern)
    if atr_val:
        kw["atr"] = atr_val
    try:
        from trading_research.live.symbol_setup_gate import evaluate_symbol_setup

        if candidate.get("symbol_math"):
            kw["symbol_math"] = dict(candidate["symbol_math"])
        else:
            ev = evaluate_symbol_setup(candidate, data_dir=Path(data_dir) if data_dir else None)
            if ev.get("symbol_math"):
                kw["symbol_math"] = dict(ev["symbol_math"])
            if ev.get("score") is not None:
                kw["symbol_math_score"] = ev["score"]
    except Exception:
        pass
    return kw


def build_manual_trade_payload(
    candidate: Dict[str, Any],
    action: str,
    *,
    settings: Optional[Settings] = None,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Return ``{kind, plan|option}`` routed by configured market trade mode."""
    sym = str(candidate.get("symbol") or "").strip().upper()
    mkt = candidate.get("market") or infer_market(sym)
    kind = trade_kind_for_market(mkt)
    if kind == "spot":
        return {
            "kind": "spot",
            "plan": build_manual_spot_plan(
                candidate, action, settings=settings, data_dir=data_dir
            ),
        }
    return {
        "kind": "option",
        "option": build_manual_order_kwargs(
            candidate, action, settings=settings, data_dir=data_dir
        ),
    }


def open_manual_trade(
    broker: PaperBroker,
    payload: Mapping[str, Any],
    *,
    candles: Optional[list] = None,
    ignore_daily_limits: bool = True,
) -> Tuple[Optional[Any], str]:
    """Open a manual paper trade from a build_manual_trade_payload result."""
    kind = str(payload.get("kind") or "")
    if kind == "spot":
        plan = payload.get("plan")
        if not isinstance(plan, TradePlan):
            return None, "invalid spot plan"
        if candles:
            from trading_research.execution.entry_bar_meta import pre_entry_instant_stop_reason_spot

            stop_reason = pre_entry_instant_stop_reason_spot(plan, candles)
            if stop_reason:
                return None, stop_reason
        trade, msg = broker.open_from_plan(
            plan,
            log=True,
            ignore_daily_limits=ignore_daily_limits,
        )
        if trade:
            from trading_research.live.order_attribution import stamp_entry_source

            src = str((plan.meta or {}).get("entry_source") or "ui_hot_symbol")
            stamp_entry_source(trade, src)
        return trade, msg
    kw = payload.get("option")
    if not isinstance(kw, dict):
        return None, "invalid option kwargs"
    if candles:
        from trading_research.execution.entry_bar_meta import (
            pre_entry_instant_stop_reason,
            pre_entry_micro_premium_reason,
        )

        pattern = str(kw.get("chart_pattern") or "")
        if not pattern:
            reason = str(kw.get("reason") or "").lower()
            for pat in (
                "scout_setup",
                "double_top breakdown",
                "double_top",
                "range_breakout_up",
                "range_breakout_down",
            ):
                if pat in reason:
                    pattern = pat
                    break
        micro = pre_entry_micro_premium_reason(
            float(kw.get("premium") or 0),
            settings=broker.s,
            pattern=pattern or None,
            right=str(kw.get("right") or ""),
        )
        if micro:
            return None, micro
        stop_reason = pre_entry_instant_stop_reason(kw, candles)
        if stop_reason:
            return None, stop_reason
    extra_meta = {
        k: kw.pop(k)
        for k in list(kw.keys())
        if k in ("symbol_math", "symbol_math_score", "chart_pattern", "live_quote")
    }
    trade, msg = broker.open_option(**kw, log=True, ignore_daily_limits=ignore_daily_limits)
    if trade:
        from trading_research.live.order_attribution import stamp_entry_source

        src = str(kw.get("entry_source") or kw.get("manual_source") or "unknown")
        stamp_entry_source(trade, src)
        if extra_meta.get("symbol_math"):
            trade.meta["symbol_math"] = extra_meta["symbol_math"]
        if extra_meta.get("symbol_math_score") is not None:
            trade.meta["symbol_math_score"] = extra_meta["symbol_math_score"]
        if extra_meta.get("chart_pattern"):
            trade.meta["chart_pattern"] = extra_meta["chart_pattern"]
        live_q = extra_meta.get("live_quote")
        if isinstance(live_q, dict):
            trade.meta["live_quote"] = live_q
            trade.meta["premium_source"] = "atm_chain"
            if live_q.get("expiration"):
                trade.meta["option_expiration"] = live_q["expiration"]
    return trade, msg


def _load_queue(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data.get("orders") or [])
    except Exception:
        return []


def _save_queue(path: Path, orders: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"updated_at": time.time(), "orders": orders}, indent=2),
        encoding="utf-8",
    )


def _market_settings(
    settings: Settings,
    candidate: Optional[Dict[str, Any]] = None,
    market: Optional[str] = None,
) -> Settings:
    mkt = market or (candidate or {}).get("market") or "crypto"
    return settings_for_market(settings, mkt)


def execute_min_win_prob_pct(
    settings: Settings,
    market: Optional[str] = None,
    *,
    data_dir: Optional[Path] = None,
) -> float:
    """Effective min win-probability entry floor (toml + trade-starvation adaptation)."""
    eff = settings_for_market(settings, market)
    base = float(getattr(eff, "min_win_prob_pct", 0) or 0)
    if data_dir is None:
        return base
    from trading_research.live.trade_adaptation import compute_effective_gates

    gates = compute_effective_gates(data_dir, settings=settings, base_min_win_prob=base)
    return gates.min_win_prob_pct


def _count_open_by_market(data_dir: Path) -> Dict[str, int]:
    counts = {"crypto": 0, "stocks": 0}
    snap_path = data_dir / "live_session_snapshot.json"
    if snap_path.is_file():
        try:
            snap = json.loads(snap_path.read_text(encoding="utf-8"))
            for pos in snap.get("positions") or []:
                mkt = infer_market(str(pos.get("symbol") or ""))
                key = "stocks" if mkt == "stock" else "crypto"
                counts[key] += 1
            return counts
        except Exception:
            pass
    ledger_path = data_dir / "live_trade_ledger.json"
    if ledger_path.is_file():
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            for trade in ledger.get("trades") or []:
                if (trade.get("status") or "").upper() != "OPEN":
                    continue
                mkt = infer_market(str(trade.get("symbol") or ""))
                key = "stocks" if mkt == "stock" else "crypto"
                counts[key] += 1
        except Exception:
            pass
    return counts


def _resolve_entry_contracts(broker: PaperBroker, settings: Settings) -> int:
    """WR scale + equity milestones for scout/manual entries."""
    from trading_research.execution.equity_scale import apply_equity_scale_to_contracts
    from trading_research.execution.option_scale import option_scale_decision

    scale = option_scale_decision(broker.closed, settings)
    n, _ = apply_equity_scale_to_contracts(scale.contracts, broker.state, settings)
    return max(1, int(n))


def _check_equity_deploy_gate(
    *,
    settings: Settings,
    equity: float,
    payload: Mapping[str, Any],
    data_dir: Optional[Path] = None,
    positions: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    from trading_research.execution.equity_deploy import (
        equity_deploy_gate_reason,
        order_cost_from_payload,
    )

    return equity_deploy_gate_reason(
        settings=settings,
        equity=equity,
        new_cost_usd=order_cost_from_payload(payload),
        positions=positions,
        data_dir=data_dir,
    )


def _check_market_gates(
    symbol: str,
    market: Optional[str],
    *,
    settings: Optional[Settings] = None,
    data_dir: Optional[Path] = None,
    positions: Optional[Dict[str, Any]] = None,
    trade_kind: Optional[str] = None,
) -> Optional[str]:
    if is_stock_market(market):
        paused = stocks_paused_reason(market)
        if paused:
            return paused
        ok, reason = stock_symbol_allowed(symbol, market)
        if not ok:
            return reason
    kind = trade_kind or trade_kind_for_market(market)
    reject = trade_mode_reject_reason(market, kind)
    if reject:
        return reject
    s = settings or get_settings()
    open_counts: Dict[str, int]
    if positions is not None:
        open_counts = count_positions_by_market(positions)
    elif data_dir is not None:
        open_counts = _count_open_by_market(data_dir)
    else:
        open_counts = {"crypto": 0, "stocks": 0}
    return market_max_open_reason(market, open_counts, settings=s)


def _check_stock_gates(
    symbol: str,
    market: Optional[str],
    *,
    settings: Optional[Settings] = None,
    data_dir: Optional[Path] = None,
    positions: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Backward-compatible alias for per-market gate checks."""
    return _check_market_gates(
        symbol,
        market,
        settings=settings,
        data_dir=data_dir,
        positions=positions,
    )


def _chart_conviction_gate_reason(
    candidate: Mapping[str, Any],
    *,
    data_dir: Optional[Path] = None,
    settings: Optional[Settings] = None,
) -> Optional[str]:
    """Reject scout setups below chart conviction / structure strategy."""
    if candidate.get("skip_chart_conviction") or candidate.get("indicator_only"):
        from trading_research.config.market_strategy import indicator_auto_config

        if not indicator_auto_config().get("require_chart_conviction", False):
            return None
    from trading_research.analysis.chart_conviction import (
        chart_setup_gate_reason,
        refresh_setup_conviction_from_backfill,
    )
    from trading_research.learning.model_store import load_model_learning

    chart_cfg = read_chart_strategy_toml()
    if not chart_cfg.get("enabled", True):
        return None
    row = dict(candidate)
    if chart_cfg.get("conviction_from_backfill_only", True) and data_dir is not None:
        row, reject = refresh_setup_conviction_from_backfill(
            row,
            data_dir,
            model_learning=load_model_learning(settings),
            chart_cfg=chart_cfg,
            settings=settings,
        )
        if reject:
            return reject
    if data_dir is not None:
        from trading_research.live.trade_adaptation import compute_effective_gates

        min_conv = compute_effective_gates(data_dir, settings=settings).min_conviction_pct
    else:
        min_conv = float(chart_cfg.get("min_conviction_pct", 72) or 72)
    return chart_setup_gate_reason(row, chart_cfg, min_conviction_pct=min_conv)


def _stamp_nautilus_meta(trade, row: Mapping[str, Any]) -> None:
    nb = row.get("nautilus_backtest")
    if isinstance(nb, dict) and nb:
        trade.meta["nautilus_backtest"] = dict(nb)
    if row.get("nautilus_strategy"):
        trade.meta["nautilus_strategy"] = row.get("nautilus_strategy")


def _check_nautilus_backtest_gate(
    candidate: Mapping[str, Any],
    *,
    data_dir: Optional[Path] = None,
) -> Optional[str]:
    """Require passing Nautilus backtest before crypto scout / manual entries."""
    sym = str(candidate.get("symbol") or "").strip().upper()
    genius_reject = _check_genius_playbook_gate(sym, data_dir=data_dir)
    if genius_reject:
        return genius_reject
    try:
        from trading_research.nautilus.backtest_gate import (
            load_nautilus_gate_config,
            nautilus_gate_reason,
        )

        return nautilus_gate_reason(candidate, data_dir=data_dir)
    except Exception as exc:
        from trading_research.nautilus.backtest_gate import load_nautilus_gate_config

        if load_nautilus_gate_config().get("block_on_backtest_error"):
            return f"nautilus gate unavailable: {exc}"
        return None


def _check_genius_playbook_gate(
    symbol: str,
    *,
    data_dir: Optional[Path] = None,
) -> Optional[str]:
    try:
        from trading_research.live.genius_playbook import genius_playbook_gate_reason

        return genius_playbook_gate_reason(symbol, data_dir=data_dir)
    except Exception:
        return None


def _check_symbol_setup_gate(
    candidate: Mapping[str, Any],
    *,
    data_dir: Optional[Path] = None,
) -> Optional[str]:
    try:
        from trading_research.live.symbol_setup_gate import symbol_setup_gate_reason

        return symbol_setup_gate_reason(candidate, data_dir=data_dir)
    except Exception:
        return None


def _scout_win_prob_gate_reason(
    candidate: Mapping[str, Any],
    *,
    threshold_pct: float,
    min_confidence_pct: float,
    data_dir: Optional[Path] = None,
    settings: Optional[Settings] = None,
) -> Optional[str]:
    """Use scout confidence as win_prob when scout feed orders are enabled."""
    chart_reject = _chart_conviction_gate_reason(
        candidate, data_dir=data_dir, settings=settings,
    )
    if chart_reject:
        return chart_reject
    conf_pct = _scout_confidence_pct(candidate)
    if conf_pct is None:
        return None
    if conf_pct < min_confidence_pct:
        sym = candidate.get("symbol") or "?"
        return (
            f"scout confidence {conf_pct:.1f}% < min scout {min_confidence_pct:.0f}% "
            f"for {sym}"
        )
    if threshold_pct <= 0 or conf_pct >= threshold_pct:
        return None
    sym = candidate.get("symbol") or "?"
    return f"scout confidence {conf_pct:.1f}% < min {threshold_pct:.0f}% for {sym}"


def _check_win_prob_gate(
    candidate: Dict[str, Any],
    *,
    settings: Settings,
    learner: Optional[SessionLearner] = None,
    market: Optional[str] = None,
    source: Optional[str] = None,
    data_dir: Optional[Path] = None,
) -> Optional[str]:
    eff = _market_settings(settings, candidate, market)
    threshold = execute_min_win_prob_pct(eff, market, data_dir=data_dir)
    scout_cfg = read_scout_strategy_toml()
    if (
        source == "market_scout_feed"
        and scout_cfg.get("allow_scout_feed_orders", False)
        and _scout_confidence_pct(candidate) is not None
    ):
        if data_dir is not None:
            from trading_research.live.trade_adaptation import compute_effective_gates

            gates = compute_effective_gates(data_dir, settings=settings, base_min_win_prob=threshold)
            min_conf = gates.min_scout_confidence_pct
            threshold = gates.min_win_prob_pct
        else:
            min_conf = float(scout_cfg.get("min_confidence_pct", 75) or 75)
        return _scout_win_prob_gate_reason(
            candidate,
            threshold_pct=threshold,
            min_confidence_pct=min_conf,
            data_dir=data_dir,
            settings=settings,
        )
    if threshold <= 0:
        return None
    ctx = None
    if learner is not None:
        ctx = {
            "session_blocklist": list(learner.session_blocklist),
            "notes": list(learner.notes),
        }
    return win_prob_gate_reason(
        candidate,
        threshold_pct=threshold,
        learner=ctx,
        settings=eff,
    )


def enqueue_manual_order(
    symbol: str,
    action: str,
    *,
    settings: Optional[Settings] = None,
    source: str = "ui_hot_symbol",
    candidate: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Queue a manual paper order (processed by live session or standalone executor)."""
    s = settings or get_settings()
    s.assert_paper_only()
    data_dir = Path(s.data_dir)
    row = candidate or resolve_order_candidate(symbol, data_dir, settings=s)
    if not row:
        return {"ok": False, "error": f"could not resolve paper order for {symbol}"}

    from trading_research.analysis.order_flow import enrich_candidate_order_flow

    row = enrich_candidate_order_flow(row, settings=s)

    stock_reject = _check_stock_gates(
        str(row.get("symbol") or symbol), row.get("market"), settings=s, data_dir=data_dir,
    )
    if stock_reject:
        return {"ok": False, "error": stock_reject, "status": "rejected"}

    block_reject = _check_session_block(str(row.get("symbol") or symbol), s, data_dir)
    if block_reject:
        return {"ok": False, "error": block_reject, "status": "rejected"}

    repeat_reject = _check_symbol_repeat_gate(
        str(row.get("symbol") or symbol), data_dir, candidate=row
    )
    if repeat_reject:
        return {"ok": False, "error": repeat_reject, "status": "rejected"}

    pattern_reject = _check_pattern_leg_gate(row)
    if pattern_reject:
        return {"ok": False, "error": pattern_reject, "status": "rejected"}

    confirm_reject = _check_direction_confirmation(row, settings=s, data_dir=data_dir)
    if confirm_reject:
        return {"ok": False, "error": confirm_reject, "status": "rejected"}

    premium_reject = _check_min_premium_gate(row, action, settings=s, data_dir=data_dir)
    if premium_reject:
        return {"ok": False, "error": premium_reject, "status": "rejected"}

    nautilus_reject = _check_nautilus_backtest_gate(row, data_dir=data_dir)
    if nautilus_reject:
        return {"ok": False, "error": nautilus_reject, "status": "rejected"}

    flow_reject = _check_order_flow_gate(row, settings=s)
    if flow_reject:
        return {"ok": False, "error": flow_reject, "status": "rejected"}

    reject = _check_win_prob_gate(
        row,
        settings=s,
        market=row.get("market"),
        source=source,
        data_dir=data_dir,
    )
    if reject:
        return {"ok": False, "error": reject, "status": "rejected"}

    order = {
        "id": f"manual-{int(time.time() * 1000)}",
        "symbol": row["symbol"],
        "action": action.lower(),
        "direction": row.get("direction"),
        "pattern": row.get("pattern"),
        "spot": row.get("spot"),
        "market": row.get("market"),
        "scout_confidence": row.get("scout_confidence") or row.get("confidence"),
        "order_flow": row.get("order_flow"),
        "source": source,
        "status": "pending",
        "created_at": time.time(),
    }
    path = manual_orders_path(data_dir)
    orders = _load_queue(path)
    orders.append(order)
    _save_queue(path, orders[-50:])
    return {"ok": True, "queued": True, "order": order}


class _ManualSessionStub:
    """Minimal session object for snapshot restore + save."""

    def __init__(self, settings: Settings, broker: PaperBroker) -> None:
        self.s = settings
        self.broker = broker
        self.session = SessionLearner(settings)
        self._started_at = time.time()
        self._bootstrapped = True
        self.last_bar_ts: Dict[str, int] = {}


def execute_manual_order_now(
    symbol: str,
    action: str,
    *,
    settings: Optional[Settings] = None,
    source: str = "ui_hot_symbol",
    candidate: Optional[Dict[str, Any]] = None,
    contracts: Optional[int] = None,
    market: Optional[str] = None,
    price: Optional[float] = None,
    tradingview_symbol: str = "",
    direction: Optional[str] = None,
    bypass_gates: bool = False,
) -> Dict[str, Any]:
    """Open a paper option immediately when no live session is running.

    When ``bypass_gates`` is set (e.g. a trusted TradingView indicator webhook),
    the pre-entry gate chain is skipped so the incoming buy/sell signal fills
    directly. PAPER ONLY; the broker/ledger safeguards still apply.
    """
    s = settings or get_settings()
    s.assert_paper_only()
    data_dir = Path(s.data_dir)
    mkt = infer_market(symbol, market)
    internal = normalize_internal_symbol(symbol, mkt)
    row = candidate or resolve_order_candidate(
        internal,
        data_dir,
        market=mkt,
        price=price,
        direction=direction or ("long" if action == "buy" else "short"),
        tradingview_symbol=tradingview_symbol or symbol,
        settings=s,
    )
    if not row:
        return {"ok": False, "error": f"could not resolve paper order for {symbol}"}

    ok_sym, sym_reason = stock_symbol_allowed(
        str(row.get("symbol") or internal),
        row.get("market") or mkt,
    )
    if not ok_sym:
        return {"ok": False, "error": sym_reason, "status": "rejected"}

    # Live session owns the book — queue so process_manual_orders fills it.
    if is_live_session_running(data_dir):
        order = {
            "id": f"manual-{int(time.time() * 1000)}",
            "symbol": row.get("symbol") or internal,
            "action": action.lower(),
            "direction": row.get("direction") or direction or "long",
            "pattern": row.get("pattern") or "manual",
            "spot": row.get("spot") or price,
            "market": row.get("market") or mkt,
            "source": source,
            "bypass_gates": bool(bypass_gates),
            "contracts": contracts,
            "status": "pending",
            "created_at": time.time(),
        }
        path = manual_orders_path(data_dir)
        q = _load_queue(path)
        q.append(order)
        _save_queue(path, q[-50:])
        return {
            "ok": True,
            "queued": True,
            "status": "queued",
            "message": f"Queued {action} for live session on {order['symbol']}",
            "order": order,
        }

    if not bypass_gates:
        news_reject = _check_news_calls_only_gate(row, candidate=row)
        if news_reject:
            return {"ok": False, "error": news_reject, "status": "rejected"}

        stock_reject = _check_stock_gates(internal, mkt, settings=s, data_dir=data_dir)
        if stock_reject:
            return {"ok": False, "error": stock_reject, "status": "rejected"}

        block_reject = _check_session_block(internal, s, data_dir)
        if block_reject:
            return {"ok": False, "error": block_reject, "status": "rejected"}

        pattern_reject = _check_pattern_leg_gate(row, settings=s)
        if pattern_reject:
            return {"ok": False, "error": pattern_reject, "status": "rejected"}

        confirm_reject = _check_direction_confirmation(row, settings=s, data_dir=data_dir)
        if confirm_reject:
            return {"ok": False, "error": confirm_reject, "status": "rejected"}

        premium_reject = _check_min_premium_gate(row, action, settings=s, data_dir=data_dir)
        if premium_reject:
            return {"ok": False, "error": premium_reject, "status": "rejected"}

        nautilus_reject = _check_nautilus_backtest_gate(row, data_dir=data_dir)
        if nautilus_reject:
            return {"ok": False, "error": nautilus_reject, "status": "rejected"}

        flow_reject = _check_order_flow_gate(row, settings=s)
        if flow_reject:
            return {"ok": False, "error": flow_reject, "status": "rejected"}

        reject = _check_win_prob_gate(
            row, settings=s, market=mkt, source=source, data_dir=data_dir,
        )
        if reject:
            return {"ok": False, "error": reject, "status": "rejected"}

    ledger = load_ledger(s)
    broker = PaperBroker(with_broker_max_open(s), starting_equity=ledger.starting_equity)
    stub = _ManualSessionStub(s, broker)
    snap = load_snapshot(s)
    if snap and (snap.get("positions") or snap.get("closed")):
        restore_session(stub, snap)
        broker.state.equity = max(broker.state.equity, ledger.equity)
        broker.state.cash = broker.state.equity

    try:
        payload = build_manual_trade_payload(row, action, settings=s, data_dir=data_dir)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    if contracts is None and payload.get("kind") == "option":
        contracts = _resolve_entry_contracts(broker, s)
    if contracts is not None and payload.get("kind") == "option":
        payload["option"]["contracts"] = contracts

    if not bypass_gates:
        deploy_reject = _check_equity_deploy_gate(
            settings=s,
            equity=ledger.equity,
            payload=payload,
            data_dir=data_dir,
            positions=broker.positions,
        )
        if deploy_reject:
            return {"ok": False, "error": deploy_reject, "status": "rejected"}

    from trading_research.execution.entry_bar_meta import (
        load_candles_for_symbol,
        stamp_entry_bar_meta,
    )

    candles = load_candles_for_symbol(internal, data_dir=data_dir)
    trade, msg = open_manual_trade(broker, payload, candles=candles, ignore_daily_limits=bypass_gates)
    if not trade:
        return {"ok": False, "error": msg or "broker rejected order"}

    stamp_entry_bar_meta(trade, candles)
    trade.meta["entry_live_ts"] = time.time()
    trade.meta["entry_day"] = time.strftime("%Y-%m-%d", time.gmtime())
    trade.meta["chart_pattern"] = row.get("pattern") or ""
    if bypass_gates:
        trade.meta["gates_bypassed"] = True
    from trading_research.live.order_attribution import stamp_entry_source

    stamp_entry_source(trade, source)
    if row.get("market"):
        trade.meta["market"] = row["market"]
    _stamp_nautilus_meta(trade, row)

    record_buy(ledger, trade.to_dict(), ts=time.time())
    save_snapshot(stub)
    save_ledger(ledger, s)
    sync_trade_ledger_file(s)

    if trade.kind == "spot":
        leg = f"{trade.side} spot"
    else:
        leg_action, right = leg_from_hot(str(row.get("direction") or "long"), action)
        leg = f"{leg_action} {right}"
    return {
        "ok": True,
        "executed": True,
        "mode": "PAPER_ONLY",
        "trade_kind": trade.kind,
        "message": f"Paper {leg} opened on {trade.symbol}",
        "trade_id": trade.id,
        "symbol": trade.symbol,
        "leg": leg,
    }


def submit_manual_paper_order(
    symbol: str,
    action: str,
    *,
    settings: Optional[Settings] = None,
    source: str = "ui_hot_symbol",
    market: Optional[str] = None,
    price: Optional[float] = None,
    tradingview_symbol: str = "",
    direction: Optional[str] = None,
    candidate: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Queue for live session, or execute immediately if session is offline."""
    s = settings or get_settings()
    s.assert_paper_only()
    data_dir = Path(s.data_dir)
    mkt = infer_market(symbol, market)
    internal = normalize_internal_symbol(symbol, mkt)
    dir_ = direction or ("long" if action == "buy" else "short")
    row = candidate or resolve_order_candidate(
        internal,
        data_dir,
        market=mkt,
        price=price,
        direction=dir_,
        tradingview_symbol=tradingview_symbol or symbol,
        settings=s,
    )

    stock_reject = _check_stock_gates(internal, mkt, settings=s, data_dir=data_dir)
    if stock_reject:
        return {"ok": False, "error": stock_reject, "status": "rejected"}

    block_reject = _check_session_block(internal, s, data_dir)
    if block_reject:
        return {"ok": False, "error": block_reject, "status": "rejected"}

    pattern_reject = _check_pattern_leg_gate(row, settings=s)
    if pattern_reject:
        return {"ok": False, "error": pattern_reject, "status": "rejected"}

    confirm_reject = _check_direction_confirmation(row, settings=s, data_dir=data_dir)
    if confirm_reject:
        return {"ok": False, "error": confirm_reject, "status": "rejected"}

    sym_math_reject = _check_symbol_setup_gate(row, data_dir=data_dir)
    if sym_math_reject:
        return {"ok": False, "error": sym_math_reject, "status": "rejected"}

    premium_reject = _check_min_premium_gate(row, action, settings=s, data_dir=data_dir)
    if premium_reject:
        return {"ok": False, "error": premium_reject, "status": "rejected"}

    nautilus_reject = _check_nautilus_backtest_gate(row, data_dir=data_dir)
    if nautilus_reject:
        return {"ok": False, "error": nautilus_reject, "status": "rejected"}

    flow_reject = _check_order_flow_gate(row, settings=s)
    if flow_reject:
        return {"ok": False, "error": flow_reject, "status": "rejected"}

    reject = _check_win_prob_gate(
        row, settings=s, market=mkt, source=source, data_dir=data_dir,
    )
    if reject:
        return {"ok": False, "error": reject, "status": "rejected"}

    try:
        payload = build_manual_trade_payload(
            row, action, settings=s, data_dir=data_dir,
        )
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "status": "rejected"}

    from trading_research.live.ledger import load_ledger as _load_ledger

    _ledger = _load_ledger(s)
    deploy_reject = _check_equity_deploy_gate(
        settings=s,
        equity=_ledger.equity,
        payload=payload,
        data_dir=data_dir,
    )
    if deploy_reject:
        return {"ok": False, "error": deploy_reject, "status": "rejected"}

    result = execute_manual_order_now(
        internal,
        action,
        settings=s,
        source=source,
        candidate=row,
        market=mkt,
        price=price,
        tradingview_symbol=tradingview_symbol or symbol,
        direction=dir_,
    )
    if result.get("ok"):
        result["status"] = "executed"
        result["message"] = result.get("message") or f"Paper {action} opened on {internal}"
    else:
        result["status"] = "rejected"
    return result


def submit_tradingview_paper_order(
    symbol: str,
    action: str,
    *,
    market: str = "crypto",
    price: Optional[float] = None,
    direction: str = "long",
    tradingview_symbol: str = "",
    contracts: Optional[int] = None,
    settings: Optional[Settings] = None,
    source: str = "tradingview_webhook",
    bypass_gates: bool = False,
    pattern: Optional[str] = None,
    levels: Optional[Mapping[str, Any]] = None,
    entry_kind: Optional[str] = None,
) -> Dict[str, Any]:
    """Paper order from a TradingView alert (hot list optional).

    When ``bypass_gates`` is set (trusted indicator mode), Jarvis's entry gates
    are skipped and the alert's buy/sell fills directly at the alert price.
    Stock ``symbol_whitelist`` still applies (universe filter, not a soft gate).

    If a live session is running, the order is queued for that session's broker
    so the in-memory book owns the fill (avoids snapshot clobber races).
    """
    s = settings or get_settings()
    s.assert_paper_only()
    data_dir = Path(s.data_dir)
    candidate = resolve_order_candidate(
        symbol,
        data_dir,
        market=market,
        price=price,
        direction=direction,
        tradingview_symbol=tradingview_symbol,
        settings=s,
        pattern=pattern,
        entry_kind=entry_kind or "",
    )

    # Universe filter always on — trust_indicator must not open non-whitelist names.
    ok_sym, sym_reason = stock_symbol_allowed(
        str(candidate.get("symbol") or symbol),
        candidate.get("market") or market,
    )
    if not ok_sym:
        return {"ok": False, "error": sym_reason, "status": "rejected"}

    if not bypass_gates:
        stock_reject = _check_stock_gates(symbol, market, settings=s, data_dir=data_dir)
        if stock_reject:
            return {"ok": False, "error": stock_reject, "status": "rejected"}

        block_reject = _check_session_block(
            str(candidate.get("symbol") or symbol), s, data_dir,
        )
        if block_reject:
            return {"ok": False, "error": block_reject, "status": "rejected"}

        reject = _check_win_prob_gate(
            candidate,
            settings=s,
            market=candidate.get("market") or market,
            source=source,
            data_dir=data_dir,
        )
        if reject:
            return {"ok": False, "error": reject, "status": "rejected"}

        try:
            payload = build_manual_trade_payload(
                candidate, action, settings=s, data_dir=data_dir,
            )
        except ValueError as exc:
            return {"ok": False, "error": str(exc), "status": "rejected"}

        from trading_research.live.ledger import load_ledger

        ledger = load_ledger(s)
        deploy_reject = _check_equity_deploy_gate(
            settings=s,
            equity=ledger.equity,
            payload=payload,
            data_dir=data_dir,
        )
        if deploy_reject:
            return {"ok": False, "error": deploy_reject, "status": "rejected"}

    # Live session owns the book — queue instead of writing a parallel snapshot.
    if is_live_session_running(data_dir):
        order = {
            "id": f"tv-{int(time.time() * 1000)}",
            "symbol": candidate.get("symbol") or symbol,
            "action": action.lower(),
            "direction": direction,
            "pattern": candidate.get("pattern") or pattern or "tradingview_alert",
            "spot": candidate.get("spot") or price,
            "market": candidate.get("market") or market,
            "source": source,
            "bypass_gates": bool(bypass_gates),
            "contracts": contracts,
            "levels": dict(levels) if levels else None,
            "entry_kind": entry_kind or "",
            "tradingview_symbol": tradingview_symbol,
            "status": "pending",
            "created_at": time.time(),
        }
        path = manual_orders_path(data_dir)
        orders = _load_queue(path)
        orders.append(order)
        _save_queue(path, orders[-50:])
        return {
            "ok": True,
            "status": "queued",
            "queued": True,
            "message": f"Queued {action} for live session on {order['symbol']}",
            "order": order,
        }

    result = execute_manual_order_now(
        symbol,
        action,
        settings=s,
        source=source,
        candidate=candidate,
        contracts=contracts,
        market=market,
        price=price,
        tradingview_symbol=tradingview_symbol,
        direction=direction,
        bypass_gates=bypass_gates,
    )
    if result.get("ok") and levels:
        try:
            _stamp_oj_levels_on_open_trade(
                symbol=str(result.get("symbol") or symbol),
                trade_id=str(result.get("trade_id") or ""),
                levels=levels,
                settings=s,
            )
        except Exception:
            pass
    if result.get("ok"):
        result["status"] = "executed"
    else:
        result["status"] = "rejected"
    return result


def _stamp_oj_levels_on_open_trade(
    *,
    symbol: str,
    trade_id: str,
    levels: Mapping[str, Any],
    settings: Settings,
) -> None:
    """Persist Pine SL/TP levels onto the open trade meta for the exit engine."""
    from trading_research.execution.paper_broker import PaperBroker
    from trading_research.config.market_strategy import with_broker_max_open
    from trading_research.live.ledger import load_ledger
    from trading_research.live.session_persistence import load_snapshot, restore_session, save_snapshot

    snap = load_snapshot(settings)
    if not snap or not snap.get("positions"):
        return
    ledger = load_ledger(settings)
    broker = PaperBroker(with_broker_max_open(settings), starting_equity=ledger.starting_equity)
    stub = _ManualSessionStub(settings, broker)
    restore_session(stub, snap)
    trade = None
    if trade_id and trade_id in broker.positions:
        trade = broker.positions[trade_id]
    else:
        for t in broker.positions.values():
            if str(t.symbol).upper() == str(symbol).upper():
                trade = t
                break
    if trade is None:
        return
    meta = trade.meta
    meta["oj_strategy"] = "oj_0dte"
    for key in ("sl", "tp1", "tp2", "tp3"):
        raw = levels.get(key)
        try:
            val = float(raw) if raw is not None else None
        except (TypeError, ValueError):
            val = None
        if val is not None and val > 0:
            meta[f"oj_{key}"] = val
            # Underlying reference levels — option exit engine still uses premium marks.
            if key == "sl":
                meta["oj_underlying_stop"] = val
            elif key == "tp1":
                meta["oj_underlying_tp1"] = val
            elif key == "tp2":
                meta["oj_underlying_tp2"] = val
            elif key == "tp3":
                meta["oj_underlying_tp3"] = val
    save_snapshot(stub)


def close_tradingview_paper_position(
    symbol: str,
    *,
    reason: str = "oj_close",
    qty_fraction: float = 1.0,
    price: Optional[float] = None,
    settings: Optional[Settings] = None,
    source: str = "oj_0dte_pine",
) -> Dict[str, Any]:
    """Close (or scale out of) open paper positions for ``symbol`` from a TV exit alert."""
    s = settings or get_settings()
    s.assert_paper_only()
    data_dir = Path(s.data_dir)
    sym = normalize_internal_symbol(symbol, infer_market(symbol))
    frac = min(1.0, max(0.0, float(qty_fraction or 0.0)))
    if frac <= 0:
        return {"ok": False, "status": "rejected", "error": "qty_fraction must be > 0"}

    # Live session owns the book — queue the close onto that process.
    if is_live_session_running(data_dir):
        order = {
            "id": f"tv-close-{int(time.time() * 1000)}",
            "symbol": sym,
            "action": "close",
            "event": reason.replace("oj_", "") if reason.startswith("oj_") else reason,
            "reason": reason,
            "qty_fraction": frac,
            "spot": price,
            "price": price,
            "source": source,
            "status": "pending",
            "created_at": time.time(),
        }
        path = manual_orders_path(data_dir)
        orders = _load_queue(path)
        orders.append(order)
        _save_queue(path, orders[-50:])
        return {
            "ok": True,
            "status": "queued",
            "queued": True,
            "symbol": sym,
            "reason": reason,
            "qty_fraction": frac,
            "message": f"Queued close for live session on {sym}",
            "source": source,
        }

    from trading_research.config.market_strategy import with_broker_max_open
    from trading_research.execution.exit_engine import ExitAction, apply_partial
    from trading_research.execution.option_premium import estimate_premium
    from trading_research.execution.paper_broker import PaperBroker
    from trading_research.live.ledger import load_ledger, save_ledger
    from trading_research.live.session_persistence import load_snapshot, restore_session, save_snapshot
    from trading_research.live.trade_ledger_sync import sync_trade_ledger_file

    snap = load_snapshot(s)
    if not snap or not snap.get("positions"):
        return {
            "ok": True,
            "status": "executed",
            "closed": 0,
            "message": f"no open positions for {sym}",
            "source": source,
        }

    ledger = load_ledger(s)
    broker = PaperBroker(with_broker_max_open(s), starting_equity=ledger.starting_equity)
    stub = _ManualSessionStub(s, broker)
    restore_session(stub, snap)
    broker.state.equity = max(broker.state.equity, ledger.equity)
    broker.state.cash = broker.state.equity

    targets = [
        t for t in list(broker.positions.values())
        if str(t.symbol).upper() == sym.upper()
    ]
    if not targets:
        return {
            "ok": True,
            "status": "executed",
            "closed": 0,
            "message": f"no open positions for {sym}",
            "source": source,
        }

    closed_ids: list[str] = []
    partials = 0
    for trade in targets:
        spot = float(price or 0.0)
        if spot <= 0:
            spot = resolve_spot_price(sym, infer_market(sym), None, settings=s)
        if trade.kind == "option" and spot > 0:
            mark = float(estimate_premium(trade, spot))
        else:
            mark = spot if spot > 0 else float(trade.entry_price or 0.0)
        if mark <= 0:
            continue

        if frac >= 0.999:
            closed, _msg = broker.close_trade(
                trade.id, mark, reason, exit_channel=source, log=True,
            )
            if closed:
                record_sell(ledger, closed.to_dict(), ts=time.time(), equity=ledger.equity)
                broker.state.equity = ledger.equity
                broker.state.cash = ledger.equity
                closed_ids.append(trade.id)
            continue

        action = ExitAction(qty_fraction=frac, price=mark, reason=reason)
        close_qty, fully = apply_partial(trade, action)
        if close_qty <= 0:
            continue
        pnl = broker._leg_pnl(trade, mark, close_qty)
        broker.state.equity += pnl
        broker.state.cash += pnl
        trade.pnl = (trade.pnl or 0.0) + pnl
        partials += 1
        if fully:
            trade.exit_price = mark
            trade.exit_reason = reason
            from trading_research.live.order_attribution import stamp_exit_channel

            stamp_exit_channel(trade, source)
            trade.status = "closed"
            trade.closed_at = time.time()
            broker.positions.pop(trade.id, None)
            broker.closed.append(trade)
            broker.state.open_trades = max(0, broker.state.open_trades - 1)
            broker.risk.register_close(broker.state, trade.pnl or 0.0)
            record_sell(ledger, trade.to_dict(), ts=time.time(), equity=ledger.equity)
            broker.state.equity = ledger.equity
            broker.state.cash = ledger.equity
            closed_ids.append(trade.id)

    save_snapshot(stub)
    save_ledger(ledger, s)
    sync_trade_ledger_file(s)
    return {
        "ok": True,
        "status": "executed",
        "closed": len(closed_ids),
        "partials": partials,
        "symbol": sym,
        "reason": reason,
        "qty_fraction": frac,
        "message": (
            f"Closed {len(closed_ids)} / scaled {partials} on {sym} ({reason})"
            if (closed_ids or partials)
            else f"no fillable positions for {sym}"
        ),
        "source": source,
    }


def submit_alpaca_paper_order(
    symbol: str,
    action: str,
    *,
    market: str = "stock",
    price: Optional[float] = None,
    notional_usd: float = 2000.0,
    settings: Optional[Settings] = None,
    source: str = "tradingview_webhook",
) -> Dict[str, Any]:
    """Route a TradingView buy/sell straight to the Alpaca PAPER account.

    Places a market order for ~``notional_usd`` worth of the symbol. Stocks use
    integer share qty (so a sell can open a short); crypto uses fractional qty
    and can only go long / flatten (Alpaca does not allow crypto shorting).
    """
    s = settings or get_settings()
    s.assert_paper_only()
    try:
        from trading_research.broker.alpaca_client import (
            AlpacaClient,
            to_alpaca_crypto_symbol,
        )
    except Exception as exc:  # pragma: no cover - import guard
        return {"ok": False, "status": "rejected", "error": f"alpaca sdk unavailable: {exc}"}

    client = AlpacaClient(settings=s)
    try:
        if not client.configured:
            return {
                "ok": False,
                "status": "rejected",
                "error": "Alpaca API keys not configured (~/.openjarvis/alpaca-keys.txt lines 2-3)",
            }
        if not bool(getattr(s, "alpaca_orders_enabled", False)):
            return {
                "ok": False,
                "status": "rejected",
                "error": "Alpaca paper orders disabled (set [alpaca] orders_enabled = true)",
            }

        is_crypto = str(market or "").lower().startswith("crypto")
        side = "buy" if action == "buy" else "sell"

        px = float(price) if price else None
        if not px or px <= 0:
            px = (
                client.latest_crypto_price(symbol)
                if is_crypto
                else client.latest_price(symbol)
            )
        if not px or px <= 0:
            return {
                "ok": False,
                "status": "rejected",
                "error": f"no live price for {symbol} to size Alpaca order",
            }

        notional = max(1.0, float(notional_usd or 0) or 2000.0)
        if is_crypto:
            sym = to_alpaca_crypto_symbol(symbol)
            tif = "gtc"
            qty = round(max(0.0001, notional / px), 6)
        else:
            sym = (symbol or "").strip().upper()
            tif = "day"
            qty = float(max(1, round(notional / px)))

        try:
            order = client.submit_paper_order(
                sym, qty, side, order_type="market", time_in_force=tif,
            )
        except Exception as exc:
            return {"ok": False, "status": "rejected", "error": f"alpaca order rejected: {exc}"}

        return {
            "ok": True,
            "status": "executed",
            "mode": "ALPACA_PAPER",
            "broker": "alpaca",
            "symbol": sym,
            "side": side,
            "qty": qty,
            "price": px,
            "alpaca_order_id": str(order.get("id") or ""),
            "message": f"Alpaca paper {side} {qty} {sym} @ ~${px:,.2f}",
        }
    finally:
        client.close()


def _fill_queued_close_on_session(session: Any, order: Mapping[str, Any]) -> int:
    """Close open positions for a queued OJ/TV exit on the live session broker."""
    from trading_research.execution.exit_engine import ExitAction, apply_partial
    from trading_research.execution.option_premium import estimate_premium
    from trading_research.live.order_attribution import stamp_exit_channel

    sym = normalize_internal_symbol(
        str(order.get("symbol") or ""),
        order.get("market") or infer_market(str(order.get("symbol") or "")),
    )
    reason = str(order.get("reason") or order.get("event") or "queued_close")
    frac = min(1.0, max(0.0, float(order.get("qty_fraction") or 1.0)))
    price = float(order.get("spot") or order.get("price") or 0) or None
    targets = [
        t for t in list(session.broker.positions.values())
        if str(t.symbol).upper() == sym.upper()
    ]
    closed_n = 0
    for trade in targets:
        spot = float(price or 0.0)
        if spot <= 0:
            spot = resolve_spot_price(sym, infer_market(sym), None, settings=session.s)
        if trade.kind == "option" and spot > 0:
            mark = float(estimate_premium(trade, spot))
        else:
            mark = spot if spot > 0 else float(trade.entry_price or 0.0)
        if mark <= 0:
            continue
        if frac >= 0.999:
            closed, _ = session.broker.close_trade(
                trade.id,
                mark,
                reason,
                exit_channel=str(order.get("source") or "oj_0dte_pine"),
                log=True,
            )
            if closed:
                record_sell(
                    session.ledger, closed.to_dict(), ts=time.time(), equity=session.ledger.equity
                )
                session.broker.state.equity = session.ledger.equity
                session.broker.state.cash = session.ledger.equity
                closed_n += 1
            continue
        action = ExitAction(qty_fraction=frac, price=mark, reason=reason)
        close_qty, fully = apply_partial(trade, action)
        if close_qty <= 0:
            continue
        pnl = session.broker._leg_pnl(trade, mark, close_qty)
        session.broker.state.equity += pnl
        session.broker.state.cash += pnl
        trade.pnl = (trade.pnl or 0.0) + pnl
        if fully:
            trade.exit_price = mark
            trade.exit_reason = reason
            stamp_exit_channel(trade, str(order.get("source") or "oj_0dte_pine"))
            trade.status = "closed"
            trade.closed_at = time.time()
            session.broker.positions.pop(trade.id, None)
            session.broker.closed.append(trade)
            session.broker.state.open_trades = max(0, session.broker.state.open_trades - 1)
            session.broker.risk.register_close(session.broker.state, trade.pnl or 0.0)
            record_sell(
                session.ledger, trade.to_dict(), ts=time.time(), equity=session.ledger.equity
            )
            session.broker.state.equity = session.ledger.equity
            session.broker.state.cash = session.ledger.equity
            closed_n += 1
    return closed_n


def process_manual_orders(session: Any) -> int:
    """Process pending manual orders on a running LivePaperSession. Returns fill count."""
    path = manual_orders_path(session.data_dir)
    orders = _load_queue(path)
    if not orders:
        return 0

    filled = 0
    changed = False
    for order in orders:
        if order.get("status") != "pending":
            continue
        sym = str(order.get("symbol") or "")
        action = str(order.get("action") or "buy").lower()
        scout_conf = order.get("scout_confidence")
        order_source = str(order.get("source") or "")
        bypass = bool(order.get("bypass_gates"))

        # OJ / TV explicit closes — fill on the live broker, not a stub snapshot.
        if action in ("close", "exit", "flat", "flatten") or str(
            order.get("event") or ""
        ).lower() in ("tp1", "tp2", "tp3", "sl", "eod", "flip"):
            closed_n = _fill_queued_close_on_session(session, order)
            order["status"] = "filled"
            order["filled_at"] = time.time()
            order["closed"] = closed_n
            if closed_n == 0:
                order["message"] = "no open position"
            filled += closed_n
            changed = True
            continue

        candidate = find_hot_candidate(sym, session.data_dir) or {
            "symbol": sym,
            "direction": order.get("direction") or "long",
            "pattern": order.get("pattern") or "manual",
            "spot": order.get("spot") or 0,
            "reason": "queued manual order",
            "market": order.get("market") or infer_market(sym),
            "scout_confidence": scout_conf,
            "confidence": scout_conf,
            "strength": scout_conf,
        }
        if scout_conf is not None:
            candidate["scout_confidence"] = scout_conf
            candidate["confidence"] = scout_conf
        if order.get("pattern"):
            candidate["pattern"] = order.get("pattern")
        if order.get("direction"):
            candidate["direction"] = order.get("direction")
        if order_source:
            candidate["manual_source"] = order_source
        if float(candidate.get("spot") or 0) <= 0:
            candidate["spot"] = resolve_spot_price(
                sym,
                str(candidate.get("market") or "crypto"),
                float(order.get("spot") or 0) or None,
                settings=session.s,
            )
        if float(candidate.get("spot") or 0) <= 0:
            order["status"] = "failed"
            order["error"] = "missing spot price"
            changed = True
            continue

        # Whitelist always — even when OJ/TV bypasses soft gates.
        ok_sym, sym_reason = stock_symbol_allowed(sym, candidate.get("market"))
        if not ok_sym:
            order["status"] = "failed"
            order["error"] = sym_reason
            changed = True
            continue

        if not bypass:
            reject = _check_market_gates(
                sym,
                candidate.get("market"),
                settings=session.s,
                data_dir=session.data_dir,
                positions=session.broker.positions,
            )
            if reject:
                order["status"] = "failed"
                order["error"] = reject
                changed = True
                continue

            reject = _check_win_prob_gate(
                candidate,
                settings=session.s,
                learner=session.session,
                market=candidate.get("market"),
                source=order_source or order.get("source"),
                data_dir=session.data_dir,
            )
            if reject:
                order["status"] = "failed"
                order["error"] = reject
                changed = True
                continue

        try:
            payload = build_manual_trade_payload(
                candidate,
                "buy" if action not in ("sell",) else "sell",
                settings=session.s,
                data_dir=session.data_dir,
            )
        except ValueError as exc:
            order["status"] = "failed"
            order["error"] = str(exc)
            changed = True
            continue

        if order.get("contracts") is not None and payload.get("kind") == "option":
            try:
                payload["option"]["contracts"] = int(order["contracts"])
            except (TypeError, ValueError, KeyError):
                pass

        if not bypass:
            deploy_reject = _check_equity_deploy_gate(
                settings=session.s,
                equity=session.ledger.equity,
                payload=payload,
                data_dir=session.data_dir,
                positions=session.broker.positions,
            )
            if deploy_reject:
                order["status"] = "failed"
                order["error"] = deploy_reject
                changed = True
                continue

        from trading_research.execution.entry_bar_meta import stamp_entry_bar_meta

        candles = session.candles_by.get(sym) or []
        trade, msg = open_manual_trade(
            session.broker,
            payload,
            candles=candles,
            ignore_daily_limits=bypass,
        )
        if not trade:
            order["status"] = "failed"
            order["error"] = msg or "broker rejected"
            changed = True
            continue

        # Fill on the live session broker (never stub-snapshot while session runs).
        stamp_entry_bar_meta(
            trade,
            candles,
            prefer_idx=session._latest_bar_index(sym, for_entry=True) if candles else None,
        )
        from trading_research.execution.entry_bar_meta import stamp_direction_confirmation_meta

        strength = float(
            candidate.get("pattern_strength")
            or candidate.get("confidence")
            or session.s.option_live_pattern_min_strength
            or 0.72
        )
        stamp_direction_confirmation_meta(
            trade,
            confirmed=True,
            pattern_strength=strength,
            grace_bars=int(getattr(session.s, "option_stop_grace_bars", 0) or 0),
        )
        trade.meta["entry_live_ts"] = time.time()
        trade.meta["entry_day"] = time.strftime("%Y-%m-%d", time.gmtime())
        trade.meta["chart_pattern"] = candidate.get("pattern") or ""
        if bypass:
            trade.meta["gates_bypassed"] = True
        if order.get("levels"):
            trade.meta["oj_strategy"] = "oj_0dte"
            for key, raw in dict(order.get("levels") or {}).items():
                try:
                    val = float(raw) if raw is not None else None
                except (TypeError, ValueError):
                    val = None
                if val is not None and val > 0:
                    trade.meta[f"oj_{key}"] = val
        from trading_research.live.order_attribution import stamp_entry_source

        stamp_entry_source(trade, str(order.get("source") or "ui_hot_symbol"))
        _stamp_nautilus_meta(trade, candidate)
        record_buy(session.ledger, trade.to_dict(), ts=time.time())
        if trade.kind == "spot":
            alert_leg = f"{trade.side} spot"
        else:
            leg_action, right = leg_from_hot(str(candidate.get("direction") or "long"), action)
            alert_leg = f"{leg_action} {right}"
        session._post_alert(
            "BUY",
            f"Manual paper {alert_leg} {trade.symbol}",
            trade,
        )
        order["status"] = "filled"
        order["filled_at"] = time.time()
        order["trade_id"] = trade.id
        filled += 1
        changed = True
        if action == "buy":
            from trading_research.live.trade_adaptation import on_buy_placed

            on_buy_placed(session.data_dir, settings=session.s)

    if changed:
        _save_queue(path, orders)
    return filled


def _open_base_assets(
    data_dir: Path,
    *,
    positions: Optional[Dict[str, Any]] = None,
) -> set[str]:
    """Base assets with an open paper position or pending manual order."""
    bases: set[str] = set()
    if positions is not None:
        for t in positions.values():
            sym = str(getattr(t, "symbol", "") or (t.get("symbol") if isinstance(t, dict) else ""))
            if sym:
                bases.add(_base_asset(sym))
    else:
        snap_path = data_dir / "live_session_snapshot.json"
        if snap_path.is_file():
            try:
                snap = json.loads(snap_path.read_text(encoding="utf-8"))
                for pos in snap.get("positions") or []:
                    sym = str(pos.get("symbol") or "")
                    if sym:
                        bases.add(_base_asset(sym))
            except Exception:
                pass
    for order in _load_queue(manual_orders_path(data_dir)):
        if order.get("status") == "pending":
            sym = str(order.get("symbol") or "")
            if sym:
                bases.add(_base_asset(sym))
    return bases


def _symbol_blocked(symbol: str, settings: Settings) -> Optional[str]:
    sym = (symbol or "").strip().upper()
    whitelist = [str(s).upper() for s in (getattr(settings, "option_crypto_whitelist", None) or [])]
    if whitelist and infer_market(sym) == "crypto":
        bases = {_base_asset(w) for w in whitelist}
        if sym not in whitelist and _base_asset(sym) not in bases:
            return f"{sym} not on crypto whitelist (prop-firm selectivity)"
    blocklist = [str(s).upper() for s in (settings.option_symbol_blocklist or [])]
    if sym in blocklist:
        return f"{sym} on symbol blocklist"
    return None


def _today_loss_counts(data_dir: Path) -> Dict[str, int]:
    """Per-base loss count for the current UTC day from snapshot."""
    from collections import defaultdict
    from datetime import datetime, timezone

    day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    counts: Dict[str, int] = defaultdict(int)
    snap_path = data_dir / "live_session_snapshot.json"
    if not snap_path.is_file():
        return {}
    try:
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    learner = snap.get("learner") or {}
    day_map = (learner.get("symbol_day_losses") or {}).get(day_key) or {}
    if day_map:
        return {str(k).upper(): int(v) for k, v in day_map.items() if int(v) > 0}
    for row in snap.get("closed") or []:
        ts = float(row.get("closed_at") or row.get("ts") or 0)
        if ts <= 0:
            continue
        if datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d") != day_key:
            continue
        if float(row.get("pnl") or 0) >= 0:
            continue
        base = _base_asset(str(row.get("symbol") or ""))
        if base:
            counts[base] += 1
    return dict(counts)


def _load_session_blocklist(data_dir: Path) -> set[str]:
    """Static symbol blocklist from settings only (not stale learner list)."""
    from trading_research.jarvis_locked import get_jarvis_settings

    s = get_jarvis_settings()
    blocked: set[str] = set()
    for entry in s.option_symbol_blocklist or []:
        raw = str(entry).strip().upper()
        if raw:
            blocked.add(raw)
            blocked.add(_base_asset(raw))
    return blocked


def _load_symbol_session_stats(data_dir: Path) -> Dict[str, Dict[str, float]]:
    """Per-base-asset cumulative and last-trade PnL from session closed trades."""
    stats: Dict[str, Dict[str, float]] = {}
    snap_path = data_dir / "live_session_snapshot.json"
    if not snap_path.is_file():
        return stats
    try:
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
    except Exception:
        return stats
    for row in snap.get("closed") or []:
        sym = str(row.get("symbol") or "").strip().upper()
        if not sym:
            continue
        base = _base_asset(sym)
        pnl = float(row.get("pnl") or 0)
        bucket = stats.setdefault(base, {"cum": 0.0, "last": 0.0, "n": 0.0})
        bucket["cum"] += pnl
        bucket["last"] = pnl
        bucket["n"] += 1
    return stats


def _check_min_premium_gate(
    candidate: Dict[str, Any],
    action: str = "buy",
    *,
    settings: Optional[Settings] = None,
    data_dir: Optional[Path] = None,
) -> Optional[str]:
    sym = str(candidate.get("symbol") or "").strip().upper()
    if not sym:
        return None
    mkt = candidate.get("market") or infer_market(sym)
    if trade_kind_for_market(mkt) != "option":
        return None
    s = settings or get_settings()
    try:
        kw = build_manual_order_kwargs(candidate, action, settings=s, data_dir=data_dir)
    except ValueError as exc:
        return str(exc)
    from trading_research.execution.entry_bar_meta import pre_entry_micro_premium_reason

    return pre_entry_micro_premium_reason(
        float(kw.get("premium") or 0),
        settings=s,
        pattern=str(candidate.get("pattern") or kw.get("chart_pattern") or "") or None,
        right=str(kw.get("right") or ""),
    )


def _check_news_calls_only_gate(
    setup: Mapping[str, Any],
    candidate: Optional[Mapping[str, Any]] = None,
) -> Optional[str]:
    """News-driven entries are bullish calls only — no puts from headlines."""
    from trading_research.config.market_strategy import read_news_media_scout_toml

    if not read_news_media_scout_toml().get("entries_calls_only", True):
        return None
    if not is_news_scout_setup(setup) and not (
        candidate is not None and is_news_scout_setup(candidate)
    ):
        return None
    ctx = str(setup.get("position_context") or "").lower()
    if ctx in ("exit_watch", "held_neutral", "bearish_watch"):
        return None
    direction = str(
        (candidate or setup).get("direction") or setup.get("direction") or "long"
    ).lower()
    if direction in ("short", "bearish", "down", "sell", "put"):
        return "news entries are calls only (bullish long) — skipped put/short"
    return None


def _learned_symbol_repeat_ok(symbol: str) -> bool:
    """Allow re-entries when we've learned repeatable movement on this symbol."""
    from trading_research.jarvis_locked import read_strategy_toml
    from trading_research.learning.symbol_movement_learner import (
        load_symbol_movement_learning,
        _normalize_symbol,
    )

    toml = read_strategy_toml()
    if not bool(toml.get("allow_learned_symbol_repeat", True)):
        return False
    min_rep = float(toml.get("learned_repeat_min_repeatability", 0.10) or 0.10)
    min_wr = float(toml.get("learned_repeat_min_book_wr", 0.45) or 0.45)

    sym = _normalize_symbol(symbol)
    profile = load_symbol_movement_learning().symbols.get(sym)
    if profile is None:
        return False
    movement = profile.movement or {}
    outcomes = profile.outcomes or {}
    repeat = float(movement.get("repeatability_score") or 0)
    samples = int(outcomes.get("samples") or 0)
    wr = float(outcomes.get("win_rate") or 0)
    if repeat < min_rep:
        return False
    if samples >= 3 and wr < min_wr:
        return False
    return True


def _check_symbol_repeat_gate(
    symbol: str,
    data_dir: Path,
    candidate: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Repeat entries use stricter direction confirmation, not hard blocks."""
    if candidate is not None:
        kind = str(candidate.get("kind") or "").lower()
        pattern = str(candidate.get("pattern") or "").lower()
        agent = str(candidate.get("scout_agent") or candidate.get("source") or "").lower()
        if pattern == "scout_setup" and (kind == "news" or agent == "news_media_scout"):
            return None

    try:
        from trading_research.live.genius_exit import _big_wins_mode, is_tier1_symbol

        if _big_wins_mode() and is_tier1_symbol(symbol, data_dir):
            return None
    except Exception:
        pass

    from trading_research.execution.direction_confirmation import compute_fakeout_risk
    from trading_research.jarvis_locked import read_strategy_toml

    base = _base_asset(symbol)
    learned_repeat = _learned_symbol_repeat_ok(symbol)
    risk = compute_fakeout_risk(symbol, data_dir)
    toml = read_strategy_toml()
    threshold = 0.45
    pattern = str((candidate or {}).get("pattern") or "").lower()
    bear_breakout = pattern in (
        "range_breakout_down", "bear_flag", "desc_triangle", "double_top"
    )
    try:
        from trading_research.live.genius_exit import is_tier1_symbol

        if is_tier1_symbol(symbol, data_dir):
            threshold = float(toml.get("tier1_fakeout_max_risk", 0.70) or 0.70)
        elif bear_breakout:
            threshold = 0.58
    except Exception:
        pass
    if learned_repeat:
        threshold = min(0.95, threshold + 0.20)
    if risk >= threshold:
        return (
            f"repeat fakeout risk on {base} (score={risk:.2f}) — "
            f"need stronger breakdown confirmation"
        )

    snap_path = data_dir / "live_session_snapshot.json"
    if not snap_path.is_file():
        return None
    try:
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    rows = [
        r
        for r in snap.get("closed") or []
        if _base_asset(str(r.get("symbol") or "")) == base
    ]
    if len(rows) >= 2 and not learned_repeat:
        try:
            from trading_research.live.genius_exit import _big_wins_mode, is_tier1_symbol

            if _big_wins_mode() and is_tier1_symbol(symbol, data_dir):
                return None
        except Exception:
            pass
        losses = sum(1 for r in rows if float(r.get("pnl") or 0) < 0)
        cum = sum(float(r.get("pnl") or 0) for r in rows)
        last_pnl = float(rows[-1].get("pnl") or 0)
        if losses >= 3 and cum <= -6.0:
            return (
                f"repeat loser {base}: {losses} losses, cum ${cum:.2f} — "
                f"need stronger breakdown"
            )
        if losses >= 2 and last_pnl < 0:
            return (
                f"last {base} closes were net losers ({losses} losses) — "
                f"need stronger setup"
            )
    return None


# Patterns that lost money live — block long/call entries on these.
_BLOCKED_LONG_PATTERNS = frozenset({"double_bottom"})


def _check_pattern_leg_gate(
    candidate: Dict[str, Any],
    settings: Optional[Settings] = None,
) -> Optional[str]:
    """Keep proven setups; block repeat losers like double_bottom calls."""
    from trading_research.config.market_strategy import pattern_allowlist_reject
    from trading_research.jarvis_locked import get_jarvis_settings

    s = settings or get_jarvis_settings()
    allow_reject = pattern_allowlist_reject(candidate, settings=s)
    if allow_reject:
        return allow_reject
    pattern = str(candidate.get("pattern") or "").lower()
    direction = str(candidate.get("direction") or "long").lower()
    mkt = candidate.get("market") or infer_market(str(candidate.get("symbol") or ""))
    if (
        pattern in _BLOCKED_LONG_PATTERNS
        and direction in ("long", "bullish", "up")
        and str(mkt).lower() not in ("stock", "stocks")
    ):
        return f"{pattern} long/call blocked (poor live win rate)"
    return None


def _check_reversal_trend_gate(
    candidate: Dict[str, Any],
    settings: Optional[Settings] = None,
    data_dir: Optional[Path] = None,
) -> Optional[str]:
    """Block reversal entries that fight EMA trend (e.g. double_top puts in bull tape)."""
    pattern = str(candidate.get("pattern") or "").lower()
    if pattern not in ("double_top", "double_bottom"):
        return None

    bull = candidate.get("bull_score")
    bear = candidate.get("bear_score")
    if bull is None or bear is None:
        if data_dir is None:
            return None
        sym = str(candidate.get("symbol") or "").upper()
        if not sym:
            return None
        from trading_research.execution.entry_bar_meta import load_candles_for_symbol
        from trading_research.learning.session_learner import learn_trend_snapshot

        candles = load_candles_for_symbol(sym, data_dir=Path(data_dir))
        if len(candles) < 30:
            return None
        bull, bear, _ = learn_trend_snapshot(candles, settings=settings or get_settings())

    from trading_research.execution.reversal_trend_gate import reversal_trend_reject_reason

    return reversal_trend_reject_reason(
        pattern=pattern,
        direction=str(candidate.get("direction") or "long"),
        bull=float(bull),
        bear=float(bear),
        settings=settings,
    )


def _check_session_block(
    symbol: str,
    settings: Settings,
    data_dir: Path,
) -> Optional[str]:
    """Reject illiquid symbols + same-day session blocks after repeat losses."""
    base = _base_asset(symbol)
    sym = symbol.strip().upper()
    static = _load_session_blocklist(data_dir)
    if base in static or sym in static:
        return _symbol_blocked(symbol, settings)

    block_after = int(getattr(settings, "option_session_block_losses", 2) or 0)
    if block_after <= 0 or block_after >= 50:
        return None
    if _learned_symbol_repeat_ok(symbol):
        return None
    today_losses = _today_loss_counts(data_dir)
    n = int(today_losses.get(base, 0))
    if n >= block_after:
        return (
            f"session block {base}: {n} losses today "
            f"(need win to retry)"
        )
    return None


def option_session_block_losses_label(settings: Settings) -> int:
    return max(0, int(getattr(settings, "option_session_block_losses", 2) or 0))


def _check_direction_confirmation(
    candidate: Dict[str, Any],
    settings: Optional[Settings] = None,
    data_dir: Optional[Path] = None,
) -> Optional[str]:
    from trading_research.execution.direction_confirmation import (
        direction_confirmation_reject_reason,
    )

    root = data_dir
    if root is None and settings is not None:
        root = Path(settings.data_dir)
    if root is not None:
        qlib_reject = _check_qlib_direction_gate(candidate, data_dir=root)
        if qlib_reject:
            return qlib_reject
        kronos_reject = _check_kronos_direction_gate(candidate, data_dir=root)
        if kronos_reject:
            return kronos_reject

    return direction_confirmation_reject_reason(
        candidate, settings=settings, data_dir=data_dir
    )


def _check_qlib_direction_gate(
    candidate: Dict[str, Any],
    *,
    data_dir: Path,
) -> Optional[str]:
    from trading_research.analysis.qlib_signals import qlib_direction_reject_reason

    return qlib_direction_reject_reason(candidate, data_dir=data_dir)


def _check_kronos_direction_gate(
    candidate: Dict[str, Any],
    *,
    data_dir: Path,
) -> Optional[str]:
    from trading_research.analysis.kronos_signals import kronos_direction_reject_reason

    return kronos_direction_reject_reason(candidate, data_dir=data_dir)


def _check_order_flow_gate(
    candidate: Mapping[str, Any],
    *,
    settings: Optional[Settings] = None,
) -> Optional[str]:
    from trading_research.analysis.order_flow import order_flow_gate_reason

    return order_flow_gate_reason(candidate, settings=settings)


def submit_scout_feed_orders(
    *,
    settings: Optional[Settings] = None,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Place paper buy orders for setups in market_scout_feed.json."""
    from trading_research.jarvis_locked import get_jarvis_settings

    s = settings or get_jarvis_settings()
    s.assert_paper_only()
    scout_cfg = read_scout_strategy_toml()
    if not scout_cfg.get("allow_scout_feed_orders", False):
        return {"ok": False, "error": "scout feed orders disabled in trading.toml"}

    root = data_dir or Path(s.data_dir)
    prune_stale_failed_orders(root)
    from trading_research.live.trade_adaptation import compute_effective_gates, on_buy_placed

    gates = compute_effective_gates(root, settings=s)
    feed_path = root / "market_scout_feed.json"
    if not feed_path.is_file():
        return {"ok": False, "error": "market_scout_feed.json not found"}

    try:
        feed = json.loads(feed_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "error": f"invalid scout feed: {exc}"}

    from trading_research.analysis.signal_tiers import enrich_setup
    from trading_research.config.trading_modes import read_trading_modes

    modes = read_trading_modes()
    min_conf = max(gates.min_scout_confidence_pct, modes.auto_buy_min_score)
    setups = list(feed.get("setups") or [])
    try:
        from trading_research.live.genius_exit import is_tier1_symbol
        from trading_research.live.genius_playbook import load_playbook

        pb = load_playbook(root)
        if pb.get("active") and pb.get("tier1_only_entries"):
            setups = [
                s
                for s in setups
                if is_tier1_symbol(str(s.get("symbol") or ""), root)
            ]
        setups.sort(
            key=lambda r: (
                0 if is_tier1_symbol(str(r.get("symbol") or ""), root) else 1,
                -float(r.get("confidence") or 0),
            )
        )
    except Exception:
        setups.sort(key=lambda r: float(r.get("confidence") or 0), reverse=True)
    setups = dedupe_setups_by_base(setups)

    open_bases = _open_base_assets(root)
    open_counts = _count_open_by_market(root)
    results: List[Dict[str, Any]] = []
    placed = 0
    seen_bases: set[str] = set()

    for setup in setups:
        sym = str(setup.get("symbol") or "").strip().upper()
        if not sym:
            continue
        setup = enrich_setup(dict(setup), modes)
        if setup.get("auto_eligible") is False:
            results.append({"symbol": sym, "status": "skipped", "error": "below auto_buy_min_score"})
            continue
        news_reject = _check_news_calls_only_gate(setup)
        if news_reject:
            results.append({"symbol": sym, "status": "skipped", "error": news_reject})
            continue
        conf_pct = _scout_confidence_pct(setup)
        score = float(setup.get("signal_score") or conf_pct or 0)
        if conf_pct is None or score < min_conf:
            shown = f"{conf_pct:.1f}%" if conf_pct is not None else "missing"
            results.append(
                {
                    "symbol": sym,
                    "status": "skipped",
                    "error": f"confidence {shown} < {min_conf:.0f}%",
                }
            )
            continue

        from trading_research.analysis.direction_predictor import (
            apply_prediction_to_setup,
            predict_direction,
        )

        if not is_news_scout_setup(setup):
            pred = predict_direction(setup, settings=s, data_dir=root)
            if pred is not None:
                setup = apply_prediction_to_setup(setup, pred, min_confidence_pct=55.0)
        else:
            setup = dict(setup)
            setup["direction"] = "long"
        candidate = build_scout_candidate(setup)
        from trading_research.analysis.order_flow import enrich_candidate_order_flow

        candidate = enrich_candidate_order_flow(candidate, settings=s)
        chart_reject = _chart_conviction_gate_reason(candidate, data_dir=root, settings=s)
        if chart_reject:
            results.append({"symbol": sym, "status": "skipped", "error": chart_reject})
            continue

        base = _base_asset(sym)
        if base in open_bases or base in seen_bases:
            results.append({"symbol": sym, "status": "skipped", "error": "duplicate symbol"})
            continue

        mkt = candidate.get("market") or infer_market(sym)

        stock_reject = _check_market_gates(sym, mkt, settings=s, data_dir=root)
        if stock_reject:
            results.append({"symbol": sym, "status": "rejected", "error": stock_reject})
            continue

        block_reject = _check_session_block(sym, s, root)
        if block_reject:
            results.append({"symbol": sym, "status": "rejected", "error": block_reject})
            continue

        repeat_reject = _check_symbol_repeat_gate(sym, root, candidate=candidate)
        if repeat_reject:
            results.append({"symbol": sym, "status": "rejected", "error": repeat_reject})
            continue

        pattern_reject = _check_pattern_leg_gate(candidate)
        if pattern_reject:
            results.append({"symbol": sym, "status": "rejected", "error": pattern_reject})
            continue

        confirm_reject = _check_direction_confirmation(candidate, settings=s, data_dir=root)
        if confirm_reject:
            results.append({"symbol": sym, "status": "rejected", "error": confirm_reject})
            continue

        sym_math_reject = _check_symbol_setup_gate(candidate, data_dir=root)
        if sym_math_reject:
            results.append({"symbol": sym, "status": "rejected", "error": sym_math_reject})
            continue

        nautilus_reject = _check_nautilus_backtest_gate(candidate, data_dir=root)
        if nautilus_reject:
            results.append({"symbol": sym, "status": "rejected", "error": nautilus_reject})
            continue

        flow_reject = _check_order_flow_gate(candidate, settings=s)
        if flow_reject:
            results.append({"symbol": sym, "status": "rejected", "error": flow_reject})
            continue

        action = "buy"
        premium_reject = _check_min_premium_gate(candidate, action, settings=s, data_dir=root)
        if premium_reject:
            results.append({"symbol": sym, "status": "rejected", "error": premium_reject})
            continue

        block_reject = _symbol_blocked(sym, s)
        if block_reject:
            results.append({"symbol": sym, "status": "rejected", "error": block_reject})
            continue

        key = "stocks" if is_stock_market(mkt) else "crypto"
        eff = settings_for_market(s, mkt)
        from trading_research.config.market_strategy import _campaign_max_open

        max_open = _campaign_max_open(getattr(eff, "option_campaign_max_open", 5), 5)
        if max_open > 0 and open_counts.get(key, 0) >= max_open:
            results.append(
                {"symbol": sym, "status": "skipped", "error": f"max open {key} positions ({max_open}) reached"}
            )
            continue

        direction = str(setup.get("direction") or "long").lower()
        action = "buy"  # calls for long, puts for short/breakdown

        result = submit_manual_paper_order(
            sym,
            action,
            settings=s,
            source="market_scout_feed",
            market=mkt,
            direction=direction,
            candidate=candidate,
        )
        result["symbol"] = sym
        result["direction"] = direction
        result["confidence_pct"] = conf_pct
        results.append(result)
        if result.get("ok"):
            placed += 1
            seen_bases.add(base)
            open_bases.add(base)
            open_counts[key] = open_counts.get(key, 0) + 1

    if placed > 0:
        on_buy_placed(root, settings=s)

    return {
        "ok": True,
        "placed": placed,
        "attempted": len(results),
        "results": results,
        "open_positions": _count_open_by_market(root),
        "adapt_level": gates.relax_level,
        "adapt_note": gates.note,
        "effective_min_confidence_pct": min_conf,
        "effective_take_profit_usd": gates.take_profit_usd,
    }
