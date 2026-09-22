"""Deterministic EMA / VWAP stack rule engine.

LLM-free so session gate, regime, confluence, setup, and plan logic can be
unit-tested and reused by CrewAI tools. Educational research only — not advice.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

from ema_vwap_stack.models import (
    REQUIRED_FIELDS,
    ClockWindow,
    FairValueGap,
    FvgAssessment,
    FvgSide,
    Instrument,
    MarketDirection,
    MarketSnapshot,
    MissingInputError,
    Regime,
    Setup,
    Side,
    Slope,
    StackPlan,
    StackSnapshot,
    TradePlanFields,
)

# US equity regular session (Eastern).
_SESSION_OPEN = time(9, 30)
_SESSION_CLOSE = time(16, 0)
_OPEN_END = time(11, 0)  # first 90 minutes
_LUNCH_START = time(11, 30)
_LUNCH_END = time(14, 0)
_POWER_HOUR_START = time(15, 0)

_LEVEL_NEAR_PCT = 0.3  # fixed level within 0.3% of EMA9/20/VWAP
_CHASE_PCT = 0.6  # do not chase when price left the zone by more than this
_TRADE_THRESHOLD = 4
_LUNCH_MIN_CONFLUENCE = 5


def validate_required_inputs(payload: dict[str, Any]) -> list[str]:
    """Return missing required field names; empty list means the payload is usable."""
    missing = [name for name in REQUIRED_FIELDS if payload.get(name) is None]
    # Opening-range fields: required once the open has had time to print (~15m).
    session_time = payload.get("session_time")
    if isinstance(session_time, str):
        try:
            session_time = time.fromisoformat(session_time)
        except ValueError:
            session_time = None
    if isinstance(session_time, time) and session_time >= time(9, 45):
        for name in ("opening_range_high", "opening_range_low"):
            if payload.get(name) is None and name not in missing:
                missing.append(name)
    return missing


def label_clock(session_time: time) -> ClockWindow:
    """Step 1 — session gate clock label."""
    if session_time < _SESSION_OPEN or session_time >= _SESSION_CLOSE:
        return ClockWindow.CLOSED
    if _SESSION_OPEN <= session_time < _OPEN_END:
        return ClockWindow.OPEN
    if _POWER_HOUR_START <= session_time < _SESSION_CLOSE:
        return ClockWindow.POWER_HOUR
    return ClockWindow.MIDDAY


def _in_lunch(session_time: time) -> bool:
    return _LUNCH_START <= session_time < _LUNCH_END


def _pct_distance(a: float, b: float) -> float:
    if b == 0:
        return float("inf")
    return abs(a - b) / b * 100.0


def _round_number_near(price: float, radius_pct: float = 0.35) -> float | None:
    """Return a nearby psychological round if within radius_pct."""
    if price >= 1000:
        step = 50.0
    elif price >= 100:
        step = 5.0
    elif price >= 20:
        step = 1.0
    else:
        step = 0.5
    candidate = round(price / step) * step
    if _pct_distance(price, candidate) <= radius_pct:
        return float(candidate)
    return None


def build_stack(snap: MarketSnapshot) -> StackSnapshot:
    """Capture price vs EMA / VWAP ordering."""
    price, e9, e20, e50, vwap = (
        snap.last,
        snap.ema9.value,
        snap.ema20.value,
        snap.ema50.value,
        snap.vwap,
    )
    bull_ordered = price > e9 > e20 > e50 and price > vwap
    # Soft bull: EMA20 only slightly below EMA50 while 50 still rising.
    soft_bull = (
        price > e9 > e20
        and e20 >= e50 * 0.998
        and snap.ema50.slope == Slope.RISING
        and price > vwap
    )
    bear_ordered = price < e9 < e20 < e50 and price < vwap
    soft_bear = (
        price < e9 < e20
        and e20 <= e50 * 1.002
        and snap.ema50.slope == Slope.FALLING
        and price < vwap
    )
    ordered = bull_ordered or soft_bull or bear_ordered or soft_bear
    return StackSnapshot(
        price=price,
        ema9=e9,
        ema20=e20,
        ema50=e50,
        vwap=vwap,
        ordered=ordered,
    )


def classify_regime(snap: MarketSnapshot, stack: StackSnapshot | None = None) -> Regime:
    """Step 2 — classify regime on the EMA timeframe."""
    stack = stack or build_stack(snap)
    e9, e20, e50 = snap.ema9, snap.ema20, snap.ema50

    if snap.emas_whipsawed:
        return Regime.STAND_ASIDE

    if (
        snap.higher_timeframe_regime is not None
        and snap.higher_timeframe_regime
        in (Regime.TREND_UP, Regime.TREND_DOWN, Regime.STAND_ASIDE)
    ):
        # Defer HTF opposition check until we know local trend direction.
        pass

    if (
        snap.next_catalyst_date is not None
        and not snap.trade_event_risk
    ):
        as_of = datetime.combine(snap.session_date, snap.session_time)
        catalyst_start = datetime.combine(snap.next_catalyst_date, time(0, 0))
        hold_end = as_of + timedelta(hours=snap.hold_window_hours)
        if as_of.date() <= snap.next_catalyst_date <= hold_end.date():
            # Catalyst inside the hold window without event-risk consent.
            if abs((catalyst_start - as_of).total_seconds()) <= snap.hold_window_hours * 3600:
                return Regime.STAND_ASIDE

    # VWAP and EMA20 disagree and neither is respected.
    vwap_vs_e20 = (snap.vwap - e20.value) / e20.value * 100.0
    price_respects_vwap = _pct_distance(snap.last, snap.vwap) <= 0.25 or (
        (snap.last > snap.vwap and e9.slope == Slope.RISING)
        or (snap.last < snap.vwap and e9.slope == Slope.FALLING)
    )
    price_respects_e20 = _pct_distance(snap.last, e20.value) <= 0.35 or (
        (snap.last > e20.value and e20.slope == Slope.RISING)
        or (snap.last < e20.value and e20.slope == Slope.FALLING)
    )
    if abs(vwap_vs_e20) > 0.5 and not price_respects_vwap and not price_respects_e20:
        return Regime.STAND_ASIDE

    bull = (
        snap.last > e9.value
        and e9.value > e20.value
        and (
            e20.value > e50.value
            or (e20.value >= e50.value * 0.998 and e50.slope == Slope.RISING)
        )
        and e9.slope == Slope.RISING
        and e20.slope == Slope.RISING
        and snap.last > snap.vwap
    )
    bear = (
        snap.last < e9.value
        and e9.value < e20.value
        and (
            e20.value < e50.value
            or (e20.value <= e50.value * 1.002 and e50.slope == Slope.FALLING)
        )
        and e9.slope == Slope.FALLING
        and e20.slope == Slope.FALLING
        and snap.last < snap.vwap
    )

    if bull:
        if (
            snap.higher_timeframe_regime == Regime.TREND_DOWN
            or snap.higher_timeframe_regime == Regime.STAND_ASIDE
        ):
            return Regime.STAND_ASIDE
        return Regime.TREND_UP
    if bear:
        if (
            snap.higher_timeframe_regime == Regime.TREND_UP
            or snap.higher_timeframe_regime == Regime.STAND_ASIDE
        ):
            return Regime.STAND_ASIDE
        return Regime.TREND_DOWN

    flat_or_tangled = (
        e9.slope == Slope.FLAT
        or e20.slope == Slope.FLAT
        or abs(e9.value - e20.value) / e20.value * 100.0 < 0.15
        or (e9.value > e20.value) != (snap.last > snap.vwap)
    )
    if flat_or_tangled or not stack.ordered:
        return Regime.RANGE

    return Regime.STAND_ASIDE


def _fixed_levels(snap: MarketSnapshot) -> list[tuple[str, float]]:
    levels: list[tuple[str, float]] = [
        ("yesterday_high", snap.yesterday_high),
        ("yesterday_low", snap.yesterday_low),
    ]
    if snap.opening_range_high is not None:
        levels.append(("or_high", snap.opening_range_high))
    if snap.opening_range_low is not None:
        levels.append(("or_low", snap.opening_range_low))
    rn = _round_number_near(snap.last)
    if rn is not None:
        levels.append(("round", rn))
    return levels


def _price_at_fixed_level(snap: MarketSnapshot, tol_pct: float = 0.35) -> str | None:
    for name, level in _fixed_levels(snap):
        if _pct_distance(snap.last, level) <= tol_pct:
            return name
    return None


def _level_near_stack_line(snap: MarketSnapshot, level: float) -> bool:
    for line in (snap.ema9.value, snap.ema20.value, snap.vwap):
        if _pct_distance(level, line) <= _LEVEL_NEAR_PCT:
            return True
    return False


def _select_relevant_fvg(snap: MarketSnapshot, regime: Regime) -> FairValueGap | None:
    """Pick an unfilled same-side FVG that overlaps a stack line."""
    wanted = {
        Regime.TREND_UP: FvgSide.BULLISH,
        Regime.TREND_DOWN: FvgSide.BEARISH,
        Regime.RANGE: None,  # either side ok at extremes
    }.get(regime)

    candidates: list[FairValueGap] = []
    for gap in snap.fvgs:
        if gap.filled or gap.side == FvgSide.NONE:
            continue
        if wanted is not None and gap.side != wanted:
            continue
        overlaps = any(
            gap.low <= line <= gap.high
            or _pct_distance(line, gap.midpoint) <= _LEVEL_NEAR_PCT
            for line in (snap.ema9.value, snap.ema20.value, snap.vwap)
        )
        if not overlaps:
            continue
        candidates.append(gap)

    if not candidates:
        return None
    # Prefer higher-timeframe magnets when tagged.
    candidates.sort(key=lambda g: (0 if g.timeframe and g.timeframe != snap.timeframe else 1))
    return candidates[0]


def assess_fvg(snap: MarketSnapshot, regime: Regime) -> FvgAssessment:
    gap = _select_relevant_fvg(snap, regime)
    if gap is None:
        return FvgAssessment(
            present=any(not g.filled and g.side != FvgSide.NONE for g in snap.fvgs),
            side=FvgSide.NONE,
            overlaps_stack=False,
            zone=None,
        )
    return FvgAssessment(
        present=True,
        side=gap.side,
        overlaps_stack=True,
        zone=f"{gap.low:.4f}-{gap.high:.4f}",
    )


def score_confluence(
    snap: MarketSnapshot,
    regime: Regime,
    clock: ClockWindow,
    stack: StackSnapshot,
    fvg: FvgAssessment,
) -> tuple[int, list[str]]:
    """Step 3 — score confluence 0–8 and list true hits."""
    hits: list[str] = []

    # 1. Stack agrees with regime
    if regime == Regime.TREND_UP and stack.ordered and snap.last > snap.vwap:
        hits.append("stack_agrees_regime")
    elif regime == Regime.TREND_DOWN and stack.ordered and snap.last < snap.vwap:
        hits.append("stack_agrees_regime")
    elif regime == Regime.RANGE and not stack.ordered:
        hits.append("stack_agrees_regime")

    # 2. Price at a fixed level
    level_name = _price_at_fixed_level(snap)
    level_value: float | None = None
    if level_name is not None:
        hits.append(f"at_fixed_level:{level_name}")
        for name, value in _fixed_levels(snap):
            if name == level_name:
                level_value = value
                break

    # 3. That fixed level sits inside 0.3% of EMA9 / EMA20 / VWAP
    if level_value is not None and _level_near_stack_line(snap, level_value):
        hits.append("level_near_stack_line")

    # 4. Pullback volume contracted then reaction on rising volume
    if snap.pullback_volume_contracted and snap.reaction_volume_rising:
        hits.append("volume_contraction_then_expansion")

    # 5. Relative strength vs QQQ / Nasdaq
    if regime == Regime.TREND_UP and snap.nasdaq_direction in (
        MarketDirection.UP,
        MarketDirection.MIXED,
    ):
        if snap.sector_direction == MarketDirection.UP or (
            snap.sector_direction is None and snap.nasdaq_direction == MarketDirection.UP
        ):
            hits.append("strong_vs_qqq_or_sector")
    elif regime == Regime.TREND_DOWN and snap.nasdaq_direction in (
        MarketDirection.DOWN,
        MarketDirection.MIXED,
    ):
        if snap.sector_direction == MarketDirection.DOWN or (
            snap.sector_direction is None and snap.nasdaq_direction == MarketDirection.DOWN
        ):
            hits.append("weak_vs_qqq_or_sector")

    # 6. Reaction candle quality
    if snap.reaction_wick_against_or_strong_close:
        hits.append("reaction_candle_quality")

    # 7. Clock is open or power-hour
    if clock in (ClockWindow.OPEN, ClockWindow.POWER_HOUR):
        hits.append("tradable_clock_window")

    # 8. Unfilled same-side FVG overlaps stack
    if fvg.present and fvg.overlaps_stack and fvg.side != FvgSide.NONE:
        hits.append("fvg_overlaps_stack")

    return len(hits), hits


def _nearest_rising_line(snap: MarketSnapshot) -> tuple[str, float]:
    """Long pullback: first stack line price will tag on the way down.

    Among EMA9, EMA20, and VWAP still below last, pick the highest (nearest
    support). That is EMA9 first when it is the closest rising line; otherwise
    EMA20 or VWAP when VWAP is the nearest rising line.
    """
    candidates: list[tuple[str, float]] = [
        ("ema9", snap.ema9.value),
        ("ema20", snap.ema20.value),
        ("vwap", snap.vwap),
    ]
    below = [(n, v) for n, v in candidates if v <= snap.last]
    if not below:
        return "ema9", snap.ema9.value
    below.sort(key=lambda row: row[1], reverse=True)
    return below[0]


def _nearest_falling_line(snap: MarketSnapshot) -> tuple[str, float]:
    """Short pullback: first stack line price will tag on the way up."""
    candidates: list[tuple[str, float]] = [
        ("ema9", snap.ema9.value),
        ("ema20", snap.ema20.value),
        ("vwap", snap.vwap),
    ]
    above = [(n, v) for n, v in candidates if v >= snap.last]
    if not above:
        return "ema9", snap.ema9.value
    above.sort(key=lambda row: row[1])  # lowest resistance first
    return above[0]


def choose_setup(
    snap: MarketSnapshot,
    regime: Regime,
    clock: ClockWindow,
    score: int,
    fvg: FvgAssessment,
) -> Setup:
    """Step 4 — pick the only allowed setup."""
    if regime == Regime.STAND_ASIDE:
        return Setup.NONE
    if score < _TRADE_THRESHOLD:
        return Setup.NONE
    if clock == ClockWindow.CLOSED:
        return Setup.NONE
    if _in_lunch(snap.session_time) and score < _LUNCH_MIN_CONFLUENCE:
        return Setup.NONE
    if snap.zero_to_three_dte_options and snap.session_time >= _LUNCH_START:
        # Extra penalty: prefer morning-only for 0–3 DTE.
        if clock != ClockWindow.OPEN and score < _LUNCH_MIN_CONFLUENCE + 1:
            return Setup.NONE

    if snap.price_left_zone_pct is not None and snap.price_left_zone_pct > _CHASE_PCT:
        return Setup.NONE

    # B. VWAP reclaim (when reclaim flags present)
    emas_rolling_against_long = (
        snap.ema9.slope == Slope.FALLING and snap.ema20.slope == Slope.FALLING
    )
    emas_rolling_against_short = (
        snap.ema9.slope == Slope.RISING and snap.ema20.slope == Slope.RISING
    )
    if (
        snap.dipped_under_vwap
        and snap.reclaim_bar_closed_above_vwap
        and not emas_rolling_against_long
        and regime in (Regime.TREND_UP, Regime.RANGE)
        and snap.ema9.slope in (Slope.RISING, Slope.FLAT)
    ):
        return Setup.RECLAIM
    if (
        snap.popped_over_vwap
        and snap.reclaim_bar_closed_below_vwap
        and not emas_rolling_against_short
        and regime in (Regime.TREND_DOWN, Regime.RANGE)
        and snap.ema9.slope in (Slope.FALLING, Slope.FLAT)
    ):
        return Setup.RECLAIM

    # C. Range fade
    if regime == Regime.RANGE:
        has_bands = snap.vwap_plus_2sd is not None and snap.vwap_minus_2sd is not None
        at_high = (
            has_bands
            and snap.last >= (snap.vwap_plus_2sd or 0) * 0.999
        ) or (
            snap.opening_range_high is not None
            and _pct_distance(snap.last, snap.opening_range_high) <= 0.2
            and snap.last > snap.vwap
        )
        at_low = (
            has_bands
            and snap.last <= (snap.vwap_minus_2sd or float("inf")) * 1.001
        ) or (
            snap.opening_range_low is not None
            and _pct_distance(snap.last, snap.opening_range_low) <= 0.2
            and snap.last < snap.vwap
        )
        if at_high or at_low:
            return Setup.FADE
        return Setup.NONE

    # A. Trend pullback (default)
    if regime in (Regime.TREND_UP, Regime.TREND_DOWN):
        return Setup.PULLBACK

    return Setup.NONE


def _entry_zone_around(
    line: float,
    buffer_pct: float,
    fvg: FairValueGap | None,
    line_name: str = "line",
) -> tuple[float, float, str]:
    half = line * (buffer_pct / 100.0)
    low, high = line - half, line + half
    note = f"{low:.4f}-{high:.4f} ({line_name} {line:.4f} ±{buffer_pct:.2f}%)"
    if fvg is not None:
        # Shrink to FVG overlap; prefer CE (midpoint), not far edge.
        low = max(low, fvg.low)
        high = min(high, fvg.high)
        if low > high:
            low, high = fvg.low, fvg.high
        mid = fvg.midpoint
        # Tighten around CE within the overlap.
        pad = (high - low) * 0.25
        low, high = mid - pad, mid + pad
        note = (
            f"{low:.4f}-{high:.4f} (FVG CE {mid:.4f} on {line_name} "
            f"{line:.4f}, gap {fvg.low:.4f}-{fvg.high:.4f})"
        )
    return low, high, note


def _next_round_above(price: float) -> float:
    if price >= 1000:
        step = 50.0
    elif price >= 100:
        step = 5.0
    else:
        step = 1.0
    return (int(price / step) + 1) * step


def _next_round_below(price: float) -> float:
    if price >= 1000:
        step = 50.0
    elif price >= 100:
        step = 5.0
    else:
        step = 1.0
    return int(price / step) * step


def _stand_aside_plan(reason: str) -> TradePlanFields:
    return TradePlanFields(
        side=Side.FLAT,
        instrument=Instrument.SHARES,
        entry_zone="none",
        invalidation="none",
        target_1="none",
        target_2="none",
        r_dollars="none",
        size_rule="none",
        time_stop="none",
        kill_switch=reason,
    )


def build_plan_fields(
    snap: MarketSnapshot,
    regime: Regime,
    setup: Setup,
    fvg_assessment: FvgAssessment,
) -> TradePlanFields:
    """Step 5 — fill every plan field or stand-aside."""
    if setup == Setup.NONE:
        return _stand_aside_plan("setup=none; stand-aside is the default")

    gap = _select_relevant_fvg(snap, regime)
    risk_dollars = snap.account_equity * (snap.risk_pct / 100.0)

    if setup == Setup.PULLBACK and regime == Regime.TREND_UP:
        line_name, line = _nearest_rising_line(snap)
        low, high, zone = _entry_zone_around(line, snap.entry_buffer_pct, gap, line_name)
        # Invalidation: close through FVG and the line, beyond the reaction wick.
        inv = (gap.low if gap else line) * (1.0 - snap.entry_buffer_pct / 100.0)
        t1 = snap.yesterday_high if snap.yesterday_high > snap.last else _next_round_above(snap.last)
        t2 = _next_round_above(t1)
        one_r = abs(((low + high) / 2.0) - inv)
        size = f"risk ${risk_dollars:.2f} / 1R ${one_r:.4f} → ~{int(risk_dollars // one_r) if one_r > 0 else 0} shares"
        return TradePlanFields(
            side=Side.LONG,
            instrument=Instrument.SHARES,
            entry_zone=zone,
            invalidation=f"{inv:.4f} (close through {line_name}"
            + (" and FVG" if gap else "")
            + ")",
            target_1=f"{t1:.4f} (scale 50%)",
            target_2=f"{t2:.4f} (runners)",
            r_dollars=f"{one_r:.4f}",
            size_rule=size,
            time_stop="scratch if not +0.5R by the next session window change",
            kill_switch=(
                f"kill if price loses {line_name} on rising volume, Nasdaq flips down, "
                "or a close fills through the long invalidation in the next 30m; "
                f"upgrade if reaction holds {line_name} with rising volume"
                + (" and FVG CE bid" if gap else "")
            ),
        )

    if setup == Setup.PULLBACK and regime == Regime.TREND_DOWN:
        line_name, line = _nearest_falling_line(snap)
        low, high, zone = _entry_zone_around(line, snap.entry_buffer_pct, gap, line_name)
        inv = (gap.high if gap else line) * (1.0 + snap.entry_buffer_pct / 100.0)
        t1 = snap.yesterday_low if snap.yesterday_low < snap.last else _next_round_below(snap.last)
        t2 = _next_round_below(t1)
        one_r = abs(inv - (low + high) / 2.0)
        size = f"risk ${risk_dollars:.2f} / 1R ${one_r:.4f} → ~{int(risk_dollars // one_r) if one_r > 0 else 0} shares"
        return TradePlanFields(
            side=Side.SHORT,
            instrument=Instrument.SHARES,
            entry_zone=zone,
            invalidation=f"{inv:.4f} (close through {line_name}"
            + (" and FVG" if gap else "")
            + ")",
            target_1=f"{t1:.4f} (scale 50%)",
            target_2=f"{t2:.4f} (runners)",
            r_dollars=f"{one_r:.4f}",
            size_rule=size,
            time_stop="scratch if not +0.5R by the next session window change",
            kill_switch=(
                f"kill if price reclaims {line_name} on rising volume or Nasdaq flips up "
                "in the next 30m; upgrade if rejection holds with expanding volume"
            ),
        )

    if setup == Setup.RECLAIM:
        long_side = bool(snap.reclaim_bar_closed_above_vwap)
        side = Side.LONG if long_side else Side.SHORT
        mid = snap.vwap
        low, high, zone = _entry_zone_around(mid, snap.entry_buffer_pct, gap, "vwap")
        if long_side:
            inv = mid * (1.0 - snap.entry_buffer_pct / 100.0)
            t1 = snap.yesterday_high if snap.yesterday_high > snap.last else _next_round_above(snap.last)
            t2 = _next_round_above(t1)
        else:
            inv = mid * (1.0 + snap.entry_buffer_pct / 100.0)
            t1 = snap.yesterday_low if snap.yesterday_low < snap.last else _next_round_below(snap.last)
            t2 = _next_round_below(t1)
        one_r = abs(((low + high) / 2.0) - inv)
        size = f"risk ${risk_dollars:.2f} / 1R ${one_r:.4f} → ~{int(risk_dollars // one_r) if one_r > 0 else 0} shares"
        return TradePlanFields(
            side=side,
            instrument=Instrument.SHARES,
            entry_zone=zone,
            invalidation=(
                f"{inv:.4f} (return under/over VWAP and fail to reclaim next bar)"
            ),
            target_1=f"{t1:.4f} (scale 50%)",
            target_2=f"{t2:.4f} (runners)",
            r_dollars=f"{one_r:.4f}",
            size_rule=size,
            time_stop="scratch if not +0.5R by the next session window change",
            kill_switch=(
                "kill if the next bar loses VWAP again without reclaim; "
                "upgrade if EMA9 flattens with the reclaim and volume expands"
            ),
        )

    # Fade
    short_fade = snap.last > snap.vwap
    side = Side.SHORT if short_fade else Side.LONG
    extreme = (
        snap.vwap_plus_2sd
        if short_fade and snap.vwap_plus_2sd is not None
        else snap.vwap_minus_2sd
        if not short_fade and snap.vwap_minus_2sd is not None
        else snap.opening_range_high
        if short_fade
        else snap.opening_range_low
    )
    if extreme is None:
        return _stand_aside_plan("fade skipped: no VWAP bands or clear range extreme")
    low, high, zone = _entry_zone_around(extreme, snap.entry_buffer_pct, gap, "range_extreme")
    if short_fade:
        inv = extreme * (1.0 + snap.entry_buffer_pct / 100.0)
    else:
        inv = extreme * (1.0 - snap.entry_buffer_pct / 100.0)
    t1 = snap.vwap
    t2 = snap.vwap  # target remains VWAP, not a new trend
    one_r = abs(((low + high) / 2.0) - inv)
    size = f"risk ${risk_dollars:.2f} / 1R ${one_r:.4f} → ~{int(risk_dollars // one_r) if one_r > 0 else 0} shares"
    return TradePlanFields(
        side=side,
        instrument=Instrument.SHARES,
        entry_zone=zone,
        invalidation=f"{inv:.4f} (range extreme breaks and holds)",
        target_1=f"{t1:.4f} (VWAP, scale 50%)",
        target_2=f"{t2:.4f} (VWAP runners — do not project a new trend)",
        r_dollars=f"{one_r:.4f}",
        size_rule=size,
        time_stop="scratch if not +0.5R by the next session window change",
        kill_switch=(
            "kill if the range extreme breaks and holds on volume; "
            "upgrade if rejection prints at the band with VWAP still flat"
        ),
    )


def build_stack_plan(snap: MarketSnapshot) -> StackPlan:
    """Run the full EMA / VWAP stack pipeline into one structured plan object."""
    clock = label_clock(snap.session_time)
    stack = build_stack(snap)
    regime = classify_regime(snap, stack)

    if clock == ClockWindow.CLOSED:
        regime = Regime.STAND_ASIDE

    fvg = assess_fvg(snap, regime)
    score, hits = score_confluence(snap, regime, clock, stack, fvg)

    # Hard rule: lunch needs confluence >= 5
    setup = choose_setup(snap, regime, clock, score, fvg)
    if regime == Regime.STAND_ASIDE:
        setup = Setup.NONE

    plan_fields = build_plan_fields(snap, regime, setup, fvg)

    uncertainty = ""
    if snap.vwap_source_mismatch:
        uncertainty = (
            " VWAP source vs EMA timeframe is mixed — VWAP used as session "
            "location filter only."
        )

    side_label = (
        plan_fields.side.value
        if isinstance(plan_fields.side, Side)
        else str(plan_fields.side)
    )
    if setup == Setup.NONE:
        reason = (
            f"Stand-aside: regime={regime.value}, clock={clock.value}, "
            f"confluence={score}/8."
            + uncertainty
        )
    else:
        reason = (
            f"{setup.value} {side_label} with confluence {score}/8 "
            f"in {regime.value} during {clock.value}."
            + uncertainty
        )

    as_of = f"{snap.session_date.isoformat()} {snap.session_time.strftime('%H:%M')} ET"
    return StackPlan(
        ticker=snap.ticker,
        as_of=as_of,
        timeframe=snap.timeframe,
        clock=clock,
        regime=regime if setup != Setup.NONE or regime == Regime.STAND_ASIDE else regime,
        stack=stack,
        confluence_score=score,
        confluence_hits=hits,
        fvg=fvg,
        setup=setup,
        plan=plan_fields,
        reason_in_one_sentence=reason.strip(),
    )


def plan_from_payload(payload: dict[str, Any]) -> StackPlan:
    """Validate required inputs then build a plan; never invent missing fields."""
    missing = validate_required_inputs(payload)
    if missing:
        raise MissingInputError(
            "Missing required inputs: "
            + ", ".join(missing)
            + ". Provide them and retry; refuse to invent values."
        )
    snap = MarketSnapshot.model_validate(payload)
    return build_stack_plan(snap)


def plan_to_yaml_dict(plan: StackPlan) -> dict[str, Any]:
    """Serialize a plan into the documented YAML-shaped dict."""
    data = plan.model_dump(mode="json")
    # Enum values already serialized via mode=json.
    return data
