"""Broker helpers for Alpaca paper trading."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from small_cap_rvol_breakout.alpaca_paper.config import AlpacaPaperConfig
from small_cap_rvol_breakout.models import TradePlan

logger = logging.getLogger(__name__)


class TradingClientProtocol(Protocol):
    """Subset of Alpaca TradingClient used by the executor."""

    def get_account(self) -> Any: ...

    def get_all_positions(self) -> list[Any]: ...

    def get_clock(self) -> Any: ...

    def submit_order(self, order_data: Any) -> Any: ...

    def cancel_orders(self) -> Any: ...


@dataclass
class SubmittedOrder:
    """Normalized order acknowledgement."""

    symbol: str
    qty: float
    client_order_id: str
    raw: Any | None = None


class AlpacaBroker:
    """Thin wrapper that can also operate in dry-run mode."""

    def __init__(
        self,
        config: AlpacaPaperConfig,
        client: TradingClientProtocol | None = None,
    ) -> None:
        self.config = config
        self._client = client

    @property
    def client(self) -> TradingClientProtocol:
        if self._client is None:
            from alpaca.trading.client import TradingClient

            self.config.require_credentials()
            self._client = TradingClient(
                api_key=self.config.api_key,
                secret_key=self.config.api_secret,
                paper=True,
            )
        return self._client

    def is_market_open(self) -> bool:
        if self.config.dry_run and self._client is None:
            return True
        clock = self.client.get_clock()
        return bool(getattr(clock, "is_open", False))

    def account_equity(self) -> float:
        if self.config.dry_run and self._client is None:
            return self.config.risk.account_equity
        account = self.client.get_account()
        return float(account.equity)

    def open_symbols(self) -> set[str]:
        if self.config.dry_run and self._client is None:
            return set()
        positions = self.client.get_all_positions()
        return {str(p.symbol).upper() for p in positions}

    def submit_dual_bracket(self, plan: TradePlan) -> list[SubmittedOrder]:
        """Enter long with two bracket legs (T1 scale-out + T2 runner).

        Splitting into two brackets approximates 50% at target1 and the
        remainder at target2, each protected by the same stop.
        """
        if plan.shares <= 0:
            return []

        scale = plan.scale_out_shares_t1
        runner = plan.runner_shares
        if scale <= 0 and runner <= 0:
            scale = plan.shares
            runner = 0

        submitted: list[SubmittedOrder] = []
        legs = []
        if scale > 0:
            legs.append(("t1", scale, plan.target1))
        if runner > 0:
            legs.append(("t2", runner, plan.target2))

        for label, qty, target in legs:
            client_order_id = f"rvol-{plan.symbol.lower()}-{label}-{qty}"
            if self.config.dry_run:
                logger.info(
                    "DRY-RUN bracket %s %s qty=%s stop=%.4f tp=%.4f",
                    label,
                    plan.symbol,
                    qty,
                    plan.stop,
                    target,
                )
                submitted.append(
                    SubmittedOrder(
                        symbol=plan.symbol,
                        qty=float(qty),
                        client_order_id=client_order_id,
                        raw={"dry_run": True, "stop": plan.stop, "take_profit": target},
                    )
                )
                continue

            from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
            from alpaca.trading.requests import (
                MarketOrderRequest,
                StopLossRequest,
                TakeProfitRequest,
            )

            request = MarketOrderRequest(
                symbol=plan.symbol,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
                order_class=OrderClass.BRACKET,
                take_profit=TakeProfitRequest(limit_price=round(target, 2)),
                stop_loss=StopLossRequest(stop_price=round(plan.stop, 2)),
                client_order_id=client_order_id[:48],
            )
            order = self.client.submit_order(order_data=request)
            submitted.append(
                SubmittedOrder(
                    symbol=plan.symbol,
                    qty=float(qty),
                    client_order_id=str(getattr(order, "client_order_id", client_order_id)),
                    raw=order,
                )
            )
            logger.info(
                "Submitted %s bracket for %s qty=%s id=%s",
                label,
                plan.symbol,
                qty,
                getattr(order, "id", None),
            )
        return submitted
