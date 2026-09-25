"""Offline sample snapshots for demos and tests (not live market data).

Includes the documented MU 22 Sep 2026 morning historical illustration from the
agent spec — documentation only, not a live signal.
"""

from __future__ import annotations

from datetime import date, time

from ema_vwap_stack.models import (
    EmaLine,
    FairValueGap,
    FvgSide,
    MarketDirection,
    MarketSnapshot,
    Regime,
    Slope,
)

# Worked example from the agent spec (historical educational snapshot).
MU_TREND_PULLBACK = MarketSnapshot(
    ticker="MU",
    session_date=date(2026, 9, 22),
    session_time=time(10, 15),
    timeframe="4h",
    last=1080.0,
    session_open=1045.0,
    session_high=1085.0,
    session_low=1040.0,
    volume=3_200_000,
    ema9=EmaLine(value=1041.0, slope=Slope.RISING),
    ema20=EmaLine(value=1017.0, slope=Slope.RISING),
    ema50=EmaLine(value=980.0, slope=Slope.RISING),
    vwap=1062.0,
    yesterday_high=1075.0,
    yesterday_low=1020.0,
    opening_range_high=1068.0,
    opening_range_low=1042.0,
    nasdaq_direction=MarketDirection.UP,
    sector_direction=MarketDirection.UP,  # SMH / SOX bid
    relative_volume=1.4,
    next_catalyst_date=date(2026, 9, 25),  # pre-earnings backdrop
    trade_event_risk=True,  # operator accepted backdrop context
    vwap_source_mismatch=True,  # daily VWAP on 4h EMA chart
    pullback_volume_contracted=True,
    reaction_volume_rising=True,
    reaction_wick_against_or_strong_close=True,
    fvgs=[
        FairValueGap(
            side=FvgSide.BULLISH,
            low=1055.0,
            high=1065.0,
            filled=False,
            timeframe="4h",
        )
    ],
    account_equity=50_000.0,
    risk_pct=1.0,
    notes="Historical MU morning stack — buy a hold of VWAP then EMA9, not the 1082 print",
)

# Price already chased >0.6% from the zone → no trade.
MU_CHASE = MU_TREND_PULLBACK.model_copy(
    update={
        "last": 1095.0,
        "price_left_zone_pct": 1.2,
        "notes": "Already left the pullback zone — do not chase",
    }
)

# Lunch with weak confluence → stand-aside.
MU_LUNCH_WEAK = MU_TREND_PULLBACK.model_copy(
    update={
        "session_time": time(12, 30),
        "pullback_volume_contracted": False,
        "reaction_volume_rising": False,
        "reaction_wick_against_or_strong_close": False,
        "fvgs": [],
        "notes": "Lunch without enough confluence",
    }
)

# Clean lunch test with high confluence can still plan.
MU_LUNCH_STRONG = MU_TREND_PULLBACK.model_copy(
    update={
        "session_time": time(12, 45),
        "last": 1063.0,
        "notes": "Lunch but testing VWAP with volume and full confluence",
    }
)

# Trend-down short pullback.
BEAR_PULLBACK = MarketSnapshot(
    ticker="AMD",
    session_date=date(2026, 9, 22),
    session_time=time(10, 5),
    timeframe="15m",
    last=148.0,
    session_open=152.0,
    session_high=152.5,
    session_low=147.5,
    volume=12_000_000,
    ema9=EmaLine(value=149.5, slope=Slope.FALLING),
    ema20=EmaLine(value=151.0, slope=Slope.FALLING),
    ema50=EmaLine(value=154.0, slope=Slope.FALLING),
    vwap=150.5,
    yesterday_high=156.0,
    yesterday_low=149.0,
    opening_range_high=152.2,
    opening_range_low=150.0,
    nasdaq_direction=MarketDirection.DOWN,
    sector_direction=MarketDirection.DOWN,
    pullback_volume_contracted=True,
    reaction_volume_rising=True,
    reaction_wick_against_or_strong_close=True,
    fvgs=[
        FairValueGap(
            side=FvgSide.BEARISH,
            low=149.0,
            high=150.2,
            filled=False,
            timeframe="15m",
        )
    ],
    notes="Trend-down pullback into EMA9 / VWAP",
)

