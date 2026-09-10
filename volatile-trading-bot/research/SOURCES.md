# Research Sources (no fabricated claims)

This bot implements rules documented by systematic trading researchers.
Win rates below are **published by those authors / independent testers**, not
guarantees for this implementation or for future live trading.

## Primary strategy: Connors RSI(2) mean reversion

| Source | Finding |
|--------|---------|
| Larry Connors / Cesar Alvarez (original research, mid-1990s–2010) | Short-lookback RSI(2) on equities; high win-rate short-term mean reversion |
| [QuantifiedStrategies – RSI 2 Strategy](https://www.quantifiedstrategies.com/rsi-2-strategy/) | SPY with RSI(2)<10 + above SMA(200): reported **~76%** win rate in their backtest |
| [QuantifiedStrategies – Connors RSI still performing](https://www.quantifiedstrategies.com/larry-connors-rsi-strategy/) | QQQ ruleset: **71%** win ratio, profit factor 2.1 |
| [BacktestedStrategies – Connors RSI(2)](https://www.backtestedstrategies.com/strategies/connors-rsi2-backtest/) | SPY daily: **73.8%** win rate, 14.1% exposure |
| [EdgeLab – Connors on Nasdaq (2026)](https://edgelabtrading.com/blog/connors-rsi2-still-work-nasdaq/) | Edge still present OOS but modest Sharpe; widely known |

### Classic Connors long rules (as commonly published)

1. Price above 200-day SMA (uptrend only).
2. RSI(2) below 5–10 (extreme short-term oversold).
3. Buy next open (or close, depending on variant).
4. Exit when price closes above 5-day SMA, or RSI(2) recovers above ~65–80.

## Volatility prioritization (high-vol stocks)

| Source | Finding |
|--------|---------|
| [Quantitativo – Mean reversion curve](https://www.quantitativo.com/p/trading-the-mean-reversion-curve) | Higher **Normalized ATR (NATR)** → higher expected return on RSI(2) entries; prioritize high-vol names when ranking signals |
| [Quantitativo – 2.11 Sharpe mean reversion](https://www.quantitativo.com/p/robustness-of-the-211-sharpe-mean) | Highest NATR quintile: higher win % and payoff; multi-stock RSI/IBS systems ~**65%** win ratio in one portfolio variant |

## IBS confirmation filter

| Source | Finding |
|--------|---------|
| [Alvarez Quant Trading – IBS](https://alvarezquanttrading.com/blog/internal-bar-strength-for-mean-reversion/) | Low IBS improves RSI(2) mean-reversion expectancy |
| [QuantifiedStrategies – IBS](https://www.quantifiedstrategies.com/ibs-internal-bar-strength-indicator-strategies/) | IBS = (Close−Low)/(High−Low); buy weakness near 0 |

## Regime / risk notes from practitioners

- Mean reversion often shows **60–70%+ win rates** with smaller winners and occasional large losers (trend breakouts) — TraderNest / DNS Research summaries.
- Volatility Risk Premium (selling options when IV ≫ RV) is a different edge (~IV > RV historically often); this bot is **equity mean reversion**, not options VRP.
- No published system guarantees a permanent ≥75% win rate. Independent Connors tests cluster **~70–76%** on liquid index ETFs with a trend filter; stock portfolios are often lower.

## What this repo claims

1. Code faithfully encodes the published rule set above.
2. Backtests use real market data via Yahoo Finance (`yfinance`).
3. Metrics printed by the CLI are computed from those runs — never hardcoded fake win rates.
4. Past backtests ≠ future results. Slippage, borrow, corporate actions, and survivorship bias can change outcomes.
