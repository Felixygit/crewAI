"""Deterministic RVOL opening-range breakout rules.

This module is intentionally LLM-free so scan/entry/exit logic can be unit-tested
and reused by CrewAI tools.
"""

from __future__ import annotations

from small_cap_rvol_breakout.models import (
    QuoteSnapshot,
    RiskConfig,
    ScanFilters,
    ScreenResult,
    Side,
    TradePlan,
)


def screen_quote(quote: QuoteSnapshot, filters: ScanFilters | None = None) -> ScreenResult:
    """Evaluate one quote against the small-cap high-vol scan filters."""
    filters = filters or ScanFilters()
    reasons: list[str] = []

    if quote.last > filters.max_price:
        reasons.append(f"price {quote.last:.2f} > max {filters.max_price:.2f}")
    if quote.rvol < filters.min_rvol:
        reasons.append(f"rvol {quote.rvol:.2f}x < min {filters.min_rvol:.2f}x")
    if quote.atr_pct < filters.min_atr_pct:
        reasons.append(f"atr% {quote.atr_pct:.2f} < min {filters.min_atr_pct:.2f}")
    if quote.dollar_volume < filters.min_dollar_volume:
        reasons.append(
            f"dollar volume {quote.dollar_volume:,.0f} < min {filters.min_dollar_volume:,.0f}"
        )
    if quote.spread_pct > filters.max_spread_pct:
        reasons.append(
            f"spread {quote.spread_pct:.2f}% > max {filters.max_spread_pct:.2f}%"
        )
    if (
        filters.max_float_shares is not None
        and quote.float_shares is not None
        and quote.float_shares > filters.max_float_shares
    ):
        reasons.append(
            f"float {quote.float_shares:,.0f} > max {filters.max_float_shares:,.0f}"
        )

    return ScreenResult(
        symbol=quote.symbol,
        passed=not reasons,
        reasons=reasons,
        rvol=round(quote.rvol, 2),
        atr_pct=round(quote.atr_pct, 2),
        spread_pct=round(quote.spread_pct, 2),
        dollar_volume=round(quote.dollar_volume, 2),
        last=quote.last,
        float_shares=quote.float_shares,
    )


def screen_universe(
    quotes: list[QuoteSnapshot],
    filters: ScanFilters | None = None,
) -> list[ScreenResult]:
    """Screen many quotes; passed names are sorted by RVOL descending."""
    results = [screen_quote(quote, filters) for quote in quotes]
    passed = [row for row in results if row.passed]
    failed = [row for row in results if not row.passed]
    passed.sort(key=lambda row: row.rvol, reverse=True)
    return passed + failed


