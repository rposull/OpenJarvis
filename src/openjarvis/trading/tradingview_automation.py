"""TradingView alert parsing and paper-trade automation."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote
from urllib.request import Request, urlopen

from openjarvis.trading.symbol_map import from_tradingview, map_symbol_response

_BUY_ACTIONS = frozenset({"buy", "long", "bull", "bullish", "enter_long"})
_SELL_ACTIONS = frozenset({"sell", "short", "bear", "bearish", "enter_short"})
_CLOSE_ACTIONS = frozenset({"close", "exit", "flat", "flatten", "eod", "sl", "tp_break", "flip"})
_OJ_STRATEGY = "oj_0dte"
# Hard exits only — tp1/tp2/tp3 are suggestion milestones (never auto-sell).
_OJ_EXIT_EVENTS = frozenset({"sl", "eod", "flip", "close", "exit", "tp_break"})
_OJ_TP_SUGGEST_EVENTS = frozenset({"tp1", "tp2", "tp3"})
_OJ_ENTRY_EVENTS = frozenset({"entry_call", "entry_put", "call", "put"})


def _trading_toml_path() -> Path:
    return Path.home() / ".openjarvis" / "trading.toml"


def load_tradingview_config() -> Dict[str, Any]:
    """Read [tradingview] section from trading.toml."""
    defaults: Dict[str, Any] = {
        "default_exchange": "COINBASE",
        "interval": "5",
        "theme": "dark",
        "webhook_secret": "",
        "ngrok_domain": "",
        "auto_execute": True,
        "trust_indicator": True,
        "execution_broker": "internal",
        "order_notional_usd": 2000.0,
        "default_qty": 1,
        "allowed_markets": ["crypto", "stocks"],
        "auto_switch_chart": True,
        "ai_enabled": False,
        "ai_mode": "consensus",
        "ai_timeout_sec": 8.0,
        "codex_decision_url": "",
        "claude_decision_url": "",
        "codex_auth_token": "",
        "claude_auth_token": "",
        # When true, only OJ 0DTE Pine (strategy=oj_0dte) alerts may trade.
        "only_oj_pine": True,
        "oj_strategy": _OJ_STRATEGY,
        "oj_tp1_exit_pct": 0.50,
        "oj_tp2_exit_pct": 0.50,
    }
    path = _trading_toml_path()
    if not path.is_file():
        return defaults
    try:
        import tomllib

        blob = path.read_bytes()
        if blob.startswith(b"\xef\xbb\xbf"):
            blob = blob[3:]
        raw = tomllib.loads(blob.decode("utf-8"))
        tv = raw.get("tradingview") or {}
        for key in defaults:
            if key in tv and tv[key] is not None:
                defaults[key] = tv[key]
    except Exception:
        pass

    if isinstance(defaults.get("allowed_markets"), str):
        defaults["allowed_markets"] = [
            m.strip().lower() for m in str(defaults["allowed_markets"]).split(",") if m.strip()
        ]
    defaults["allowed_markets"] = [
        str(m).lower() for m in (defaults.get("allowed_markets") or ["crypto", "stocks"])
    ]
    defaults["auto_execute"] = bool(defaults.get("auto_execute", True))
    defaults["trust_indicator"] = bool(defaults.get("trust_indicator", True))
    defaults["auto_switch_chart"] = bool(defaults.get("auto_switch_chart", True))
    defaults["execution_broker"] = str(defaults.get("execution_broker") or "internal").strip().lower()
    try:
        defaults["order_notional_usd"] = max(1.0, float(defaults.get("order_notional_usd") or 2000.0))
    except (TypeError, ValueError):
        defaults["order_notional_usd"] = 2000.0
    try:
        # 0 = let the strategy size (equity-scaled base); >0 = fixed contracts.
        defaults["default_qty"] = max(0, int(defaults.get("default_qty") or 0))
    except (TypeError, ValueError):
        defaults["default_qty"] = 0
    defaults["only_oj_pine"] = bool(defaults.get("only_oj_pine", True))
    defaults["oj_strategy"] = str(defaults.get("oj_strategy") or _OJ_STRATEGY).strip() or _OJ_STRATEGY
    try:
        defaults["oj_tp1_exit_pct"] = min(1.0, max(0.05, float(defaults.get("oj_tp1_exit_pct") or 0.5)))
    except (TypeError, ValueError):
        defaults["oj_tp1_exit_pct"] = 0.5
    try:
        defaults["oj_tp2_exit_pct"] = min(1.0, max(0.05, float(defaults.get("oj_tp2_exit_pct") or 0.5)))
    except (TypeError, ValueError):
        defaults["oj_tp2_exit_pct"] = 0.5
    return defaults


def _normalize_ai_decision_payload(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {"ok": False, "error": "invalid ai response"}
    action = normalize_action(raw.get("action"))
    confidence = raw.get("confidence")
    try:
        confidence = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence = None
    allow = raw.get("allow")
    if allow is None:
        allow = action in ("buy", "sell")
    return {
        "ok": bool(raw.get("ok", True)),
        "action": action,
        "allow": bool(allow),
        "confidence": confidence,
        "reason": str(raw.get("reason") or "").strip(),
        "model": str(raw.get("model") or "").strip(),
        "raw": raw,
    }


def _call_ai_endpoint(url: str, payload: Dict[str, Any], timeout_sec: float, token: str = "") -> Dict[str, Any]:
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            **({"authorization": f"Bearer {token}"} if token else {}),
        },
        method="POST",
    )
    with urlopen(req, timeout=max(1.0, timeout_sec)) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return {"ok": False, "error": "non-json ai response", "body": body[:300]}
    return _normalize_ai_decision_payload(parsed)


def evaluate_dual_ai_decision(parsed_alert: Dict[str, Any]) -> Dict[str, Any]:
    """Query Codex/Claude endpoints for trade decision approval/override."""
    cfg = load_tradingview_config()
    if bool(cfg.get("trust_indicator")):
        return {"enabled": False, "status": "disabled", "reason": "trust_indicator"}
    if not bool(cfg.get("ai_enabled")):
        return {"enabled": False, "status": "disabled"}

    codex_url = str(cfg.get("codex_decision_url") or "").strip()
    claude_url = str(cfg.get("claude_decision_url") or "").strip()
    mode = str(cfg.get("ai_mode") or "consensus").strip().lower()
    timeout_sec = float(cfg.get("ai_timeout_sec") or 8.0)
    codex_token = str(cfg.get("codex_auth_token") or "").strip()
    claude_token = str(cfg.get("claude_auth_token") or "").strip()
    endpoints = [("codex", codex_url, codex_token), ("claude", claude_url, claude_token)]
    available = [(name, url, token) for name, url, token in endpoints if url]
    if not available:
        return {"enabled": True, "status": "skipped", "error": "no ai endpoints configured"}

    request_payload = {
        "symbol": parsed_alert.get("internal_symbol"),
        "tradingview_symbol": parsed_alert.get("tradingview_symbol"),
        "market": parsed_alert.get("market"),
        "action": parsed_alert.get("action"),
        "price": parsed_alert.get("price"),
        "alert_name": parsed_alert.get("alert_name"),
        "message": parsed_alert.get("message"),
        "payload": parsed_alert.get("payload") or {},
    }
    decisions: Dict[str, Dict[str, Any]] = {}
    for name, url, token in available:
        try:
            decisions[name] = _call_ai_endpoint(url, request_payload, timeout_sec, token=token)
        except Exception as exc:
            decisions[name] = {"ok": False, "allow": False, "action": None, "error": str(exc)}

    ok_votes = [d for d in decisions.values() if d.get("ok")]
    allowed_votes = [d for d in ok_votes if d.get("allow")]
    if mode == "primary":
        primary_name = "claude" if "claude" in decisions else next(iter(decisions))
        primary = decisions.get(primary_name) or {}
        action = normalize_action(primary.get("action")) or normalize_action(parsed_alert.get("action"))
        return {
            "enabled": True,
            "status": "approved" if primary.get("allow") and action else "blocked",
            "mode": mode,
            "decisions": decisions,
            "final_action": action,
            "reason": primary.get("reason") or ("primary model blocked trade" if not primary.get("allow") else ""),
        }

    # consensus/default
    if len(ok_votes) < len(available):
        return {
            "enabled": True,
            "status": "blocked",
            "mode": "consensus",
            "decisions": decisions,
            "reason": "ai endpoint error in consensus mode",
        }
    if len(allowed_votes) != len(available):
        return {
            "enabled": True,
            "status": "blocked",
            "mode": "consensus",
            "decisions": decisions,
            "reason": "consensus denied",
        }
    action_set = {normalize_action(d.get("action")) for d in allowed_votes if normalize_action(d.get("action"))}
    if len(action_set) > 1:
        return {
            "enabled": True,
            "status": "blocked",
            "mode": "consensus",
            "decisions": decisions,
            "reason": "action mismatch between ai models",
        }
    final_action = next(iter(action_set), normalize_action(parsed_alert.get("action")))
    return {
        "enabled": True,
        "status": "approved" if final_action else "blocked",
        "mode": "consensus",
        "decisions": decisions,
        "final_action": final_action,
        "reason": "" if final_action else "no actionable decision",
    }


def _parse_message_json(message: str) -> Dict[str, Any]:
    """Try to parse alert message as JSON (TradingView alert templates)."""
    text = (message or "").strip()
    if not text:
        return {}
    if text.startswith("{") and text.endswith("}"):
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {}


def normalize_action(raw: Optional[str]) -> Optional[str]:
    """Map TradingView action strings to buy/sell/close/suggest."""
    if not raw:
        return None
    val = str(raw).strip().lower()
    if val in _OJ_TP_SUGGEST_EVENTS:
        return "suggest"
    if val in _CLOSE_ACTIONS:
        return "close"
    if val in _BUY_ACTIONS:
        return "buy"
    if val in _SELL_ACTIONS:
        return "sell"
    if val == "suggest":
        return "suggest"
    return None


def _action_from_text(text: str) -> Optional[str]:
    """Infer buy/sell/close from free-form alert message."""
    lower = (text or "").lower()
    if re.search(r"\bentry\s+call\b|\bcall\b", lower) and "put" not in lower:
        return "buy"
    if re.search(r"\bentry\s+put\b|\bput\b", lower):
        return "buy"
    # TP touches are suggestions — not closes. tp_break / SL / EOD / flip are closes.
    if re.search(r"\b(tp_break|sl|eod|flip|flat|close|exit)\b", lower):
        return "close"
    if re.search(r"\b(tp1|tp2|tp3)\b", lower):
        return "suggest"
    for word in ("buy", "long", "bullish"):
        if re.search(rf"\b{word}\b", lower):
            return "buy"
    for word in ("sell", "short", "bearish"):
        if re.search(rf"\b{word}\b", lower):
            return "sell"
    return None


def _oj_event_from_merged(merged: Dict[str, Any], msg: str) -> Optional[str]:
    """Resolve OJ Pine event name from JSON fields or legacy free-text."""
    raw = str(merged.get("event") or merged.get("signal") or "").strip().lower()
    if raw in _OJ_ENTRY_EVENTS or raw in _OJ_EXIT_EVENTS or raw in _OJ_TP_SUGGEST_EVENTS:
        return "entry_call" if raw == "call" else "entry_put" if raw == "put" else raw
    right = str(merged.get("right") or "").strip().lower()
    action = str(merged.get("action") or "").strip().lower()
    if right == "call" or action in ("call", "entry_call"):
        return "entry_call"
    if right == "put" or action in ("put", "entry_put"):
        return "entry_put"
    lower = (msg or "").lower()
    if re.search(r"\bentry\s+call\b", lower) or (
        re.search(r"\bcall\b", lower) and "put" not in lower
        and not re.search(r"\b(tp1|tp2|tp3|tp_break|sl|eod|flip)\b", lower)
    ):
        return "entry_call"
    if re.search(r"\bentry\s+put\b", lower) or (
        re.search(r"\bput\b", lower)
        and not re.search(r"\b(tp1|tp2|tp3|tp_break|sl|eod|flip)\b", lower)
    ):
        return "entry_put"
    for ev in ("tp_break", "tp1", "tp2", "tp3", "eod", "flip", "sl"):
        if re.search(rf"\b{ev}\b", lower):
            return ev
    if re.search(r"\b(flat|close|exit)\b", lower):
        return "close"
    return None


def _oj_direction_for_event(event: Optional[str], merged: Dict[str, Any]) -> Optional[str]:
    if event == "entry_call":
        return "long"
    if event == "entry_put":
        return "short"
    direction = str(merged.get("direction") or "").strip().lower()
    if direction in ("long", "short"):
        return direction
    right = str(merged.get("right") or "").strip().lower()
    if right == "call":
        return "long"
    if right == "put":
        return "short"
    return None


def parse_alert_payload(body: Dict[str, Any]) -> Dict[str, Any]:
    """Extract symbol, action, price, and message from a TV webhook body."""
    merged = dict(body)
    msg = str(body.get("message") or body.get("text") or "")
    nested = _parse_message_json(msg)
    if nested:
        merged.update(nested)
    # Body itself may already be the OJ JSON object (webhook posts alert() string as JSON).
    if not nested and str(merged.get("strategy") or "").strip().lower() == _OJ_STRATEGY:
        pass

    symbol = (
        merged.get("symbol")
        or merged.get("ticker")
        or merged.get("{{ticker}}")
        or ""
    )
    tv_symbol = merged.get("tradingview_symbol") or ""
    if not tv_symbol and symbol:
        if ":" in str(symbol):
            tv_symbol = str(symbol).upper()
        else:
            cfg = load_tradingview_config()
            mapped = map_symbol_response(
                str(symbol),
                default_exchange=str(cfg.get("default_exchange") or "COINBASE"),
            )
            tv_symbol = mapped["tradingview_symbol"]

    strategy = str(merged.get("strategy") or "").strip().lower()
    oj_event = _oj_event_from_merged(merged, msg)
    if oj_event and not strategy:
        strategy = _OJ_STRATEGY

    action = normalize_action(
        merged.get("action")
        or merged.get("side")
        or merged.get("order")
        or merged.get("signal")
    )
    if oj_event in _OJ_EXIT_EVENTS:
        action = "close"
    elif oj_event in _OJ_TP_SUGGEST_EVENTS:
        action = "suggest"
    elif oj_event in _OJ_ENTRY_EVENTS:
        action = "buy"
    if not action:
        action = _action_from_text(msg) or _action_from_text(str(symbol))

    direction = _oj_direction_for_event(oj_event, merged)
    if not direction and action == "buy":
        direction = "long"
    if not direction and action == "sell":
        direction = "short"

    price_raw = merged.get("price") or merged.get("close") or merged.get("{{close}}")
    price: Optional[float] = None
    if price_raw is not None:
        try:
            price = float(price_raw)
        except (TypeError, ValueError):
            price = None

    levels: Dict[str, Optional[float]] = {}
    for key in ("sl", "tp1", "tp2", "tp3"):
        raw_lvl = merged.get(key)
        try:
            levels[key] = float(raw_lvl) if raw_lvl is not None and str(raw_lvl) != "na" else None
        except (TypeError, ValueError):
            levels[key] = None

    internal = from_tradingview(
        tv_symbol,
        default_exchange=str(load_tradingview_config().get("default_exchange") or "COINBASE"),
    )

    return {
        "tradingview_symbol": tv_symbol,
        "internal_symbol": internal["symbol"],
        "market": internal["market"],
        "exchange": internal["exchange"],
        "action": action,
        "direction": direction,
        "strategy": strategy or None,
        "event": oj_event,
        "right": str(merged.get("right") or "").strip().lower() or None,
        "entry_kind": str(merged.get("entry_kind") or "").strip() or None,
        "levels": levels,
        "price": price,
        "message": msg or str(body),
        "alert_name": merged.get("alert_name") or merged.get("name"),
        "payload": body,
    }


def market_allowed(market: str, allowed: List[str]) -> bool:
    """Check if market type is in allowed_markets config."""
    m = (market or "unknown").lower()
    if m == "stock" and "stocks" in allowed:
        return True
    if m == "crypto" and "crypto" in allowed:
        return True
    return False


def execute_alert_paper_trade(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Queue or execute a paper order from a parsed TradingView alert."""
    action = parsed.get("action")
    symbol = parsed.get("internal_symbol") or ""
    market = parsed.get("market") or "unknown"
    cfg = load_tradingview_config()
    strategy = str(parsed.get("strategy") or "").strip().lower()
    event = str(parsed.get("event") or "").strip().lower() or None
    oj_name = str(cfg.get("oj_strategy") or _OJ_STRATEGY).strip().lower()
    is_oj = strategy == oj_name or (
        event in _OJ_ENTRY_EVENTS
        or event in _OJ_EXIT_EVENTS
        or event in _OJ_TP_SUGGEST_EVENTS
    )

    if bool(cfg.get("only_oj_pine", True)) and not is_oj:
        return {
            "ok": False,
            "status": "rejected",
            "error": "only OJ 0DTE Pine alerts are allowed (strategy=oj_0dte)",
        }

    # TP1/TP2/TP3 are suggestion milestones — acknowledge, never sell.
    if event in _OJ_TP_SUGGEST_EVENTS or action == "suggest":
        return {
            "ok": True,
            "status": "suggestion",
            "event": event or action,
            "symbol": symbol,
            "message": (
                f"TP {(event or 'touch')} noted as suggestion — holding full size "
                "until EOD, SL, or prior-TP break"
            ),
            "source": "oj_0dte_pine",
        }

    if action not in ("buy", "sell", "close"):
        return {
            "ok": False,
            "status": "rejected",
            "error": "could not determine buy/sell/close action from alert",
        }
    if not symbol:
        return {
            "ok": False,
            "status": "rejected",
            "error": "could not map TradingView symbol",
        }
    if not market_allowed(market, cfg.get("allowed_markets") or []):
        return {
            "ok": False,
            "status": "rejected",
            "error": f"market {market!r} not in allowed_markets",
        }

    try:
        from trading_research.live.manual_orders import (
            close_tradingview_paper_position,
            submit_alpaca_paper_order,
            submit_tradingview_paper_order,
        )
    except ImportError as exc:
        return {"ok": False, "status": "rejected", "error": f"trading_research unavailable: {exc}"}

    try:
        from trading_research.jarvis_locked import get_jarvis_settings

        settings = get_jarvis_settings()
    except Exception:
        settings = None

    # OJ Pine always trades internal paper options (CALL/PUT), never Alpaca shares.
    broker = "internal" if is_oj else str(cfg.get("execution_broker") or "internal").strip().lower()
    source = "oj_0dte_pine" if is_oj else "tradingview_webhook"
    direction = parsed.get("direction") or ("long" if action == "buy" else "short")

    if action == "close" or event in _OJ_EXIT_EVENTS:
        return close_tradingview_paper_position(
            symbol=symbol,
            reason=f"oj_{event or 'close'}",
            qty_fraction=1.0,
            price=parsed.get("price"),
            settings=settings,
            source=source,
        )

    if broker == "alpaca" and not is_oj:
        return submit_alpaca_paper_order(
            symbol=symbol,
            action=action,
            market=market,
            price=parsed.get("price"),
            notional_usd=float(cfg.get("order_notional_usd") or 2000.0),
            settings=settings,
            source=source,
        )

    # default_qty <= 0 means "let the strategy size it" (equity-scaled base).
    qty = int(cfg.get("default_qty") or 0)
    contracts = qty if qty > 0 else None

    # Flatten any open book on this symbol before a fresh OJ entry (handles flips).
    if is_oj and action == "buy":
        close_tradingview_paper_position(
            symbol=symbol,
            reason="oj_pre_entry_flat",
            qty_fraction=1.0,
            price=parsed.get("price"),
            settings=settings,
            source=source,
        )

    return submit_tradingview_paper_order(
        symbol=symbol,
        action="buy" if action == "buy" else "sell",
        market=market,
        price=parsed.get("price"),
        direction=str(direction),
        tradingview_symbol=parsed.get("tradingview_symbol") or "",
        contracts=contracts,
        settings=settings,
        source=source,
        bypass_gates=bool(cfg.get("trust_indicator")) or is_oj,
        pattern="oj_0dte" if is_oj else None,
        levels=parsed.get("levels") if is_oj else None,
        entry_kind=parsed.get("entry_kind") if is_oj else None,
    )


