#!/usr/bin/env python3
"""Backtest hedge-fund options regime strategy (3-sleeve book).

Usage:
    python3 examples/trading_backtest/backtest_hf_options.py
    python3 examples/trading_backtest/backtest_hf_options.py --years 5
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from engine import buy_hold_benchmark
from options_hf import combine_hf_book, metrics_from_returns

ROOT = Path(__file__).resolve().parent
UNDERLYINGS = ["SPY", "QQQ", "IWM"]


def download(years: int) -> tuple[pd.DataFrame, pd.Series]:
    tickers = UNDERLYINGS + ["^VIX"]
    raw = yf.download(
        tickers,
        period=f"{years}y",
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="ticker",
    )
    vix = raw["^VIX"]["Close"].dropna()
    prices = {}
    for t in UNDERLYINGS:
        prices[t] = raw[t]["Close"].dropna()
    return prices, vix


def run(years: int, output: Path) -> pd.DataFrame:
    print(f"Downloading {UNDERLYINGS} + VIX ({years}y)…")
    prices, vix = download(years)

    rows: list[dict] = []
    breakdowns: dict[str, pd.DataFrame] = {}

    for ticker, close in prices.items():
        bh = buy_hold_benchmark(close)
        book_ret, detail = combine_hf_book(close, vix)
        m = metrics_from_returns(book_ret)
        rows.append(
            {
                "ticker": ticker,
                "strategy": "hf_options_book",
                **m,
                "vs_buy_hold": round(m["total_return"] - bh["total_return"], 4),
            }
        )
        breakdowns[ticker] = detail

        # Sleeve attribution (cumulative)
        for sleeve in ("sleeve_income", "sleeve_directional", "sleeve_tail"):
            cum = (1 + detail[sleeve]).cumprod().iloc[-1] - 1
            rows.append(
                {
                    "ticker": ticker,
                    "strategy": sleeve,
                    "total_return": round(float(cum), 4),
                    "sharpe": round(
                        float(
                            detail[sleeve].mean()
                            / detail[sleeve].std()
                            * (252**0.5)
                        )
                        if detail[sleeve].std() > 0
                        else 0.0,
                        3,
                    ),
                }
            )

        rows.append(
            {
                "ticker": ticker,
                "strategy": "buy_and_hold",
                **bh,
            }
        )

        print(
            f"  {ticker}: book Sharpe {m['sharpe']:.2f} | "
            f"return {m['total_return']:.1%} | max DD {m['max_drawdown']:.1%} | "
            f"vs B&H {m['total_return'] - bh['total_return']:+.1%}"
        )

    results = pd.DataFrame(rows)
    output.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    csv = output / f"hf_options_backtest_{ts}.csv"
    results.to_csv(csv, index=False)

    # Combined SPY+QQQ equal-weight book
    spy = prices["SPY"]
    qqq = prices["QQQ"]
    idx = spy.index.intersection(qqq.index)
    ew_ret = (spy.pct_change().reindex(idx) + qqq.pct_change().reindex(idx)) / 2
    ew_close = (1 + ew_ret.fillna(0)).cumprod() * 100
    book_ret, _ = combine_hf_book(ew_close, vix.reindex(idx))
    combo = metrics_from_returns(book_ret)
    print(
        f"\n  SPY+QQQ EW book: Sharpe {combo['sharpe']:.2f} | "
        f"return {combo['total_return']:.1%} | max DD {combo['max_drawdown']:.1%}"
    )

    meta = {
        "run_at": ts,
        "years": years,
        "model": "3-sleeve options proxy (income / directional / tail)",
        "underlyings": UNDERLYINGS,
        "combo_spy_qqq": combo,
    }
    (output / f"hf_options_meta_{ts}.json").write_text(json.dumps(meta, indent=2))
    print(f"\nSaved: {csv}")
    return results


def main() -> None:
    p = argparse.ArgumentParser(description="HF options strategy backtest")
    p.add_argument("--years", type=int, default=5)
    p.add_argument("--output", type=Path, default=ROOT / "results")
    args = p.parse_args()
    run(args.years, args.output)


if __name__ == "__main__":
    main()
