"""Ten classic strategy signal generators (daily bars)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _sma(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(n, min_periods=n).mean()


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(n, min_periods=n).mean()
    loss = (-delta.clip(upper=0)).rolling(n, min_periods=n).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    prev = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev).abs(), (low - prev).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(n, min_periods=n).mean()


def trend_following(df: pd.DataFrame) -> pd.Series:
    """50/200 SMA golden cross — long when fast > slow."""
    fast = _sma(df["Close"], 50)
    slow = _sma(df["Close"], 200)
    return (fast > slow).astype(float)


def mean_reversion(df: pd.DataFrame) -> pd.Series:
    """RSI(14) oversold entry, exit above 55."""
    rsi = _rsi(df["Close"], 14)
    signal = pd.Series(0.0, index=df.index)
    hold = False
    for i in range(len(df)):
        if not hold and rsi.iloc[i] < 30:
            hold = True
        elif hold and rsi.iloc[i] > 55:
            hold = False
        signal.iloc[i] = 1.0 if hold else 0.0
    return signal


def support_resistance(df: pd.DataFrame) -> pd.Series:
    """20-day Donchian breakout — long on break above channel."""
    upper = df["High"].rolling(20, min_periods=20).max().shift(1)
    lower = df["Low"].rolling(20, min_periods=20).min().shift(1)
    signal = pd.Series(0.0, index=df.index)
    hold = False
    for i in range(len(df)):
        c = df["Close"].iloc[i]
        if not hold and c > upper.iloc[i]:
            hold = True
        elif hold and c < lower.iloc[i]:
            hold = False
        signal.iloc[i] = 1.0 if hold else 0.0
    return signal


def opening_range_breakout(df: pd.DataFrame) -> pd.Series:
    """Daily proxy: trade break of prior session high/low."""
    prev_high = df["High"].shift(1)
    prev_low = df["Low"].shift(1)
    signal = pd.Series(0.0, index=df.index)
    hold = False
    for i in range(len(df)):
        c = df["Close"].iloc[i]
        if not hold and c > prev_high.iloc[i]:
            hold = True
        elif hold and c < prev_low.iloc[i]:
            hold = False
        signal.iloc[i] = 1.0 if hold else 0.0
    return signal


def pullback_in_trend(df: pd.DataFrame) -> pd.Series:
    """Uptrend (above 200 SMA) + reclaim 20 SMA after dip."""
    sma200 = _sma(df["Close"], 200)
    sma20 = _sma(df["Close"], 20)
    signal = pd.Series(0.0, index=df.index)
    hold = False
    dipped = False
    for i in range(len(df)):
        if df["Close"].iloc[i] < sma200.iloc[i]:
            hold = False
            dipped = False
            continue
        if df["Close"].iloc[i] < sma20.iloc[i]:
            dipped = True
        if dipped and df["Close"].iloc[i] > sma20.iloc[i]:
            hold = True
            dipped = False
        signal.iloc[i] = 1.0 if hold else 0.0
    return signal


def momentum(df: pd.DataFrame) -> pd.Series:
    """12-month return positive + within 2% of 252-day high."""
    ret_12m = df["Close"] / df["Close"].shift(252) - 1
    high_252 = df["Close"].rolling(252, min_periods=126).max()
    near_high = df["Close"] >= high_252 * 0.98
    return ((ret_12m > 0.05) & near_high).astype(float)


def pairs_mean_reversion(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
) -> pd.Series:
    """Z-score of log price ratio — mean revert spread."""
    idx = df_a.index.intersection(df_b.index)
    a = df_a.loc[idx, "Close"]
    b = df_b.loc[idx, "Close"]
    spread = np.log(a) - np.log(b)
    z = (spread - spread.rolling(60, min_periods=60).mean()) / spread.rolling(
        60, min_periods=60
    ).std()
    signal = pd.Series(0.0, index=idx)
    hold = False
    direction = 0  # 1 = long A short B proxy via long A only simplified
    for i in range(len(z)):
        zi = z.iloc[i]
        if not hold and zi < -2:
            hold = True
            direction = 1
        elif not hold and zi > 2:
            hold = True
            direction = -1
        elif hold and abs(zi) < 0.5:
            hold = False
        # Long-only simplification: only take long A when spread cheap
        signal.iloc[i] = 1.0 if hold and direction == 1 else 0.0
    return signal


def carry_trade(df: pd.DataFrame) -> pd.Series:
    """Proxy for FX carry: long when 6m return > 0 and 50 > 200 SMA."""
    ret_6m = df["Close"] / df["Close"].shift(126) - 1
    fast = _sma(df["Close"], 50)
    slow = _sma(df["Close"], 200)
    return ((ret_6m > 0) & (fast > slow)).astype(float)


def volatility_breakout(df: pd.DataFrame) -> pd.Series:
    """ATR expansion + 20-day high breakout."""
    atr = _atr(df["High"], df["Low"], df["Close"], 14)
    atr_ma = atr.rolling(50, min_periods=50).mean()
    upper = df["High"].rolling(20, min_periods=20).max().shift(1)
    expanding = atr > atr_ma * 1.1
    breakout = df["Close"] > upper
    signal = (expanding & breakout).astype(float)
    # hold until close below 20-day low
    lower = df["Low"].rolling(20, min_periods=20).min()
    out = pd.Series(0.0, index=df.index)
    hold = False
    for i in range(len(df)):
        if signal.iloc[i] > 0:
            hold = True
        elif hold and df["Close"].iloc[i] < lower.iloc[i]:
            hold = False
        out.iloc[i] = 1.0 if hold else 0.0
    return out


def systematic_trend_risk(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Trend following with vol-target position scaling (meta-strategy #10)."""
    base = trend_following(df)
    atr = _atr(df["High"], df["Low"], df["Close"], 14)
    vol = (atr / df["Close"]).replace(0, np.nan)
    target_vol = 0.01  # ~1% daily vol target
    scale = (target_vol / vol).clip(0.25, 1.0).fillna(0.5)
    return base, scale


STRATEGIES = {
    "trend_following": trend_following,
    "mean_reversion": mean_reversion,
    "support_resistance": support_resistance,
    "opening_range_breakout": opening_range_breakout,
    "pullback_in_trend": pullback_in_trend,
    "momentum": momentum,
    "carry_trade": carry_trade,
    "volatility_breakout": volatility_breakout,
}
