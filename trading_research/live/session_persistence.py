"""Persist live session broker + marks across restarts."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from trading_research.config.settings import Settings, get_settings
from trading_research.core_types import PaperTrade
from trading_research.execution.paper_broker import PaperBroker
from trading_research.execution.risk_manager import AccountState, RiskManager
from trading_research.learning.session_learner import SessionLearner


def snapshot_path(settings: Optional[Settings] = None) -> Path:
    s = settings or get_settings()
    return Path(s.data_dir) / "live_session_snapshot.json"


def _trade_from_dict(d: Dict[str, Any]) -> PaperTrade:
    from dataclasses import fields

    from trading_research.config.market_strategy import detect_market

    names = {f.name for f in fields(PaperTrade)}
    kw = {k: v for k, v in d.items() if k in names}
    sym = str(kw.get("symbol") or d.get("symbol") or "")
    if sym:
        kw["market"] = detect_market(sym)
    meta = dict(kw.get("meta") or d.get("meta") or {})
    if sym:
        meta["market"] = detect_market(sym)
    kw["meta"] = meta
    return PaperTrade(**kw)


def save_snapshot(
    session: Any,
    *,
    intentional_stop: bool = False,
    crash_reason: str = "",
) -> None:
    """Save broker, learner, and mark state.

    Merges any open positions already on disk that are missing from memory so a
    live session tick cannot clobber webhook/manual fills that landed between
    sync and save (race that previously wiped OJ Pine entries).
    """
    s = session.s
    broker = session.broker
    path = snapshot_path(s)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Adopt orphan opens from disk before we overwrite.
    try:
        if path.is_file():
            existing = json.loads(path.read_text(encoding="utf-8"))
            disk_positions = existing.get("positions") or []
            mem_ids = set(broker.positions.keys())
            adopted = 0
            for d in disk_positions:
                if not isinstance(d, dict):
                    continue
                tid = str(d.get("id") or "")
                if not tid or tid in mem_ids:
                    continue
                trade = _trade_from_dict(d)
                broker.positions[tid] = trade
                mem_ids.add(tid)
                adopted += 1
            if adopted:
                broker.state.open_trades = len(broker.positions)
                # Prefer newer closed list when disk has more history.
                disk_closed = existing.get("closed") or []
                if len(disk_closed) > len(broker.closed):
                    seen = {t.id for t in broker.closed}
                    for d in disk_closed:
                        if not isinstance(d, dict):
                            continue
                        cid = str(d.get("id") or "")
                        if cid and cid not in seen:
                            broker.closed.append(_trade_from_dict(d))
                            seen.add(cid)
    except Exception:
        pass

    st = broker.stats()
    payload = {
        "version": 1,
        "saved_at": time.time(),
        "intentional_stop": intentional_stop,
        "crash_reason": crash_reason,
        "started_at": session._started_at,
        "bootstrapped": session._bootstrapped,
        "last_bar_ts": session.last_bar_ts,
        "starting_equity": s.starting_equity,
        "account": {
            "starting_equity": broker.state.starting_equity,
            "equity": broker.state.equity,
            "cash": broker.state.cash,
            "open_trades": broker.state.open_trades,
            "trades_today": broker.state.trades_today,
            "losing_trades_today": broker.state.losing_trades_today,
            "consecutive_losses": broker.state.consecutive_losses,
            "daily_pnl": broker.state.daily_pnl,
            "wins_today": broker.state.wins_today,
            "total_trades": broker.state.total_trades,
            "wins": broker.state.wins,
            "losses": broker.state.losses,
            "peak_equity": broker.state.peak_equity,
            "max_drawdown": broker.state.max_drawdown,
            "cooldown_ticks": broker.state.cooldown_ticks,
            "hourly_trade_count": broker.state.hourly_trade_count,
            "bars_in_hour_window": broker.state.bars_in_hour_window,
            "day": broker.state.day,
        },
        "positions": [t.to_dict() for t in broker.positions.values()],
        "closed": [t.to_dict() for t in broker.closed],
        "learner": {
            "session_blocklist": list(session.session.session_blocklist),
            "fakeout_strikes": dict(session.session.fakeout_strikes),
            "day_modes": dict(session.session.day_modes),
            "symbol_losses": dict(session.session.symbol_losses),
            "symbol_day_losses": {
                day: dict(losses)
                for day, losses in session.session.symbol_day_losses.items()
            },
            "learn_count": session.session.learn_count,
            "notes": list(session.session.notes)[-20:],
        },
        "stats": st,
    }
    # Atomic replace so readers never see a partial wipe.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def load_snapshot(settings: Settings) -> Optional[Dict[str, Any]]:
    path = snapshot_path(settings)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def restore_session(session: Any, snap: Dict[str, Any]) -> None:
    """Restore broker + learner from snapshot."""
    acc = snap.get("account") or {}
    session.broker.state = AccountState(
        starting_equity=float(acc.get("starting_equity", session.s.starting_equity)),
        equity=float(acc.get("equity", session.s.starting_equity)),
        cash=float(acc.get("cash", session.s.starting_equity)),
        open_trades=int(acc.get("open_trades", 0)),
        trades_today=int(acc.get("trades_today", 0)),
        losing_trades_today=int(acc.get("losing_trades_today", 0)),
        consecutive_losses=int(acc.get("consecutive_losses", 0)),
        daily_pnl=float(acc.get("daily_pnl", 0)),
        wins_today=int(acc.get("wins_today", 0)),
        total_trades=int(acc.get("total_trades", 0)),
        wins=int(acc.get("wins", 0)),
        losses=int(acc.get("losses", 0)),
        peak_equity=float(acc.get("peak_equity", acc.get("equity", 1000))),
        max_drawdown=float(acc.get("max_drawdown", 0)),
        cooldown_ticks=int(acc.get("cooldown_ticks", 0)),
        hourly_trade_count=int(acc.get("hourly_trade_count", 0)),
        bars_in_hour_window=int(acc.get("bars_in_hour_window", 0)),
        day=str(acc.get("day", "")),
    )
    session.broker.positions = {
        t["id"]: _trade_from_dict(t) for t in snap.get("positions", [])
    }
    session.broker.closed = [_trade_from_dict(t) for t in snap.get("closed", [])]
    session.broker.risk = RiskManager(session.s)

    learn = snap.get("learner") or {}
    session.session.session_blocklist = list(learn.get("session_blocklist", []))
    session.session.day_modes = dict(learn.get("day_modes", {}))
    from collections import defaultdict

    session.session.fakeout_strikes = defaultdict(
        int, learn.get("fakeout_strikes", {})
    )
    session.session.symbol_losses = defaultdict(
        int, learn.get("symbol_losses", {})
    )
    session.session.symbol_day_losses = defaultdict(
        lambda: defaultdict(int),
        {
            day: defaultdict(int, dict(losses or {}))
            for day, losses in (learn.get("symbol_day_losses") or {}).items()
        },
    )
    session.session.learn_count = int(learn.get("learn_count", 0))
    session.session.notes = list(learn.get("notes", []))

    session.last_bar_ts = {k: int(v) for k, v in (snap.get("last_bar_ts") or {}).items()}
    session._bootstrapped = bool(snap.get("bootstrapped", True))
    session._started_at = float(snap.get("started_at", time.time()))
