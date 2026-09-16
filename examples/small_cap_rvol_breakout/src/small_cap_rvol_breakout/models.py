"""Data models for the small-cap RVOL breakout strategy."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Side(str, Enum):
    """Trade direction."""

    LONG = "long"
    FLAT = "flat"


class ScanFilters(BaseModel):
    """Universe filters for the morning scan."""

    max_price: float = Field(default=20.0, gt=0, description="Maximum last price.")
    min_rvol: float = Field(
        default=2.0,
        gt=0,
        description="Minimum relative volume vs same time-of-day average.",
    )
    min_atr_pct: float = Field(
        default=3.0,
        ge=0,
        description="Minimum ATR as a percent of price (volatility floor).",
    )
    min_dollar_volume: float = Field(
        default=5_000_000.0,
        ge=0,
        description="Minimum session dollar volume for liquidity.",
    )
    max_spread_pct: float = Field(
        default=1.0,
        ge=0,
        description="Maximum bid-ask spread as a percent of mid.",
    )
    max_float_shares: float | None = Field(
        default=50_000_000.0,
        gt=0,
        description="Optional float ceiling; None disables the float filter.",
    )


class RiskConfig(BaseModel):
    """Position sizing and exit geometry."""

    account_equity: float = Field(default=25_000.0, gt=0)
    risk_per_trade_pct: float = Field(
        default=0.5,
        gt=0,
        le=5.0,
        description="Percent of equity risked if the stop is hit.",
    )
    opening_range_minutes: int = Field(default=5, ge=1, le=30)
    stop_buffer_pct: float = Field(
        default=0.15,
        ge=0,
        description="Extra percent below the OR high used for the stop.",
    )
    target1_r_multiple: float = Field(default=1.5, gt=0)
    target2_r_multiple: float = Field(default=3.0, gt=0)
    scale_out_at_target1_pct: float = Field(
        default=50.0,
        gt=0,
        le=100.0,
        description="Percent of shares to exit at target 1.",
    )
    max_hold_minutes: int = Field(
        default=180,
        gt=0,
        description="Time stop from entry if targets are not hit.",
    )


class QuoteSnapshot(BaseModel):
    """Point-in-time market snapshot used by the screener and planner."""

    symbol: str
    last: float = Field(gt=0)
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)
    session_volume: float = Field(ge=0)
    avg_volume_tod: float = Field(
        gt=0,
        description="Average volume for the same time-of-day window.",
    )
    atr: float = Field(gt=0, description="Average true range in dollars.")
    float_shares: float | None = Field(default=None, gt=0)
    or_high: float = Field(gt=0, description="Opening-range high.")
    or_low: float = Field(gt=0, description="Opening-range low.")
    vwap: float = Field(gt=0)
    broke_or_high: bool = Field(
        default=False,
        description="True when price has traded through the OR high on volume.",
    )
    notes: str = ""

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread_pct(self) -> float:
        return ((self.ask - self.bid) / self.mid) * 100.0

    @property
    def rvol(self) -> float:
        return self.session_volume / self.avg_volume_tod

    @property
    def atr_pct(self) -> float:
        return (self.atr / self.last) * 100.0

    @property
    def dollar_volume(self) -> float:
        return self.session_volume * self.last


class ScreenResult(BaseModel):
    """Pass/fail result for one symbol against the scan filters."""

    symbol: str
    passed: bool
    reasons: list[str] = Field(default_factory=list)
    rvol: float
    atr_pct: float
    spread_pct: float
    dollar_volume: float
    last: float
    float_shares: float | None = None


class TradePlan(BaseModel):
    """Concrete entry/exit plan for a screened name."""

    symbol: str
    side: Side
    entry: float
    stop: float
    target1: float
    target2: float
    shares: int
    risk_dollars: float
    reward_to_risk_t1: float
    reward_to_risk_t2: float
    scale_out_shares_t1: int
    runner_shares: int
    max_hold_minutes: int
    rules_summary: list[str] = Field(default_factory=list)
    skip_reason: str | None = None
