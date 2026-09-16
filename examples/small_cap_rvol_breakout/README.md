# Small-Cap RVOL Opening-Range Breakout Crew

CrewAI example that screens **sub-$20, high-volume, high-volatility small caps** and builds **opening-range high breakout** trade plans.

> Educational research only. Not financial advice. Do not trade real capital from this sample without your own testing, broker data, and risk controls.

## Strategy rules (defaults)

### Scan
| Filter | Default |
|--------|---------|
| Max price | `$20` |
| Min relative volume (RVOL) | `2.0x` same time-of-day average |
| Min ATR% | `3.0%` of price |
| Min dollar volume | `$5,000,000` |
| Max spread | `1.0%` of mid |
| Max float (optional) | `50,000,000` shares |

### Entry (long)
1. Symbol must pass the scan.
2. Wait for the first **5-minute opening range**.
3. Enter only after a **break of the OR high** with volume confirmation.
4. Require **last ≥ VWAP** after the break (avoid failed breakouts that already lost VWAP).

### Exit / risk
| Rule | Default |
|------|---------|
| Stop | OR high minus `0.15%` buffer |
| Risk per trade | `0.5%` of account equity |
| Target 1 | `1.5R` — sell `50%` |
| Target 2 | `3R` runner |
| Time stop | Flatten after `180` minutes if targets miss |
| Invalidation | Close back inside OR, RVOL collapse, or spread blowout |

## Project layout

```
examples/small_cap_rvol_breakout/
├── src/small_cap_rvol_breakout/
│   ├── rules.py              # Deterministic scan / entry / exit engine
│   ├── models.py             # Quote, filter, and trade-plan models
│   ├── sample_data.py        # Offline synthetic quotes
│   ├── tools/screener_tools.py
│   ├── config/{agents,tasks}.yaml
│   ├── crew.py
│   └── main.py
└── tests/test_rules.py
```

## Quick start (no LLM)

From this directory:

```bash
cd examples/small_cap_rvol_breakout
uv sync
uv run pytest
uv run run_screen
```

`run_screen` writes `output/morning_brief_rules_only.md` using the sample universe (`VOLA`, `PUMP`, `WAIT`, …).

## Run the CrewAI agents (LLM required)

1. Copy env and add a provider key:

```bash
cp .env.example .env
# set OPENAI_API_KEY or another CrewAI-supported provider
```

2. Install and run:

```bash
uv sync
crewai run
# or: uv run run_crew
```

Agents:
- **market_screener** — runs `small_cap_rvol_screener`
- **breakout_strategist** — runs `rvol_breakout_trade_plan` per ticker
- **risk_officer** — writes the final brief to `output/morning_brief.md`

## Wiring live data

Replace `SAMPLE_QUOTES` (or pass a custom `quotes=` list into the tools) with snapshots from your broker / market-data vendor. Each `QuoteSnapshot` needs:

`symbol, last, bid, ask, session_volume, avg_volume_tod, atr, or_high, or_low, vwap, broke_or_high`, plus optional `float_shares`.

## Support

- [CrewAI docs](https://docs.crewai.com)
- [CrewAI examples](https://github.com/crewAIInc/crewAI-examples)
