"""Track where paper buy/sell orders originate (supervisor, session, manual)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

ENTRY_SOURCE_LABELS: Dict[str, str] = {
    "market_scout_feed": "BUY-SUPERVISOR · scout feed",
    "auto_trader_hot": "BUY-SUPERVISOR · hot breakout",
    "ui_hot_symbol": "Manual / UI",
    "tradingview_webhook": "TradingView webhook",
    "oj_0dte_pine": "OJ 0DTE Pine",
    "session_pattern_scan": "Session pattern scan",
    "session_trend_scan": "Session trend scan",
    "unknown": "Unknown",
}

EXIT_CHANNEL_LABELS: Dict[str, str] = {
    "sell_supervisor": "SELL-SUPERVISOR · auto rules",
    "session_tick": "Session tick · exit engine",
    "session_flatten": "Session flatten",
    "oj_0dte_pine": "OJ 0DTE Pine",
    "manual": "Manual close",
    "unknown": "Unknown",
}

STATS_FILENAME = "order_source_stats.json"


def normalize_entry_source(raw: Optional[str]) -> str:
    key = (raw or "").strip().lower() or "unknown"
    if key in ENTRY_SOURCE_LABELS:
        return key
    if key.startswith("auto_trader"):
        return "auto_trader_hot"
    if "scout" in key:
        return "market_scout_feed"
    if key.startswith("oj_") or "oj_0dte" in key:
        return "oj_0dte_pine"
    if "tradingview" in key:
        return "tradingview_webhook"
    if "session" in key or "pattern" in key:
        return "session_pattern_scan"
    return key if key else "unknown"


def entry_source_label(source: Optional[str]) -> str:
    key = normalize_entry_source(source)
    return ENTRY_SOURCE_LABELS.get(key, key.replace("_", " ").title())


def classify_exit_channel(reason: str, *, meta: Optional[Mapping[str, Any]] = None) -> str:
    if meta and meta.get("exit_channel"):
        return str(meta["exit_channel"])
    r = (reason or "").strip().lower()
    if r.startswith("oj_") or "oj_0dte" in r:
        return "oj_0dte_pine"
    if r.startswith("auto_"):
        return "sell_supervisor"
    if r in ("session_stop", "user_flatten_equity", "user_flatten"):
        return "session_flatten"
    if r in ("manual", "manual_close"):
        return "manual"
    if r in (
        "stop",
        "trailing_stop",
        "quick_scalp_partial",
        "quick_scalp_lock",
        "flat_premium",
        "loss_cut",
        "time_take",
        "take_profit_1",
        "take_profit_2",
    ) or r.startswith("take_profit"):
        return "session_tick"
    return "unknown"


def exit_channel_label(channel: Optional[str]) -> str:
    key = (channel or "unknown").strip().lower()
    return EXIT_CHANNEL_LABELS.get(key, key.replace("_", " ").title())


def stamp_entry_source(trade: Any, source: str) -> str:
    """Attach normalized entry source on trade.meta."""
    key = normalize_entry_source(source)
    trade.meta["entry_source"] = key
    trade.meta["entry_source_label"] = entry_source_label(key)
    return key


def stamp_exit_channel(trade: Any, channel: str) -> str:
    """Attach exit channel on trade.meta (alongside exit_reason)."""
    key = (channel or "unknown").strip().lower()
    trade.meta["exit_channel"] = key
    trade.meta["exit_channel_label"] = exit_channel_label(key)
    return key


def _trade_entry_source(trade: Any) -> str:
    meta = getattr(trade, "meta", None) or {}
    if isinstance(trade, dict):
        meta = trade.get("meta") or {}
    raw = meta.get("entry_source") or meta.get("manual_source") or ""
    if not raw:
        reason = getattr(trade, "entry_reason", None) or (trade.get("entry_reason") if isinstance(trade, dict) else "")
        if reason and str(reason).startswith("session_"):
            return "session_pattern_scan"
    return normalize_entry_source(str(raw))


def _trade_exit_channel(trade: Any) -> str:
    meta = getattr(trade, "meta", None) or {}
    if isinstance(trade, dict):
        meta = trade.get("meta") or {}
        reason = str(trade.get("exit_reason") or "")
    else:
        reason = str(getattr(trade, "exit_reason", "") or "")
    return classify_exit_channel(reason, meta=meta)


def compute_order_source_stats(
    closed: Sequence[Any],
    *,
    open_positions: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    """Aggregate entry/exit source counts from closed (+ open entry) trades."""
    entry_counts: Counter[str] = Counter()
    exit_counts: Counter[str] = Counter()

    for trade in closed:
        entry_counts[_trade_entry_source(trade)] += 1
        exit_counts[_trade_exit_channel(trade)] += 1

    open_entry_counts: Counter[str] = Counter()
    for trade in open_positions or ():
        open_entry_counts[_trade_entry_source(trade)] += 1

    def _top(counter: Counter[str], labels: Dict[str, str]) -> List[Dict[str, Any]]:
        total = sum(counter.values())
        if total <= 0:
            return []
        rows = []
        for key, n in counter.most_common():
            rows.append(
                {
                    "source": key,
                    "label": labels.get(key, key),
                    "count": n,
                    "pct": round(100.0 * n / total, 1),
                }
            )
        return rows

    entry_top = _top(entry_counts, ENTRY_SOURCE_LABELS)
    exit_top = _top(exit_counts, EXIT_CHANNEL_LABELS)
    majority_entry = entry_top[0] if entry_top else None
    majority_exit = exit_top[0] if exit_top else None

    return {
        "closed_trades": len(closed),
        "open_positions": sum(open_entry_counts.values()),
        "entry_sources": entry_top,
        "exit_channels": exit_top,
        "majority_entry": majority_entry,
        "majority_exit": majority_exit,
        "open_entry_sources": _top(open_entry_counts, ENTRY_SOURCE_LABELS),
    }


def format_order_source_summary(stats: Mapping[str, Any]) -> str:
    """One-line summary for status / logs."""
    parts: List[str] = []
    maj_e = stats.get("majority_entry")
    if maj_e:
        parts.append(
            f"buys mostly {maj_e.get('label')} ({maj_e.get('pct', 0):.0f}%)"
        )
    maj_x = stats.get("majority_exit")
    if maj_x:
        parts.append(
            f"sells mostly {maj_x.get('label')} ({maj_x.get('pct', 0):.0f}%)"
        )
    return " | ".join(parts) if parts else "no closed trades yet"


def format_order_source_detail(stats: Mapping[str, Any]) -> List[str]:
    """Multi-line breakdown for status."""
    lines: List[str] = []
    summary = format_order_source_summary(stats)
    if summary != "no closed trades yet":
        lines.append(f"  Order flow: {summary}")

    for title, key in (("Buy sources", "entry_sources"), ("Sell channels", "exit_channels")):
        rows = list(stats.get(key) or [])
        if not rows:
            continue
        chunks = [f"{r['label']} {r['pct']:.0f}%" for r in rows[:4]]
        lines.append(f"  {title}: {', '.join(chunks)}")
    return lines


def stats_path(data_dir: Path) -> Path:
    return Path(data_dir) / STATS_FILENAME


def save_order_source_stats(
    data_dir: Path,
    closed: Sequence[Any],
    *,
    open_positions: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    import json
    import time

    payload = compute_order_source_stats(closed, open_positions=open_positions)
    payload["updated_at"] = time.time()
    path = stats_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_order_source_stats(data_dir: Path) -> Dict[str, Any]:
    import json

    path = stats_path(data_dir)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
