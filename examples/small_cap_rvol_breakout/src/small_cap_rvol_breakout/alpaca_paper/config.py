"""Alpaca paper-trading configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from small_cap_rvol_breakout.models import RiskConfig, ScanFilters
from small_cap_rvol_breakout.run_backtest import DEFAULT_UNIVERSE


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass
class AlpacaPaperConfig:
    """Credentials and runtime settings for the paper executor."""

    api_key: str
    api_secret: str
    paper: bool = True
    base_url: str = "https://paper-api.alpaca.markets"
    data_feed: str = "iex"  # free IEX feed; use "sip" if subscribed
    dry_run: bool = False
    poll_seconds: int = 15
    max_open_positions: int = 3
    universe: list[str] = field(default_factory=lambda: list(DEFAULT_UNIVERSE))
    filters: ScanFilters = field(default_factory=ScanFilters)
    risk: RiskConfig = field(default_factory=RiskConfig)

    @classmethod
    def from_env(cls) -> AlpacaPaperConfig:
        """Build config from ``ALPACA_*`` / ``APCA_*`` environment variables."""
        api_key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID") or ""
        api_secret = (
            os.getenv("ALPACA_API_SECRET")
            or os.getenv("APCA_API_SECRET_KEY")
            or ""
        )
        paper = _env_bool("ALPACA_PAPER", True)
        dry_run = _env_bool("ALPACA_DRY_RUN", False)
        universe_raw = os.getenv("ALPACA_UNIVERSE", "")
        universe = (
            [s.strip().upper() for s in universe_raw.split(",") if s.strip()]
            if universe_raw
            else list(DEFAULT_UNIVERSE)
        )
        equity = float(os.getenv("ALPACA_ACCOUNT_EQUITY", "25000"))
        risk_pct = float(os.getenv("ALPACA_RISK_PER_TRADE_PCT", "0.5"))
        or_minutes = int(os.getenv("ALPACA_OR_MINUTES", "5"))
        max_positions = int(os.getenv("ALPACA_MAX_OPEN_POSITIONS", "3"))
        poll_seconds = int(os.getenv("ALPACA_POLL_SECONDS", "15"))
        data_feed = os.getenv("ALPACA_DATA_FEED", "iex").lower()

        risk = RiskConfig(
            account_equity=equity,
            risk_per_trade_pct=risk_pct,
            opening_range_minutes=or_minutes,
        )
        filters = ScanFilters(
            max_price=float(os.getenv("ALPACA_MAX_PRICE", "20")),
            min_rvol=float(os.getenv("ALPACA_MIN_RVOL", "2.0")),
            min_atr_pct=float(os.getenv("ALPACA_MIN_ATR_PCT", "3.0")),
            min_dollar_volume=float(os.getenv("ALPACA_MIN_DOLLAR_VOLUME", "5000000")),
            max_spread_pct=float(os.getenv("ALPACA_MAX_SPREAD_PCT", "1.0")),
        )
        return cls(
            api_key=api_key,
            api_secret=api_secret,
            paper=paper,
            dry_run=dry_run,
            poll_seconds=poll_seconds,
            max_open_positions=max_positions,
            universe=universe,
            filters=filters,
            risk=risk,
            data_feed=data_feed,
        )

    def require_credentials(self) -> None:
        """Raise if API credentials are missing (unless dry-run)."""
        if self.dry_run:
            return
        if not self.api_key or not self.api_secret:
            raise RuntimeError(
                "Missing Alpaca credentials. Set ALPACA_API_KEY and "
                "ALPACA_API_SECRET (or APCA_API_KEY_ID / APCA_API_SECRET_KEY), "
                "or run with ALPACA_DRY_RUN=true / --dry-run."
            )
        if not self.paper:
            raise RuntimeError(
                "Refusing to start: ALPACA_PAPER is false. This example is "
                "paper-trading only. Set ALPACA_PAPER=true."
            )
