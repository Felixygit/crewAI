"""Technical indicators used by the mean-reversion strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(window=period, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 2) -> pd.Series:
    """Wilder-smoothed RSI (matches common Connors RSI(2) implementations)."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    result = 100.0 - (100.0 / (1.0 + rs))
    # Flat / zero-loss bars → RSI 100; zero-gain+zero-loss → NaN then ffill mid
    result = result.where(avg_loss != 0, 100.0)
    return result


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    ranges = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range (Wilder smoothing)."""
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def natr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    """Normalized ATR as percent of close (Quantitativo volatility ranking)."""
    return 100.0 * atr(high, low, close, period) / close.replace(0.0, np.nan)


def ibs(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """Internal Bar Strength: (Close - Low) / (High - Low)."""
    bar_range = (high - low).replace(0.0, np.nan)
    return (close - low) / bar_range


def enrich(ohlc: pd.DataFrame) -> pd.DataFrame:
    """Add strategy indicator columns to an OHLC DataFrame."""
    required = {"Open", "High", "Low", "Close"}
    missing = required - set(ohlc.columns)
    if missing:
        raise ValueError(f"OHLC missing columns: {sorted(missing)}")

    out = ohlc.copy()
    close, high, low = out["Close"], out["High"], out["Low"]
    out["sma_200"] = sma(close, 200)
    out["sma_5"] = sma(close, 5)
    out["rsi_2"] = rsi(close, 2)
    out["atr_14"] = atr(high, low, close, 14)
    out["natr_14"] = natr(high, low, close, 14)
    out["ibs"] = ibs(high, low, close)
    out["prev_high"] = high.shift(1)
    return out