def _position_shares(entry: float, stop: float, risk: RiskConfig) -> tuple[int, float]:
    """Return share count and dollars risked for a fixed fractional stop."""
    per_share_risk = entry - stop
    if per_share_risk <= 0:
        return 0, 0.0
    risk_dollars = risk.account_equity * (risk.risk_per_trade_pct / 100.0)
    shares = int(risk_dollars // per_share_risk)
    return shares, round(shares * per_share_risk, 2)


def build_long_breakout_plan(
    quote: QuoteSnapshot,
    filters: ScanFilters | None = None,
    risk: RiskConfig | None = None,
) -> TradePlan:
    """Build a long OR-high breakout plan, or return a skipped plan with reason."""
    filters = filters or ScanFilters()
    risk = risk or RiskConfig()

    screen = screen_quote(quote, filters)
    if not screen.passed:
        return TradePlan(
            symbol=quote.symbol,
            side=Side.FLAT,
            entry=quote.last,
            stop=quote.last,
            target1=quote.last,
            target2=quote.last,
            shares=0,
            risk_dollars=0.0,
            reward_to_risk_t1=0.0,
            reward_to_risk_t2=0.0,
            scale_out_shares_t1=0,
            runner_shares=0,
            max_hold_minutes=risk.max_hold_minutes,
            skip_reason="; ".join(screen.reasons),
        )

    if not quote.broke_or_high:
        return TradePlan(
            symbol=quote.symbol,
            side=Side.FLAT,
            entry=quote.last,
            stop=quote.last,
            target1=quote.last,
            target2=quote.last,
            shares=0,
            risk_dollars=0.0,
            reward_to_risk_t1=0.0,
            reward_to_risk_t2=0.0,
            scale_out_shares_t1=0,
            runner_shares=0,
            max_hold_minutes=risk.max_hold_minutes,
            skip_reason="waiting for opening-range high break with volume",
        )

    if quote.last <= quote.or_high:
        return TradePlan(
            symbol=quote.symbol,
            side=Side.FLAT,
            entry=quote.last,
            stop=quote.last,
            target1=quote.last,
            target2=quote.last,
            shares=0,
            risk_dollars=0.0,
            reward_to_risk_t1=0.0,
            reward_to_risk_t2=0.0,
            scale_out_shares_t1=0,
            runner_shares=0,
            max_hold_minutes=risk.max_hold_minutes,
            skip_reason="last price is not above the opening-range high",
        )

    # Prefer entries that hold above VWAP after the break.
    if quote.last < quote.vwap:
        return TradePlan(
            symbol=quote.symbol,
            side=Side.FLAT,
            entry=quote.last,
            stop=quote.last,
            target1=quote.last,
            target2=quote.last,
            shares=0,
            risk_dollars=0.0,
            reward_to_risk_t1=0.0,
            reward_to_risk_t2=0.0,
            scale_out_shares_t1=0,
            runner_shares=0,
            max_hold_minutes=risk.max_hold_minutes,
            skip_reason="break occurred but price is back below VWAP",
        )

    entry = round(quote.last, 4)
    stop = round(quote.or_high * (1.0 - risk.stop_buffer_pct / 100.0), 4)
    if stop >= entry:
        stop = round(entry * (1.0 - max(risk.stop_buffer_pct, 0.25) / 100.0), 4)

    per_share_risk = entry - stop
    shares, risk_dollars = _position_shares(entry, stop, risk)
    if shares <= 0:
        return TradePlan(
            symbol=quote.symbol,
            side=Side.FLAT,
            entry=entry,
            stop=stop,
            target1=entry,
            target2=entry,
            shares=0,
            risk_dollars=0.0,
            reward_to_risk_t1=0.0,
            reward_to_risk_t2=0.0,
            scale_out_shares_t1=0,
            runner_shares=0,
            max_hold_minutes=risk.max_hold_minutes,
            skip_reason="stop too wide for configured risk budget",
        )

    target1 = round(entry + per_share_risk * risk.target1_r_multiple, 4)
    target2 = round(entry + per_share_risk * risk.target2_r_multiple, 4)
    scale_out = max(1, int(shares * (risk.scale_out_at_target1_pct / 100.0)))
    if scale_out >= shares:
        scale_out = max(1, shares - 1) if shares > 1 else shares
    runner = shares - scale_out

    return TradePlan(
        symbol=quote.symbol,
        side=Side.LONG,
        entry=entry,
        stop=stop,
        target1=target1,
        target2=target2,
        shares=shares,
        risk_dollars=risk_dollars,
        reward_to_risk_t1=risk.target1_r_multiple,
        reward_to_risk_t2=risk.target2_r_multiple,
        scale_out_shares_t1=scale_out,
        runner_shares=runner,
        max_hold_minutes=risk.max_hold_minutes,
        rules_summary=[
            f"Scan passed: price<{filters.max_price}, RVOL>={filters.min_rvol}x, "
            f"ATR%>={filters.min_atr_pct}, liquid, tight spread",
            f"Entry: long break of {risk.opening_range_minutes}m OR high "
            f"({quote.or_high:.2f}) with RVOL {quote.rvol:.2f}x and last above VWAP",
            f"Stop: {stop:.4f} (OR high minus {risk.stop_buffer_pct:.2f}% buffer)",
            f"Targets: T1 {target1:.4f} ({risk.target1_r_multiple}R, sell "
            f"{risk.scale_out_at_target1_pct:.0f}%), T2 {target2:.4f} "
            f"({risk.target2_r_multiple}R runner)",
            f"Size: {shares} shares risking ~${risk_dollars:.2f} "
            f"({risk.risk_per_trade_pct}% of ${risk.account_equity:,.0f})",
            f"Time stop: flatten after {risk.max_hold_minutes} minutes if targets miss",
            "Invalidation: close back inside OR, RVOL collapse, or spread blows out",
        ],
    )


def plans_for_universe(
    quotes: list[QuoteSnapshot],
    filters: ScanFilters | None = None,
    risk: RiskConfig | None = None,
) -> list[TradePlan]:
    """Build plans for every quote; actionable longs first."""
    plans = [build_long_breakout_plan(quote, filters, risk) for quote in quotes]
    actionable = [plan for plan in plans if plan.side == Side.LONG]
    skipped = [plan for plan in plans if plan.side != Side.LONG]
    actionable.sort(key=lambda plan: plan.shares * (plan.entry - plan.stop), reverse=True)
    return actionable + skipped
