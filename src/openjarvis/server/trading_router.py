"""HTTP routes for live trading data and TradingView integration."""



from __future__ import annotations



import json

import logging

import os

import time

from pathlib import Path

from typing import Any, Dict, List, Optional



from fastapi import APIRouter, HTTPException, Request

from pydantic import BaseModel, Field



from openjarvis.trading.symbol_map import (

    from_tradingview,

    list_stock_exchanges,

    map_symbol_response,

    normalize_for_dedup,

    prefer_chart_symbol,

    to_tradingview,

)

from openjarvis.trading.tradingview_automation import (

    automation_status_payload,

    build_webhook_url,

    chart_url_for_symbol,

    execute_alert_paper_trade,
    evaluate_dual_ai_decision,

    load_persisted_tv_alerts,

    load_tradingview_config,

    load_tradingview_account,

    market_allowed,

    parse_alert_payload,

    save_persisted_tv_alerts,

    save_tradingview_account,

    setup_row_from_tv_alert,

    tradingview_account_payload,

    tradingview_link_payload,

)



logger = logging.getLogger(__name__)



router = APIRouter(prefix="/api/trading", tags=["trading"])

# TradingPage quick-pick chips (subset of [strategy.stocks] whitelist).
STOCK_QUICK_PICKS = ("AAPL", "MSFT", "NVDA", "SPY", "QQQ")



# In-memory ring buffer for TradingView webhook alerts (last 50).

_TV_ALERTS: List[Dict[str, Any]] = []

_TV_ALERTS_MAX = 50





def _trading_data_dir() -> Path:

    """Resolve trading data directory from trading.toml or defaults."""

    try:

        from trading_research.jarvis_locked import get_jarvis_settings



        return Path(get_jarvis_settings().data_dir)

    except ImportError:

        pass



    cfg_path = Path.home() / ".openjarvis" / "trading.toml"

    if cfg_path.is_file():

        try:

            import tomllib



            with cfg_path.open("rb") as fh:

                raw = tomllib.load(fh)

            data_dir = (raw.get("trading") or {}).get("data_dir")

            if data_dir:

                return Path(str(data_dir))

        except Exception:

            pass



    env_dir = os.environ.get("TR_DATA_DIR")

    if env_dir:

        return Path(env_dir)



    return Path(__file__).resolve().parents[3] / "trading_research" / "data"





def _read_json(name: str) -> Optional[Dict[str, Any]]:

    path = _trading_data_dir() / name

    if not path.is_file():

        return None

    try:

        with path.open(encoding="utf-8") as fh:

            return json.load(fh)

    except Exception as exc:

        logger.warning("Failed to read %s: %s", path, exc)

        return None





def _tradingview_exchange() -> str:

    return str(load_tradingview_config().get("default_exchange") or "COINBASE").upper()





def _tradingview_webhook_secret() -> Optional[str]:

    secret = load_tradingview_config().get("webhook_secret")

    if secret is not None and str(secret).strip():

        return str(secret).strip()

    return None


def _load_tv_alerts_from_disk() -> None:

    global _TV_ALERTS

    try:

        _TV_ALERTS = load_persisted_tv_alerts(_trading_data_dir(), max_items=_TV_ALERTS_MAX)

    except Exception as exc:

        logger.warning("Failed to load TradingView alerts: %s", exc)

        _TV_ALERTS = []


def _persist_tv_alerts() -> None:

    try:

        save_persisted_tv_alerts(_TV_ALERTS, _trading_data_dir(), max_items=_TV_ALERTS_MAX)

    except Exception as exc:

        logger.warning("Failed to persist TradingView alerts: %s", exc)


def _recent_tv_alert_for_symbol(symbol: str) -> Optional[Dict[str, Any]]:

    sym = (symbol or "").strip().upper()

    if not sym:

        return None

    for alert in _TV_ALERTS:

        internal = str(alert.get("internal_symbol") or "").upper()

        if internal == sym or internal.replace("-", "") == sym.replace("-", ""):

            if alert.get("price") is not None:

                return alert

    return None


def _merge_tv_alerts_into_scanner(payload: Dict[str, Any]) -> Dict[str, Any]:

    exchange = _tradingview_exchange()

    setups = list(payload.get("setups") or [])

    seen = {f"{str(r.get('symbol') or '').upper()}:{r.get('pattern')}" for r in setups}

    for alert in _TV_ALERTS[:20]:

        row = setup_row_from_tv_alert(alert, default_exchange=exchange)

        sym = str(row.get("symbol") or "").upper()

        pat = str(row.get("pattern") or "")

        key = f"{sym}:{pat}"

        if key in seen:

            continue

        seen.add(key)

        setups.insert(0, row)

    payload["setups"] = setups[:60]

    payload["count"] = len(payload["setups"])

    payload["tradingview_alert_count"] = sum(

        1 for r in payload["setups"] if r.get("scan_source") == "tradingview_alert"

    )

    return payload


_load_tv_alerts_from_disk()





def _dedupe_symbols(symbols: List[str]) -> List[Dict[str, str]]:

    """Collapse USD/USDC pairs to one chart symbol per base asset."""

    groups: Dict[str, List[str]] = {}

    for sym in symbols:

        if not sym:

            continue

        groups.setdefault(normalize_for_dedup(sym), []).append(sym.upper())



    exchange = _tradingview_exchange()

    out: List[Dict[str, str]] = []

    for base in sorted(groups):

        chosen = prefer_chart_symbol(groups[base])

        mapped = map_symbol_response(chosen, default_exchange=exchange)

        out.append(

            {

                "symbol": mapped["symbol"],

                "tradingview_symbol": mapped["tradingview_symbol"],

                "market": mapped.get("market", "unknown"),

            }

        )

    return out





class TradingViewAlert(BaseModel):

    """Payload TradingView sends from alert webhooks."""



    symbol: Optional[str] = None

    exchange: Optional[str] = None

    price: Optional[float] = None

    action: Optional[str] = None

    alert_name: Optional[str] = Field(None, alias="alert_name")

    message: Optional[str] = None

    timestamp: Optional[str] = None



    model_config = {"extra": "allow", "populate_by_name": True}





@router.get("/learning-summary")

async def trading_learning_summary() -> Dict[str, Any]:

    """Cross-model learning, refinement schedule, and current strategy params."""

    try:

        from trading_research.learning.model_store import load_model_learning

        from trading_research.learning.optimization_log import load_optimization_log

        from trading_research.learning.structure_learner import load_structure_learning

        from trading_research.learning.win_rate_optimizer import load_win_rate_optimizer

        from trading_research.jarvis_locked import get_jarvis_settings

        from trading_research.live.learning_agents_control import learning_agents_status

        from trading_research.live.refinement_daemon import refinement_summary



        settings = get_jarvis_settings()

        store = load_model_learning(settings)

        refinement = refinement_summary()

        opt_log = load_optimization_log(settings)

        last_event = opt_log.get("last_event")

        return {

            "available": True,

            "learning_active": refinement.get("learning_active", True),

            **store.summary(),

            "structure_learner": load_structure_learning(settings).summary(),

            "win_rate_optimizer": load_win_rate_optimizer(settings).summary(),

            "learning_agents": learning_agents_status(),

            "refinement": refinement,

            "last_learning_event": last_event,

        }

    except ImportError:

        return {"available": False, "error": "trading_research not installed"}

    except Exception as exc:

        logger.warning("learning-summary failed: %s", exc)

        return {"available": False, "error": str(exc)}