# VWAP reclaim long.
VWAP_RECLAIM = MarketSnapshot(
    ticker="NVDA",
    session_date=date(2026, 9, 22),
    session_time=time(10, 40),
    timeframe="5m",
    last=120.5,
    session_open=118.0,
    session_high=121.0,
    session_low=117.5,
    volume=25_000_000,
    ema9=EmaLine(value=119.8, slope=Slope.RISING),
    ema20=EmaLine(value=119.0, slope=Slope.RISING),
    ema50=EmaLine(value=117.5, slope=Slope.RISING),
    vwap=119.5,
    yesterday_high=122.0,
    yesterday_low=116.0,
    opening_range_high=119.2,
    opening_range_low=117.8,
    nasdaq_direction=MarketDirection.UP,
    sector_direction=MarketDirection.UP,
    dipped_under_vwap=True,
    reclaim_bar_closed_above_vwap=True,
    pullback_volume_contracted=True,
    reaction_volume_rising=True,
    reaction_wick_against_or_strong_close=True,
    notes="Dipped under VWAP then closed back above with rising stack",
)

# Range fade at +2SD.
RANGE_FADE = MarketSnapshot(
    ticker="SPY",
    session_date=date(2026, 9, 22),
    session_time=time(10, 20),
    timeframe="5m",
    last=572.0,
    session_open=568.0,
    session_high=572.2,
    session_low=567.5,
    volume=40_000_000,
    ema9=EmaLine(value=569.5, slope=Slope.FLAT),
    ema20=EmaLine(value=569.2, slope=Slope.FLAT),
    ema50=EmaLine(value=569.0, slope=Slope.FLAT),
    vwap=569.0,
    yesterday_high=571.0,
    yesterday_low=565.0,
    opening_range_high=570.0,
    opening_range_low=567.8,
    nasdaq_direction=MarketDirection.MIXED,
    vwap_plus_1sd=570.5,
    vwap_minus_1sd=567.5,
    vwap_plus_2sd=572.0,
    vwap_minus_2sd=566.0,
    pullback_volume_contracted=True,
    reaction_volume_rising=True,
    reaction_wick_against_or_strong_close=True,
    notes="Stretched to VWAP +2SD in a flat EMA range",
)

# Whipsaw EMAs → stand-aside.
WHIPSAW = MarketSnapshot(
    ticker="TSLA",
    session_date=date(2026, 9, 22),
    session_time=time(10, 10),
    timeframe="15m",
    last=250.0,
    session_open=248.0,
    session_high=252.0,
    session_low=247.0,
    volume=20_000_000,
    ema9=EmaLine(value=249.5, slope=Slope.RISING),
    ema20=EmaLine(value=250.5, slope=Slope.FALLING),
    ema50=EmaLine(value=249.0, slope=Slope.FLAT),
    vwap=249.8,
    yesterday_high=255.0,
    yesterday_low=245.0,
    opening_range_high=251.0,
    opening_range_low=247.5,
    nasdaq_direction=MarketDirection.MIXED,
    emas_whipsawed=True,
    notes="EMAs crossed both ways — stand-aside",
)

# HTF opposes entry TF.
HTF_OPPOSE = MU_TREND_PULLBACK.model_copy(
    update={
        "ticker": "MU",
        "higher_timeframe_regime": Regime.TREND_DOWN,
        "trade_event_risk": True,
        "notes": "4h up but daily opposing — stand-aside",
    }
)

# After hours → closed.
CLOSED_SESSION = MU_TREND_PULLBACK.model_copy(
    update={
        "session_time": time(17, 0),
        "notes": "Regular session closed",
    }
)

SAMPLE_SNAPSHOTS: list[MarketSnapshot] = [
    MU_TREND_PULLBACK,
    MU_CHASE,
    MU_LUNCH_WEAK,
    MU_LUNCH_STRONG,
    BEAR_PULLBACK,
    VWAP_RECLAIM,
    RANGE_FADE,
    WHIPSAW,
    HTF_OPPOSE,
    CLOSED_SESSION,
]


def snapshots_as_dicts() -> list[dict]:
    """Serialize sample snapshots for tool / JSON consumers."""
    return [snap.model_dump(mode="json") for snap in SAMPLE_SNAPSHOTS]


def get_snapshot(ticker: str, tag: str | None = None) -> MarketSnapshot | None:
    """Lookup helper for demos; MU defaults to the trend-pullback example."""
    ticker = ticker.upper()
    if tag is None and ticker == "MU":
        return MU_TREND_PULLBACK
    for snap in SAMPLE_SNAPSHOTS:
        if snap.ticker.upper() != ticker:
            continue
        if tag is None or tag.lower() in snap.notes.lower():
            return snap
    return next((s for s in SAMPLE_SNAPSHOTS if s.ticker.upper() == ticker), None)
