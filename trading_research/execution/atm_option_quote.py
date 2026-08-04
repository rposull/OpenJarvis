"""ATM option quotes for paper entries — strike nearest spot, live mid premium.

Uses Yahoo options chain (httpx + crumb). Falls back to None so callers can
keep the ATR synthetic premium when the chain is unavailable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from trading_research.utils.logging import get_logger

logger = get_logger("trading_research.atm_option_quote")

_CRUMB: Optional[str] = None
_CRUMB_TS: float = 0.0
_CRUMB_TTL_SEC = 300.0
_SESSION: Optional[httpx.Client] = None


@dataclass(frozen=True)
class AtmOptionQuote:
    symbol: str
    right: str
    strike: float
    premium: float
    bid: float
    ask: float
    last: float
    underlying: float
    expiration: str  # YYYY-MM-DD
    days_to_expiry: int
    source: str = "yahoo"


def _session() -> httpx.Client:
    global _SESSION
    if _SESSION is None:
        _SESSION = httpx.Client(
            timeout=12.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
            },
        )
    return _SESSION


def _yahoo_crumb(*, force: bool = False) -> Optional[str]:
    global _CRUMB, _CRUMB_TS
    now = time.time()
    if not force and _CRUMB and (now - _CRUMB_TS) < _CRUMB_TTL_SEC:
        return _CRUMB
    s = _session()
    try:
        s.get("https://fc.yahoo.com")
        crumb = str(s.get("https://query2.finance.yahoo.com/v1/test/getcrumb").text).strip()
        if not crumb or "Too Many Requests" in crumb:
            return None
        _CRUMB = crumb
        _CRUMB_TS = now
        return crumb
    except Exception as exc:
        logger.debug("yahoo crumb failed: %s", exc)
        return None


def _mid_premium(row: Dict[str, Any]) -> Optional[float]:
    try:
        bid = float(row.get("bid") or 0)
        ask = float(row.get("ask") or 0)
        last = float(row.get("lastPrice") or 0)
    except (TypeError, ValueError):
        return None
    if bid > 0 and ask > 0 and ask >= bid:
        return round((bid + ask) / 2.0, 4)
    if last > 0:
        return round(last, 4)
    if ask > 0:
        return round(ask, 4)
    if bid > 0:
        return round(bid, 4)
    return None


def _nearest_strike_row(rows: List[Dict[str, Any]], spot: float) -> Optional[Dict[str, Any]]:
    best: Optional[Dict[str, Any]] = None
    best_dist = float("inf")
    for row in rows:
        try:
            strike = float(row.get("strike"))
        except (TypeError, ValueError):
            continue
        if _mid_premium(row) is None:
            continue
        dist = abs(strike - spot)
        if dist < best_dist:
            best_dist = dist
            best = row
    if best is not None:
        return best
    best_dist = float("inf")
    for row in rows:
        try:
            strike = float(row.get("strike"))
        except (TypeError, ValueError):
            continue
        dist = abs(strike - spot)
        if dist < best_dist:
            best_dist = dist
            best = row
    return best


def _exp_ymd(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()


def _dte(exp_ymd: str, *, today: Optional[date] = None) -> int:
    d0 = today or datetime.now(timezone.utc).date()
    try:
        d1 = date.fromisoformat(exp_ymd)
    except ValueError:
        return 0
    return max(0, (d1 - d0).days)


def _pick_expiration(
    expiration_dates: List[int],
    *,
    prefer_0dte: bool = True,
    today: Optional[date] = None,
) -> Optional[int]:
    if not expiration_dates:
        return None
    d0 = today or datetime.now(timezone.utc).date()
    dated = [
        (int(ts), datetime.fromtimestamp(int(ts), tz=timezone.utc).date())
        for ts in expiration_dates
    ]
    if prefer_0dte:
        for ts, d in dated:
            if d == d0:
                return ts
    future = [(ts, d) for ts, d in dated if d >= d0]
    pool = future or dated
    pool.sort(key=lambda x: abs((x[1] - d0).days))
    return pool[0][0]


def fetch_atm_option_quote(
    symbol: str,
    right: str,
    *,
    spot: Optional[float] = None,
    prefer_0dte: bool = True,
    client: Optional[httpx.Client] = None,
) -> Optional[AtmOptionQuote]:
    """Return ATM (strike closest to spot) quote for ``right`` on nearest/0DTE expiry."""
    sym = (symbol or "").strip().upper()
    if ":" in sym:
        sym = sym.split(":", 1)[1]
    side = (right or "call").strip().lower()
    if side not in ("call", "put") or not sym:
        return None

    s = client or _session()
    crumb = _yahoo_crumb()
    if not crumb:
        return None

    url = f"https://query2.finance.yahoo.com/v7/finance/options/{sym}"

    def _get(params: Dict[str, Any]) -> Any:
        resp = s.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    try:
        data = _get({"crumb": crumb})
    except Exception:
        crumb = _yahoo_crumb(force=True)
        if not crumb:
            return None
        try:
            data = _get({"crumb": crumb})
        except Exception as exc:
            logger.debug("yahoo options %s failed: %s", sym, exc)
            return None

    result = (data or {}).get("optionChain", {}).get("result") or []
    if not result:
        return None
    row0 = result[0]
    quote = row0.get("quote") or {}
    under = float(spot or 0) or float(
        quote.get("regularMarketPrice")
        or quote.get("postMarketPrice")
        or quote.get("preMarketPrice")
        or 0
    )
    if under <= 0:
        return None

    exp_ts = _pick_expiration(list(row0.get("expirationDates") or []), prefer_0dte=prefer_0dte)
    options = list(row0.get("options") or [])
    chosen = None
    if options and exp_ts is not None:
        for block in options:
            if int(block.get("expirationDate") or 0) == int(exp_ts):
                chosen = block
                break
    if chosen is None and exp_ts is not None:
        try:
            data2 = _get({"crumb": crumb, "date": int(exp_ts)})
            result2 = (data2 or {}).get("optionChain", {}).get("result") or []
            opts2 = (result2[0].get("options") or []) if result2 else []
            chosen = opts2[0] if opts2 else None
        except Exception as exc:
            logger.debug("yahoo options date=%s failed: %s", exp_ts, exc)
            chosen = options[0] if options else None
    elif chosen is None:
        chosen = options[0] if options else None
    if not chosen:
        return None

    legs = list((chosen.get("calls") if side == "call" else chosen.get("puts")) or [])
    best = _nearest_strike_row(legs, under)
    if not best:
        return None
    prem = _mid_premium(best)
    if prem is None or prem <= 0:
        return None
    try:
        strike = float(best["strike"])
        bid = float(best.get("bid") or 0)
        ask = float(best.get("ask") or 0)
        last = float(best.get("lastPrice") or 0)
        exp_raw = int(chosen.get("expirationDate") or exp_ts or 0)
    except (TypeError, ValueError, KeyError):
        return None
    exp = _exp_ymd(exp_raw)
    return AtmOptionQuote(
        symbol=sym,
        right=side,
        strike=round(strike, 2),
        premium=round(float(prem), 4),
        bid=round(bid, 4),
        ask=round(ask, 4),
        last=round(last, 4),
        underlying=round(under, 4),
        expiration=exp,
        days_to_expiry=_dte(exp),
        source="yahoo",
    )
