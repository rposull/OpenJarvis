#!/usr/bin/env python3
"""Run top-10 strategy backtests across stocks, indices, FX, crypto, commodities.

Usage:
    python3 examples/trading_backtest/run_backtests.py
    python3 examples/trading_backtest/run_backtests.py --years 3 --output results/
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from engine import buy_hold_benchmark, run_backtest
from markets import MARKETS, PAIR_SPECS, STRATEGY_NAMES
from strategies import STRATEGIES, pairs_mean_reversion, systematic_trend_risk

ROOT = Path(__file__).resolve().parent


def download(tickers: list[str], years: int) -> dict[str, pd.DataFrame]:
    period = f"{years}y"
    raw = yf.download(
        tickers,
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    out: dict[str, pd.DataFrame] = {}
    if len(tickers) == 1:
        t = tickers[0]
        df = raw.copy()
        df.columns = [c if isinstance(c, str) else c[0] for c in df.columns]
        out[t] = df.dropna(how="all")
        return out

    for t in tickers:
        try:
            df = raw[t].dropna(how="all")
            if len(df) > 50:
                out[t] = df
        except (KeyError, TypeError):
            continue
    return out


def run_all(years: int, output_dir: Path) -> pd.DataFrame:
    all_tickers = sorted({t for g in MARKETS.values() for t in g})
    print(f"Downloading {len(all_tickers)} tickers ({years}y)…")
    data = download(all_tickers, years)
    print(f"Got data for {len(data)} tickers.\n")

    rows: list[dict] = []

    for asset_class, tickers in MARKETS.items():
        for ticker in tickers:
            if ticker not in data:
                print(f"  skip {ticker} (no data)")
                continue
            df = data[ticker]
            close = df["Close"]
            bh = buy_hold_benchmark(close)

            for name, fn in STRATEGIES.items():
                try:
                    sig = fn(df)
                    res = run_backtest(close, sig)
                    rows.append(
                        {
                            "asset_class": asset_class,
                            "ticker": ticker,
                            "strategy": name,
                            **res,
                            "vs_buy_hold": round(res["total_return"] - bh["total_return"], 4),
                        }
                    )
                except Exception as exc:
                    rows.append(
                        {
                            "asset_class": asset_class,
                            "ticker": ticker,
                            "strategy": name,
                            "error": str(exc),
                        }
                    )

            # Strategy 10: systematic trend + vol scaling
            try:
                sig, scale = systematic_trend_risk(df)
                res = run_backtest(close, sig, risk_scaled=scale)
                rows.append(
                    {
                        "asset_class": asset_class,
                        "ticker": ticker,
                        "strategy": "systematic_trend_risk",
                        **res,
                        "vs_buy_hold": round(res["total_return"] - bh["total_return"], 4),
                    }
                )
            except Exception as exc:
                rows.append(
                    {
                        "asset_class": asset_class,
                        "ticker": ticker,
                        "strategy": "systematic_trend_risk",
                        "error": str(exc),
                    }
                )

    # Strategy 7: pairs on FX
    for asset_class, a, b in PAIR_SPECS:
        if a in data and b in data:
            try:
                sig = pairs_mean_reversion(data[a], data[b])
                close = data[a]["Close"].reindex(sig.index).dropna()
                sig = sig.reindex(close.index).fillna(0)
                res = run_backtest(close, sig)
                bh = buy_hold_benchmark(close)
                rows.append(
                    {
                        "asset_class": asset_class,
                        "ticker": f"{a}/{b}",
                        "strategy": "pairs_mean_reversion",
                        **res,
                        "vs_buy_hold": round(res["total_return"] - bh["total_return"], 4),
                    }
                )
            except Exception as exc:
                rows.append(
                    {
                        "asset_class": asset_class,
                        "ticker": f"{a}/{b}",
                        "strategy": "pairs_mean_reversion",
                        "error": str(exc),
                    }
                )

    results = pd.DataFrame(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"backtest_results_{ts}.csv"
    results.to_csv(csv_path, index=False)

    # Summary: best strategy per asset class by avg Sharpe
    numeric = results.dropna(subset=["sharpe"])
    summary_rows = []
    if not numeric.empty:
        for strat in STRATEGY_NAMES:
            sub = numeric[numeric["strategy"] == strat]
            if sub.empty:
                continue
            summary_rows.append(
                {
                    "strategy": strat,
                    "runs": len(sub),
                    "avg_return": round(sub["total_return"].mean(), 4),
                    "avg_sharpe": round(sub["sharpe"].mean(), 3),
                    "avg_max_dd": round(sub["max_drawdown"].mean(), 4),
                    "avg_win_rate": round(sub["win_rate"].mean(), 3),
                    "beat_buy_hold_pct": round((sub["vs_buy_hold"] > 0).mean() * 100, 1),
                }
            )
        summary = pd.DataFrame(summary_rows).sort_values("avg_sharpe", ascending=False)
        summary_path = output_dir / f"strategy_summary_{ts}.csv"
        summary.to_csv(summary_path, index=False)

        # Top combos
        top = numeric.nlargest(15, "sharpe")[
            ["asset_class", "ticker", "strategy", "total_return", "sharpe", "max_drawdown", "win_rate"]
        ]
        top_path = output_dir / f"top_combos_{ts}.csv"
        top.to_csv(top_path, index=False)

        print(summary.to_string(index=False))
        print(f"\nSaved:\n  {csv_path}\n  {summary_path}\n  {top_path}")
    else:
        print("No numeric results — check data download.")
        print(f"Saved: {csv_path}")

    meta = {
        "run_at": ts,
        "years": years,
        "tickers": list(data.keys()),
        "strategies": STRATEGY_NAMES,
    }
    (output_dir / f"run_meta_{ts}.json").write_text(json.dumps(meta, indent=2))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-market strategy backtests")
    parser.add_argument("--years", type=int, default=5, help="History length (default 5)")
    parser.add_argument("--output", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    run_all(args.years, args.output)


if __name__ == "__main__":
    main()
