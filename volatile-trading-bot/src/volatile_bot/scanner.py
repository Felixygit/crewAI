"""Scan a universe for current Connors-style mean-reversion setups."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from volatile_bot.strategy import MeanReversionStrategy, StrategyConfig


@dataclass(frozen=True)
class ScanHit:
    symbol: str
    date: pd.Timestamp
    close: float
    rsi_2: float
    ibs: float
    natr_14: float
    above_sma200: bool


def scan_universe(
    data: dict[str, pd.DataFrame],
    strategy: MeanReversionStrategy | None = None,
    as_of: pd.Timestamp | None = None,
) -> list[ScanHit]:
    """Return symbols with an entry signal on the latest (or as_of) bar."""
    strategy = strategy or MeanReversionStrategy(StrategyConfig())
    hits: list[ScanHit] = []
    for symbol, ohlc in data.items():
        prepared = strategy.prepare(ohlc)
        if prepared.empty:
            continue
        if as_of is not None:
            if as_of not in prepared.index:
                continue
            row = prepared.loc[as_of]
            ts = as_of
        else:
            ts = prepared.index[-1]
            row = prepared.iloc[-1]
        if not bool(strategy.entry_mask(prepared).loc[ts]):
            continue
        hits.append(
            ScanHit(
                symbol=symbol,
                date=pd.Timestamp(ts),
                close=float(row["Close"]),
                rsi_2=float(row["rsi_2"]),
                ibs=float(row["ibs"]) if pd.notna(row["ibs"]) else float("nan"),
                natr_14=float(row["natr_14"]),
                above_sma200=bool(row["Close"] > row["sma_200"]),
            )
        )
    hits.sort(key=lambda h: h.natr_14, reverse=True)
    return hits
