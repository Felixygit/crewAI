"""CrewAI tools that wrap the deterministic strategy engine."""

from __future__ import annotations

import json
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from small_cap_rvol_breakout.models import QuoteSnapshot, RiskConfig, ScanFilters
from small_cap_rvol_breakout.rules import build_long_breakout_plan, screen_universe
from small_cap_rvol_breakout.sample_data import SAMPLE_QUOTES


class ScreenUniverseInput(BaseModel):
    """Optional filter overrides for the morning scan."""

    max_price: float = Field(default=20.0, description="Maximum last price.")
    min_rvol: float = Field(default=2.0, description="Minimum relative volume.")
    min_atr_pct: float = Field(default=3.0, description="Minimum ATR percent.")
    min_dollar_volume: float = Field(
        default=5_000_000.0,
        description="Minimum dollar volume.",
    )
    max_spread_pct: float = Field(default=1.0, description="Maximum spread percent.")
    max_float_shares: float | None = Field(
        default=50_000_000.0,
        description="Optional float ceiling.",
    )
    only_passed: bool = Field(
        default=True,
        description="If true, return only symbols that pass the scan.",
    )


class SmallCapRvolScreenerTool(BaseTool):
    """Screen the sample (or injected) universe for RVOL breakout candidates."""

    name: str = "small_cap_rvol_screener"
    description: str = (
        "Screen small-cap names for price under $20, high relative volume, "
        "high volatility, adequate dollar volume, and a tight spread. "
        "Returns JSON screen results sorted by RVOL."
    )
    args_schema: type[BaseModel] = ScreenUniverseInput
    quotes: list[QuoteSnapshot] = Field(default_factory=lambda: list(SAMPLE_QUOTES))

    def _run(
        self,
        max_price: float = 20.0,
        min_rvol: float = 2.0,
        min_atr_pct: float = 3.0,
        min_dollar_volume: float = 5_000_000.0,
        max_spread_pct: float = 1.0,
        max_float_shares: float | None = 50_000_000.0,
        only_passed: bool = True,
    ) -> str:
        filters = ScanFilters(
            max_price=max_price,
            min_rvol=min_rvol,
            min_atr_pct=min_atr_pct,
            min_dollar_volume=min_dollar_volume,
            max_spread_pct=max_spread_pct,
            max_float_shares=max_float_shares,
        )
        results = screen_universe(self.quotes, filters)
        if only_passed:
            results = [row for row in results if row.passed]
        payload: list[dict[str, Any]] = [row.model_dump() for row in results]
        return json.dumps({"count": len(payload), "results": payload}, indent=2)


class TradePlanInput(BaseModel):
    """Build an entry/exit plan for one symbol."""

    symbol: str = Field(..., description="Ticker symbol to plan, e.g. VOLA.")
    account_equity: float = Field(default=25_000.0, description="Account equity.")
    risk_per_trade_pct: float = Field(
        default=0.5,
        description="Percent of equity to risk if stopped out.",
    )


class RvolBreakoutTradePlanTool(BaseTool):
    """Create a long OR-high breakout trade plan for a screened symbol."""

    name: str = "rvol_breakout_trade_plan"
    description: str = (
        "Build a concrete long opening-range breakout plan for one symbol: "
        "entry, stop, targets, share size, and skip reasons when invalid."
    )
    args_schema: type[BaseModel] = TradePlanInput
    quotes: list[QuoteSnapshot] = Field(default_factory=lambda: list(SAMPLE_QUOTES))

    def _run(
        self,
        symbol: str,
        account_equity: float = 25_000.0,
        risk_per_trade_pct: float = 0.5,
    ) -> str:
        match = next(
            (quote for quote in self.quotes if quote.symbol.upper() == symbol.upper()),
            None,
        )
        if match is None:
            available = ", ".join(sorted({quote.symbol for quote in self.quotes}))
            return json.dumps(
                {
                    "error": f"Unknown symbol {symbol!r}",
                    "available_symbols": available,
                }
            )

        plan = build_long_breakout_plan(
            match,
            risk=RiskConfig(
                account_equity=account_equity,
                risk_per_trade_pct=risk_per_trade_pct,
            ),
        )
        return json.dumps(plan.model_dump(), indent=2)
