"""Market data loading via Yahoo Finance (real prices, not synthetic)."""

from __future__ import annotations

from typing import Iterable

import pandas as pd
import yfinance as yf

# Liquid, typically high-volatility names for scanning / demos.
# Not an endorsement; universe is user-replaceable.
DEFAULT_VOLATILE_UNIVERSE: tuple[str, ...] = (
    "TSLA",
    "NVDA",
    "AMD",
    "META",
    "AMZN",
    "NFLX",
    "COIN",
    "PLTR",
    "SHOP",
    "SQ",
    "ROKU",
    "SNAP",
    "UBER",
    "BA",
    "MU",
    "SMCI",
    "ARM",
    "AVGO",
    "QQQ",  # liquid high-beta proxy / benchmark sleeve
)


def _normalize_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    cols = {c: str(c).title() for c in df.columns}
    # yfinance uses Open/High/Low/Close/Volume/Adj Close
    rename = {}
    for c in df.columns:
        key = str(c)
        if key.lower() == "open":
            rename[c] = "Open"
        elif key.lower() == "high":
            rename[c] = "High"
        elif key.lower() == "low":
            rename[c] = "Low"
        elif key.lower() in {"close", "adj close"}:
            # Prefer Close; Adj Close remapped only if Close absent later
            rename[c] = "Adj Close" if key.lower() == "adj close" else "Close"
        elif key.lower() == "volume":
            rename[c] = "Volume"
        else:
            rename[c] = key
    out = df.rename(columns=rename)
    if "Close" not in out.columns and "Adj Close" in out.columns:
        out["Close"] = out["Adj Close"]
    needed = ["Open", "High", "Low", "Close"]
    missing = [c for c in needed if c not in out.columns]
    if missing:
        raise ValueError(f"Downloaded data missing {missing}; columns={list(out.columns)}")
    out = out[needed + (["Volume"] if "Volume" in out.columns else [])].copy()
    out = out.dropna(subset=needed)
    out.index = pd.to_datetime(out.index).tz_localize(None)
    return out.sort_index()


def download_symbol(
    symbol: str,
    start: str | None = "2015-01-01",
    end: str | None = None,
    auto_adjust: bool = True,
) -> pd.DataFrame:
    """Download daily OHLCV for one symbol. Raises if empty."""
    raw = yf.download(
        symbol,
        start=start,
        end=end,
        auto_adjust=auto_adjust,
        progress=False,
        threads=False,
    )
    if raw is None or raw.empty:
        raise RuntimeError(f"No data returned for {symbol}")
    return _normalize_ohlc(raw)


def download_universe(
    symbols: Iterable[str] | None = None,
    start: str | None = "2015-01-01",
    end: str | None = None,
) -> dict[str, pd.DataFrame]:
    """Download many symbols; skips failures with a warning print to stderr."""
    import sys

    symbols = tuple(symbols) if symbols is not None else DEFAULT_VOLATILE_UNIVERSE
    out: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        try:
            out[sym] = download_symbol(sym, start=start, end=end)
        except Exception as exc:  # noqa: BLE001 — keep universe resilient
            print(f"skip {sym}: {exc}", file=sys.stderr)
    if not out:
        raise RuntimeError("No symbols downloaded successfully")
    return out
