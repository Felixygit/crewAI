"""Offline sample quotes for demos and tests (not live market data)."""

from __future__ import annotations

from small_cap_rvol_breakout.models import QuoteSnapshot

# Synthetic morning snapshots shaped like liquid sub-$20 small caps.
SAMPLE_QUOTES: list[QuoteSnapshot] = [
    QuoteSnapshot(
        symbol="VOLA",
        last=8.42,
        bid=8.40,
        ask=8.44,
        session_volume=4_800_000,
        avg_volume_tod=900_000,
        atr=0.55,
        float_shares=18_000_000,
        or_high=8.20,
        or_low=7.85,
        vwap=8.10,
        broke_or_high=True,
        notes="Clean OR-high break on 5.3x RVOL",
    ),
    QuoteSnapshot(
        symbol="PUMP",
        last=14.10,
        bid=14.05,
        ask=14.15,
        session_volume=6_200_000,
        avg_volume_tod=1_100_000,
        atr=0.95,
        float_shares=22_000_000,
        or_high=13.80,
        or_low=13.20,
        vwap=13.90,
        broke_or_high=True,
        notes="Strong break, still above VWAP",
    ),
    QuoteSnapshot(
        symbol="WAIT",
        last=6.55,
        bid=6.53,
        ask=6.57,
        session_volume=3_100_000,
        avg_volume_tod=700_000,
        atr=0.40,
        float_shares=12_000_000,
        or_high=6.70,
        or_low=6.20,
        vwap=6.45,
        broke_or_high=False,
        notes="Passes scan but still inside opening range",
    ),
    QuoteSnapshot(
        symbol="FADE",
        last=9.10,
        bid=9.08,
        ask=9.12,
        session_volume=5_000_000,
        avg_volume_tod=800_000,
        atr=0.70,
        float_shares=15_000_000,
        or_high=8.90,
        or_low=8.40,
        vwap=9.35,
        broke_or_high=True,
        notes="Broke OR high then lost VWAP — skip",
    ),
    QuoteSnapshot(
        symbol="THIN",
        last=4.25,
        bid=4.10,
        ask=4.40,
        session_volume=400_000,
        avg_volume_tod=350_000,
        atr=0.35,
        float_shares=8_000_000,
        or_high=4.00,
        or_low=3.80,
        vwap=4.05,
        broke_or_high=True,
        notes="Fails liquidity and spread filters",
    ),
    QuoteSnapshot(
        symbol="BIGX",
        last=42.50,
        bid=42.45,
        ask=42.55,
        session_volume=8_000_000,
        avg_volume_tod=2_000_000,
        atr=1.80,
        float_shares=40_000_000,
        or_high=41.00,
        or_low=40.20,
        vwap=41.50,
        broke_or_high=True,
        notes="Fails max price filter",
    ),
]


def quotes_as_dicts() -> list[dict]:
    """Serialize sample quotes for tool / JSON consumers."""
    return [quote.model_dump() for quote in SAMPLE_QUOTES]