def read_tunnel_url() -> Optional[str]:
    """Read public webhook URL or base from tunnel URL file if present."""
    path = Path.home() / ".openjarvis" / "tradingview-tunnel-url.txt"
    if path.is_file():
        try:
            raw = path.read_text(encoding="utf-8-sig")
            kv: Dict[str, str] = {}
            for line in raw.splitlines():
                line = line.strip().lstrip("\ufeff")
                if "=" in line:
                    key, val = line.split("=", 1)
                    kv[key.strip().lower().lstrip("\ufeff")] = val.strip()
            webhook_url = kv.get("webhook_url") or ""
            if webhook_url.startswith("http"):
                return webhook_url
            if kv.get("public_base"):
                return kv["public_base"]
            # Legacy: file contained only a bare URL on one line
            first = raw.strip().splitlines()[0] if raw.strip() else ""
            if first.startswith("http"):
                return first
        except Exception:
            pass
    cfg = load_tradingview_config()
    domain = str(cfg.get("ngrok_domain") or "").strip()
    if domain:
        return f"https://{domain}"
    return None


def build_webhook_url(secret: Optional[str] = None) -> str:
    """Full public webhook URL when tunnel or ngrok domain is configured."""
    tunnel = read_tunnel_url()
    if tunnel and "webhook/tradingview" in tunnel:
        return tunnel
    if not tunnel:
        path = "/api/trading/webhook/tradingview"
        if secret:
            return f"{path}?secret={secret}"
        return path
    base = tunnel.rstrip("/")
    if not base.endswith("/api/trading/webhook/tradingview"):
        if base.endswith("/api/trading"):
            base = f"{base}/webhook/tradingview"
        else:
            base = f"{base}/api/trading/webhook/tradingview"
    if secret and "secret=" not in base:
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}secret={secret}"
    return base


