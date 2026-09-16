"""Build strategy QuoteSnapshots from Alpaca market data."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from small_cap_rvol_breakout.alpaca_paper.config import AlpacaPaperConfig
from small_cap_rvol_breakout.models import QuoteSnapshot, RiskConfig

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")


def _bars_to_frame(bars: Any) -> pd.DataFrame:
    """Convert alpaca BarSet / dict-like bars into a DataFrame."""
    if bars is None:
        return pd.DataFrame()
    # BarSet supports data[symbol] or .df
    if hasattr(bars, "df"):
        df = bars.df
        if isinstance(df.index, pd.MultiIndex):
            # columns may be multi-symbol; caller should pass single-symbol subset
            return df.copy()
        return df.copy()
    if isinstance(bars, list):
        rows = [
            {
                "timestamp": getattr(b, "timestamp", None),
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": float(b.volume),
                "vwap": float(getattr(b, "vwap", 0) or 0),
            }
            for b in bars
        ]
        frame = pd.DataFrame(rows)
        if frame.empty:
            return frame
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True).dt.tz_convert(ET)
        return frame.set_index("timestamp").sort_index()
    return pd.DataFrame()


def atr_pct_from_daily(daily: pd.DataFrame, period: int = 14) -> float | None:
    if daily is None or len(daily) < period + 1:
        return None
    high = daily["high"] if "high" in daily.columns else daily["High"]
    low = daily["low"] if "low" in daily.columns else daily["Low"]
    close = daily["close"] if "close" in daily.columns else daily["Close"]
    prev = close.shift(1)
    tr = pd.concat([(high - low), (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    atr = float(tr.tail(period).mean())
    last = float(close.iloc[-1])
    if last <= 0:
        return None
    return (atr / last) * 100.0


def build_quote_from_minutes(
    symbol: str,
    minutes: pd.DataFrame,
    daily: pd.DataFrame,
    risk: RiskConfig,
    bid: float | None = None,
    ask: float | None = None,
) -> QuoteSnapshot | None:
    """Construct a QuoteSnapshot for the live strategy engine.

    Opening range uses the first ``risk.opening_range_minutes`` minute bars
    of the regular session.
    """
    if minutes is None or minutes.empty or daily is None or daily.empty:
        return None

    frame = minutes.copy()
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC").tz_convert(ET)
    else:
        frame.index = frame.index.tz_convert(ET)

    # Regular session only
    frame = frame.between_time("09:30", "16:00")
    if frame.empty:
        return None

    today = frame.index[-1].date()
    session = frame[frame.index.date == today]
    if session.empty:
        return None

    or_minutes = max(1, risk.opening_range_minutes)
    or_bars = session.iloc[:or_minutes]
    if len(or_bars) < or_minutes:
        # OR not complete yet
        return None

    close_col = "close" if "close" in session.columns else "Close"
    high_col = "high" if "high" in session.columns else "High"
    low_col = "low" if "low" in session.columns else "Low"
    vol_col = "volume" if "volume" in session.columns else "Volume"

    or_high = float(or_bars[high_col].max())
    or_low = float(or_bars[low_col].min())
    last = float(session.iloc[-1][close_col])
    session_volume = float(session[vol_col].sum())

    # VWAP from session
    typical = (session[high_col] + session[low_col] + session[close_col]) / 3.0
    cum_vol = session[vol_col].cumsum().replace(0, pd.NA)
    vwap_series = (typical * session[vol_col]).cumsum() / cum_vol
    vwap = float(vwap_series.iloc[-1])

    # Average volume for same elapsed minutes over prior sessions (approx via daily)
    daily_vol_col = "volume" if "volume" in daily.columns else "Volume"
    avg_daily = float(daily[daily_vol_col].tail(20).mean())
    minutes_elapsed = len(session)
    expected_frac = min(1.0, minutes_elapsed / 390.0)
    avg_volume_tod = max(avg_daily * expected_frac, 1.0)

    atr_pct = atr_pct_from_daily(daily)
    atr = (atr_pct / 100.0) * last if atr_pct is not None else last * 0.03

    mid = last
    if bid is None or ask is None:
        # Approximate a tight spread when quote is unavailable
        spread = last * 0.001
        bid = last - spread / 2
        ask = last + spread / 2

    broke = bool(session[high_col].max() > or_high and last > or_high)

    return QuoteSnapshot(
        symbol=symbol.upper(),
        last=last,
        bid=float(bid),
        ask=float(ask),
        session_volume=session_volume,
        avg_volume_tod=avg_volume_tod,
        atr=float(atr),
        float_shares=None,
        or_high=or_high,
        or_low=or_low,
        vwap=vwap,
        broke_or_high=broke,
        notes=f"OR={or_minutes}m session_bars={len(session)}",
    )


class AlpacaMarketData:
    """Fetch minute/daily bars and latest quotes from Alpaca."""

    def __init__(self, config: AlpacaPaperConfig, client: Any | None = None) -> None:
        self.config = config
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            from alpaca.data.historical import StockHistoricalDataClient

            self.config.require_credentials()
            self._client = StockHistoricalDataClient(
                api_key=self.config.api_key,
                secret_key=self.config.api_secret,
            )
        return self._client

    def _feed(self) -> Any:
        from alpaca.data.enums import DataFeed

        return DataFeed.SIP if self.config.data_feed == "sip" else DataFeed.IEX

    def get_minute_bars(self, symbol: str, lookback_days: int = 5) -> pd.DataFrame:
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        end = datetime.now(tz=ET)
        start = end - timedelta(days=lookback_days)
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Minute,
            start=start,
            end=end,
            feed=self._feed(),
        )
        bars = self.client.get_stock_bars(request)
        raw = bars.data.get(symbol, []) if hasattr(bars, "data") else []
        frame = _bars_to_frame(raw)
        if frame.empty and hasattr(bars, "df") and not bars.df.empty:
            df = bars.df
            if isinstance(df.index, pd.MultiIndex):
                try:
                    frame = df.xs(symbol)
                except KeyError:
                    frame = pd.DataFrame()
            else:
                frame = df
        return frame

    def get_daily_bars(self, symbol: str, lookback_days: int = 40) -> pd.DataFrame:
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        end = datetime.now(tz=ET)
        start = end - timedelta(days=lookback_days)
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            feed=self._feed(),
        )
        bars = self.client.get_stock_bars(request)
        raw = bars.data.get(symbol, []) if hasattr(bars, "data") else []
        frame = _bars_to_frame(raw)
        if frame.empty and hasattr(bars, "df") and not bars.df.empty:
            df = bars.df
            if isinstance(df.index, pd.MultiIndex):
                try:
                    frame = df.xs(symbol)
                except KeyError:
                    frame = pd.DataFrame()
            else:
                frame = df
        # normalize column names
        frame = frame.rename(columns={c: c.lower() for c in frame.columns})
        return frame

    def get_latest_quote(self, symbol: str) -> tuple[float | None, float | None]:
        try:
            from alpaca.data.requests import StockLatestQuoteRequest

            req = StockLatestQuoteRequest(symbol_or_symbols=symbol, feed=self._feed())
            quotes = self.client.get_stock_latest_quote(req)
            quote = quotes.get(symbol) if isinstance(quotes, dict) else None
            if quote is None and hasattr(quotes, "__getitem__"):
                quote = quotes[symbol]
            if quote is None:
                return None, None
            bid = float(getattr(quote, "bid_price", 0) or 0) or None
            ask = float(getattr(quote, "ask_price", 0) or 0) or None
            return bid, ask
        except Exception as exc:  # noqa: BLE001
            logger.debug("quote unavailable for %s: %s", symbol, exc)
            return None, None

    def snapshot(self, symbol: str) -> QuoteSnapshot | None:
        try:
            minutes = self.get_minute_bars(symbol)
            daily = self.get_daily_bars(symbol)
            bid, ask = self.get_latest_quote(symbol)
            return build_quote_from_minutes(
                symbol,
                minutes,
                daily,
                self.config.risk,
                bid=bid,
                ask=ask,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed snapshot for %s: %s", symbol, exc)
            return None
