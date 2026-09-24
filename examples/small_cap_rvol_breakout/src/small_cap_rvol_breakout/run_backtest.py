#!/usr/bin/env python
"""Download history and run the 1-year RVOL ORB backtest."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from small_cap_rvol_breakout.backtest import (
    BacktestConfig,
    TradeResult,
    cap_trades_per_day,
    format_summary,
    simulate_symbol,
    summarize_trades,
)
from small_cap_rvol_breakout.models import RiskConfig, ScanFilters

# Liquid names that frequently trade in/near the sub-$20 band.
DEFAULT_UNIVERSE = [
    "PLUG", "OPEN", "AMC", "SOFI", "MARA", "RIOT", "CLSK", "CIFR", "HUT",
    "SNAP", "NIO", "AAL", "JOBY", "ACHR", "LUNR", "RKLB", "SMR", "UUUU",
    "URG", "HL", "CDE", "AG", "PAAS", "BTG", "DNN", "UEC", "NAK",
    "BBAI", "SOUN", "RGTI", "QBTS", "QUBT", "IONQ", "PATH", "ONDS",
    "EOSE", "LCID", "RIVN", "FCEL", "BLNK", "CHPT", "EVGO", "CLOV",
    "FUBO", "SPCE", "ARRY", "KOPN", "MNKD", "CABA", "ALT", "EDIT",
    "ABAT", "SENS", "OCGN", "JBLU", "ULCC", "RIG", "KOS", "BORR",
    "GRAB", "NOK", "BBD", "ABEV", "NU", "VALE", "WULF", "APLD",
    "HIVE", "CORZ", "BTDR", "BTBT", "SGML", "LAC", "MP", "NNE",
    "SERV", "RR", "BYND", "PTON", "TLRY", "CGC", "MSOS", "BNGO",
]


def _download_symbol(symbol: str, start: date, end: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    ticker = yf.Ticker(symbol)
    hourly = ticker.history(
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        interval="1h",
        auto_adjust=True,
    )
    daily = ticker.history(
        start=(start - timedelta(days=60)).isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        interval="1d",
        auto_adjust=True,
    )
    return hourly, daily


def run_backtest(
    symbols: list[str] | None = None,
    lookback_days: int = 365,
    account_equity: float = 25_000.0,
    risk_per_trade_pct: float = 0.5,
    max_trades_per_day: int = 3,
) -> tuple[str, list[TradeResult]]:
    """Run the backtest and return a markdown report plus trades."""
    symbols = symbols or DEFAULT_UNIVERSE
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=lookback_days)

    config = BacktestConfig(
        lookback_days=lookback_days,
        filters=ScanFilters(max_price=20.0, min_rvol=2.0, min_atr_pct=3.0, min_dollar_volume=5_000_000.0),
        risk=RiskConfig(account_equity=account_equity, risk_per_trade_pct=risk_per_trade_pct),
        max_trades_per_day=max_trades_per_day,
    )

    all_trades: list[TradeResult] = []
    tested = 0
    errors: list[str] = []

    for symbol in symbols:
        try:
            hourly, daily = _download_symbol(symbol, start, end)
            if hourly is None or hourly.empty or daily is None or daily.empty:
                errors.append(f"{symbol}: no data")
                continue
            tested += 1
            all_trades.extend(simulate_symbol(symbol, hourly, daily, config))
        except Exception as exc:  # noqa: BLE001 - keep batch running
            errors.append(f"{symbol}: {exc}")

    capped = cap_trades_per_day(all_trades, config.max_trades_per_day)
    summary = summarize_trades(
        capped,
        starting_equity=account_equity,
        symbols_tested=tested,
        start=start,
        end=end,
    )
    report = format_summary(summary)
    if errors:
        report += "\n## Data warnings\n"
        for err in errors[:30]:
            report += f"- {err}\n"
        if len(errors) > 30:
            report += f"- ... and {len(errors) - 30} more\n"

    return report, summary.trades


def main() -> None:
    report, trades = run_backtest()
    out_dir = Path(__file__).resolve().parents[2] / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "backtest_1y_report.md"
    trades_path = out_dir / "backtest_1y_trades.json"
    report_path.write_text(report, encoding="utf-8")
    payload = [
        {
            "symbol": t.symbol,
            "entry_time": t.entry_time.isoformat(),
            "exit_time": t.exit_time.isoformat(),
            "entry": t.entry,
            "exit": t.exit,
            "stop": t.stop,
            "target1": t.target1,
            "target2": t.target2,
            "shares": t.shares,
            "pnl": t.pnl,
            "return_pct": t.return_pct,
            "r_multiple": t.r_multiple,
            "exit_reason": t.exit_reason,
            "rvol_at_entry": t.rvol_at_entry,
            "atr_pct": t.atr_pct,
        }
        for t in trades
    ]
    trades_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(report)  # noqa: T201
    print(f"Wrote {report_path}")  # noqa: T201
    print(f"Wrote {trades_path} ({len(trades)} trades)")  # noqa: T201


if __name__ == "__main__":
    main()
