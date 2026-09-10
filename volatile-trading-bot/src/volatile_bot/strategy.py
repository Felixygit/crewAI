"""Connors RSI(2) + high-NATR + IBS mean-reversion strategy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from volatile_bot.indicators import enrich

ExitMode = Literal["sma5", "rsi_recover", "prev_high"]


@dataclass(frozen=True)
class StrategyConfig:
    """Parameters aligned with published Connors / Quantitativo / Alvarez rules.

    Tighter ``rsi_entry_max`` historically raises win rate and lowers trade count
    (Quantitativo; Connors). Default 5 is the classic high-probability entry.
    """

    rsi_entry_max: float = 5.0
    rsi_exit_min: float = 65.0
    ibs_entry_max: float = 0.30
    require_above_sma200: bool = True
    require_ibs_filter: bool = True
    min_natr: float | None = None  # absolute NATR floor; ranking handled in portfolio
    # Connors' published high-probability variant exits on RSI(2) recovery
    # (often >65). SMA(5) and prior-day high are supported alternatives.
    exit_mode: ExitMode = "rsi_recover"
    max_hold_days: int = 10


@dataclass(frozen=True)
class SignalRow:
    date: pd.Timestamp
    symbol: str
    rsi_2: float
    ibs: float
    natr_14: float
    close: float
    action: Literal["enter", "exit"]


class MeanReversionStrategy:
    """Long-only short-term mean reversion for volatile equities.

    Signal timing: evaluate on bar close; backtester executes at next open
    (standard Connors / Quantitativo convention).
    """

    def __init__(self, config: StrategyConfig | None = None) -> None:
        self.config = config or StrategyConfig()

    def prepare(self, ohlc: pd.DataFrame) -> pd.DataFrame:
        return enrich(ohlc)

    def entry_mask(self, prepared: pd.DataFrame) -> pd.Series:
        cfg = self.config
        mask = prepared["rsi_2"] < cfg.rsi_entry_max
        if cfg.require_above_sma200:
            mask &= prepared["Close"] > prepared["sma_200"]
        if cfg.require_ibs_filter:
            mask &= prepared["ibs"] < cfg.ibs_entry_max
        if cfg.min_natr is not None:
            mask &= prepared["natr_14"] >= cfg.min_natr
        return mask.fillna(False)

    def exit_mask(self, prepared: pd.DataFrame) -> pd.Series:
        cfg = self.config
        if cfg.exit_mode == "sma5":
            mask = prepared["Close"] > prepared["sma_5"]
        elif cfg.exit_mode == "rsi_recover":
            mask = prepared["rsi_2"] > cfg.rsi_exit_min
        elif cfg.exit_mode == "prev_high":
            mask = prepared["Close"] > prepared["prev_high"]
        else:
            raise ValueError(f"Unknown exit_mode: {cfg.exit_mode}")
        return mask.fillna(False)

    def signals_for_symbol(self, symbol: str, ohlc: pd.DataFrame) -> list[SignalRow]:
        """Generate chronological enter/exit signal rows (close of signal day)."""
        prepared = self.prepare(ohlc)
        entries = self.entry_mask(prepared)
        exits = self.exit_mask(prepared)
        rows: list[SignalRow] = []
        in_pos = False
        hold_days = 0

        for ts, row in prepared.iterrows():
            if in_pos:
                hold_days += 1
                timed_out = hold_days >= self.config.max_hold_days
                if bool(exits.loc[ts]) or timed_out:
                    rows.append(
                        SignalRow(
                            date=pd.Timestamp(ts),
                            symbol=symbol,
                            rsi_2=float(row["rsi_2"]),
                            ibs=float(row["ibs"]) if pd.notna(row["ibs"]) else float("nan"),
                            natr_14=float(row["natr_14"]),
                            close=float(row["Close"]),
                            action="exit",
                        )
                    )
                    in_pos = False
                    hold_days = 0
            elif bool(entries.loc[ts]):
                rows.append(
                    SignalRow(
                        date=pd.Timestamp(ts),
                        symbol=symbol,
                        rsi_2=float(row["rsi_2"]),
                        ibs=float(row["ibs"]) if pd.notna(row["ibs"]) else float("nan"),
                        natr_14=float(row["natr_14"]),
                        close=float(row["Close"]),
                        action="enter",
                    )
                )
                in_pos = True
                hold_days = 0
        return rows
