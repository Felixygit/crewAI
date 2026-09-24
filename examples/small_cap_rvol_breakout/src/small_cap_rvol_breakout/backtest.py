"""One-year opening-range breakout backtest for the small-cap RVOL strategy.

Uses Yahoo hourly bars as a practical proxy for a 5-minute opening range:
the first regular-session hour defines the OR high/low. Relative volume at
entry is measured from session volume so far versus expected volume, so the
signal does not peek at the full-day total.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from small_cap_rvol_breakout.models import RiskConfig, ScanFilters

ET = ZoneInfo("America/New_York")
SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)
HOURS_IN_SESSION = 6.5


@dataclass
class BacktestConfig:
    """Runtime knobs for the historical simulation."""

    lookback_days: int = 365
    filters: ScanFilters = field(default_factory=ScanFilters)
    risk: RiskConfig = field(default_factory=RiskConfig)
    min_price: float = 1.0
    slippage_pct: float = 0.05
    commission_per_share: float = 0.0
    max_trades_per_day: int = 3
    require_close_above_vwap: bool = True
    eod_flatten: bool = True


@dataclass
class TradeResult:
    """One completed round-trip."""

    symbol: str
    entry_time: datetime
    exit_time: datetime
    entry: float
    exit: float
    stop: float
    target1: float
    target2: float
    shares: int
    pnl: float
    return_pct: float
    r_multiple: float
    exit_reason: str
    rvol_at_entry: float
    atr_pct: float


@dataclass
class BacktestSummary:
    """Aggregate performance stats."""

    start: date
    end: date
    symbols_tested: int
    trades: list[TradeResult]
    starting_equity: float
    ending_equity: float
    total_pnl: float
    total_return_pct: float
    win_rate: float
    profit_factor: float
    avg_r: float
    max_drawdown_pct: float
    avg_trades_per_week: float


def _to_et_index(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    if idx.tz is None:
        return idx.tz_localize("UTC").tz_convert(ET)
    return idx.tz_convert(ET)


def _session_dates(index: pd.DatetimeIndex) -> pd.Series:
    return pd.Series(index.date, index=index)


def compute_daily_stats(daily: pd.DataFrame) -> pd.DataFrame:
    """Build prior-day ATR% and 20-session average volume (no look-ahead)."""
    high, low, close, volume = daily["High"], daily["Low"], daily["Close"], daily["Volume"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(14, min_periods=14).mean()
    out = pd.DataFrame(
        {
            "close": close,
            "volume": volume,
            # Shift so the signal day only sees completed prior sessions.
            "atr_pct": ((atr / close) * 100.0).shift(1),
            "avg_vol_20": volume.rolling(20, min_periods=20).mean().shift(1),
        },
        index=daily.index,
    )
    return out


def _vwap(session: pd.DataFrame) -> pd.Series:
    typical = (session["High"] + session["Low"] + session["Close"]) / 3.0
    cum_vol = session["Volume"].cumsum().replace(0, np.nan)
    return (typical * session["Volume"]).cumsum() / cum_vol


def _apply_slippage(price: float, side: str, slippage_pct: float) -> float:
    bump = price * (slippage_pct / 100.0)
    if side == "buy":
        return price + bump
    return price - bump


def simulate_symbol(
    symbol: str,
    hourly: pd.DataFrame,
    daily: pd.DataFrame,
    config: BacktestConfig,
) -> list[TradeResult]:
    """Simulate OR-high breakouts for one symbol over the hourly history."""
    if hourly.empty or daily.empty:
        return []

    hourly = hourly.copy()
    hourly.index = _to_et_index(hourly.index)
    hourly = hourly.sort_index()
    hourly = hourly.between_time(SESSION_OPEN, SESSION_CLOSE)

    daily = daily.copy()
    daily.index = _to_et_index(pd.DatetimeIndex(daily.index)).normalize()
    daily = daily.sort_index()
    stats = compute_daily_stats(daily)

    trades: list[TradeResult] = []
    risk = config.risk
    filters = config.filters

    for session_day, session in hourly.groupby(hourly.index.date):
        session = session.sort_index()
        if len(session) < 2:
            continue

        day_ts = pd.Timestamp(datetime.combine(session_day, time(0, 0), tzinfo=ET))
        usable = stats.loc[:day_ts]
        if usable.empty:
            # Fall back when daily labels are date-only / tz-normalized differently.
            usable = stats[stats.index.date <= session_day]
        if usable.empty:
            continue
        day_stats = usable.iloc[-1]

        avg_vol = float(day_stats["avg_vol_20"]) if pd.notna(day_stats["avg_vol_20"]) else 0.0
        atr_pct = float(day_stats["atr_pct"]) if pd.notna(day_stats["atr_pct"]) else 0.0
        if avg_vol <= 0 or atr_pct < filters.min_atr_pct:
            continue

        or_bar = session.iloc[0]
        or_high = float(or_bar["High"])
        or_low = float(or_bar["Low"])
        if or_high <= or_low:
            continue

        session = session.copy()
        session["vwap"] = _vwap(session)
        session["cum_vol"] = session["Volume"].cumsum()

        entry_idx = None
        for i in range(1, len(session)):
            bar = session.iloc[i]
            last = float(bar["Close"])
            if not (config.min_price <= last <= filters.max_price):
                continue

            # Expected volume by this clock time, using full-day average.
            minutes_elapsed = (
                (bar.name.hour * 60 + bar.name.minute)
                - (SESSION_OPEN.hour * 60 + SESSION_OPEN.minute)
                + 60  # bar is ~1h wide; count completed hour
            )
            minutes_elapsed = max(60, min(int(HOURS_IN_SESSION * 60), minutes_elapsed))
            expected = avg_vol * (minutes_elapsed / (HOURS_IN_SESSION * 60))
            rvol = float(bar["cum_vol"]) / expected if expected > 0 else 0.0
            dollar_vol = float(bar["cum_vol"]) * last
            if rvol < filters.min_rvol or dollar_vol < filters.min_dollar_volume:
                continue
            if atr_pct < filters.min_atr_pct:
                continue

            # Break of OR high: use bar high cross, fill at OR high or open of bar.
            if float(bar["High"]) <= or_high:
                continue
            vwap = float(bar["vwap"]) if pd.notna(bar["vwap"]) else last
            fill_raw = max(or_high, float(bar["Open"]))
            if config.require_close_above_vwap and last < vwap:
                continue
            # Confirm the break held into the close of the signal bar.
            if last <= or_high:
                continue

            entry_idx = i
            entry_raw = fill_raw
            entry_rvol = rvol
            break

        if entry_idx is None:
            continue

        entry = _apply_slippage(entry_raw, "buy", config.slippage_pct)
        stop = or_high * (1.0 - risk.stop_buffer_pct / 100.0)
        if stop >= entry:
            stop = entry * (1.0 - max(risk.stop_buffer_pct, 0.25) / 100.0)
        per_share_risk = entry - stop
        if per_share_risk <= 0:
            continue

        risk_dollars = risk.account_equity * (risk.risk_per_trade_pct / 100.0)
        shares = int(risk_dollars // per_share_risk)
        if shares <= 0:
            continue

        target1 = entry + per_share_risk * risk.target1_r_multiple
        target2 = entry + per_share_risk * risk.target2_r_multiple
        scale = max(1, int(shares * (risk.scale_out_at_target1_pct / 100.0)))
        if scale >= shares and shares > 1:
            scale = shares - 1
        runner = shares - scale

        entry_time = session.index[entry_idx]
        max_hold = timedelta(minutes=risk.max_hold_minutes)
        remaining = shares
        realized = 0.0
        t1_done = False
        exit_time = session.index[-1]
        exit_px = float(session.iloc[-1]["Close"])
        exit_reason = "eod" if config.eod_flatten else "session_end"

        for j in range(entry_idx + 1, len(session)):
            bar = session.iloc[j]
            ts = session.index[j]
            if ts - entry_time >= max_hold:
                px = _apply_slippage(float(bar["Open"]), "sell", config.slippage_pct)
                realized += remaining * (px - entry)
                remaining = 0
                exit_time, exit_px, exit_reason = ts, px, "time_stop"
                break

            low = float(bar["Low"])
            high = float(bar["High"])

            # Conservative path: if stop and target both touched, assume stop first.
            if low <= stop:
                px = _apply_slippage(stop, "sell", config.slippage_pct)
                realized += remaining * (px - entry)
                remaining = 0
                exit_time, exit_px, exit_reason = ts, px, "stop"
                break

            if not t1_done and high >= target1 and scale > 0:
                px = _apply_slippage(target1, "sell", config.slippage_pct)
                realized += scale * (px - entry)
                remaining -= scale
                t1_done = True
                exit_time, exit_px, exit_reason = ts, px, "target1"
                if remaining <= 0:
                    break

            if t1_done and remaining > 0 and high >= target2:
                px = _apply_slippage(target2, "sell", config.slippage_pct)
                realized += remaining * (px - entry)
                remaining = 0
                exit_time, exit_px, exit_reason = ts, px, "target2"
                break

        if remaining > 0:
            px = _apply_slippage(float(session.iloc[-1]["Close"]), "sell", config.slippage_pct)
            realized += remaining * (px - entry)
            exit_time = session.index[-1]
            exit_px = px
            exit_reason = "eod" if t1_done is False else "eod_after_t1"

        commission = config.commission_per_share * shares * 2
        pnl = realized - commission
        r_mult = pnl / (per_share_risk * shares) if shares else 0.0
        ret_pct = (pnl / (entry * shares)) * 100.0 if shares else 0.0

        trades.append(
            TradeResult(
                symbol=symbol,
                entry_time=entry_time.to_pydatetime(),
                exit_time=exit_time.to_pydatetime(),
                entry=round(entry, 4),
                exit=round(exit_px, 4),
                stop=round(stop, 4),
                target1=round(target1, 4),
                target2=round(target2, 4),
                shares=shares,
                pnl=round(pnl, 2),
                return_pct=round(ret_pct, 3),
                r_multiple=round(r_mult, 3),
                exit_reason=exit_reason,
                rvol_at_entry=round(entry_rvol, 2),
                atr_pct=round(atr_pct, 2),
            )
        )

    return trades


def _equity_curve(trades: list[TradeResult], starting_equity: float) -> pd.Series:
    if not trades:
        return pd.Series([starting_equity])
    ordered = sorted(trades, key=lambda t: t.exit_time)
    equity = starting_equity
    points = []
    for trade in ordered:
        equity += trade.pnl
        points.append((trade.exit_time, equity))
    return pd.Series({ts: val for ts, val in points})


def _max_drawdown_pct(curve: pd.Series) -> float:
    if curve.empty:
        return 0.0
    peak = curve.cummax()
    dd = (curve - peak) / peak.replace(0, np.nan)
    return float(dd.min() * 100.0) if len(dd) else 0.0


def summarize_trades(
    trades: list[TradeResult],
    starting_equity: float,
    symbols_tested: int,
    start: date,
    end: date,
) -> BacktestSummary:
    """Aggregate trade list into summary metrics."""
    # Enforce max trades/day globally by keeping earliest entries.
    by_day: dict[date, list[TradeResult]] = {}
    for trade in sorted(trades, key=lambda t: t.entry_time):
        by_day.setdefault(trade.entry_time.date(), []).append(trade)

    capped: list[TradeResult] = []
    # max_trades_per_day applied by caller usually; keep all here if already capped
    for day_trades in by_day.values():
        capped.extend(day_trades)

    total_pnl = sum(t.pnl for t in capped)
    ending = starting_equity + total_pnl
    wins = [t for t in capped if t.pnl > 0]
    losses = [t for t in capped if t.pnl <= 0]
    gross_win = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0
    win_rate = (len(wins) / len(capped) * 100.0) if capped else 0.0
    avg_r = float(np.mean([t.r_multiple for t in capped])) if capped else 0.0
    curve = _equity_curve(capped, starting_equity)
    weeks = max((end - start).days / 7.0, 1.0)

    return BacktestSummary(
        start=start,
        end=end,
        symbols_tested=symbols_tested,
        trades=capped,
        starting_equity=starting_equity,
        ending_equity=round(ending, 2),
        total_pnl=round(total_pnl, 2),
        total_return_pct=round((ending / starting_equity - 1.0) * 100.0, 2),
        win_rate=round(win_rate, 2),
        profit_factor=round(profit_factor, 2) if profit_factor != float("inf") else float("inf"),
        avg_r=round(avg_r, 3),
        max_drawdown_pct=round(_max_drawdown_pct(curve), 2),
        avg_trades_per_week=round(len(capped) / weeks, 2),
    )


def cap_trades_per_day(trades: list[TradeResult], max_trades: int) -> list[TradeResult]:
    """Keep the earliest trades each day up to ``max_trades``."""
    if max_trades <= 0:
        return []
    selected: list[TradeResult] = []
    for _, group in sorted(
        _group_by_day(trades).items(),
        key=lambda item: item[0],
    ):
        chosen = sorted(group, key=lambda t: t.entry_time)[:max_trades]
        selected.extend(chosen)
    return selected


def _group_by_day(trades: Iterable[TradeResult]) -> dict[date, list[TradeResult]]:
    out: dict[date, list[TradeResult]] = {}
    for trade in trades:
        out.setdefault(trade.entry_time.date(), []).append(trade)
    return out


def format_summary(summary: BacktestSummary) -> str:
    """Human-readable backtest report."""
    lines = [
        "# Small-Cap RVOL ORB Backtest (1h opening-range proxy)",
        "",
        "Educational simulation only. Not financial advice. Yahoo hourly data is"
        " a proxy for a 5-minute OR and includes slippage assumptions.",
        "",
        f"- Period: {summary.start} → {summary.end}",
        f"- Symbols tested: {summary.symbols_tested}",
        f"- Trades: {len(summary.trades)} ({summary.avg_trades_per_week:.2f}/week)",
        f"- Starting equity: ${summary.starting_equity:,.0f}",
        f"- Ending equity: ${summary.ending_equity:,.2f}",
        f"- Total P&L: ${summary.total_pnl:,.2f} ({summary.total_return_pct:+.2f}%)",
        f"- Win rate: {summary.win_rate:.1f}%",
        f"- Profit factor: {summary.profit_factor if summary.profit_factor != float('inf') else 'inf'}",
        f"- Avg R-multiple: {summary.avg_r:.3f}",
        f"- Max drawdown: {summary.max_drawdown_pct:.2f}%",
        "",
        "## Exit reason breakdown",
    ]
    reasons: dict[str, int] = {}
    for trade in summary.trades:
        reasons[trade.exit_reason] = reasons.get(trade.exit_reason, 0) + 1
    if not reasons:
        lines.append("- None")
    else:
        for reason, count in sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"- {reason}: {count}")

    lines.extend(["", "## Top / bottom trades by P&L"])
    if not summary.trades:
        lines.append("- None")
    else:
        ranked = sorted(summary.trades, key=lambda t: t.pnl, reverse=True)
        for trade in ranked[:5]:
            lines.append(
                f"- + {trade.symbol} {trade.entry_time.date()} "
                f"${trade.pnl:.2f} ({trade.r_multiple:+.2f}R, {trade.exit_reason})"
            )
        lines.append("- ...")
        for trade in ranked[-5:]:
            lines.append(
                f"- - {trade.symbol} {trade.entry_time.date()} "
                f"${trade.pnl:.2f} ({trade.r_multiple:+.2f}R, {trade.exit_reason})"
            )
    return "\n".join(lines) + "\n"
