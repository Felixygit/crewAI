#!/usr/bin/env python
"""Entry points for the EMA / VWAP stack educational trade-plan agent."""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import yaml

from ema_vwap_stack.models import MissingInputError, Setup
from ema_vwap_stack.rules import build_stack_plan, plan_from_payload, plan_to_yaml_dict
from ema_vwap_stack.sample_data import MU_TREND_PULLBACK, SAMPLE_SNAPSHOTS, get_snapshot

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

DEFAULT_INPUTS = {
    "ticker": "MU",
    "account_equity": 50_000.0,
    "risk_pct": 1.0,
}


def run_rules_only(ticker: str = "MU", tag: str | None = None) -> str:
    """Run the deterministic stack planner without an LLM.

    Useful for local demos and CI where no model API key is available.
    """
    snap = get_snapshot(ticker, tag) or MU_TREND_PULLBACK
    # Allow equity / risk overrides via DEFAULT_INPUTS when planning MU.
    if ticker.upper() == "MU" and tag is None:
        snap = snap.model_copy(
            update={
                "account_equity": float(DEFAULT_INPUTS["account_equity"]),
                "risk_pct": float(DEFAULT_INPUTS["risk_pct"]),
            }
        )
    plan = build_stack_plan(snap)
    payload = plan_to_yaml_dict(plan)

    output_dir = Path(__file__).resolve().parents[2] / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    yaml_text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    (output_dir / "stack_plan_rules_only.yaml").write_text(yaml_text, encoding="utf-8")

    lines = [
        "# EMA / VWAP Stack — Rules-Only Plan",
        "",
        "Educational research output only. Not financial advice. No orders placed.",
        "",
        f"- ticker: {plan.ticker}",
        f"- as_of: {plan.as_of}",
        f"- timeframe: {plan.timeframe}",
        f"- clock: {plan.clock.value}",
        f"- regime: {plan.regime.value}",
        f"- stack.ordered: {plan.stack.ordered}",
        f"- confluence: {plan.confluence_score}/8 — {', '.join(plan.confluence_hits) or 'none'}",
        f"- setup: {plan.setup.value}",
        f"- reason: {plan.reason_in_one_sentence}",
        "",
    ]
    if plan.setup == Setup.NONE or plan.plan is None:
        lines.append("Stand-aside — no live setup.")
    else:
        p = plan.plan
        side = p.side.value if hasattr(p.side, "value") else p.side
        instrument = (
            p.instrument.value if hasattr(p.instrument, "value") else p.instrument
        )
        lines.extend(
            [
                "## Plan",
                f"- side: {side}",
                f"- instrument: {instrument}",
                f"- entry_zone: {p.entry_zone}",
                f"- invalidation: {p.invalidation}",
                f"- target_1: {p.target_1}",
                f"- target_2: {p.target_2}",
                f"- r_dollars: {p.r_dollars}",
                f"- size_rule: {p.size_rule}",
                f"- time_stop: {p.time_stop}",
                f"- kill_switch: {p.kill_switch}",
            ]
        )
    brief = "\n".join(lines) + "\n"
    (output_dir / "stack_plan_rules_only.md").write_text(brief, encoding="utf-8")
    return brief


def run_screen():
    """Print the rules-only plan to stdout (sample MU by default)."""
    ticker = sys.argv[1] if len(sys.argv) > 1 else "MU"
    tag = sys.argv[2] if len(sys.argv) > 2 else None
    print(run_rules_only(ticker=ticker, tag=tag))  # noqa: T201 - CLI entry point


def run_all_samples():
    """Emit a compact table for every offline sample snapshot."""
    rows = []
    for snap in SAMPLE_SNAPSHOTS:
        plan = build_stack_plan(snap)
        rows.append(
            {
                "ticker": plan.ticker,
                "clock": plan.clock.value,
                "regime": plan.regime.value,
                "score": plan.confluence_score,
                "setup": plan.setup.value,
                "reason": plan.reason_in_one_sentence,
            }
        )
    print(json.dumps(rows, indent=2))  # noqa: T201


def run():
    """Run the CrewAI crew (requires a configured LLM provider)."""
    from ema_vwap_stack.crew import EmaVwapStack

    inputs = dict(DEFAULT_INPUTS)
    if len(sys.argv) > 1:
        inputs["ticker"] = sys.argv[1]
    try:
        EmaVwapStack().crew().kickoff(inputs=inputs)
    except Exception as exc:  # noqa: BLE001 - surface crew failures cleanly
        raise RuntimeError(f"An error occurred while running the crew: {exc}") from exc


def plan_json():
    """Read a market snapshot JSON from stdin or a file path argv[1]."""
    if len(sys.argv) > 1:
        raw = Path(sys.argv[1]).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()
    payload = json.loads(raw)
    try:
        plan = plan_from_payload(payload)
    except MissingInputError as exc:
        print(json.dumps({"refused": True, "message": str(exc)}, indent=2))  # noqa: T201
        sys.exit(2)
    print(json.dumps(plan_to_yaml_dict(plan), indent=2))  # noqa: T201


def train():
    from ema_vwap_stack.crew import EmaVwapStack

    inputs = dict(DEFAULT_INPUTS)
    try:
        EmaVwapStack().crew().train(
            n_iterations=int(sys.argv[1]),
            filename=sys.argv[2],
            inputs=inputs,
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"An error occurred while training the crew: {exc}") from exc


def replay():
    from ema_vwap_stack.crew import EmaVwapStack

    try:
        EmaVwapStack().crew().replay(task_id=sys.argv[1])
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"An error occurred while replaying the crew: {exc}") from exc


def test():
    from ema_vwap_stack.crew import EmaVwapStack

    inputs = dict(DEFAULT_INPUTS)
    try:
        EmaVwapStack().crew().test(
            n_iterations=int(sys.argv[1]),
            eval_llm=sys.argv[2],
            inputs=inputs,
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"An error occurred while testing the crew: {exc}") from exc


if __name__ == "__main__":
    run_screen()
