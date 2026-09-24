#!/usr/bin/env python
"""Entry points for the small-cap RVOL breakout example."""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

from small_cap_rvol_breakout.models import RiskConfig, ScanFilters, Side
from small_cap_rvol_breakout.rules import plans_for_universe, screen_universe
from small_cap_rvol_breakout.sample_data import SAMPLE_QUOTES

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

DEFAULT_INPUTS = {
    "max_price": 20.0,
    "min_rvol": 2.0,
    "min_atr_pct": 3.0,
    "account_equity": 25_000.0,
    "risk_per_trade_pct": 0.5,
}


def _filters_from_inputs(inputs: dict) -> ScanFilters:
    return ScanFilters(
        max_price=float(inputs["max_price"]),
        min_rvol=float(inputs["min_rvol"]),
        min_atr_pct=float(inputs["min_atr_pct"]),
    )


def _risk_from_inputs(inputs: dict) -> RiskConfig:
    return RiskConfig(
        account_equity=float(inputs["account_equity"]),
        risk_per_trade_pct=float(inputs["risk_per_trade_pct"]),
    )


def run_rules_only(inputs: dict | None = None) -> str:
    """Run the deterministic screener/planner without an LLM.

    Useful for local demos and CI where no model API key is available.
    """
    inputs = {**DEFAULT_INPUTS, **(inputs or {})}
    filters = _filters_from_inputs(inputs)
    risk = _risk_from_inputs(inputs)

    screens = [row for row in screen_universe(SAMPLE_QUOTES, filters) if row.passed]
    plans = plans_for_universe(SAMPLE_QUOTES, filters, risk)
    actionable = [plan for plan in plans if plan.side == Side.LONG]
    waiting = [plan for plan in plans if plan.side != Side.LONG and plan.symbol in {s.symbol for s in screens}]

    lines = [
        "# Small-Cap RVOL Breakout — Rules-Only Brief",
        "",
        "Educational research output only. Not financial advice.",
        "",
        "## Scan filters",
        (
            f"- price <= ${filters.max_price:.2f}, RVOL >= {filters.min_rvol:.1f}x, "
            f"ATR% >= {filters.min_atr_pct:.1f}, equity ${risk.account_equity:,.0f}, "
            f"risk {risk.risk_per_trade_pct}%/trade"
        ),
        "",
        "## Passed scan",
    ]
    if not screens:
        lines.append("- None")
    else:
        for row in screens:
            lines.append(
                f"- **{row.symbol}**: last ${row.last:.2f}, RVOL {row.rvol:.2f}x, "
                f"ATR% {row.atr_pct:.2f}, $vol {row.dollar_volume:,.0f}, "
                f"spread {row.spread_pct:.2f}%"
            )

    lines.extend(["", "## Actionable long plans"])
    if not actionable:
        lines.append("- None")
    else:
        for plan in actionable:
            lines.append(
                f"- **{plan.symbol}**: buy {plan.shares} @ {plan.entry:.2f}, "
                f"stop {plan.stop:.2f}, T1 {plan.target1:.2f} "
                f"({plan.scale_out_shares_t1} sh), T2 {plan.target2:.2f} "
                f"({plan.runner_shares} sh), risk ${plan.risk_dollars:.2f}"
            )

    lines.extend(["", "## Waiting / skipped (passed scan only)"])
    if not waiting:
        lines.append("- None")
    else:
        for plan in waiting:
            lines.append(f"- **{plan.symbol}**: {plan.skip_reason}")

    lines.extend(
        [
            "",
            "## Risk reminders",
            f"- Time stop: {risk.max_hold_minutes} minutes",
            f"- Scale out {risk.scale_out_at_target1_pct:.0f}% at T1 "
            f"({risk.target1_r_multiple}R); leave runner for T2 "
            f"({risk.target2_r_multiple}R)",
            "- Invalidate on close back inside OR, RVOL collapse, or spread blowout",
        ]
    )

    brief = "\n".join(lines) + "\n"
    output_dir = Path(__file__).resolve().parents[2] / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "morning_brief_rules_only.md").write_text(brief, encoding="utf-8")
    return brief


def run():
    """Run the CrewAI crew (requires a configured LLM provider)."""
    from small_cap_rvol_breakout.crew import SmallCapRvolBreakout

    inputs = dict(DEFAULT_INPUTS)
    try:
        SmallCapRvolBreakout().crew().kickoff(inputs=inputs)
    except Exception as exc:  # noqa: BLE001 - surface crew failures cleanly
        raise RuntimeError(f"An error occurred while running the crew: {exc}") from exc


def run_screen():
    """Print the rules-only brief to stdout."""
    print(run_rules_only())  # noqa: T201 - CLI entry point


def train():
    from small_cap_rvol_breakout.crew import SmallCapRvolBreakout

    inputs = dict(DEFAULT_INPUTS)
    try:
        SmallCapRvolBreakout().crew().train(
            n_iterations=int(sys.argv[1]),
            filename=sys.argv[2],
            inputs=inputs,
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"An error occurred while training the crew: {exc}") from exc


def replay():
    from small_cap_rvol_breakout.crew import SmallCapRvolBreakout

    try:
        SmallCapRvolBreakout().crew().replay(task_id=sys.argv[1])
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"An error occurred while replaying the crew: {exc}") from exc


def test():
    from small_cap_rvol_breakout.crew import SmallCapRvolBreakout

    inputs = dict(DEFAULT_INPUTS)
    try:
        SmallCapRvolBreakout().crew().test(
            n_iterations=int(sys.argv[1]),
            eval_llm=sys.argv[2],
            inputs=inputs,
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"An error occurred while testing the crew: {exc}") from exc


def dump_sample_quotes():
    """Emit sample quotes as JSON for external scanners."""
    print(json.dumps([q.model_dump() for q in SAMPLE_QUOTES], indent=2))  # noqa: T201


if __name__ == "__main__":
    run_screen()