@router.get("/hedge-fund/desk")
async def trading_hedge_fund_desk() -> Dict[str, Any]:
    """Hedge-fund desk: observe regimes, learn edges, adapt risk — not price forecasts."""
    try:
        from trading_research.live.hedge_fund_desk import desk_snapshot

        return desk_snapshot()
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.warning("hedge-fund desk failed: %s", exc)
        return {"ok": False, "error": str(exc)}


@router.post("/hedge-fund/sweep")
async def trading_hedge_fund_sweep(force: bool = True) -> Dict[str, Any]:
    """Run market-genius backtest sweep across symbols × strategies."""
    try:
        from trading_research.live.market_genius import run_market_genius_sweep

        return run_market_genius_sweep(force=force)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.warning("hedge-fund sweep failed: %s", exc)
        return {"ok": False, "error": str(exc)}


@router.post("/hedge-fund/execute")
async def trading_hedge_fund_execute() -> Dict[str, Any]:
    """Apply genius sweep edges to live gates, Freqtrade, and entry filters."""
    try:
        from trading_research.live.genius_playbook import execute_genius_playbook

        return execute_genius_playbook(force=True)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.warning("hedge-fund execute failed: %s", exc)
        return {"ok": False, "error": str(exc)}


@router.get("/setup-scanner")
async def trading_setup_scanner() -> Dict[str, Any]:
    """Posted scout setups enriched for visual scanner."""
    try:
        from trading_research.jarvis_locked import get_jarvis_settings
        from trading_research.live.setup_chart_view import setup_scanner_snapshot

        s = get_jarvis_settings()
        payload = setup_scanner_snapshot(data_dir=Path(s.data_dir))
        exchange = _tradingview_exchange()
        for row in payload.get("setups") or []:
            sym = str(row.get("symbol") or "")
            if sym and not row.get("tradingview_symbol"):
                mapped = map_symbol_response(sym, default_exchange=exchange)
                row["tradingview_symbol"] = mapped.get("tradingview_symbol")
                row["market"] = mapped.get("market", "crypto")
            if sym and not row.get("chart_url") and row.get("tradingview_symbol"):
                row["chart_url"] = chart_url_for_symbol(str(row["tradingview_symbol"]))
        return _merge_tv_alerts_into_scanner(payload)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.warning("setup-scanner failed: %s", exc)
        return {"ok": False, "error": str(exc)}


@router.get("/setup-chart")
async def trading_setup_chart(symbol: str, pattern: str = "") -> Dict[str, Any]:
    """Candlesticks + pattern overlays + trade markers for one symbol setup."""
    try:
        from trading_research.jarvis_locked import get_jarvis_settings
        from trading_research.live.setup_chart_view import (
            build_setup_chart_payload,
            find_setup_in_feeds,
        )

        s = get_jarvis_settings()
        root = Path(s.data_dir)
        sym = (symbol or "").strip().upper()
        if not sym:
            return {"ok": False, "error": "symbol required"}
        pat = (pattern or "").strip()
        setup = find_setup_in_feeds(sym, root, pattern=pat or None) or {
            "symbol": sym,
            "direction": "long",
            "pattern": pat or None,
        }
        payload = build_setup_chart_payload(sym, setup, data_dir=root)
        tv_ref = _recent_tv_alert_for_symbol(sym)
        if payload.get("ok") and tv_ref and tv_ref.get("price") is not None:
            ref_price = float(tv_ref["price"])
            overlays = list(payload.get("overlays") or [])
            overlays.append(
                {
                    "kind": "tv_alert",
                    "price": round(ref_price, 6),
                    "label": f"TV alert @ {ref_price:.2f}",
                    "color": "#f472b6",
                }
            )
            payload["overlays"] = overlays
            payload["tv_alert_reference"] = {
                "price": ref_price,
                "received_at": tv_ref.get("received_at"),
                "action": tv_ref.get("action"),
                "tradingview_symbol": tv_ref.get("tradingview_symbol"),
            }
        return payload
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.warning("setup-chart failed: %s", exc)
        return {"ok": False, "error": str(exc)}


@router.post("/hedge-fund/check-setups")
async def trading_hedge_fund_check_setups() -> Dict[str, Any]:
    """Check scout feed setups against learned symbol movement math."""
    try:
        from trading_research.live.symbol_setup_gate import check_feed_setups

        return check_feed_setups()
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.warning("hedge-fund check-setups failed: %s", exc)
        return {"ok": False, "error": str(exc)}


