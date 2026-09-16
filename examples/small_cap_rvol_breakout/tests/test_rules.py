"""Behavior tests for the RVOL breakout rule engine."""

from __future__ import annotations

from small_cap_rvol_breakout.models import QuoteSnapshot, RiskConfig, ScanFilters, Side
from small_cap_rvol_breakout.rules import (
    build_long_breakout_plan,
    screen_quote,
    screen_universe,
)
from small_cap_rvol_breakout.sample_data import SAMPLE_QUOTES


def _by_symbol(symbol: str) -> QuoteSnapshot:
    return next(quote for quote in SAMPLE_QUOTES if quote.symbol == symbol)


def test_screen_passes_liquid_sub20_high_rvol_names():
    filters = ScanFilters()
    passed = {row.symbol for row in screen_universe(SAMPLE_QUOTES, filters) if row.passed}
    assert "VOLA" in passed
    assert "PUMP" in passed
    assert "WAIT" in passed
    assert "FADE" in passed
    assert "THIN" not in passed
    assert "BIGX" not in passed


def test_screen_rejects_wide_spread_and_low_liquidity():
    result = screen_quote(_by_symbol("THIN"))
    assert result.passed is False
    assert any("spread" in reason or "dollar volume" in reason for reason in result.reasons)


def test_screen_rejects_price_above_max():
    result = screen_quote(_by_symbol("BIGX"), ScanFilters(max_price=20.0))
    assert result.passed is False
    assert any("price" in reason for reason in result.reasons)


def test_plan_builds_long_for_confirmed_breakout():
    plan = build_long_breakout_plan(
        _by_symbol("VOLA"),
        risk=RiskConfig(account_equity=25_000, risk_per_trade_pct=0.5),
    )
    assert plan.side == Side.LONG
    assert plan.shares > 0
    assert plan.stop < plan.entry < plan.target1 < plan.target2
    assert plan.scale_out_shares_t1 + plan.runner_shares == plan.shares
    assert plan.skip_reason is None
    assert plan.risk_dollars <= 25_000 * 0.005 + 1e-6


def test_plan_skips_when_still_inside_opening_range():
    plan = build_long_breakout_plan(_by_symbol("WAIT"))
    assert plan.side == Side.FLAT
    assert plan.shares == 0
    assert plan.skip_reason is not None
    assert "opening-range" in plan.skip_reason


def test_plan_skips_when_price_loses_vwap_after_break():
    plan = build_long_breakout_plan(_by_symbol("FADE"))
    assert plan.side == Side.FLAT
    assert "VWAP" in (plan.skip_reason or "")


def test_passed_results_sorted_by_rvol_descending():
    passed = [row for row in screen_universe(SAMPLE_QUOTES) if row.passed]
    rvols = [row.rvol for row in passed]
    assert rvols == sorted(rvols, reverse=True)


def test_wide_stop_can_zero_size_when_risk_budget_is_tiny():
    quote = _by_symbol("PUMP")
    plan = build_long_breakout_plan(
        quote,
        risk=RiskConfig(account_equity=100.0, risk_per_trade_pct=0.1),
    )
    # With a tiny budget the engine should either size small or skip cleanly.
    assert plan.shares >= 0
    if plan.shares == 0:
        assert plan.side == Side.FLAT
        assert plan.skip_reason is not None
