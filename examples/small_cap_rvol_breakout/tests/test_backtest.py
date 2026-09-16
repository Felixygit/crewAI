"""Unit tests for the ORB backtest engine using synthetic bars."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from small_cap_rvol_breakout.backtest import (
    BacktestConfig,
    cap_trades_per_day,
    simulate_symbol,
    summarize_trades,
)
from small_cap_rvol_breakout.models import RiskConfig, ScanFilters

ET = ZoneInfo("America/New_York")


def _bar(ts: datetime, o: float, h: float, l: float, c: float, v: float) -> dict:
    return {"Open": o, "High": h, "Low": l, "Close": c, "Volume": v}


def test_simulate_symbol_takes_orb_long_and_hits_targets():
    # Build ~25 daily bars for ATR/avg volume warm-up, then one signal day.
    days = pd.bdate_range("2025-08-01", periods=30, tz=ET)
    daily_rows = []
    for i, d in enumerate(days[:-1]):
        px = 8.0 + (i % 5) * 0.1
        daily_rows.append(
            {
                "Open": px,
                "High": px + 0.4,
                "Low": px - 0.4,
                "Close": px + 0.1,
                "Volume": 2_000_000,
            }
        )
    daily = pd.DataFrame(daily_rows, index=days[:-1])

    signal_day = days[-1]
    hourly_index = [
        signal_day + pd.Timedelta(hours=9, minutes=30),
        signal_day + pd.Timedelta(hours=10, minutes=30),
        signal_day + pd.Timedelta(hours=11, minutes=30),
        signal_day + pd.Timedelta(hours=12, minutes=30),
        signal_day + pd.Timedelta(hours=13, minutes=30),
    ]
    # OR hour: 8.0-8.2, then break to 8.5 with huge volume, then run to targets.
    hourly = pd.DataFrame(
        [
            _bar(hourly_index[0], 8.0, 8.2, 7.9, 8.1, 3_000_000),
            _bar(hourly_index[1], 8.25, 8.55, 8.2, 8.5, 4_000_000),
            _bar(hourly_index[2], 8.5, 8.9, 8.45, 8.85, 1_000_000),
            _bar(hourly_index[3], 8.85, 9.3, 8.8, 9.2, 1_000_000),
            _bar(hourly_index[4], 9.2, 9.4, 9.0, 9.3, 500_000),
        ],
        index=pd.DatetimeIndex(hourly_index),
    )

    config = BacktestConfig(
        filters=ScanFilters(max_price=20, min_rvol=2.0, min_atr_pct=1.0, min_dollar_volume=1_000_000),
        risk=RiskConfig(account_equity=25_000, risk_per_trade_pct=0.5, stop_buffer_pct=0.15),
        slippage_pct=0.0,
    )
    trades = simulate_symbol("TEST", hourly, daily, config)
    assert len(trades) == 1
    trade = trades[0]
    assert trade.shares > 0
    assert trade.pnl > 0
    assert trade.exit_reason in {"target1", "target2", "eod_after_t1", "eod"}


def test_cap_trades_per_day_keeps_earliest():
    from small_cap_rvol_breakout.backtest import TradeResult

    base = dict(
        exit_time=datetime(2026, 1, 2, 15, tzinfo=ET),
        entry=10.0,
        exit=10.5,
        stop=9.8,
        target1=10.3,
        target2=10.6,
        shares=100,
        pnl=50.0,
        return_pct=5.0,
        r_multiple=1.0,
        exit_reason="eod",
        rvol_at_entry=3.0,
        atr_pct=4.0,
    )
    trades = [
        TradeResult(symbol="A", entry_time=datetime(2026, 1, 2, 10, 30, tzinfo=ET), **base),
        TradeResult(symbol="B", entry_time=datetime(2026, 1, 2, 11, 30, tzinfo=ET), **base),
        TradeResult(symbol="C", entry_time=datetime(2026, 1, 2, 12, 30, tzinfo=ET), **base),
    ]
    capped = cap_trades_per_day(trades, max_trades=2)
    assert [t.symbol for t in capped] == ["A", "B"]


def test_summarize_handles_empty():
    summary = summarize_trades([], 25_000, 0, date_start(), date_end())
    assert summary.total_pnl == 0
    assert summary.win_rate == 0


def date_start():
    from datetime import date

    return date(2025, 9, 16)


def date_end():
    from datetime import date

    return date(2026, 9, 16)
