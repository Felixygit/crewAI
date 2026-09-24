"""Tests for Alpaca paper trading helpers (no live API calls)."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd

from small_cap_rvol_breakout.alpaca_paper.broker import AlpacaBroker
from small_cap_rvol_breakout.alpaca_paper.config import AlpacaPaperConfig
from small_cap_rvol_breakout.alpaca_paper.market_data import build_quote_from_minutes
from small_cap_rvol_breakout.alpaca_paper.strategy_loop import PaperStrategyRunner
from small_cap_rvol_breakout.models import RiskConfig, Side, TradePlan

ET = ZoneInfo("America/New_York")


def test_build_quote_from_minutes_marks_or_break():
    day = datetime(2026, 9, 15, tzinfo=ET)
    idx = pd.date_range(day.replace(hour=9, minute=30), periods=20, freq="min", tz=ET)
    # First 5 minutes OR 8.0-8.2, then break to 8.5
    rows = []
    for i, _ in enumerate(idx):
        if i < 5:
            rows.append({"open": 8.0, "high": 8.2, "low": 7.95, "close": 8.1, "volume": 50_000})
        elif i == 5:
            rows.append({"open": 8.25, "high": 8.55, "low": 8.2, "close": 8.5, "volume": 200_000})
        else:
            rows.append({"open": 8.5, "high": 8.6, "low": 8.45, "close": 8.55, "volume": 80_000})
    minutes = pd.DataFrame(rows, index=idx)
    daily_idx = pd.date_range("2026-08-01", periods=25, freq="B", tz=ET)
    daily = pd.DataFrame(
        {
            "open": 8.0,
            "high": 8.5,
            "low": 7.5,
            "close": 8.1,
            "volume": 2_000_000,
        },
        index=daily_idx,
    )
    quote = build_quote_from_minutes(
        "TEST",
        minutes,
        daily,
        RiskConfig(opening_range_minutes=5),
        bid=8.54,
        ask=8.56,
    )
    assert quote is not None
    assert quote.or_high == 8.2
    assert quote.broke_or_high is True
    assert quote.last > quote.vwap


def test_broker_dry_run_dual_bracket_does_not_need_client():
    config = AlpacaPaperConfig(
        api_key="",
        api_secret="",
        dry_run=True,
        paper=True,
    )
    broker = AlpacaBroker(config)
    plan = TradePlan(
        symbol="PLUG",
        side=Side.LONG,
        entry=2.10,
        stop=2.00,
        target1=2.25,
        target2=2.40,
        shares=100,
        risk_dollars=10.0,
        reward_to_risk_t1=1.5,
        reward_to_risk_t2=3.0,
        scale_out_shares_t1=50,
        runner_shares=50,
        max_hold_minutes=180,
    )
    orders = broker.submit_dual_bracket(plan)
    assert len(orders) == 2
    assert orders[0].raw["dry_run"] is True


def test_runner_once_submits_actionable_plan(monkeypatch):
    config = AlpacaPaperConfig(
        api_key="k",
        api_secret="s",
        dry_run=True,
        paper=True,
        universe=["PLUG"],
        max_open_positions=3,
    )

    class FakeData:
        def snapshot(self, symbol: str):
            from small_cap_rvol_breakout.models import QuoteSnapshot

            return QuoteSnapshot(
                symbol=symbol,
                last=8.5,
                bid=8.48,
                ask=8.52,
                session_volume=5_000_000,
                avg_volume_tod=1_000_000,
                atr=0.5,
                float_shares=20_000_000,
                or_high=8.2,
                or_low=7.9,
                vwap=8.3,
                broke_or_high=True,
            )

    class FakeBroker(AlpacaBroker):
        def is_market_open(self) -> bool:
            return True

        def account_equity(self) -> float:
            return 25_000

        def open_symbols(self) -> set[str]:
            return set()

    runner = PaperStrategyRunner(config, broker=FakeBroker(config), market_data=FakeData())
    result = runner.run_once()
    assert result.scanned == 1
    assert result.passed_scan == 1
    assert len(result.actionable) == 1
    assert len(result.submitted) == 2  # t1 + t2 brackets


def test_config_refuses_live_mode(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_API_SECRET", "s")
    monkeypatch.setenv("ALPACA_PAPER", "false")
    monkeypatch.setenv("ALPACA_DRY_RUN", "false")
    config = AlpacaPaperConfig.from_env()
    try:
        config.require_credentials()
        raised = False
    except RuntimeError:
        raised = True
    assert raised is True
