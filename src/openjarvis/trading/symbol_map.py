"""Map trading_research pair symbols to TradingView ticker format."""

from __future__ import annotations

import re
from typing import Dict, Literal, Optional, Tuple

# Pairs that chart better on a non-default exchange in TradingView.
_EXCHANGE_OVERRIDES: Dict[str, str] = {
    "LIGHTER": "BINANCE",
    "FARTCOIN": "COINBASE",
    "PENGU": "COINBASE",
}

# Explicit TV tickers when auto-mapping fails or is wrong.
_SYMBOL_OVERRIDES: Dict[str, str] = {}

# US equity exchanges supported for paper stock options.
_STOCK_EXCHANGES: frozenset[str] = frozenset(
    {"NASDAQ", "NYSE", "AMEX", "OTC", "BATS", "ARCA"}
)

# Default TV exchange when mapping a bare stock ticker.
_DEFAULT_STOCK_EXCHANGE = "NASDAQ"

# Crypto exchanges TradingView uses for spot pairs.
_CRYPTO_EXCHANGES: frozenset[str] = frozenset(
    {"COINBASE", "BINANCE", "KRAKEN", "BITSTAMP", "GEMINI", "BYBIT", "OKX"}
)

MarketType = Literal["crypto", "stock", "unknown"]


def parse_pair(symbol: str) -> Tuple[str, str]:
    """Split ``DOGE-USDC`` into ``(DOGE, USDC)``."""
    raw = (symbol or "").strip().upper()
    if "-" not in raw:
        return raw, "USD"
    base, quote = raw.split("-", 1)
    return base.strip(), quote.strip()


def list_stock_exchanges() -> list[str]:
    """US equity exchanges supported for TradingView stock charts."""
    return sorted(_STOCK_EXCHANGES)


def is_stock_exchange(exchange: str) -> bool:
    return (exchange or "").strip().upper() in _STOCK_EXCHANGES


def is_crypto_exchange(exchange: str) -> bool:
    return (exchange or "").strip().upper() in _CRYPTO_EXCHANGES


def detect_market(symbol: str, *, exchange: Optional[str] = None) -> MarketType:
    """Classify an internal or TV symbol as crypto or stock."""
    if exchange and is_stock_exchange(exchange):
        return "stock"
    if exchange and is_crypto_exchange(exchange):
        return "crypto"
    raw = (symbol or "").strip().upper()
    if "-" in raw:
        return "crypto"
    if re.fullmatch(r"[A-Z]{1,5}", raw):
        return "stock"
    return "unknown"


def to_tradingview(
    symbol: str,
    *,
    default_exchange: str = "COINBASE",
    stock_exchange: str = _DEFAULT_STOCK_EXCHANGE,
) -> str:
    """Convert a live-session pair or stock ticker to a TradingView symbol.

    Examples:
        DOGE-USDC -> COINBASE:DOGEUSDC
        TAO-USD   -> COINBASE:TAOUSD
        AAPL      -> NASDAQ:AAPL
    """
    raw = (symbol or "").strip().upper()
    if raw in _SYMBOL_OVERRIDES:
        return _SYMBOL_OVERRIDES[raw]
    if ":" in raw:
        return raw

    base, quote = parse_pair(raw)
    if "-" not in raw and re.fullmatch(r"[A-Z]{1,5}", raw):
        return f"{stock_exchange}:{raw}"
    exchange = _EXCHANGE_OVERRIDES.get(base, default_exchange)
    return f"{exchange}:{base}{quote}"


def from_tradingview(
    tv_symbol: str,
    *,
    default_exchange: str = "COINBASE",
) -> Dict[str, str]:
    """Reverse-map a TradingView ticker to an internal paper-trade symbol.

    Examples:
        COINBASE:DOGEUSDC -> DOGE-USDC (crypto)
        NASDAQ:AAPL       -> AAPL (stock)
        BINANCE:BTCUSDT   -> BTC-USDT (crypto)
    """
    raw = (tv_symbol or "").strip().upper()
    if not raw:
        return {
            "symbol": "",
            "tradingview_symbol": "",
            "market": "unknown",
            "exchange": "",
            "base": "",
            "quote": "",
        }

    if ":" in raw:
        exchange, ticker = raw.split(":", 1)
    else:
        exchange, ticker = default_exchange, raw

    exchange = exchange.upper()
    ticker = ticker.upper()

    if is_stock_exchange(exchange):
        return {
            "symbol": ticker,
            "tradingview_symbol": f"{exchange}:{ticker}",
            "market": "stock",
            "exchange": exchange,
            "base": ticker,
            "quote": "USD",
        }

    # Crypto: COINBASE:DOGEUSDC, BINANCE:BTCUSDT
    for quote in ("USDC", "USDT", "USD", "EUR", "GBP"):
        if ticker.endswith(quote) and len(ticker) > len(quote):
            base = ticker[: -len(quote)]
            internal = f"{base}-{quote}"
            return {
                "symbol": internal,
                "tradingview_symbol": f"{exchange}:{ticker}",
                "market": "crypto",
                "exchange": exchange,
                "base": base,
                "quote": quote,
            }

    return {
        "symbol": ticker,
        "tradingview_symbol": f"{exchange}:{ticker}",
        "market": "unknown",
        "exchange": exchange,
        "base": ticker,
        "quote": "USD",
    }


def normalize_for_dedup(symbol: str) -> str:
    """Group USD/USDC variants by base asset."""
    base, _ = parse_pair(symbol)
    return base


def prefer_chart_symbol(symbols: list[str]) -> str:
    """Pick one representative pair when USD and USDC variants exist."""
    if not symbols:
        return ""
    usd = [s for s in symbols if s.upper().endswith("-USD")]
    usdc = [s for s in symbols if s.upper().endswith("-USDC")]
    if usd:
        return sorted(usd)[0]
    if usdc:
        return sorted(usdc)[0]
    return sorted(symbols)[0]


def map_symbol_response(
    symbol: str,
    *,
    default_exchange: str = "COINBASE",
    stock_exchange: str = _DEFAULT_STOCK_EXCHANGE,
) -> Dict[str, str]:
    """Build API payload for a single symbol mapping."""
    raw = (symbol or "").strip().upper()
    if ":" in raw:
        mapped = from_tradingview(raw, default_exchange=default_exchange)
        return {
            "symbol": mapped["symbol"],
            "base": mapped["base"],
            "quote": mapped["quote"],
            "exchange": mapped["exchange"],
            "market": mapped["market"],
            "tradingview_symbol": mapped["tradingview_symbol"],
            "tradingview_ticker": mapped["tradingview_symbol"].split(":", 1)[-1],
        }

    base, quote = parse_pair(raw)
    tv = to_tradingview(
        symbol,
        default_exchange=default_exchange,
        stock_exchange=stock_exchange,
    )
    exchange, tv_ticker = tv.split(":", 1) if ":" in tv else (default_exchange, tv)
    market = detect_market(raw, exchange=exchange)
    return {
        "symbol": raw if "-" in raw else base,
        "base": base,
        "quote": quote,
        "exchange": exchange,
        "market": market,
        "tradingview_symbol": tv,
        "tradingview_ticker": tv_ticker,
    }


__all__ = [
    "parse_pair",
    "to_tradingview",
    "from_tradingview",
    "detect_market",
    "list_stock_exchanges",
    "is_stock_exchange",
    "is_crypto_exchange",
    "normalize_for_dedup",
    "prefer_chart_symbol",
    "map_symbol_response",
]
