# SPY 45 DTE options — Greeks, structures, paper trading

Rigorous-ish options layer on top of the proxy backtests. Uses **Black-Scholes** for pricing/Greeks and **yfinance** for live chains.

## Architecture

```
options/
  greeks.py         # BS price, delta, gamma, theta, vega, IV solve
  structures.py     # Iron condor, put credit spread, exit rules
  providers.py      # yfinance (free) | Polygon | ORATS stubs
  journal.py        # Paper position JSON log
  paper_trade.py    # CLI — propose / status / close
  backtest_ic.py    # Historical 45 DTE IC backtest (SPY + VIX)
```

## Paper trade (live chain)

```bash
cd examples/trading_backtest/options

# Open 45 DTE iron condor on SPY (~16 delta, $5 wings)
python3 paper_trade.py propose ic --symbol SPY --dte 45

# Put credit spread
python3 paper_trade.py propose pcs --symbol SPY

# Mark-to-market + exit signals (50% profit, 21 DTE, 2x loss stop)
python3 paper_trade.py status

# Close
python3 paper_trade.py close <id> --reason manual
```

Positions saved to `paper_journal.json`.

## Backtest 45 DTE iron condors

```bash
python3 backtest_ic.py --years 5
```

Opens simulated ICs every 30 sessions when VIX 14–28; marks daily with BS; exits at 21 DTE / 50% profit / 2× credit loss.

## Data providers

| Provider | Env var | Status |
|----------|---------|--------|
| **yfinance** | — | Live chains + spot (default) |
| **Polygon** | `POLYGON_API_KEY` | Spot wired; chain TODO |
| **ORATS** | `ORATS_API_KEY` | Stub for historical IV/Greeks |

Copy `.env.example` → `.env` when you add API keys.

## Default IC rules (hedge fund style)

| Rule | Value |
|------|-------|
| Target DTE | 45 |
| Short delta | ~16Δ puts & calls |
| Wing width | $5 |
| Take profit | 50% of credit |
| Time exit | 21 DTE |
| Stop | 2× credit received |

## Caveats

- BS assumes European options, constant vol — SPY options are American.
- Historical backtest uses **VIX as IV** — not strike-specific skew.
- Paper marks use mid from BS; real fills differ (bid/ask, slippage).
- **Not financial advice.** Paper trade before live capital.
