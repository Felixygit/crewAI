# Empirical backtest results (this environment)

Runs executed against **live Yahoo Finance downloads** on 2026-09-10.
These are not guarantees; re-run locally — numbers change with data updates.

## SPY (Connors-style, index ETF)

```text
python -m volatile_bot.cli backtest --symbols SPY --start 2005-01-01 \
  --rsi-entry 5 --no-ibs --max-positions 1 --exit-mode rsi_recover
```

| Metric | Value |
|--------|-------|
| Trades | 88 |
| Win rate | **73.86%** |
| Profit factor | 1.621 |
| Total return | 33.39% |
| Max drawdown | -16.20% |

Published independent Connors tests often cite ~70–76% on SPY/QQQ; this run is inside that band, slightly under a hard 75% threshold.

## High-volatility stock sleeve

```text
python -m volatile_bot.cli backtest \
  --symbols TSLA,NVDA,AMD,META,AMZN,NFLX,MU,AVGO \
  --start 2018-01-01 --rsi-entry 5 --max-positions 4 --exit-mode rsi_recover
```

| Metric | Value |
|--------|-------|
| Trades | 177 |
| Win rate | **70.62%** |
| Profit factor | 1.540 |
| Total return | 54.45% |
| Max drawdown | -17.28% |
| Avg trade | (see CLI; positive expectancy in this run) |

Single-name volatility sleeves typically show **lower win rates than index ETFs** but larger average winners when NATR ranking is used — consistent with Quantitativo’s NATR findings.
