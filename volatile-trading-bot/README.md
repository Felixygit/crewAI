# High-Volatility Mean-Reversion Trading Bot

Research-backed **equity mean-reversion** bot for liquid, high-volatility stocks.
Implements Larry Connors’ RSI(2) pullback rules, ranks candidates by Normalized ATR
(Quantitativo), and optionally confirms with Internal Bar Strength (Alvarez).

> **Honest constraint on “75% win rate”:** No live system can *guarantee* a ≥75%
> win rate. Independent published Connors RSI(2) backtests on index ETFs (SPY/QQQ)
> often land around **~70–76%** with a 200-day trend filter. Multi-stock high-vol
> portfolios in public research are often closer to **~65%**. This repo **never
> hardcodes** a win rate — the CLI prints the empirical rate from your backtest
> on real Yahoo Finance data. See [`research/SOURCES.md`](research/SOURCES.md).

## Strategy rules (encoded)

**Entry** (signal on day *T* close → fill day *T+1* open):

1. Close > SMA(200) — long-term uptrend only (Connors).
2. RSI(2) < 5 (default; tighten for higher historical win rate / fewer trades).
3. IBS < 0.30 — close near the day’s low (Alvarez filter; disable with `--no-ibs`).
4. Among signals, prefer highest NATR(14) names (Quantitativo volatility ranking).

**Exit** (signal on close → fill next open):

- Default: RSI(2) > 65 (Connors recovery exit; often the higher win-rate variant).
- Alternatives: close > SMA(5), or close > prior day high (Quantitativo).
- Time stop: `max_hold_days` (default 10).

**Risk:** equal capital slots (`--max-positions`), commission + slippage fractions.

This is **not** options short-vol / VRP harvesting (iron condors, etc.), though
that literature also targets high-probability setups when IV ≫ RV.

## Install

```bash
cd volatile-trading-bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Usage

```bash
# Backtest default volatile universe (real Yahoo data)
python -m volatile_bot.cli backtest --start 2018-01-01

# Tighter Connors entry (historically higher win rate, fewer trades)
python -m volatile_bot.cli backtest --symbols QQQ,SPY --rsi-entry 5 --start 2010-01-01

# Scan for signals on the latest bar (ranked by NATR)
python -m volatile_bot.cli scan --symbols TSLA,NVDA,AMD,META,AMZN,NFLX

# Export trades JSON
python -m volatile_bot.cli backtest --symbols TSLA,NVDA,AMD,QQQ --json-out /tmp/bt.json
```

## Tests

```bash
pip install -e ".[dev]"
pytest -q
```

## Sample results (real Yahoo data, 2026-09-10)

| Universe | Setup | Win rate | Profit factor |
|----------|--------|----------|---------------|
| SPY 2005+ | RSI(2)<5, exit RSI>65, no IBS | 73.86% | 1.62 |
| 8 volatile names 2018+ | RSI(2)<5 + IBS + NATR rank | 70.62% | 1.54 |

Full command lines: [`research/EMPIRICAL_RESULTS.md`](research/EMPIRICAL_RESULTS.md).

## Disclaimer

Educational / research software only. Not financial advice. Markets involve
substantial risk of loss. Past backtests do not predict future results. Yahoo
Finance data can have gaps, adjustments, and survivorship issues.
