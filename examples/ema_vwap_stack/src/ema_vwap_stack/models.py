"""Data models for the EMA / VWAP stack trade-plan agent."""

from __future__ import annotations

from datetime import date, datetime, time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class Slope(str, Enum):
    """EMA slope label."""

    RISING = "rising"
    FLAT = "flat"
    FALLING = "falling"


class MarketDirection(str, Enum):
    """Session direction for an index or sector."""

    UP = "up"
    DOWN = "down"
    MIXED = "mixed"


class ClockWindow(str, Enum):
    """Session clock label from the session gate."""

    OPEN = "open"
    MIDDAY = "midday"
    POWER_HOUR = "power-hour"
    CLOSED = "closed"


class Regime(str, Enum):
    """Market regime on the EMA timeframe."""

    TREND_UP = "trend-up"
    TREND_DOWN = "trend-down"
    RANGE = "range"
    STAND_ASIDE = "stand-aside"


class Setup(str, Enum):
    """Allowed setups; never mix trend and fade on one ticket."""

    PULLBACK = "pullback"
    RECLAIM = "reclaim"
    FADE = "fade"
    NONE = "none"


class Side(str, Enum):
    """Trade side."""

    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class FvgSide(str, Enum):
    """Fair-value-gap direction."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NONE = "none"


class Instrument(str, Enum):
    """Allowed instruments — never naked short options."""

    SHARES = "shares"
    DEFINED_RISK_DEBIT_SPREAD = "defined-risk debit spread"


class EmaLine(BaseModel):
    """EMA value plus slope on the chart timeframe."""

    value: float = Field(gt=0)
    slope: Slope


class FairValueGap(BaseModel):
    """Unfilled 3-candle imbalance on (or above) the EMA timeframe."""

    side: FvgSide
    low: float = Field(gt=0, description="Lower edge of the gap.")
    high: float = Field(gt=0, description="Upper edge of the gap.")
    filled: bool = False
    timeframe: str = Field(
        default="",
        description="Timeframe the gap was marked on, e.g. 15m or 1h.",
    )

    @property
    def midpoint(self) -> float:
        return (self.low + self.high) / 2.0

    @model_validator(mode="after")
    def _edges_ordered(self) -> FairValueGap:
        if self.high < self.low:
            raise ValueError("FVG high must be >= low")
        return self


class MissingInputError(ValueError):
    """Raised when a required market input is missing."""


REQUIRED_FIELDS: tuple[str, ...] = (
    "ticker",
    "session_date",
    "session_time",
    "timeframe",
    "last",
    "session_open",
    "session_high",
    "session_low",
    "volume",
    "ema9",
    "ema20",
    "ema50",
    "vwap",
    "yesterday_high",
    "yesterday_low",
    "opening_range_high",
    "opening_range_low",
    "nasdaq_direction",
)


class MarketSnapshot(BaseModel):
    """Required + optional inputs for one ticker / session window.

    Refuse to invent missing required fields — validate before planning.
    """

    ticker: str
    session_date: date
    session_time: time = Field(description="Local market-hours clock (US/Eastern).")
    timeframe: str = Field(description="EMA chart timeframe, e.g. 5m, 15m, 4h.")
    last: float = Field(gt=0)
    session_open: float = Field(gt=0)
    session_high: float = Field(gt=0)
    session_low: float = Field(gt=0)
    volume: float = Field(ge=0)
    ema9: EmaLine
    ema20: EmaLine
    ema50: EmaLine
    vwap: float = Field(gt=0)
    yesterday_high: float = Field(gt=0)
    yesterday_low: float = Field(gt=0)
    opening_range_high: float | None = Field(
        default=None,
        description="OR high after the open has printed; None if still forming.",
    )
    opening_range_low: float | None = Field(default=None)
    nasdaq_direction: MarketDirection
    sector_direction: MarketDirection | None = Field(
        default=None,
        description="e.g. SMH/SOX for MU; optional but scored when present.",
    )

    # Optional confluence / filter fields
    vwap_plus_1sd: float | None = None
    vwap_minus_1sd: float | None = None
    vwap_plus_2sd: float | None = None
    vwap_minus_2sd: float | None = None
    fvgs: list[FairValueGap] = Field(default_factory=list)
    relative_volume: float | None = Field(
        default=None,
        gt=0,
        description="Session volume vs 20-day average.",
    )
    next_catalyst_date: date | None = None
    trade_event_risk: bool = Field(
        default=False,
        description="True only when the operator explicitly accepts catalyst risk.",
    )
    higher_timeframe_regime: Regime | None = Field(
        default=None,
        description="One step up from the entry TF; opposing HTF → stand-aside.",
    )
    emas_whipsawed: bool = Field(
        default=False,
        description="True when EMAs crossed both ways in the last few bars.",
    )
    vwap_source_mismatch: bool = Field(
        default=False,
        description="True when VWAP is daily but EMAs are on a higher TF (e.g. 4h).",
    )
    pullback_volume_contracted: bool | None = None
    reaction_volume_rising: bool | None = None
    reaction_wick_against_or_strong_close: bool | None = None
    price_left_zone_pct: float | None = Field(
        default=None,
        ge=0,
        description="How far (%) price already left a candidate entry zone.",
    )
    reclaim_bar_closed_above_vwap: bool | None = None
    reclaim_bar_closed_below_vwap: bool | None = None
    dipped_under_vwap: bool | None = None
    popped_over_vwap: bool | None = None
    hold_window_hours: float = Field(
        default=4.0,
        gt=0,
        description="Expected hold horizon used for catalyst / clock gating.",
    )
    zero_to_three_dte_options: bool = Field(
        default=False,
        description="When True, apply extra midday penalty for short-dated options.",
    )
    account_equity: float = Field(default=25_000.0, gt=0)
    risk_pct: float = Field(default=1.0, gt=0, le=5.0)
    entry_buffer_pct: float = Field(
        default=0.25,
        ge=0.15,
        le=0.35,
        description="Entry zone half-width around the stack line (%%).",
    )
    notes: str = ""

    @classmethod
    def missing_required(cls, payload: dict[str, Any]) -> list[str]:
        """Return names of required fields absent from a raw payload."""
        missing: list[str] = []
        for name in REQUIRED_FIELDS:
            if name not in payload or payload[name] is None:
                missing.append(name)
        # Opening range may be absent only before the open has printed.
        # After 9:45 ET we treat missing OR as an error when session_time is set.
        return missing


class StackSnapshot(BaseModel):
    """Ordered relationship of price and the EMA / VWAP stack."""

    price: float
    ema9: float
    ema20: float
    ema50: float
    vwap: float
    ordered: bool


class FvgAssessment(BaseModel):
    """FVG filter result — refine only, never a standalone setup."""

    present: bool
    side: FvgSide
    overlaps_stack: bool
    zone: str | None = None


class TradePlanFields(BaseModel):
    """Filled when a live setup exists; otherwise stand-aside values."""

    side: Side | str
    instrument: Instrument | str
    entry_zone: str
    invalidation: str
    target_1: str
    target_2: str
    r_dollars: str
    size_rule: str
    time_stop: str
    kill_switch: str


class StackPlan(BaseModel):
    """Structured completion object — one plan, no extra commentary."""

    ticker: str
    as_of: str
    timeframe: str
    clock: ClockWindow
    regime: Regime
    stack: StackSnapshot
    confluence_score: int = Field(ge=0, le=8)
    confluence_hits: list[str] = Field(default_factory=list)
    fvg: FvgAssessment
    setup: Setup
    plan: TradePlanFields | None = None
    reason_in_one_sentence: str
    refused_missing_inputs: list[str] = Field(default_factory=list)
