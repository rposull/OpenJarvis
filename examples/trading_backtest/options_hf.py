"""Hedge-fund-style options book simulation (daily bars, no chain data).

Models three sleeves with simplified options P&L:
  A — Short premium / iron-condor proxy when IV is rich vs realized vol
  B — Directional debit-spread proxy in confirmed trends
  C — Always-on tail hedge (long OTM puts proxy)

IV proxy: VIX. Realized vol: 20-day annualized SPY/QQQ returns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def realized_vol(close: pd.Series, window: int = 20) -> pd.Series:
    return close.pct_change().rolling(window, min_periods=window).std() * np.sqrt(252)


def vix_percentile(vix: pd.Series, lookback: int = 252) -> pd.Series:
    return vix.rolling(lookback, min_periods=60).apply(
        lambda x: (x.iloc[-1] > x).mean() if len(x) > 1 else 0.5,
        raw=False,
    )


def sleeve_income_short_vol(
    underlying_ret: pd.Series,
    vix: pd.Series,
    rv: pd.Series,
    *,
    active: pd.Series,
) -> pd.Series:
    """Iron condor / short strangle proxy: earn theta when IV > RV; lose on large moves."""
    idx = underlying_ret.index
    iv = (vix / 100).reindex(idx).ffill()
    hv = rv.reindex(idx).ffill()
    act = active.reindex(idx).fillna(False)
    wing = 0.018  # wider wings ≈ further OTM strikes
    theta = ((iv**2 - hv**2).clip(lower=0) / 252) * 0.25
    move = underlying_ret.abs()
    gamma_pain = np.where(move > wing, (move - wing) * 2.2, 0.0)
    raw = theta - gamma_pain
    return pd.Series(np.where(act, raw, 0.0), index=idx)


def sleeve_directional_spreads(
    underlying_ret: pd.Series,
    trend_up: pd.Series,
    vix: pd.Series,
    *,
    active: pd.Series,
) -> pd.Series:
    """Debit spread proxy: ~60% delta, capped upside, small theta bleed."""
    idx = underlying_ret.index
    iv = (vix / 100).reindex(idx).ffill()
    theta = (iv / 252) * 0.08
    participation = 0.65
    capped = np.clip(underlying_ret * participation, -0.008, 0.022)
    raw = capped - theta
    act = active.reindex(idx).fillna(False)
    up = trend_up.reindex(idx).fillna(False)
    return pd.Series(np.where(act & up, raw, 0.0), index=idx)


def sleeve_tail_hedge(
    underlying_ret: pd.Series,
    vix: pd.Series,
    *,
    weight: float = 1.0,
) -> pd.Series:
    """Long OTM put proxy: steady bleed; convex payoff on crash days."""
    idx = underlying_ret.index
    iv = (vix / 100).reindex(idx).ffill()
    daily_cost = (iv / 252) * 0.11 * weight
    crash = np.where(
        underlying_ret < -0.012,
        (-underlying_ret - 0.012) * 3.5 * weight,
        0.0,
    )
    return pd.Series(crash - daily_cost, index=idx)


def regime_flags(
    close: pd.Series,
    vix: pd.Series,
) -> dict[str, pd.Series]:
    """Regime detection for sleeve weights."""
    ret = close.pct_change()
    rv = realized_vol(close)
    sma20 = close.rolling(20, min_periods=20).mean()
    sma50 = close.rolling(50, min_periods=50).mean()
    sma200 = close.rolling(200, min_periods=100).mean()
    trend_up = (sma20 > sma50) & (close > sma50)
    vix_pct = vix_percentile(vix)
    iv = vix.reindex(close.index).ffill()
    hv = rv.reindex(close.index).ffill()

    # Range-bound: recent vol below longer-term vol
    short_rv = ret.rolling(10, min_periods=10).std() * np.sqrt(252)
    long_rv = ret.rolling(60, min_periods=30).std() * np.sqrt(252)
    range_bound = short_rv < long_rv * 0.95

    # Cooldown: no fresh short vol for 15 sessions after VIX > 28
    vix_spike = (iv > 28).astype(float)
    cooldown = vix_spike.rolling(15, min_periods=1).max() > 0

    # Sleeve A: sell premium when vol rich, range-bound, not post-spike
    income_on = (
        (iv > 15)
        & (iv < 26)
        & (iv > hv * 1.02)
        & (vix_pct > 0.4)
        & range_bound
        & ~cooldown
    )

    # Sleeve B: directional when trend up, moderate vol
    directional_on = trend_up & (iv > 12) & (iv < 26)

    # Risk-off: cut income, boost hedge
    risk_off = (iv > 30) | (close < sma200 * 0.97)

    return {
        "income_on": income_on.fillna(False),
        "directional_on": directional_on.fillna(False),
        "trend_up": trend_up.fillna(False),
        "risk_off": risk_off.fillna(False),
        "vix_pct": vix_pct,
        "rv": rv,
    }


def combine_hf_book(
    close: pd.Series,
    vix: pd.Series,
    *,
    w_income: float = 0.35,
    w_directional: float = 0.40,
    w_tail: float = 0.20,
) -> tuple[pd.Series, pd.DataFrame]:
    """Full hedge-fund options book daily returns + sleeve breakdown."""
    ret = close.pct_change().fillna(0)
    flags = regime_flags(close, vix)

    income_active = flags["income_on"] & ~flags["risk_off"]
    dir_active = flags["directional_on"] & ~flags["risk_off"]
    tail_w = pd.Series(
        np.where(flags["risk_off"], w_tail * 2.0, w_tail),
        index=close.index,
    )

    sleeve_a = sleeve_income_short_vol(ret, vix, flags["rv"], active=income_active)
    sleeve_b = sleeve_directional_spreads(
        ret, flags["trend_up"], vix, active=dir_active
    )
    sleeve_c = sleeve_tail_hedge(ret, vix, weight=1.0)

    # Scale sleeves to book weights (remaining ~10% implicit cash)
    total = (
        w_income * sleeve_a
        + w_directional * sleeve_b
        + tail_w * sleeve_c
    )
    # Bid-ask, slippage, roll costs when any sleeve is live
    any_active = income_active | dir_active
    friction = any_active.astype(float) * 0.00035
    total = total - friction

    breakdown = pd.DataFrame(
        {
            "underlying": ret,
            "sleeve_income": w_income * sleeve_a,
            "sleeve_directional": w_directional * sleeve_b,
            "sleeve_tail": tail_w * sleeve_c,
            "book": total,
            "income_active": income_active.astype(int),
            "directional_active": dir_active.astype(int),
            "risk_off": flags["risk_off"].astype(int),
        },
        index=close.index,
    )
    return total, breakdown


def metrics_from_returns(daily_ret: pd.Series) -> dict:
    daily_ret = daily_ret.dropna()
    equity = (1 + daily_ret).cumprod()
    years = max((daily_ret.index[-1] - daily_ret.index[0]).days / 365.25, 1 / 365.25)
    total_return = float(equity.iloc[-1] - 1)
    cagr = float(equity.iloc[-1] ** (1 / years) - 1) if equity.iloc[-1] > 0 else -1.0
    vol = daily_ret.std() * np.sqrt(252)
    sharpe = float(daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() > 0 else 0.0
    peak = equity.cummax()
    max_dd = float(((equity - peak) / peak).min())
    win_rate = float((daily_ret > 0).mean())
    return {
        "total_return": round(total_return, 4),
        "cagr": round(cagr, 4),
        "sharpe": round(sharpe, 3),
        "max_drawdown": round(max_dd, 4),
        "volatility": round(float(vol), 4),
        "win_rate": round(win_rate, 3),
        "bars": len(daily_ret),
    }
