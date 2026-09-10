"""CLI for backtesting and scanning high-volatility mean-reversion setups."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as `python -m volatile_bot.cli` from src layout
_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from volatile_bot.backtest import PortfolioBacktester
from volatile_bot.data import DEFAULT_VOLATILE_UNIVERSE, download_universe
from volatile_bot.scanner import scan_universe
from volatile_bot.strategy import MeanReversionStrategy, StrategyConfig


def _fmt_pct(x: float | None) -> str:
    if x is None:
        return "n/a"
    return f"{100.0 * x:.2f}%"


def cmd_backtest(args: argparse.Namespace) -> int:
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    print(
        "Downloading real Yahoo Finance data for:",
        ", ".join(symbols),
        flush=True,
    )
    data = download_universe(symbols, start=args.start, end=args.end or None)
    cfg = StrategyConfig(
        rsi_entry_max=args.rsi_entry,
        ibs_entry_max=args.ibs_entry,
        require_ibs_filter=not args.no_ibs,
        require_above_sma200=not args.no_trend_filter,
        exit_mode=args.exit_mode,
        max_hold_days=args.max_hold,
        min_natr=args.min_natr,
    )
    bt = PortfolioBacktester(
        strategy=MeanReversionStrategy(cfg),
        initial_capital=args.capital,
        max_positions=args.max_positions,
        commission_pct=args.commission,
        slippage_pct=args.slippage,
    )
    result = bt.run(data)
    summary = result.summary()

    print("\n=== Backtest summary (computed from live-downloaded prices) ===")
    print(f"Symbols loaded : {len(data)}")
    print(f"Trades         : {summary['trades']}")
    print(f"Win rate       : {_fmt_pct(summary['win_rate'])}")
    pf = summary["profit_factor"]
    print(f"Profit factor  : {'n/a' if pf is None else f'{pf:.3f}'}")
    exp = summary["expectancy_pct"]
    print(f"Avg trade      : {'n/a' if exp is None else f'{100.0 * exp:.3f}%'}")
    print(f"Total return   : {_fmt_pct(summary['total_return'])}")
    print(f"Max drawdown   : {_fmt_pct(summary['max_drawdown'])}")
    print(f"Final equity   : {summary['final_equity']}")
    print(
        "\nNote: Published Connors RSI(2) studies often report ~70–76% win rates on "
        "index ETFs with a 200-SMA filter. Multi-stock results vary. This run's win "
        "rate is the empirical value above — not a hardcoded guarantee."
    )

    if args.json_out:
        payload = {
            "summary": summary,
            "config": cfg.__dict__,
            "trades": [
                {
                    "symbol": t.symbol,
                    "entry_date": str(t.entry_date.date()),
                    "exit_date": str(t.exit_date.date()),
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "pnl": t.pnl,
                    "return_pct": t.return_pct,
                    "bars_held": t.bars_held,
                    "entry_natr": t.entry_natr,
                    "entry_rsi": t.entry_rsi,
                }
                for t in result.trades
            ],
        }
        Path(args.json_out).write_text(json.dumps(payload, indent=2, default=str))
        print(f"Wrote {args.json_out}")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    data = download_universe(symbols, start=args.start)
    cfg = StrategyConfig(
        rsi_entry_max=args.rsi_entry,
        ibs_entry_max=args.ibs_entry,
        require_ibs_filter=not args.no_ibs,
        require_above_sma200=not args.no_trend_filter,
        min_natr=args.min_natr,
    )
    hits = scan_universe(data, MeanReversionStrategy(cfg))
    if not hits:
        print("No entry signals on the latest bar.")
        return 0
    print(f"{'SYMBOL':<8} {'DATE':<12} {'CLOSE':>10} {'RSI2':>8} {'IBS':>8} {'NATR%':>8}")
    for h in hits:
        print(
            f"{h.symbol:<8} {str(h.date.date()):<12} {h.close:>10.2f} "
            f"{h.rsi_2:>8.2f} {h.ibs:>8.3f} {h.natr_14:>8.2f}"
        )
    print("\nSignals ranked by NATR (higher vol first). Execute next open if following research rules.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "High-volatility mean-reversion bot (Connors RSI(2) + NATR rank + IBS). "
            "See research/SOURCES.md. No guaranteed win rate."
        )
    )
    sub = p.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--symbols",
        default=",".join(DEFAULT_VOLATILE_UNIVERSE),
        help="Comma-separated tickers",
    )
    common.add_argument("--start", default="2018-01-01")
    common.add_argument("--rsi-entry", type=float, default=5.0)
    common.add_argument("--ibs-entry", type=float, default=0.30)
    common.add_argument("--no-ibs", action="store_true")
    common.add_argument("--no-trend-filter", action="store_true")
    common.add_argument("--min-natr", type=float, default=None)

    bt = sub.add_parser("backtest", parents=[common], help="Run historical backtest")
    bt.add_argument("--end", default=None)
    bt.add_argument("--capital", type=float, default=100_000.0)
    bt.add_argument("--max-positions", type=int, default=5)
    bt.add_argument("--commission", type=float, default=0.0005)
    bt.add_argument("--slippage", type=float, default=0.0005)
    bt.add_argument(
        "--exit-mode",
        choices=["sma5", "rsi_recover", "prev_high"],
        default="rsi_recover",
    )
    bt.add_argument("--max-hold", type=int, default=10)
    bt.add_argument("--json-out", default=None)
    bt.set_defaults(func=cmd_backtest)

    sc = sub.add_parser("scan", parents=[common], help="Scan for today's entry signals")
    sc.set_defaults(func=cmd_scan)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
