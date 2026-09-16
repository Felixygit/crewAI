"""Live/paper strategy loop: scan → plan → submit Alpaca brackets."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from small_cap_rvol_breakout.alpaca_paper.broker import AlpacaBroker, SubmittedOrder
from small_cap_rvol_breakout.alpaca_paper.config import AlpacaPaperConfig
from small_cap_rvol_breakout.alpaca_paper.market_data import AlpacaMarketData
from small_cap_rvol_breakout.models import Side, TradePlan
from small_cap_rvol_breakout.rules import build_long_breakout_plan, screen_quote

logger = logging.getLogger(__name__)


@dataclass
class CycleResult:
    """Outcome of one scan/execute cycle."""

    scanned: int = 0
    passed_scan: int = 0
    actionable: list[TradePlan] = field(default_factory=list)
    submitted: list[SubmittedOrder] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class PaperStrategyRunner:
    """Runs the RVOL ORB playbook against an Alpaca paper account."""

    def __init__(
        self,
        config: AlpacaPaperConfig,
        broker: AlpacaBroker | None = None,
        market_data: AlpacaMarketData | None = None,
    ) -> None:
        self.config = config
        self.broker = broker or AlpacaBroker(config)
        self.market_data = market_data or AlpacaMarketData(config)
        self._traded_today: set[str] = set()

    def refresh_equity(self) -> None:
        try:
            equity = self.broker.account_equity()
            self.config.risk.account_equity = equity
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not refresh equity: %s", exc)

    def run_once(self) -> CycleResult:
        """Single scan + optional order submission pass."""
        result = CycleResult()
        self.refresh_equity()

        if not self.config.dry_run and not self.broker.is_market_open():
            result.skipped.append("market_closed")
            logger.info("Market closed — skipping cycle")
            return result

        open_symbols = self.broker.open_symbols()
        slots = max(0, self.config.max_open_positions - len(open_symbols))
        if slots <= 0:
            result.skipped.append("max_open_positions_reached")
            logger.info("Max open positions reached (%s)", self.config.max_open_positions)
            return result

        actionable: list[TradePlan] = []
        for symbol in self.config.universe:
            result.scanned += 1
            if symbol in open_symbols or symbol in self._traded_today:
                continue
            try:
                quote = self.market_data.snapshot(symbol)
                if quote is None:
                    continue
                screen = screen_quote(quote, self.config.filters)
                if not screen.passed:
                    continue
                result.passed_scan += 1
                plan = build_long_breakout_plan(quote, self.config.filters, self.config.risk)
                if plan.side == Side.LONG and plan.shares > 0:
                    actionable.append(plan)
                else:
                    result.skipped.append(f"{symbol}:{plan.skip_reason}")
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"{symbol}:{exc}")

        # Prefer higher RVOL / tighter risk first
        actionable.sort(
            key=lambda p: (p.shares * (p.entry - p.stop), p.entry),
            reverse=True,
        )
        result.actionable = actionable

        for plan in actionable[:slots]:
            try:
                orders = self.broker.submit_dual_bracket(plan)
                result.submitted.extend(orders)
                self._traded_today.add(plan.symbol)
                logger.info(
                    "Actioned %s shares=%s entry~%.2f stop=%.2f t1=%.2f t2=%.2f",
                    plan.symbol,
                    plan.shares,
                    plan.entry,
                    plan.stop,
                    plan.target1,
                    plan.target2,
                )
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"submit:{plan.symbol}:{exc}")

        return result

    def run_forever(self) -> None:
        """Poll until interrupted."""
        logger.info(
            "Starting Alpaca paper loop dry_run=%s poll=%ss universe=%s",
            self.config.dry_run,
            self.config.poll_seconds,
            len(self.config.universe),
        )
        while True:
            cycle = self.run_once()
            logger.info(
                "Cycle scanned=%s passed=%s actionable=%s submitted=%s skipped=%s errors=%s",
                cycle.scanned,
                cycle.passed_scan,
                len(cycle.actionable),
                len(cycle.submitted),
                len(cycle.skipped),
                len(cycle.errors),
            )
            time.sleep(max(5, self.config.poll_seconds))
