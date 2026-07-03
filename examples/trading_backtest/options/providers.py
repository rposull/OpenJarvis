"""Options data providers — yfinance (free), Polygon/ORATS (API keys)."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import yfinance as yf

from greeks import iv_from_price


@dataclass
class ChainSnapshot:
    underlying: str
    spot: float
    expiry: date
    iv_atm: float
    calls: pd.DataFrame
    puts: pd.DataFrame
    source: str


class OptionsDataProvider(ABC):
    @abstractmethod
    def get_spot(self, symbol: str) -> float:
        ...

    @abstractmethod
    def get_chain(self, symbol: str, expiry: date) -> ChainSnapshot:
        ...

    def pick_expiry(self, symbol: str, dte_target: int = 45) -> date:
        ticker = yf.Ticker(symbol)
        today = date.today()
        best: date | None = None
        best_diff = 999
        for exp_str in ticker.options:
            exp = datetime.strptime(exp_str, "%Y-%m-%d").date()
            diff = abs((exp - today).days - dte_target)
            if diff < best_diff:
                best_diff = diff
                best = exp
        if best is None:
            raise ValueError(f"No options expiries for {symbol}")
        return best


class YFinanceProvider(OptionsDataProvider):
    def get_spot(self, symbol: str) -> float:
        hist = yf.Ticker(symbol).history(period="5d")
        if hist.empty:
            raise ValueError(f"No spot for {symbol}")
        return float(hist["Close"].iloc[-1])

    def get_chain(self, symbol: str, expiry: date) -> ChainSnapshot:
        ticker = yf.Ticker(symbol)
        spot = self.get_spot(symbol)
        exp_str = expiry.strftime("%Y-%m-%d")
        if exp_str not in ticker.options:
            raise ValueError(f"Expiry {exp_str} not in chain for {symbol}")
        chain = ticker.option_chain(exp_str)
        calls, puts = chain.calls.copy(), chain.puts.copy()
        t = max((expiry - date.today()).days, 1) / 365.0
        iv_atm = self._atm_iv(spot, calls, puts, t)
        return ChainSnapshot(
            underlying=symbol,
            spot=spot,
            expiry=expiry,
            iv_atm=iv_atm,
            calls=calls,
            puts=puts,
            source="yfinance",
        )

    def _atm_iv(
        self,
        spot: float,
        calls: pd.DataFrame,
        puts: pd.DataFrame,
        t: float,
    ) -> float:
        if calls.empty:
            return 0.18
        strikes = calls["strike"].astype(float)
        idx = (strikes - spot).abs().idxmin()
        row = calls.loc[idx]
        mid = float(row.get("lastPrice") or 0)
        if mid <= 0:
            bid, ask = float(row.get("bid") or 0), float(row.get("ask") or 0)
            mid = (bid + ask) / 2 if bid and ask else 0
        if mid <= 0:
            return float(row.get("impliedVolatility") or 0.18)
        k = float(row["strike"])
        try:
            return iv_from_price(mid, spot, k, t, 0.045, is_call=True)
        except Exception:
            return float(row.get("impliedVolatility") or 0.18)


class PolygonProvider(OptionsDataProvider):
    """Polygon.io — set POLYGON_API_KEY in env. https://polygon.io"""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("POLYGON_API_KEY", "")
        if not self.api_key:
            raise ValueError("POLYGON_API_KEY not set")

    def get_spot(self, symbol: str) -> float:
        import httpx

        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev"
        r = httpx.get(url, params={"apiKey": self.api_key}, timeout=30)
        r.raise_for_status()
        return float(r.json()["results"][0]["c"])

    def get_chain(self, symbol: str, expiry: date) -> ChainSnapshot:
        raise NotImplementedError(
            "Polygon chain fetch: implement with /v3/snapshot/options/{symbol} "
            "or use YFinanceProvider for paper trading"
        )


class ORATSProvider(OptionsDataProvider):
    """ORATS — set ORATS_API_KEY. https://orats.com"""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("ORATS_API_KEY", "")
        if not self.api_key:
            raise ValueError("ORATS_API_KEY not set")

    def get_spot(self, symbol: str) -> float:
        raise NotImplementedError("Wire ORATS live summaries endpoint")

    def get_chain(self, symbol: str, expiry: date) -> ChainSnapshot:
        raise NotImplementedError("Wire ORATS strikes endpoint for historical IV/Greeks")


def get_provider(name: str = "yfinance") -> OptionsDataProvider:
    if name == "yfinance":
        return YFinanceProvider()
    if name == "polygon":
        return PolygonProvider()
    if name == "orats":
        return ORATSProvider()
    raise ValueError(f"Unknown provider: {name}")
