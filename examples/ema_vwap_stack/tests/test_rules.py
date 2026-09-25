"""Behavior tests for the EMA / VWAP stack rule engine."""

from __future__ import annotations

import pytest

from ema_vwap_stack.models import (
    ClockWindow,
    MissingInputError,
    Regime,
    Setup,
    Side,
)
from ema_vwap_stack.rules import (
    build_stack_plan,
    classify_regime,
    label_clock,
    plan_from_payload,
    score_confluence,
    validate_required_inputs,
)
from ema_vwap_stack.sample_data import (
    BEAR_PULLBACK,
    CLOSED_SESSION,
    HTF_OPPOSE,
    MU_CHASE,
    MU_LUNCH_STRONG,
    MU_LUNCH_WEAK,
    MU_TREND_PULLBACK,
    RANGE_FADE,
    VWAP_RECLAIM,
    WHIPSAW,
)


def test_clock_labels_open_midday_power_hour_closed():
    assert label_clock(MU_TREND_PULLBACK.session_time) == ClockWindow.OPEN
    assert label_clock(MU_LUNCH_WEAK.session_time) == ClockWindow.MIDDAY
    assert label_clock(CLOSED_SESSION.session_time) == ClockWindow.CLOSED
    from datetime import time

    assert label_clock(time(15, 30)) == ClockWindow.POWER_HOUR


def test_mu_historical_example_is_trend_up_pullback():
    plan = build_stack_plan(MU_TREND_PULLBACK)
    assert plan.clock == ClockWindow.OPEN
    assert plan.regime == Regime.TREND_UP
    assert plan.stack.ordered is True
    assert plan.confluence_score >= 4
    assert plan.setup == Setup.PULLBACK
    assert plan.plan is not None
    assert plan.plan.side == Side.LONG
    assert "mixed" in plan.reason_in_one_sentence
    assert "long" in plan.reason_in_one_sentence
    # Spec: buy a hold of VWAP then EMA9 — not the extended print / not a put lottery.
    assert "vwap" in plan.plan.entry_zone.lower() or "1060" in plan.plan.entry_zone
    instrument = (
        plan.plan.instrument.value
        if hasattr(plan.plan.instrument, "value")
        else str(plan.plan.instrument)
    )
    assert "put" not in instrument.lower()
    assert instrument in {"shares", "defined-risk debit spread"}


def test_chase_rule_blocks_plan_when_price_left_zone():
    plan = build_stack_plan(MU_CHASE)
    assert plan.setup == Setup.NONE
    assert plan.plan is not None
    assert plan.plan.side == Side.FLAT


def test_lunch_requires_high_confluence():
    weak = build_stack_plan(MU_LUNCH_WEAK)
    assert weak.clock == ClockWindow.MIDDAY
    assert weak.setup == Setup.NONE

    strong = build_stack_plan(MU_LUNCH_STRONG)
    assert strong.clock == ClockWindow.MIDDAY
    assert strong.confluence_score >= 5
    assert strong.setup == Setup.PULLBACK


def test_bear_pullback_short():
    plan = build_stack_plan(BEAR_PULLBACK)
    assert plan.regime == Regime.TREND_DOWN
    assert plan.setup == Setup.PULLBACK
    assert plan.plan is not None
    assert plan.plan.side == Side.SHORT


def test_vwap_reclaim_setup():
    plan = build_stack_plan(VWAP_RECLAIM)
    assert plan.setup == Setup.RECLAIM
    assert plan.plan is not None
    assert plan.plan.side == Side.LONG
    assert "VWAP" in plan.plan.invalidation or "vwap" in plan.plan.invalidation.lower()


def test_range_fade_targets_vwap():
    plan = build_stack_plan(RANGE_FADE)
    assert plan.regime == Regime.RANGE
    assert plan.setup == Setup.FADE
    assert plan.plan is not None
    assert plan.plan.side == Side.SHORT
    assert "VWAP" in plan.plan.target_1


def test_whipsaw_and_htf_oppose_stand_aside():
    assert classify_regime(WHIPSAW) == Regime.STAND_ASIDE
    whip = build_stack_plan(WHIPSAW)
    assert whip.setup == Setup.NONE

    htf = build_stack_plan(HTF_OPPOSE)
    assert htf.regime == Regime.STAND_ASIDE
    assert htf.setup == Setup.NONE


def test_closed_session_stand_aside():
    plan = build_stack_plan(CLOSED_SESSION)
    assert plan.clock == ClockWindow.CLOSED
    assert plan.setup == Setup.NONE


def test_refuse_missing_required_inputs():
    missing = validate_required_inputs({"ticker": "MU"})
    assert "last" in missing
    assert "ema9" in missing
    with pytest.raises(MissingInputError) as exc:
        plan_from_payload({"ticker": "MU", "session_date": "2026-09-22"})
    assert "Missing required inputs" in str(exc.value)


def test_confluence_hits_are_named_and_capped():
    from ema_vwap_stack.rules import assess_fvg, build_stack, label_clock

    snap = MU_TREND_PULLBACK
    stack = build_stack(snap)
    regime = classify_regime(snap, stack)
    clock = label_clock(snap.session_time)
    fvg = assess_fvg(snap, regime)
    score, hits = score_confluence(snap, regime, clock, stack, fvg)
    assert 0 <= score <= 8
    assert score == len(hits)
    assert "stack_agrees_regime" in hits
    assert "tradable_clock_window" in hits


def test_fvg_is_filter_not_standalone_without_stack_overlap():
    from ema_vwap_stack.models import FairValueGap, FvgSide
    from ema_vwap_stack.rules import assess_fvg

    snap = WHIPSAW.model_copy(
        update={
            "emas_whipsawed": False,
            "fvgs": [
                FairValueGap(
                    side=FvgSide.BULLISH,
                    low=260.0,
                    high=265.0,
                    filled=False,
                    timeframe="15m",
                )
            ],
        }
    )
    # Gap sits in empty space far above the stack — no overlap.
    fvg = assess_fvg(snap, Regime.TREND_UP)
    assert fvg.overlaps_stack is False