@router.post("/hedge-fund/learn-symbols")
async def trading_hedge_fund_learn_symbols() -> Dict[str, Any]:
    """Learn repeatable movement math for symbols on the book."""
    try:
        from trading_research.jarvis_locked import get_jarvis_settings
        from trading_research.learning.symbol_movement_learner import learn_symbol_movements

        s = get_jarvis_settings()
        store = learn_symbol_movements(settings=s)
        summary = store.summary()
        return {"ok": True, **summary}
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.warning("hedge-fund learn-symbols failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _build_pnl_payload() -> Dict[str, Any]:
    """Aggregate PnL from live session JSON files."""
    try:
        from trading_research.live.pnl_summary import build_pnl_summary
        from trading_research.config.settings import get_settings

        s = get_settings()
        try:
            from trading_research.jarvis_locked import get_jarvis_settings

            s = get_jarvis_settings()
        except ImportError:
            pass
        return build_pnl_summary(Path(s.data_dir))
    except ImportError as exc:
        return {"available": False, "error": f"trading_research not installed: {exc}"}
    except Exception as exc:
        logger.warning("pnl summary failed: %s", exc)
        return {"available": False, "error": str(exc)}


def _alpaca_status() -> Dict[str, Any]:
    try:
        from trading_research.broker.alpaca_client import AlpacaClient
        from trading_research.config.settings import get_settings
        from trading_research.config.market_strategy import read_alpaca_toml, stocks_strategy_summary

        s = get_settings()
        keys_file = Path.home() / ".openjarvis" / "alpaca-keys.txt"
        health = AlpacaClient(s).health()
        return {
            **health,
            "keys_file": str(keys_file),
            "keys_file_exists": keys_file.is_file(),
            "config": read_alpaca_toml(),
            "stock_gates": stocks_strategy_summary(),
        }
    except Exception as exc:
        return {"configured": False, "ok": False, "error": str(exc)}


@router.get("/alpaca/status")
async def alpaca_status() -> Dict[str, Any]:
    """Alpaca connectivity, account summary, and stock gate config."""
    return _alpaca_status()


@router.get("/alpaca/quote/{symbol}")
async def alpaca_quote(symbol: str) -> Dict[str, Any]:
    """Latest Alpaca trade price for a US equity ticker."""
    try:
        from trading_research.broker.alpaca_client import AlpacaClient
        from trading_research.config.settings import get_settings

        with AlpacaClient(get_settings()) as client:
            if not client.configured:
                raise HTTPException(503, "Alpaca API keys not configured")
            price = client.latest_price(symbol)
            if price is None or price <= 0:
                raise HTTPException(404, f"No quote for {symbol.upper()}")
            return {"symbol": symbol.upper(), "price": price, "source": "alpaca"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/live-quote/{symbol}")
async def live_quote(symbol: str, market: str = "") -> Dict[str, Any]:
    """Latest live spot — Coinbase crypto, Alpaca or Yahoo stocks."""
    try:
        from trading_research.config.market_strategy import detect_market
        from trading_research.live.crypto_quotes import fetch_crypto_spot
        from trading_research.live.manual_orders import resolve_spot_price
        from trading_research.live.stock_quotes import fetch_stock_price
        from trading_research.config.settings import get_settings

        sym = (symbol or "").strip().upper()
        mkt = (market or "").strip().lower() or detect_market(sym)
        if mkt in ("stock", "stocks"):
            mkt = "stock"
        else:
            mkt = "crypto"
        s = get_settings()
        price = resolve_spot_price(sym, mkt, settings=s)
        if price <= 0:
            raise HTTPException(404, f"No live quote for {sym}")
        source = "coinbase" if mkt == "crypto" and not s.has_alpaca_credentials() else (
            "alpaca" if s.has_alpaca_credentials() else "yahoo"
        )
        if mkt == "crypto":
            from trading_research.config.market_strategy import alpaca_crypto_data_enabled
            from trading_research.live.crypto_quotes import fetch_alpaca_crypto_spot

            if alpaca_crypto_data_enabled() and fetch_alpaca_crypto_spot(sym, settings=s):
                source = "alpaca"
            else:
                source = "coinbase"
        elif s.has_alpaca_credentials() and fetch_stock_price(sym, settings=s):
            source = "alpaca"
        else:
            source = "yahoo"
        return {"symbol": sym, "market": mkt, "price": round(float(price), 8), "source": source}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/order-flow/{symbol}")
async def order_flow_snapshot(symbol: str, market: str = "") -> Dict[str, Any]:
    """Bid/ask imbalance and flow pressure for entry gating."""
    try:
        from trading_research.analysis.order_flow import fetch_order_flow
        from trading_research.config.settings import get_settings
        from trading_research.live.stock_quotes import fetch_yahoo_stock_price

        mkt = market.strip() or None
        reading = fetch_order_flow(symbol, market=mkt, settings=get_settings())
        if reading is not None:
            return reading.to_dict()
        if mkt == "stocks" or ("-" not in symbol.upper()):
            px = fetch_yahoo_stock_price(symbol)
            if px:
                return {
                    "symbol": symbol.upper(),
                    "market": "stocks",
                    "mid": px,
                    "imbalance": 0.0,
                    "pressure": "neutral",
                    "score_pct": 50.0,
                    "source": "yahoo",
                    "note": "Add Alpaca paper keys for bid/ask order flow",
                }
        raise HTTPException(404, f"order flow unavailable for {symbol}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/alpaca/bars/{symbol}")
async def alpaca_bars(symbol: str, days: float = 30) -> Dict[str, Any]:
    """OHLCV bars from Alpaca market data."""
    try:
        from trading_research.broker.alpaca_client import AlpacaClient
        from trading_research.config.settings import get_settings

        with AlpacaClient(get_settings()) as client:
            if not client.configured:
                raise HTTPException(503, "Alpaca API keys not configured")
            bars = client.stock_bars(symbol, days=days)
            return {
                "symbol": symbol.upper(),
                "count": len(bars),
                "bars": [c.to_dict() for c in bars[-500:]],
            }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/alpaca/account")
async def alpaca_account() -> Dict[str, Any]:
    """Alpaca paper account snapshot."""
    try:
        from trading_research.broker.alpaca_client import AlpacaClient
        from trading_research.config.settings import get_settings

        with AlpacaClient(get_settings()) as client:
            if not client.configured:
                raise HTTPException(503, "Alpaca API keys not configured")
            acct = client.get_account()
            return {
                "status": acct.get("status"),
                "equity": acct.get("equity"),
                "cash": acct.get("cash"),
                "buying_power": acct.get("buying_power"),
                "portfolio_value": acct.get("portfolio_value"),
                "pattern_day_trader": acct.get("pattern_day_trader"),
            }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/pnl")
async def trading_pnl() -> Dict[str, Any]:
    """Full PnL summary: equity, realized/session/today, per-market breakdown."""
    try:
        from trading_research.live.trade_ledger_sync import sync_trade_ledger_file

        sync_trade_ledger_file()
    except Exception:
        pass
    payload = _build_pnl_payload()
    payload["alpaca"] = _alpaca_status()
    payload["data_dir"] = str(_trading_data_dir())
    return payload


@router.get("/strategy-performance")
async def trading_strategy_performance() -> Dict[str, Any]:
    """Alpha score index and time series for dashboard Strategy Performance chart."""
    try:
        from trading_research.live.strategy_performance import build_strategy_performance

        return build_strategy_performance()
    except Exception as exc:
        logger.warning("strategy performance failed: %s", exc)
        return {"available": False, "alpha_index": 0.0, "series": [], "error": str(exc)}


@router.get("/status")

async def trading_status() -> Dict[str, Any]:

    """Live session status and ledger summary."""

    state = _read_json("live_session_state.json") or {}

    ledger = _read_json("live_trade_ledger.json") or {}

    pnl = _build_pnl_payload()

    return {

        "available": bool(state or ledger),

        "data_dir": str(_trading_data_dir()),

        "pnl": pnl,

        "alpaca": _alpaca_status(),

        "session": {

            "running": bool(state.get("running")),

            "mode": state.get("mode", "PAPER_ONLY"),

            "equity": pnl.get("equity") or state.get("equity") or ledger.get("equity"),

            "return_pct": pnl.get("return_pct") or state.get("return_pct") or ledger.get("return_pct"),

            "open_positions": pnl.get("open_positions") or state.get("open_positions") or ledger.get("open_count", 0),

            "closed_trades": pnl.get("closed_trades") or state.get("closed_trades") or ledger.get("closed_count", 0),

            "session_pnl": pnl.get("session_pnl") or state.get("session_pnl") or ledger.get("session_pnl"),

            "realized_pnl": pnl.get("realized_pnl"),

            "unrealized_pnl": pnl.get("unrealized_pnl"),

            "today_pnl": pnl.get("today_pnl"),

            "win_rate_pct": pnl.get("win_rate_pct"),

            "wins": pnl.get("wins"),

            "losses": pnl.get("losses"),

            "kill_switch": bool(state.get("kill_switch")),

            "updated_at": state.get("updated_at") or ledger.get("updated_at"),

        },

        "ledger": {

            "starting_equity": ledger.get("starting_equity") or pnl.get("starting_equity"),

            "equity": ledger.get("equity") or pnl.get("equity"),

            "ledger_realized_pnl": ledger.get("ledger_realized_pnl") or pnl.get("realized_pnl"),

            "return_pct": ledger.get("return_pct") or pnl.get("return_pct"),

        },

        "markets": pnl.get("markets"),

    }





@router.get("/positions")

async def trading_positions() -> Dict[str, Any]:

    """Open positions from the live trade ledger."""

    ledger = _read_json("live_trade_ledger.json") or {}

    state = _read_json("live_session_state.json") or {}

    snapshot = _read_json("live_session_snapshot.json") or {}

    exchange = _tradingview_exchange()



    trades = ledger.get("trades") or []

    open_trades = [t for t in trades if (t.get("status") or "").upper() == "OPEN"]

    if not open_trades:
        open_trades = ledger.get("open") or []



    detail_by_sym: Dict[str, Any] = {}
    for od in state.get("open_detail") or []:
        sym = str(od.get("symbol") or "").upper()
        if sym:
            detail_by_sym[sym] = od

    snap_by_id: Dict[str, Any] = {}
    for pos in snapshot.get("positions") or []:
        pid = str(pos.get("id") or "")
        if pid:
            snap_by_id[pid] = pos

    from trading_research.live.trade_display import live_position_metrics_for_row, position_entry_context

    _ctx_keys = (
        "bought_at", "bought_at_ts", "exit_plan",
        "bars_held", "max_hold_bars", "bars_remaining", "kind",
    )
    _live_keys = (
        "spot", "mark_premium", "entry_premium", "market_value_usd",
        "entry_cost_usd", "unrealized_pnl", "unrealized", "worth_line",
    )

    positions = []

    for i, trade in enumerate(open_trades, start=1):

        sym = str(trade.get("symbol") or "")

        mapped = map_symbol_response(sym, default_exchange=exchange)

        od = detail_by_sym.get(sym.upper(), {})

        tid = str(trade.get("trade_id") or trade.get("id") or "")
        snap_t = snap_by_id.get(tid) or {}
        ctx = position_entry_context(snap_t or trade)
        for k in _ctx_keys:
            if od.get(k) is not None:
                ctx[k] = od[k]

        live_m: Dict[str, Any] = {}
        try:
            live_m = live_position_metrics_for_row(trade, snap_t or None)
        except Exception:
            logger.debug("live position metrics failed for %s", sym, exc_info=True)

        nb = None
        meta = trade.get("meta") if isinstance(trade.get("meta"), dict) else {}
        if isinstance(meta.get("nautilus_backtest"), dict):
            nb = meta["nautilus_backtest"]
        if nb is None:
            try:
                from trading_research.live.freqtrade_nautilus import enrich_symbols_with_nautilus

                nb = enrich_symbols_with_nautilus([sym]).get(sym)
            except Exception:
                nb = None

        qty_s = str(trade.get("qty") or "2x BUY CALL")

        positions.append(

            {

                **trade,

                "n": trade.get("n") or i,

                "tradingview_symbol": mapped["tradingview_symbol"],

                "market": mapped.get("market", "unknown"),

                "entry_cost_usd": live_m.get("entry_cost_usd") or od.get("entry_cost_usd") or trade.get("entry_cost_usd"),

                "market_value_usd": live_m.get("market_value_usd") or od.get("market_value_usd") or trade.get("market_value_usd"),

                "mark_premium": live_m.get("mark_premium") or od.get("mark_premium") or trade.get("mark_premium"),

                "spot": live_m.get("spot"),

                "unrealized_pnl": (
                    live_m.get("unrealized_pnl")
                    if live_m.get("unrealized_pnl") is not None
                    else od.get("unrealized_pnl")
                    if od.get("unrealized_pnl") is not None
                    else trade.get("pnl")
                ),

                "unrealized": live_m.get("unrealized") or od.get("unrealized") or trade.get("unrealized"),

                "live_mark": bool(live_m),

                "qty": qty_s if isinstance(trade.get("qty"), (int, float)) else trade.get("qty") or qty_s,

                **ctx,

                **({"nautilus_backtest": nb} if nb else {}),

            }

        )



    return {

        "count": len(positions),

        "positions": positions,

        "open_detail": state.get("open_detail") or [],

    }


@router.get("/ledger-trades")

async def trading_ledger_trades() -> Dict[str, Any]:

    """All-time open/closed trades — merged alert archives, book never wiped on restart."""

    try:

        from trading_research.live.all_time_trades import build_all_time_payload

        from trading_research.live.trade_ledger_sync import sync_trade_ledger_file

        sync_trade_ledger_file()

        payload = build_all_time_payload()

        closed = payload.get("closed") or []

        try:
            from trading_research.jarvis_locked import get_jarvis_settings
            from trading_research.live.strategy_display import (
                build_strategy_chart_series,
                build_strategy_closed_rows,
                build_strategy_display,
            )

            s = get_jarvis_settings()
            data_dir = Path(s.data_dir)
            strat = build_strategy_display(data_dir)
            if strat and strat.get("active"):
                strategy_closed = build_strategy_closed_rows(data_dir, settings=s)
                charts = build_strategy_chart_series(
                    strategy_closed,
                    starting_equity=float(payload.get("starting_equity") or s.starting_equity or 10000),
                )
                payload["strategy_display"] = strat
                payload["strategy_charts"] = charts
                payload["closed_strategy"] = strategy_closed
                payload["closed_count_strategy"] = len(strategy_closed)
                payload["closed_count_raw"] = len(closed)
                payload["wins"] = strat.get("wins")
                payload["losses"] = strat.get("losses")
                payload["win_rate_pct"] = strat.get("win_rate_pct")
                payload["ledger_realized_pnl"] = strat.get("realized_pnl")
                payload["equity"] = strat.get("equity")
                payload["return_pct"] = strat.get("return_pct")
                closed = strategy_closed
        except Exception:
            pass

        for i, row in enumerate(closed, start=1):

            row["n"] = i

        payload["closed"] = closed
        payload["closed_count"] = len(closed)

        return payload

    except Exception:

        ledger = _read_json("live_trade_ledger.json") or {}

        trades = ledger.get("trades") or []

        open_trades = [t for t in trades if (t.get("status") or "").upper() == "OPEN"]

        closed_trades = [t for t in trades if (t.get("status") or "").upper() == "CLOSED"]

        return {

            "available": bool(ledger),

            "all_time": ledger.get("all_time", False),

            "starting_equity": ledger.get("starting_equity"),

            "equity": ledger.get("equity"),

            "ledger_realized_pnl": ledger.get("ledger_realized_pnl"),

            "session_pnl": ledger.get("session_pnl"),

            "return_pct": ledger.get("return_pct"),

            "open_count": len(open_trades),

            "closed_count": len(closed_trades),

            "wins": ledger.get("wins"),

            "losses": ledger.get("losses"),

            "win_rate_pct": ledger.get("win_rate_pct"),

            "open": open_trades,

            "closed": closed_trades,

            "updated_at": ledger.get("updated_at"),

        }


def _learner_context() -> Optional[Dict[str, Any]]:

    snap = _read_json("live_session_snapshot.json") or {}

    return snap.get("learner")





@router.get("/hot-symbols")

async def trading_hot_symbols() -> Dict[str, Any]:

    """Breakout scanner hot candidates."""

    hot = _read_json("breakout_hot.json") or {}

    exchange = _tradingview_exchange()

    candidates = hot.get("candidates") or []

    learner = _learner_context()



    try:

        from trading_research.live.hot_win_prob import enrich_hot_candidate

    except ImportError:

        enrich_hot_candidate = None  # type: ignore[assignment]



    items = []

    seen: set[str] = set()

    for c in candidates:

        sym = str(c.get("symbol") or "")

        base = normalize_for_dedup(sym)

        if base in seen:

            continue

        seen.add(base)

        mapped = map_symbol_response(sym, default_exchange=exchange)

        row = {

            "symbol": sym,

            "tradingview_symbol": mapped["tradingview_symbol"],

            "market": mapped.get("market", "crypto"),

            "pattern": c.get("pattern"),

            "direction": c.get("direction"),

            "kind": c.get("kind"),

            "strength": c.get("strength"),

            "spot": c.get("spot"),

            "spot_fmt": c.get("spot_fmt"),

            "reason": c.get("reason"),

            "spread_pct": c.get("spread_pct"),

        }

        if enrich_hot_candidate is not None:

            try:

                from trading_research.jarvis_locked import get_jarvis_settings

                tr_settings = get_jarvis_settings()

            except ImportError:

                tr_settings = None

            row = enrich_hot_candidate(

                {**c, **row},

                learner=learner,

                settings=tr_settings,

            )

        try:
            from trading_research.live.freqtrade_nautilus import enrich_symbols_with_nautilus

            nb = enrich_symbols_with_nautilus([sym]).get(sym)
            if nb:
                row["nautilus_backtest"] = nb
        except Exception:
            pass

        items.append(row)



    return {

        "updated_at": hot.get("updated_at"),

        "count": len(items),

        "candidates": items,

        "mode": "PAPER_ONLY",

    }





@router.get("/scout-feed")
async def trading_scout_feed(include_nautilus: bool = False) -> Dict[str, Any]:
    """Market scout setup alerts (patterns + indicators + SMC)."""
    feed = _read_json("market_scout_feed.json") or {}
    exchange = _tradingview_exchange()
    setups = []
    for row in feed.get("setups") or []:
        sym = str(row.get("symbol") or "")
        if not sym:
            continue
        mapped = map_symbol_response(sym, default_exchange=exchange)
        item = {
            **row,
            "tradingview_symbol": mapped["tradingview_symbol"],
            "market": mapped.get("market", "crypto"),
        }
        if include_nautilus:
            try:
                from trading_research.nautilus.backtest_gate import (
                    attach_validation_summary,
                    cached_validations_for_symbols,
                )

                cached = cached_validations_for_symbols([sym]).get("validations", {})
                if sym in cached:
                    item["nautilus_backtest"] = cached[sym]
            except Exception:
                pass
        setups.append(item)
    return {
        "updated_at": feed.get("updated_at"),
        "count": len(setups),
        "setups": setups,
        "hot_agreement": feed.get("hot_agreement") or [],
    }


@router.get("/breakout-test-scout-feed")
async def trading_breakout_test_scout_feed() -> Dict[str, Any]:
    """Strict up/down breakout candidates — TEST ONLY, no live orders."""
    feed = _read_json("breakout_test_scout_feed.json") or {}
    algo = _read_json("breakout_test_algorithm.json") or {}
    exchange = _tradingview_exchange()
    setups = []
    for row in feed.get("setups") or []:
        sym = str(row.get("symbol") or "")
        if not sym:
            continue
        mapped = map_symbol_response(sym, default_exchange=exchange)
        setups.append(
            {
                **row,
                "tradingview_symbol": mapped["tradingview_symbol"],
                "market": mapped.get("market", "crypto"),
            }
        )
    return {
        "test_only": True,
        "live_orders": False,
        "updated_at": feed.get("updated_at"),
        "count": len(setups),
        "setups": setups,
        "watchlist": feed.get("watchlist") or [],
        "algorithm": algo.get("winner_profile") or {},
        "algorithm_summary": {
            "min_strength_up": algo.get("min_strength_up"),
            "min_strength_down": algo.get("min_strength_down"),
            "min_test_score_pct": algo.get("min_test_score_pct"),
            "direction_bias": algo.get("direction_bias"),
            "optimizations": algo.get("optimizations"),
        },
    }


@router.get("/breakout-test-scout-status")
async def trading_breakout_test_scout_status() -> Dict[str, Any]:
    """Breakout test scout heartbeat (TEST ONLY)."""
    state = _read_json("breakout_test_scout_state.json") or {}
    return {
        "test_only": True,
        "live_orders": False,
        "running": bool(state.get("running")),
        "updated_at": state.get("updated_at"),
        "breakout_hits": state.get("breakout_hits", 0),
        "passed_test_gate": state.get("passed_test_gate", 0),
        "algorithm": state.get("algorithm") or {},
        "note": state.get("note", ""),
    }


@router.get("/news-scout-feed")
async def trading_news_scout_feed() -> Dict[str, Any]:
    """News/media scout headline sentiment setups."""
    feed = _read_json("news_media_scout_feed.json") or {}
    state = _read_json("news_media_scout_state.json") or {}
    exchange = _tradingview_exchange()
    setups = []
    for row in feed.get("setups") or []:
        sym = str(row.get("symbol") or "")
        if not sym:
            continue
        mapped = map_symbol_response(sym, default_exchange=exchange)
        setups.append(
            {
                **row,
                "tradingview_symbol": mapped["tradingview_symbol"],
                "market": mapped.get("market", "crypto"),
            }
        )
    return {
        "updated_at": feed.get("updated_at"),
        "running": bool(state.get("running")),
        "count": len(setups),
        "setups": setups,
        "exit_watch": feed.get("exit_watch") or [],
        "hold_boost": feed.get("hold_boost") or [],
        "held_symbols": feed.get("held_symbols") or [],
    }


@router.get("/qlib-signals")
async def trading_qlib_signals() -> Dict[str, Any]:
    """Qlib ML signal bus (options gate, news tilt, Freqtrade bias)."""
    payload = _read_json("qlib_signals.json") or {}
    from trading_research.config.market_strategy import read_qlib_signals_toml

    cfg = read_qlib_signals_toml()
    symbols = payload.get("symbols") or {}
    return {
        "enabled": cfg.get("enabled", True),
        "updated_at": payload.get("updated_at"),
        "as_of_date": payload.get("as_of_date"),
        "global_bias": payload.get("global_bias"),
        "source": payload.get("source"),
        "symbol_count": len(symbols) if isinstance(symbols, dict) else 0,
        "symbols": symbols,
        "errors": payload.get("errors") or {},
        "config": {
            "min_confidence_pct": cfg.get("min_confidence_pct"),
            "apply_to_options_gate": cfg.get("apply_to_options_gate"),
            "apply_to_news_macro": cfg.get("apply_to_news_macro"),
            "apply_to_freqtrade": cfg.get("apply_to_freqtrade"),
            "block_misaligned": cfg.get("block_misaligned"),
        },
    }


@router.post("/qlib-signals/refresh")
async def trading_qlib_signals_refresh() -> Dict[str, Any]:
    """Force refresh qlib_signals.json via Qlib LightGBM job."""
    from trading_research.jarvis_locked import get_jarvis_settings
    from trading_research.scripts.run_qlib_signals import run_qlib_signal_job

    settings = get_jarvis_settings()
    return run_qlib_signal_job(data_dir=Path(settings.data_dir), force=True)


@router.get("/kronos-signals")
async def trading_kronos_signals() -> Dict[str, Any]:
    """Kronos foundation-model forecast bus (direction predictor + optional gate)."""
    payload = _read_json("kronos_signals.json") or {}
    from trading_research.config.market_strategy import read_kronos_signals_toml

    cfg = read_kronos_signals_toml()
    symbols = payload.get("symbols") or {}
    return {
        "enabled": cfg.get("enabled", True),
        "updated_at": payload.get("updated_at"),
        "global_bias": payload.get("global_bias"),
        "source": payload.get("source"),
        "model": payload.get("model"),
        "symbol_count": len(symbols) if isinstance(symbols, dict) else 0,
        "symbols": symbols,
        "errors": payload.get("errors") or {},
        "config": {
            "min_confidence_pct": cfg.get("min_confidence_pct"),
            "apply_to_direction_predictor": cfg.get("apply_to_direction_predictor"),
            "apply_to_options_gate": cfg.get("apply_to_options_gate"),
            "block_misaligned": cfg.get("block_misaligned"),
            "refresh_hours": cfg.get("refresh_hours"),
        },
    }


@router.post("/kronos-signals/refresh")
async def trading_kronos_signals_refresh() -> Dict[str, Any]:
    """Force refresh kronos_signals.json via Kronos forecast job."""
    from trading_research.jarvis_locked import get_jarvis_settings
    from trading_research.scripts.run_kronos_signals import run_kronos_signal_job

    settings = get_jarvis_settings()
    return run_kronos_signal_job(data_dir=Path(settings.data_dir), force=True)


@router.get("/scout-status")
async def trading_scout_status() -> Dict[str, Any]:
    """Market scout agent heartbeat and per-scout stats."""
    state = _read_json("market_scout_state.json") or {}
    running = bool(state.get("running"))
    return {
        "running": running,
        "updated_at": state.get("updated_at"),
        "started_at": state.get("started_at"),
        "universe": state.get("universe", 0),
        "setup_count": state.get("setup_count", 0),
        "scouts": state.get("scouts") or [],
        "note": state.get("note", ""),
        "pid": state.get("pid"),
    }


@router.get("/chart-specialist")
async def trading_chart_specialist() -> Dict[str, Any]:
    """Bullish/bearish pattern setups from the chart specialist agent."""
    feed = _read_json("chart_specialist_feed.json") or {}
    exchange = _tradingview_exchange()
    setups = []
    for row in feed.get("setups") or []:
        sym = str(row.get("symbol") or "")
        if not sym:
            continue
        mapped = map_symbol_response(sym, default_exchange=exchange)
        setups.append(
            {
                **row,
                "tradingview_symbol": mapped["tradingview_symbol"],
                "market": mapped.get("market", "crypto"),
            }
        )
    reports = feed.get("reports") or []
    return {
        "updated_at": feed.get("updated_at"),
        "agent": feed.get("agent", "chart_specialist"),
        "symbols_scanned": feed.get("symbols_scanned", 0),
        "reports_count": feed.get("reports_count", len(reports)),
        "bullish_count": feed.get("bullish_count", 0),
        "bearish_count": feed.get("bearish_count", 0),
        "count": len(setups),
        "setups": setups,
        "reports": reports,
    }


@router.get("/chart-specialist-status")
async def trading_chart_specialist_status() -> Dict[str, Any]:
    """Chart specialist daemon heartbeat and config."""
    try:
        from trading_research.config.market_strategy import read_chart_specialist_toml
        from trading_research.live.chart_specialist_control import chart_specialist_status

        return {
            "available": True,
            **chart_specialist_status(),
            "config": read_chart_specialist_toml(),
        }
    except ImportError as exc:
        return {"available": False, "error": f"trading_research not installed: {exc}"}
    except Exception as exc:
        logger.warning("chart-specialist-status failed: %s", exc)
        return {"available": False, "error": str(exc)}


def _attach_nautilus_trader_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from trading_research.live.freqtrade_nautilus import nautilus_summary_for_trader

        payload["nautilus"] = nautilus_summary_for_trader()
    except Exception:
        pass
    return payload


@router.get("/auto-status")
async def trading_auto_status() -> Dict[str, Any]:
    """Persistent auto buy/sell rules, daemon PID, and today's action counts."""
    try:
        from trading_research.live.auto_trader import auto_trader_summary
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"trading_research not available: {exc}",
        ) from exc
    return _attach_nautilus_trader_summary(auto_trader_summary())


class PaperOrderRequest(BaseModel):

    """Manual paper order from the Trading UI (no live routing)."""



    symbol: str

    action: str = Field(..., description="buy or sell")

    source: str = "ui_hot_symbol"

    market: Optional[str] = None

    price: Optional[float] = None

    tradingview_symbol: Optional[str] = None





@router.post("/paper-order")

async def trading_paper_order(body: PaperOrderRequest) -> Dict[str, Any]:

    """Queue or execute a paper-only option leg for any mapped symbol."""

    symbol = body.symbol.strip()

    action = (body.action or "").strip().lower()

    if not symbol:

        raise HTTPException(status_code=400, detail="symbol required")

    if action not in ("buy", "sell"):

        raise HTTPException(status_code=400, detail="action must be buy or sell")



    exchange = _tradingview_exchange()

    mapped = map_symbol_response(symbol, default_exchange=exchange)

    internal = mapped.get("symbol") or symbol

    market = body.market or mapped.get("market") or "crypto"

    tv_symbol = body.tradingview_symbol or mapped.get("tradingview_symbol") or symbol



    tv_cfg = load_tradingview_config()

    if not market_allowed(market, tv_cfg.get("allowed_markets") or []):

        raise HTTPException(

            status_code=400,

            detail=f"market {market!r} not in allowed_markets",

        )



    try:

        from trading_research.live.manual_orders import submit_manual_paper_order

    except ImportError as exc:

        raise HTTPException(

            status_code=503,

            detail=f"trading_research not available: {exc}",

        ) from exc



    try:

        result = submit_manual_paper_order(

            internal,

            action,

            source=body.source or "ui_hot_symbol",

            market=market,

            price=body.price,

            tradingview_symbol=tv_symbol,

        )

    except Exception as exc:

        logger.warning("paper-order failed: %s", exc)

        raise HTTPException(status_code=500, detail=str(exc)) from exc



    if not result.get("ok"):

        raise HTTPException(status_code=400, detail=result.get("error", "order rejected"))

    return result





@router.get("/symbols")

async def trading_symbols() -> Dict[str, Any]:

    """All symbols tracked by the live session (deduped for charting)."""

    snapshot = _read_json("live_session_snapshot.json") or {}

    state = _read_json("live_session_state.json") or {}

    ledger = _read_json("live_trade_ledger.json") or {}



    raw: List[str] = []

    last_bar = snapshot.get("last_bar_ts") or {}

    raw.extend(last_bar.keys())



    for detail in state.get("open_detail") or []:

        sym = detail.get("symbol")

        if sym:

            raw.append(str(sym))



    for trade in ledger.get("trades") or []:

        sym = trade.get("symbol")

        if sym:

            raw.append(str(sym))



    deduped = _dedupe_symbols(raw)

    return {"count": len(deduped), "symbols": deduped}





@router.get("/symbol-map/{symbol}")

async def trading_symbol_map(symbol: str) -> Dict[str, str]:

    """Map one pair symbol or TV ticker to TradingView format."""

    if not symbol.strip():

        raise HTTPException(status_code=400, detail="symbol required")

    return map_symbol_response(symbol, default_exchange=_tradingview_exchange())





@router.get("/config")

async def trading_config() -> Dict[str, Any]:

    """TradingView widget settings for the frontend."""

    tv_cfg = load_tradingview_config()

    exchange = _tradingview_exchange()

    interval = str(tv_cfg.get("interval") or "5")

    theme = str(tv_cfg.get("theme") or "dark")

    secret = _tradingview_webhook_secret()



    default_symbol = "COINBASE:BTCUSD"

    positions = await trading_positions()

    if positions["positions"]:

        default_symbol = positions["positions"][0]["tradingview_symbol"]

    else:

        hot = await trading_hot_symbols()

        if hot["candidates"]:

            default_symbol = hot["candidates"][0]["tradingview_symbol"]



    stock_gates: Dict[str, Any] = {}
    crypto_gates: Dict[str, Any] = {}
    trade_modes: Dict[str, Any] = {}
    example_stock_symbols: List[Dict[str, str]] = []
    try:
        from trading_research.config.market_strategy import (
            crypto_strategy_summary,
            stocks_strategy_summary,
            trade_modes_summary,
        )

        stock_gates = stocks_strategy_summary()
        crypto_gates = crypto_strategy_summary()
        trade_modes = trade_modes_summary()
        whitelist = {
            str(t).strip().upper()
            for t in (stock_gates.get("symbol_whitelist") or [])
            if str(t).strip()
        }
        for ticker in STOCK_QUICK_PICKS:
            if whitelist and ticker not in whitelist:
                continue
            mapped = map_symbol_response(ticker, default_exchange=exchange)
            example_stock_symbols.append(
                {
                    "symbol": mapped["symbol"],
                    "tradingview_symbol": mapped["tradingview_symbol"],
                    "exchange": mapped.get("exchange") or "NASDAQ",
                    "market": mapped.get("market") or "stock",
                }
            )
    except ImportError:
        pass

    return {

        "default_exchange": exchange,

        "default_symbol": default_symbol,

        "interval": interval,

        "theme": theme,

        "webhook_url": build_webhook_url(secret),

        "webhook_secret_configured": bool(secret),

        "auto_execute": bool(tv_cfg.get("auto_execute")),

        "allowed_markets": tv_cfg.get("allowed_markets") or ["crypto", "stocks"],

        "auto_switch_chart": bool(tv_cfg.get("auto_switch_chart")),

        "paper_only": True,

        "stock_exchanges": list_stock_exchanges(),

        "crypto_exchanges": ["COINBASE", "BINANCE", "KRAKEN", "BITSTAMP", "GEMINI"],

        "example_stock_symbols": example_stock_symbols,

        "stock_gates": stock_gates,

        "crypto_gates": crypto_gates,

        "trade_modes": trade_modes,

    }





@router.get("/tradingview/link")

async def trading_tradingview_link() -> Dict[str, Any]:

    """TradingView account link status, webhook URL, and alert templates."""

    return tradingview_link_payload(_TV_ALERTS, data_dir=_trading_data_dir())




@router.get("/tradingview/account")

async def trading_tradingview_account_get() -> Dict[str, Any]:

    """TradingView account link preferences (local, no OAuth token)."""

    return tradingview_account_payload(data_dir=_trading_data_dir())




class TradingViewAccountBody(BaseModel):

    """Link or update TradingView account preferences after embedded-widget sign-in."""

    action: str = "link"

    display_name: Optional[str] = None

    confirmed_in_widget: bool = False




@router.post("/tradingview/account")

async def trading_tradingview_account_post(body: TradingViewAccountBody) -> Dict[str, Any]:

    """Persist TradingView account link state after user confirms embedded chart sign-in."""

    action = (body.action or "link").strip().lower()

    if action in {"unlink", "disconnect", "clear"}:

        record = save_tradingview_account({"linked": False}, data_dir=_trading_data_dir())

        return {"ok": True, "account": record}



    if not body.confirmed_in_widget:

        raise HTTPException(

            status_code=400,

            detail="Confirm that you signed in via the embedded TradingView chart",

        )



    display_name = (body.display_name or "").strip()

    record = save_tradingview_account(

        {

            "linked": True,

            "display_name": display_name or "TradingView user",

            "link_method": "embedded_widget",

        },

        data_dir=_trading_data_dir(),

    )

    return {"ok": True, "account": record}




@router.get("/automation-status")

async def trading_automation_status() -> Dict[str, Any]:

    """TradingView ↔ Jarvis automation health and linkage status."""

    status = automation_status_payload()

    status["alerts_buffered"] = len(_TV_ALERTS)

    if _TV_ALERTS:

        latest = _TV_ALERTS[0]

        status["last_alert"] = {

            "received_at": latest.get("received_at"),

            "tradingview_symbol": latest.get("tradingview_symbol"),

            "action": latest.get("action"),

            "trade_status": latest.get("trade_status"),

            "internal_symbol": latest.get("internal_symbol"),

        }

    else:

        status["last_alert"] = None

    return status





class ExecuteAlertRequest(BaseModel):

    """Re-run paper trade for a buffered TradingView alert."""



    tradingview_symbol: Optional[str] = None

    index: int = 0





@router.post("/execute-tradingview-alert")

async def execute_tradingview_alert(body: ExecuteAlertRequest) -> Dict[str, Any]:

    """Execute or re-execute paper trade for a recent TradingView alert."""

    if not _TV_ALERTS:

        raise HTTPException(status_code=404, detail="no buffered alerts")



    entry: Optional[Dict[str, Any]] = None

    if body.tradingview_symbol:

        sym = body.tradingview_symbol.upper()

        for alert in _TV_ALERTS:

            if (alert.get("tradingview_symbol") or "").upper() == sym:

                entry = alert

                break

    else:

        idx = max(0, min(body.index, len(_TV_ALERTS) - 1))

        entry = _TV_ALERTS[idx]



    if not entry:

        raise HTTPException(status_code=404, detail="alert not found")



    parsed = {

        "tradingview_symbol": entry.get("tradingview_symbol"),

        "internal_symbol": entry.get("internal_symbol"),

        "market": entry.get("market"),

        "action": entry.get("action"),

        "direction": entry.get("direction"),

        "strategy": entry.get("strategy"),

        "event": entry.get("event"),

        "price": entry.get("price"),

        "message": entry.get("message"),

        "payload": entry.get("payload") or {},

    }

    if not parsed.get("internal_symbol") or not parsed.get("action") or (
        not parsed.get("strategy") and not parsed.get("event")
    ):

        parsed = parse_alert_payload(entry.get("payload") or {})



    result = execute_alert_paper_trade(parsed)

    entry["trade_status"] = result.get("status") or ("executed" if result.get("ok") else "rejected")

    entry["order_result"] = result

    _persist_tv_alerts()

    return {"ok": result.get("ok", False), "alert": entry, "order": result}





@router.post("/webhook/tradingview")

async def tradingview_webhook(request: Request) -> Dict[str, Any]:

    """Receive TradingView alert webhooks and optionally auto-execute paper trades."""

    expected = _tradingview_webhook_secret()

    if expected:

        provided = (

            request.query_params.get("secret")

            or request.query_params.get("token")

            or request.headers.get("x-webhook-secret")

            or request.headers.get("x-tradingview-secret")

        )

        if provided != expected:

            raise HTTPException(status_code=401, detail="invalid or missing webhook secret")



    body: Dict[str, Any]

    try:

        body = await request.json()

    except Exception:

        raw = (await request.body()).decode("utf-8", errors="replace")

        body = {"message": raw}



    parsed = parse_alert_payload(body)
    ai_result = evaluate_dual_ai_decision(parsed)
    if ai_result.get("enabled"):
        entry_ai = {
            "ai_status": ai_result.get("status"),
            "ai_mode": ai_result.get("mode"),
            "ai_reason": ai_result.get("reason"),
        }
        final_action = ai_result.get("final_action")
        if final_action:
            parsed["action"] = final_action

    tv_symbol = parsed.get("tradingview_symbol") or ""

    if not tv_symbol:

        symbol = body.get("symbol") or body.get("ticker") or ""

        if symbol:

            if ":" in str(symbol):

                tv_symbol = str(symbol).upper()

            else:

                tv_symbol = to_tradingview(str(symbol), default_exchange=_tradingview_exchange())

            parsed["tradingview_symbol"] = tv_symbol

            if not parsed.get("internal_symbol"):

                internal = from_tradingview(tv_symbol, default_exchange=_tradingview_exchange())

                parsed["internal_symbol"] = internal["symbol"]

                parsed["market"] = internal["market"]



    entry: Dict[str, Any] = {

        "received_at": time.time(),

        "tradingview_symbol": tv_symbol,

        "internal_symbol": parsed.get("internal_symbol"),

        "market": parsed.get("market"),

        "action": parsed.get("action"),

        "direction": parsed.get("direction"),

        "strategy": parsed.get("strategy"),

        "event": parsed.get("event"),

        "price": parsed.get("price"),

        "message": parsed.get("message"),

        "alert_name": parsed.get("alert_name"),

        "payload": body,

        "trade_status": "received",

    }
    if ai_result.get("enabled"):
        entry.update(entry_ai)



    tv_cfg = load_tradingview_config()

    order_result: Optional[Dict[str, Any]] = None

    if ai_result.get("enabled") and ai_result.get("status") != "approved":
        entry["trade_status"] = "ai_blocked"
    elif tv_cfg.get("auto_execute") and parsed.get("action"):

        order_result = execute_alert_paper_trade(parsed)

        entry["order_result"] = order_result

        entry["trade_status"] = order_result.get("status") or (

            "executed" if order_result.get("ok") else "rejected"

        )

    elif not parsed.get("action"):

        entry["trade_status"] = "no_action"



    _TV_ALERTS.insert(0, entry)

    del _TV_ALERTS[_TV_ALERTS_MAX:]

    _persist_tv_alerts()



    logger.info(

        "TradingView alert: %s action=%s status=%s",

        tv_symbol,

        parsed.get("action"),

        entry.get("trade_status"),

    )

    return {

        "ok": True,

        "tradingview_symbol": tv_symbol,

        "internal_symbol": parsed.get("internal_symbol"),

        "action": parsed.get("action"),

        "trade_status": entry.get("trade_status"),
        "ai": ai_result,

        "order": order_result,

    }





@router.get("/alerts")

async def trading_alerts() -> Dict[str, Any]:

    """Recent TradingView webhook alerts with paper trade status."""

    return {"count": len(_TV_ALERTS), "alerts": _TV_ALERTS}


@router.get("/freqtrade/status")
async def trading_freqtrade_status() -> Dict[str, Any]:
    """Freqtrade bot status (REST proxy + supervisor PID)."""
    from openjarvis.trading.freqtrade_client import freqtrade_status_payload

    try:
        from trading_research.live.freqtrade_control import _read_pid

        pid = _read_pid()
    except ImportError:
        pid = None
    payload = freqtrade_status_payload()
    payload["supervisor_pid"] = pid
    payload["supervisor_running"] = pid is not None
    try:
        from trading_research.live.freqtrade_nautilus import enrich_freqtrade_payload

        enrich_freqtrade_payload(payload)
    except Exception:
        pass
    return payload


@router.post("/freqtrade/start")
async def trading_freqtrade_start() -> Dict[str, Any]:
    """Start Freqtrade subprocess (dry-run by default)."""
    try:
        from trading_research.live.freqtrade_control import start_freqtrade

        msg = start_freqtrade()
        return {"ok": "failed" not in msg.lower(), "message": msg}
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/freqtrade/stop")
async def trading_freqtrade_stop() -> Dict[str, Any]:
    """Stop Freqtrade subprocess."""
    try:
        from trading_research.live.freqtrade_control import stop_freqtrade

        msg = stop_freqtrade()
        return {"ok": True, "message": msg}
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/freqtrade/bot/{command}")
async def trading_freqtrade_bot_command(command: str) -> Dict[str, Any]:
    """Proxy start/stop/pause to running Freqtrade REST API."""
    from openjarvis.trading.freqtrade_client import (
        freqtrade_pause,
        freqtrade_start,
        freqtrade_stop,
    )

    cmd = (command or "").strip().lower()
    if cmd == "start":
        return freqtrade_start()
    if cmd == "stop":
        return freqtrade_stop()
    if cmd == "pause":
        return freqtrade_pause()
    raise HTTPException(status_code=400, detail=f"unknown freqtrade command: {command}")


@router.get("/nautilus/status")
async def trading_nautilus_status() -> Dict[str, Any]:
    """Nautilus research worker status (JSON state from runner)."""
    from openjarvis.trading.nautilus_client import nautilus_status_payload

    try:
        from trading_research.live.nautilus_control import _read_pid

        pid = _read_pid()
    except ImportError:
        pid = None
    payload = nautilus_status_payload()
    payload["supervisor_pid"] = pid
    payload["supervisor_running"] = pid is not None
    return payload


@router.post("/nautilus/start")
async def trading_nautilus_start() -> Dict[str, Any]:
    """Start Nautilus research worker subprocess."""
    try:
        from trading_research.live.nautilus_control import start_nautilus

        msg = start_nautilus()
        return {"ok": "failed" not in msg.lower(), "message": msg}
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/nautilus/stop")
async def trading_nautilus_stop() -> Dict[str, Any]:
    """Stop Nautilus research worker subprocess."""
    try:
        from trading_research.live.nautilus_control import stop_nautilus

        msg = stop_nautilus()
        return {"ok": True, "message": msg}
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/nautilus/strategies")
async def trading_nautilus_strategies() -> Dict[str, Any]:
    try:
        from trading_research.nautilus.service import list_strategies

        return list_strategies()
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/nautilus/data-status")
async def trading_nautilus_data_status(
    symbol: str = "BTC-USD",
    timeframe: str = "1h",
) -> Dict[str, Any]:
    try:
        from trading_research.nautilus.service import probe_data

        return probe_data(symbol=symbol, timeframe=timeframe)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/nautilus/history")
async def trading_nautilus_history(limit: int = 20) -> Dict[str, Any]:
    try:
        from trading_research.nautilus.service import fetch_history

        return fetch_history(limit=limit)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/nautilus/summary")
async def trading_nautilus_summary() -> Dict[str, Any]:
    try:
        from trading_research.nautilus.service import fetch_summary

        return fetch_summary()
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


class NautilusBacktestRequest(BaseModel):
    symbol: str = "BTC-USD"
    timeframe: str = "1h"
    strategy: str = "ma_crossover"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    data_source: Optional[str] = None
    mode: str = "backtest"


class NautilusValidateSetupRequest(BaseModel):
    symbol: str
    direction: Optional[str] = "long"
    pattern: Optional[str] = None
    label: Optional[str] = None
    market: Optional[str] = "crypto"
    timeframe: Optional[str] = None
    strategy: Optional[str] = None
    force_refresh: bool = False


@router.post("/nautilus/validate-setup")
async def trading_nautilus_validate_setup(body: NautilusValidateSetupRequest) -> Dict[str, Any]:
    """Run Nautilus backtest for a scout setup and return pass/fail for traders."""
    try:
        from trading_research.nautilus.backtest_gate import (
            attach_validation_summary,
            validate_trade_setup,
        )

        setup = body.model_dump()
        result = validate_trade_setup(setup, force_refresh=body.force_refresh)
        return attach_validation_summary(setup, result)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/nautilus/learner")
async def trading_nautilus_learner() -> Dict[str, Any]:
    """Nautilus adaptive win-rate and strategy learning summary."""
    try:
        from trading_research.nautilus.backtest_gate import effective_gate_config, load_nautilus_gate_config
        from trading_research.nautilus.nautilus_learner import load_nautilus_learning

        store = load_nautilus_learning()
        gate = effective_gate_config()
        summary = store.summary()
        summary["effective_min_win_rate"] = gate.get("min_win_rate")
        summary["base_min_win_rate"] = load_nautilus_gate_config().get("min_win_rate")
        return {"ok": True, "learner": summary, "gate": gate}
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/nautilus/validations")
async def trading_nautilus_validations(symbols: str = "") -> Dict[str, Any]:
    """Cached Nautilus validation results for scout symbols (comma-separated)."""
    try:
        from trading_research.nautilus.backtest_gate import cached_validations_for_symbols

        sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
        return cached_validations_for_symbols(sym_list)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/nautilus/backtest")
async def trading_nautilus_backtest(body: NautilusBacktestRequest) -> Dict[str, Any]:
    """Run a Nautilus backtest with real market data."""
    from openjarvis.trading.nautilus_client import load_nautilus_config

    cfg = load_nautilus_config()
    if body.mode == "live" and not cfg.get("live_trading_unlock"):
        raise HTTPException(
            status_code=403,
            detail="Live trading locked. Set [nautilus] live_trading_unlock = true manually in trading.toml.",
        )
    try:
        from trading_research.nautilus.service import run_backtest

        return run_backtest(
            symbol=body.symbol,
            timeframe=body.timeframe,
            strategy=body.strategy,
            start_date=body.start_date,
            end_date=body.end_date,
            data_source=body.data_source,
            mode=body.mode,
        )
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


__all__ = ["router"]

