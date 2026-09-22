# EMA / VWAP Stack Trade-Plan Agent

Educational CrewAI example that classifies **regime**, scores **confluence**, and emits **one structured trade plan** (or stand-aside). It does **not** place orders and it does **not** promise P&L.

> Educational research only. Not financial advice.

## Mission

Given a ticker, chart timeframe, live quotes, and session clock, decide:

1. Regime — `trend-up` | `trend-down` | `range` | `stand-aside`
2. Whether a setup is live
3. If live — entry zone, invalidation, targets, size rule
4. If not — why, then stop

Completion criterion: **one structured plan object**.

## Pipeline

| Step | What it does |
|------|----------------|
| 1. Session gate | Label clock `open` / `midday` / `power-hour` / `closed` |
| 2. Regime | Ordered EMA 9/20/50 + VWAP stack |
| 3. Confluence | Score 0–8; trade threshold `>= 4` (lunch needs `>= 5`) |
| 4. Setup | Exactly one of `pullback` / `reclaim` / `fade` / `none` |
| 5. Plan | Side, instrument, zone, invalidation, targets, size, time stop, kill switch |

### Allowed setups

- **Trend pullback** (default in trend-up / trend-down) — dip into EMA9 → EMA20 → VWAP
- **VWAP reclaim** — lose VWAP, close back through it while the stack still agrees
- **Range fade** — stretch to VWAP ±2SD or a clear range extreme; target is VWAP

FVGs refine a pullback/reclaim/fade that the stack already allows. An FVG alone is never a trade.

## Project layout

```
examples/ema_vwap_stack/
├── src/ema_vwap_stack/
│   ├── rules.py              # Deterministic gate / regime / confluence / plan
│   ├── models.py             # Snapshot + output schema
│   ├── sample_data.py        # Offline snapshots (incl. historical MU example)
│   ├── tools/stack_tools.py
│   ├── config/{agents,tasks}.yaml
│   ├── crew.py
│   └── main.py
└── tests/test_rules.py
```

## Quick start (no LLM)

```bash
cd examples/ema_vwap_stack
uv sync
uv run pytest
uv run run_plan          # MU historical morning sample
uv run run_all_samples   # compact JSON for every offline snapshot
```

`run_plan` writes `output/stack_plan_rules_only.yaml` and `.md`.

### Plan from your own JSON

```bash
uv run plan_json path/to/snapshot.json
# or: cat snapshot.json | uv run plan_json
```

Required fields (refuses to invent missing ones):

`ticker`, `session_date`, `session_time`, `timeframe`, `last`, `session_open`,
`session_high`, `session_low`, `volume`, `ema9`/`ema20`/`ema50` (`value` + `slope`),
`vwap`, `yesterday_high`/`yesterday_low`, `opening_range_high`/`opening_range_low`
(after the open has printed), `nasdaq_direction`.

## Run the CrewAI agents (LLM required)

```bash
cp .env.example .env
# set OPENAI_API_KEY or another CrewAI-supported provider
uv sync
uv run run_crew
# optional: uv run run_crew AMD
```

Agents:

- **regime_analyst** — clock + regime via `ema_vwap_stack_plan`
- **stack_strategist** — confluence + setup
- **risk_scribe** — final schema object → `output/stack_plan.yaml`

## Worked example (MU, 22 Sep 2026 morning — historical)

Inputs then: 4h EMAs, daily VWAP, price ~1080, EMA9 ~1041, EMA20 ~1017, VWAP ~1062.

| Field | Result |
|-------|--------|
| clock | `open` |
| regime | `trend-up` |
| stack.ordered | `true` |
| setup | `pullback` (buy a hold of VWAP then EMA9, **not** the extended print) |
| invalidation | sustained hold under VWAP then EMA9 |
| not a put | far-OTM lottery puts fail regime, confluence, and instrument rules |

That example is documentation, not a live signal. The agent also names the VWAP/EMA timeframe mix (daily VWAP on a 4h chart) and treats VWAP as a session location filter only.

## Hard rules (enforced in `rules.py`)

- Stand-aside is the default
- One setup per ticker per window
- Stop belongs beyond invalidation
- Do not chase when price already left the zone by more than **0.6%**
- Do not emit a plan during lunch unless confluence **>= 5**
- Never recommend naked short options or cheap far-OTM lottery options
- No stack overlap → ignore the FVG

## Output schema

```yaml
ticker:
as_of:
timeframe:
clock: open | midday | power-hour | closed
regime: trend-up | trend-down | range | stand-aside
stack: { price, ema9, ema20, ema50, vwap, ordered }
confluence_score: 0-8
confluence_hits: []
fvg: { present, side, overlaps_stack, zone }
setup: pullback | reclaim | fade | none
plan: { side, instrument, entry_zone, invalidation, target_1, target_2,
        r_dollars, size_rule, time_stop, kill_switch }
reason_in_one_sentence:
```

## Support

- [CrewAI docs](https://docs.crewai.com)
- [CrewAI examples](https://github.com/crewAIInc/crewAI-examples)