_TV_ALERTS_FILENAME = "tradingview_alerts.json"
_TV_ACCOUNT_FILENAME = "tradingview_account.json"
_LINK_RECENT_SEC = 7 * 24 * 3600


def _resolve_data_dir() -> Path:
    try:
        from trading_research.jarvis_locked import get_jarvis_settings

        return Path(get_jarvis_settings().data_dir)
    except Exception:
        pass
    env_dir = Path.home() / ".openjarvis"
    try:
        import tomllib

        cfg_path = env_dir / "trading.toml"
        if cfg_path.is_file():
            raw = tomllib.loads(cfg_path.read_bytes().decode("utf-8-sig"))
            data_dir = (raw.get("trading") or {}).get("data_dir")
            if data_dir:
                return Path(str(data_dir))
    except Exception:
        pass
    return Path(__file__).resolve().parents[3] / "trading_research" / "data"


def tv_alerts_path(data_dir: Optional[Path] = None) -> Path:
    root = data_dir if data_dir is not None else _resolve_data_dir()
    return root / _TV_ALERTS_FILENAME


def tradingview_account_path(data_dir: Optional[Path] = None) -> Path:
    root = data_dir if data_dir is not None else _resolve_data_dir()
    return root / _TV_ACCOUNT_FILENAME


def load_tradingview_account(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Load locally persisted TradingView account link preferences."""
    defaults: Dict[str, Any] = {
        "linked": False,
        "display_name": "",
        "linked_at": None,
        "link_method": "",
        "updated_at": None,
    }
    path = tradingview_account_path(data_dir)
    if not path.is_file():
        return defaults
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return defaults
        merged = dict(defaults)
        for key in defaults:
            if key in raw and raw[key] is not None:
                merged[key] = raw[key]
        merged["linked"] = bool(merged.get("linked"))
        return merged
    except Exception:
        return defaults


def save_tradingview_account(
    payload: Dict[str, Any],
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Persist TradingView account link preferences to disk."""
    path = tradingview_account_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    existing = load_tradingview_account(data_dir)
    linked = bool(payload.get("linked", existing.get("linked")))
    display_name = str(payload.get("display_name") or existing.get("display_name") or "").strip()
    link_method = str(payload.get("link_method") or existing.get("link_method") or "").strip()
    linked_at = payload.get("linked_at", existing.get("linked_at"))
    if linked and not linked_at:
        linked_at = now
    if not linked:
        linked_at = None
        display_name = ""
        link_method = ""
    record = {
        "linked": linked,
        "display_name": display_name[:120],
        "linked_at": linked_at,
        "link_method": link_method or ("embedded_widget" if linked else ""),
        "updated_at": now,
    }
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def tradingview_account_payload(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Account link status for API responses."""
    account = load_tradingview_account(data_dir)
    return {
        "linked": bool(account.get("linked")),
        "display_name": str(account.get("display_name") or ""),
        "linked_at": account.get("linked_at"),
        "link_method": str(account.get("link_method") or ""),
        "updated_at": account.get("updated_at"),
        "oauth_available": False,
        "login_method": "embedded_widget",
        "limitations": (
            "TradingView does not offer public OAuth for third-party apps. "
            "Sign in inside the embedded chart to use your TV session in this browser. "
            "Alerts and paper trades still use webhooks, not your TV account token."
        ),
    }


def load_persisted_tv_alerts(
    data_dir: Optional[Path] = None,
    *,
    max_items: int = 50,
) -> List[Dict[str, Any]]:
    """Load TradingView webhook alerts from disk."""
    path = tv_alerts_path(data_dir)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        alerts = raw.get("alerts") if isinstance(raw, dict) else raw
        if not isinstance(alerts, list):
            return []
        return list(alerts[:max_items])
    except Exception:
        return []


def save_persisted_tv_alerts(
    alerts: List[Dict[str, Any]],
    data_dir: Optional[Path] = None,
    *,
    max_items: int = 50,
) -> None:
    """Persist TradingView webhook alerts to disk."""
    path = tv_alerts_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    trimmed = list(alerts[:max_items])
    payload = {"alerts": trimmed, "updated_at": time.time()}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def alert_json_template(exchange: Optional[str] = None) -> Dict[str, Any]:
    """Example JSON for TradingView alert message field (OJ 0DTE Pine)."""
    ex = (exchange or load_tradingview_config().get("default_exchange") or "NASDAQ").upper()
    return {
        "strategy": "oj_0dte",
        "event": "entry_call",
        "symbol": f"{ex}:SOXL",
        "ticker": "{{ticker}}",
        "action": "buy",
        "direction": "long",
        "right": "call",
        "price": "{{close}}",
        "message": "OJ 0DTE Pine signal",
    }


def chart_url_for_symbol(tradingview_symbol: str) -> str:
    sym = (tradingview_symbol or "").strip().upper()
    if not sym:
        ex = str(load_tradingview_config().get("default_exchange") or "COINBASE").upper()
        sym = f"{ex}:BTCUSD"
    return f"https://www.tradingview.com/chart/?symbol={quote(sym, safe=':')}"


def chart_url_template(exchange: Optional[str] = None) -> str:
    ex = (exchange or load_tradingview_config().get("default_exchange") or "COINBASE").upper()
    return chart_url_for_symbol(f"{ex}:BTCUSD")


def tradingview_link_payload(
    alerts: List[Dict[str, Any]],
    *,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """TradingView account link status for the Setup Scanner / Trading UI."""
    cfg = load_tradingview_config()
    secret = str(cfg.get("webhook_secret") or "").strip() or None
    tunnel_url = read_tunnel_url()
    ngrok_domain = str(cfg.get("ngrok_domain") or "").strip()
    exchange = str(cfg.get("default_exchange") or "COINBASE").upper()
    now = time.time()

    recent = [
        a
        for a in alerts
        if float(a.get("received_at") or 0) >= now - _LINK_RECENT_SEC
    ]
    last_at = max((float(a.get("received_at") or 0) for a in alerts), default=0.0) or None

    linked = bool(
        tunnel_url
        or secret
        or any(float(a.get("received_at") or 0) >= now - _LINK_RECENT_SEC for a in alerts)
    )

    webhook_local = "/api/trading/webhook/tradingview"
    if secret:
        webhook_local = f"{webhook_local}?secret={secret}"

    account = tradingview_account_payload(data_dir)

    return {
        "webhook_url": build_webhook_url(secret),
        "webhook_local_path": webhook_local,
        "tunnel_configured": bool(tunnel_url),
        "tunnel_url": tunnel_url,
        "ngrok_domain": ngrok_domain,
        "default_exchange": exchange,
        "interval": str(cfg.get("interval") or "5"),
        "theme": str(cfg.get("theme") or "dark"),
        "auto_execute": bool(cfg.get("auto_execute")),
        "webhook_secret_configured": bool(secret),
        "alert_json_template": alert_json_template(exchange),
        "chart_url_template": chart_url_template(exchange),
        "linked": linked,
        "webhook_ready": linked,
        "account_linked": bool(account.get("linked")),
        "account": account,
        "recent_alert_count": len(recent),
        "last_alert_at": last_at,
        "alerts_buffered": len(alerts),
    }


def setup_row_from_tv_alert(alert: Dict[str, Any], *, default_exchange: str) -> Dict[str, Any]:
    """Map a buffered TradingView alert to a Setup Scanner row."""
    tv_symbol = str(alert.get("tradingview_symbol") or "").upper()
    internal = str(alert.get("internal_symbol") or "").strip().upper()
    if not internal and tv_symbol:
        internal = from_tradingview(tv_symbol, default_exchange=default_exchange)["symbol"]
    action = str(alert.get("action") or "").lower()
    direction = "short" if action == "sell" else "long"
    price = alert.get("price")
    alert_name = alert.get("alert_name") or "TradingView alert"
    label = str(alert.get("message") or "").strip()
    if not label:
        if price is not None:
            label = f"{action or 'signal'} @ {price}"
        else:
            label = alert_name
    mapped = map_symbol_response(internal or tv_symbol, default_exchange=default_exchange)
    return {
        "symbol": mapped.get("symbol") or internal,
        "tradingview_symbol": mapped.get("tradingview_symbol") or tv_symbol,
        "market": mapped.get("market") or alert.get("market") or "crypto",
        "direction": direction,
        "confidence": 0.75,
        "signal_score": 75.0,
        "label": label[:160],
        "tools": ["tradingview_webhook"],
        "pattern": str(alert_name)[:80],
        "scan_source": "tradingview_alert",
        "received_at": alert.get("received_at"),
        "action": action or None,
        "price": price,
        "trade_status": alert.get("trade_status"),
        "chart_url": chart_url_for_symbol(mapped.get("tradingview_symbol") or tv_symbol),
        "chart_ready": True,
        "entry_allowed": action in ("buy", "sell"),
    }


def automation_status_payload() -> Dict[str, Any]:
    """Build automation health snapshot for API and Jarvis tool."""
    cfg = load_tradingview_config()
    secret = str(cfg.get("webhook_secret") or "").strip() or None

    live_running = False
    queue_depth = 0
    try:
        from trading_research.jarvis_locked import get_jarvis_settings
        from trading_research.live.manual_orders import (
            is_live_session_running,
            manual_orders_path,
        )

        data_dir = Path(get_jarvis_settings().data_dir)
        live_running = is_live_session_running(data_dir)
        qpath = manual_orders_path(data_dir)
        if qpath.is_file():
            data = json.loads(qpath.read_text(encoding="utf-8"))
            queue_depth = sum(
                1 for o in (data.get("orders") or []) if o.get("status") == "pending"
            )
    except Exception:
        pass

    return {
        "paper_only": True,
        "auto_execute": bool(cfg.get("auto_execute")),
        "trust_indicator": bool(cfg.get("trust_indicator")),
        "only_oj_pine": bool(cfg.get("only_oj_pine", True)),
        "oj_strategy": str(cfg.get("oj_strategy") or _OJ_STRATEGY),
        "execution_broker": str(cfg.get("execution_broker") or "internal"),
        "order_notional_usd": float(cfg.get("order_notional_usd") or 2000.0),
        "allowed_markets": cfg.get("allowed_markets") or ["crypto", "stocks"],
        "default_qty": cfg.get("default_qty", 1),
        "webhook_secret_configured": bool(secret),
        "webhook_url": build_webhook_url(secret),
        "tunnel_active": bool(read_tunnel_url()),
        "live_session_running": live_running,
        "manual_order_queue_depth": queue_depth,
        "auto_switch_chart": bool(cfg.get("auto_switch_chart")),
    }


__all__ = [
    "load_tradingview_config",
    "parse_alert_payload",
    "normalize_action",
    "market_allowed",
    "execute_alert_paper_trade",
    "automation_status_payload",
    "build_webhook_url",
    "read_tunnel_url",
    "load_persisted_tv_alerts",
    "save_persisted_tv_alerts",
    "tv_alerts_path",
    "tradingview_account_path",
    "load_tradingview_account",
    "save_tradingview_account",
    "tradingview_account_payload",
    "alert_json_template",
    "chart_url_for_symbol",
    "chart_url_template",
    "tradingview_link_payload",
    "setup_row_from_tv_alert",
    "evaluate_dual_ai_decision",
]
