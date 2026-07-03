#!/usr/bin/env python3
"""Historical backtest: SPY 45 DTE iron condors with Black-Scholes marks."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from options_hf import metrics_from_returns
from structures import IronCondorParams, build_iron_condor, should_close_ic


def download(years: int) -> tuple[pd.Series, pd.Series]:
    raw = yf.download(
        ["SPY", "^VIX"],
        period=f"{years}y",
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="column",
    )
    if isinstance(raw.columns, pd.MultiIndex):
        spy = raw["Close"]["SPY"].dropna()
        vix = raw["Close"]["^VIX"].reindex(spy.index).ffill()
    else:
        spy = raw["Close"].dropna()
        vix = spy  # fallback
    return spy, vix


def run_backtest(years: int, output: Path) -> dict:
    spy, vix = download(years)
    params = IronCondorParams()
    daily_pnl: list[float] = []
    dates: list = []
    trades: list[dict] = []

    i = 252
    open_struct = None
    prev_net = 0.0
    capital = 100_000.0

    while i < len(spy):
        dt = pd.Timestamp(spy.index[i]).date()
        spot = float(spy.iloc[i])
        iv = float(vix.iloc[i]) / 100 if pd.notna(vix.iloc[i]) else 0.18
        iv = float(min(max(iv, 0.08), 0.80))
        day_pnl = 0.0

        if open_struct is None:
            if i % 30 == 0 and 14 < iv * 100 < 28:
                expiry = dt + timedelta(days=params.dte_target)
                open_struct = build_iron_condor("SPY", spot, expiry, iv, params=params)
                prev_net = open_struct.mark(spot, iv, as_of=dt)["net_mark"]
                trades.append(
                    {
                        "entry": str(dt),
                        "expiry": expiry.isoformat(),
                        "credit": open_struct.credit_debit,
                        "spot": round(spot, 2),
                        "iv": round(iv, 4),
                    }
                )
        else:
            mark = open_struct.mark(spot, iv, as_of=dt)
            day_pnl = (mark["net_mark"] - prev_net) / capital
            prev_net = mark["net_mark"]
            close, reason = should_close_ic(open_struct, mark, params)
            if close or mark["dte"] <= 0:
                reason = reason or "expiry"
                trades[-1].update(
                    {
                        "exit": str(dt),
                        "reason": reason,
                        "pnl": round(mark["pnl"], 2),
                        "dte": mark["dte"],
                    }
                )
                open_struct = None
                prev_net = 0.0

        daily_pnl.append(day_pnl)
        dates.append(spy.index[i])
        i += 1

    ret = pd.Series(daily_pnl, index=dates)
    m = metrics_from_returns(ret)
    completed = [t for t in trades if "exit" in t]
    out = {
        "strategy": "spy_45dte_iron_condor_bs",
        "years": years,
        "trades": len(completed),
        "metrics": m,
        "win_rate_trades": round(
            len([t for t in completed if t.get("pnl", 0) > 0]) / max(len(completed), 1),
            3,
        ),
        "avg_credit": round(
            sum(t["credit"] for t in trades) / max(len(trades), 1),
            2,
        ),
        "trade_log": trades[-12:],
    }
    output.mkdir(parents=True, exist_ok=True)
    path = output / "ic45_backtest.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"SPY 45DTE iron condor backtest ({years}y, Black-Scholes + VIX)")
    print(f"  Completed trades: {out['trades']}")
    print(f"  Book return: {m['total_return']:.1%} | Sharpe: {m['sharpe']:.2f} | Max DD: {m['max_drawdown']:.1%}")
    print(f"  Trade win rate: {out['win_rate_trades']:.0%}")
    print(f"  Saved: {path}")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Backtest SPY 45 DTE iron condors")
    p.add_argument("--years", type=int, default=5)
    p.add_argument("--output", type=Path, default=ROOT.parent / "results")
    args = p.parse_args()
    sys.path.insert(0, str(ROOT))
    run_backtest(args.years, args.output)


if __name__ == "__main__":
    main()
