#!/usr/bin/env python
"""CLI entrypoint for Alpaca paper trading of the RVOL ORB strategy."""

from __future__ import annotations

import argparse
import logging
import sys

from small_cap_rvol_breakout.alpaca_paper.config import AlpacaPaperConfig
from small_cap_rvol_breakout.alpaca_paper.strategy_loop import PaperStrategyRunner


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the small-cap RVOL opening-range breakout strategy on an "
            "Alpaca PAPER account."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and print orders without submitting to Alpaca.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scan/execute cycle and exit.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    parser.add_argument(
        "--universe",
        type=str,
        default="",
        help="Comma-separated tickers (overrides ALPACA_UNIVERSE).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _configure_logging(args.verbose)

    # Load .env if python-dotenv is available (crew projects usually have it).
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    config = AlpacaPaperConfig.from_env()
    if args.dry_run:
        config.dry_run = True
    if args.universe:
        config.universe = [s.strip().upper() for s in args.universe.split(",") if s.strip()]

    try:
        config.require_credentials()
    except RuntimeError as exc:
        logging.error("%s", exc)
        return 1

    if not config.paper:
        logging.error("Paper mode required. Set ALPACA_PAPER=true.")
        return 1

    runner = PaperStrategyRunner(config)
    if args.once:
        result = runner.run_once()
        print(  # noqa: T201
            f"scanned={result.scanned} passed={result.passed_scan} "
            f"actionable={len(result.actionable)} submitted={len(result.submitted)}"
        )
        for plan in result.actionable:
            print(  # noqa: T201
                f"PLAN {plan.symbol}: shares={plan.shares} entry={plan.entry:.2f} "
                f"stop={plan.stop:.2f} t1={plan.target1:.2f} t2={plan.target2:.2f}"
            )
        for err in result.errors:
            logging.error("%s", err)
        return 0 if not result.errors else 2

    try:
        runner.run_forever()
    except KeyboardInterrupt:
        logging.info("Stopped by user")
    return 0


if __name__ == "__main__":
    sys.exit(main())
