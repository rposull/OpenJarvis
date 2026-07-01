"""Backtest metrics and execution engine."""

from __future__ import annotations

import numpy as np
import pandas as pd


def max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd = (equity - peak) / peak
    return float(dd.min())


def trade_stats(position: pd.Series, returns: pd.Series) -> tuple[int, float, float]:
    """Count round trips, win rate, profit factor from position changes."""
    pos = position.fillna(0).astype(float)
    changes = pos.diff().fillna(pos)
    entries = changes > 0
    if not entries.any():
        return 0, 0.0, 0.0

    trade_returns: list[float] = []
    in_trade = False
    acc = 1.0
    for i in range(len(pos)):
        if not in_trade and pos.iloc[i] > 0:
            in_trade = True
            acc = 1.0
        if in_trade:
            acc *= 1.0 + (returns.iloc[i] if not np.isnan(returns.iloc[i]) else 0.0)
        if in_trade and (pos.iloc[i] == 0 or (i == len(pos) - 1)):
            trade_returns.append(acc - 1.0)
            in_trade = False

    if not trade_returns:
        return 0, 0.0, 0.0

    wins = [r for r in trade_returns if r > 0]
    losses = [r for r in trade_returns if r <= 0]
    win_rate = len(wins) / len(trade_returns)
    gross_win = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0
    return len(trade_returns), win_rate, pf


def run_backtest(
    close: pd.Series,
    signal: pd.Series,
    *,
    risk_scaled: pd.Series | None = None,
    commission: float = 0.001,
) -> dict:
    """Long-only backtest. signal: 1 = invested, 0 = cash. Executes next bar."""
    close = close.dropna()
    signal = signal.reindex(close.index).fillna(0).clip(0, 1)
    if risk_scaled is not None:
        signal = (signal * risk_scaled.reindex(close.index).fillna(1)).clip(0, 1)

    daily_ret = close.pct_change().fillna(0)
    position = signal.shift(1).fillna(0)
    turnover = position.diff().abs().fillna(position.abs())
    costs = turnover * commission
    strat_ret = position * daily_ret - costs
    equity = (1 + strat_ret).cumprod()

    years = max((close.index[-1] - close.index[0]).days / 365.25, 1 / 365.25)
    total_return = float(equity.iloc[-1] - 1)
    cagr = float(equity.iloc[-1] ** (1 / years) - 1) if equity.iloc[-1] > 0 else -1.0
    vol = strat_ret.std() * np.sqrt(252)
    sharpe = float(strat_ret.mean() / strat_ret.std() * np.sqrt(252)) if strat_ret.std() > 0 else 0.0
    n_trades, win_rate, pf = trade_stats(position, daily_ret)

    return {
        "total_return": round(total_return, 4),
        "cagr": round(cagr, 4),
        "sharpe": round(sharpe, 3),
        "max_drawdown": round(max_drawdown(equity), 4),
        "volatility": round(float(vol), 4),
        "num_trades": n_trades,
        "win_rate": round(win_rate, 3),
        "profit_factor": round(pf, 3) if pf != float("inf") else 999.0,
        "bars": len(close),
    }


def buy_hold_benchmark(close: pd.Series) -> dict:
    signal = pd.Series(1.0, index=close.index)
    return run_backtest(close, signal, commission=0.0)
