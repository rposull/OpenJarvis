# Multi-market strategy backtests

Backtests the **top 10 trading strategies** across stocks, indices, FX, crypto, and commodities using daily OHLCV from Yahoo Finance.

## Strategies

| # | ID | Description |
|---|-----|-------------|
| 1 | `trend_following` | 50/200 SMA golden cross |
| 2 | `mean_reversion` | RSI(14) oversold / exit mid-range |
| 3 | `support_resistance` | 20-day Donchian breakout |
| 4 | `opening_range_breakout` | Prior day high/low break (daily proxy) |
| 5 | `pullback_in_trend` | 200 SMA trend + 20 SMA reclaim |
| 6 | `momentum` | 12-month strength near 52-week high |
| 7 | `pairs_mean_reversion` | EUR/USD vs GBP/USD spread z-score |
| 8 | `carry_trade` | 6m positive return + MA trend (FX proxy) |
| 9 | `volatility_breakout` | ATR expansion + range break |
| 10 | `systematic_trend_risk` | Trend following + vol-scaled size |

## Markets

- **Stocks:** SPY, AAPL, MSFT, NVDA  
- **Indices:** ^GSPC, ^IXIC, ^DJI  
- **FX:** EURUSD, GBPUSD, USDJPY, AUDJPY  
- **Crypto:** BTC-USD, ETH-USD  
- **Commodities:** GC=F, CL=F, SI=F  

## Run

```bash
pip install -r examples/trading_backtest/requirements.txt
python3 examples/trading_backtest/run_backtests.py
python3 examples/trading_backtest/run_backtests.py --years 3 --output examples/trading_backtest/results
```

Outputs CSV files in `results/`:
- `backtest_results_*.csv` — every strategy × market run
- `strategy_summary_*.csv` — average performance per strategy
- `top_combos_*.csv` — best Sharpe combinations

## Caveats

- **Daily bars only** — intraday strategies (true ORB) are approximated.
- **Long-only** on single assets; pairs strategy simplified.
- **No slippage model** beyond 0.1% commission per position change.
- **Past performance ≠ future results.** Paper-trade before risking capital.
