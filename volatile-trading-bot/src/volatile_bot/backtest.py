"""Event-driven next-open backtester with equal-slot capital allocation."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from volatile_bot.strategy import MeanReversionStrategy, StrategyConfig


@dataclass
class Trade:
    symbol: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    shares: float
    pnl: float
    return_pct: float
    bars_held: int
    entry_natr: float
    entry_rsi: float


@dataclass
class BacktestResult:
    trades: list[Trade] = field(default_factory=list)
    equity_curve: pd.Series | None = None
    initial_capital: float = 100_000.0

    @property
    def n_trades(self) -> int:
        return len(self.trades)

    @property
    def win_rate(self) -> float | None:
        if not self.trades:
            return None
        wins = sum(1 for t in self.trades if t.pnl > 0)
        return wins / len(self.trades)

    @property
    def profit_factor(self) -> float | None:
        gains = sum(t.pnl for t in self.trades if t.pnl > 0)
        losses = sum(-t.pnl for t in self.trades if t.pnl < 0)
        if losses == 0:
            return None if gains == 0 else float("inf")
        return gains / losses

    @property
    def expectancy_pct(self) -> float | None:
        if not self.trades:
            return None
        return float(np.mean([t.return_pct for t in self.trades]))

    def summary(self) -> dict[str, float | int | None]:
        eq = self.equity_curve
        total_return = None
        max_dd = None
        if eq is not None and len(eq) > 1:
            total_return = float(eq.iloc[-1] / eq.iloc[0] - 1.0)
            peak = eq.cummax()
            dd = eq / peak - 1.0
            max_dd = float(dd.min())
        return {
            "trades": self.n_trades,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "expectancy_pct": self.expectancy_pct,
            "total_return": total_return,
            "max_drawdown": max_dd,
            "final_equity": float(eq.iloc[-1]) if eq is not None and len(eq) else None,
        }


@dataclass
class _OpenPosition:
    symbol: str
    entry_date: pd.Timestamp
    entry_price: float
    shares: float
    entry_natr: float
    entry_rsi: float
    signal_idx: int


class PortfolioBacktester:
    """Backtest mean-reversion across a universe.

    Rules:
    - Signals evaluated on day T close; fills at day T+1 open.
    - Capital split into ``max_positions`` equal slots.
    - When more entries than free slots, rank by NATR descending (Quantitativo).
    - Commission + slippage applied per fill as a fraction of notional.
    """

    def __init__(
        self,
        strategy: MeanReversionStrategy | None = None,
        initial_capital: float = 100_000.0,
        max_positions: int = 5,
        commission_pct: float = 0.0005,
        slippage_pct: float = 0.0005,
    ) -> None:
        self.strategy = strategy or MeanReversionStrategy()
        self.initial_capital = initial_capital
        self.max_positions = max_positions
        self.commission_pct = commission_pct
        self.slippage_pct = slippage_pct

    def run(self, data: dict[str, pd.DataFrame]) -> BacktestResult:
        prepared = {sym: self.strategy.prepare(df) for sym, df in data.items()}
        # Align calendar to union of trading days
        all_dates = sorted({d for df in prepared.values() for d in df.index})
        if len(all_dates) < 3:
            return BacktestResult(initial_capital=self.initial_capital)

        cash = self.initial_capital
        open_pos: dict[str, _OpenPosition] = {}
        trades: list[Trade] = []
        equity_points: list[tuple[pd.Timestamp, float]] = []

        entry_pending: dict[str, dict] = {}
        exit_pending: set[str] = set()

        date_to_idx = {d: i for i, d in enumerate(all_dates)}

        for i, dt in enumerate(all_dates):
            # --- fills at today's open ---
            # Exits first
            for sym in list(exit_pending):
                if sym not in open_pos:
                    exit_pending.discard(sym)
                    continue
                df = prepared[sym]
                if dt not in df.index:
                    continue
                fill = float(df.loc[dt, "Open"]) * (1.0 - self.slippage_pct)
                pos = open_pos.pop(sym)
                proceeds = pos.shares * fill
                costs = proceeds * self.commission_pct
                cash += proceeds - costs
                pnl = proceeds - costs - (pos.shares * pos.entry_price)
                # entry already paid commission at buy; approximate round-trip PnL:
                entry_notional = pos.shares * pos.entry_price
                entry_cost = entry_notional * self.commission_pct
                pnl = proceeds - costs - entry_notional - entry_cost
                bars_held = date_to_idx[dt] - date_to_idx[pos.entry_date]
                trades.append(
                    Trade(
                        symbol=sym,
                        entry_date=pos.entry_date,
                        exit_date=dt,
                        entry_price=pos.entry_price,
                        exit_price=fill,
                        shares=pos.shares,
                        pnl=pnl,
                        return_pct=pnl / (entry_notional + entry_cost),
                        bars_held=max(bars_held, 0),
                        entry_natr=pos.entry_natr,
                        entry_rsi=pos.entry_rsi,
                    )
                )
                exit_pending.discard(sym)

            # Entries
            free_slots = self.max_positions - len(open_pos)
            if free_slots > 0 and entry_pending:
                candidates = []
                for sym, meta in list(entry_pending.items()):
                    if sym in open_pos:
                        entry_pending.pop(sym, None)
                        continue
                    df = prepared[sym]
                    if dt not in df.index:
                        continue
                    candidates.append((sym, meta, float(df.loc[dt, "Open"])))
                # Rank by NATR from signal day
                candidates.sort(key=lambda x: x[1]["natr"], reverse=True)
                slot_equity = cash / free_slots if free_slots else 0.0
                for sym, meta, open_px in candidates[:free_slots]:
                    fill = open_px * (1.0 + self.slippage_pct)
                    if fill <= 0 or slot_equity <= 0:
                        continue
                    # Size so notional + commission fit inside the slot budget.
                    budget = min(slot_equity, cash) / (1.0 + self.commission_pct)
                    shares = budget / fill
                    cost = shares * fill
                    commission = cost * self.commission_pct
                    if cost + commission > cash + 1e-9:
                        continue
                    cash -= cost + commission
                    open_pos[sym] = _OpenPosition(
                        symbol=sym,
                        entry_date=dt,
                        entry_price=fill,
                        shares=shares,
                        entry_natr=meta["natr"],
                        entry_rsi=meta["rsi"],
                        signal_idx=meta["signal_idx"],
                    )
                    entry_pending.pop(sym, None)
                # Drop unfilled pending entries for this signal batch
                entry_pending.clear()

            # --- mark equity at close ---
            mtm = cash
            for sym, pos in open_pos.items():
                df = prepared[sym]
                if dt in df.index:
                    mtm += pos.shares * float(df.loc[dt, "Close"])
            equity_points.append((dt, mtm))

            # --- generate signals on today's close for next open ---
            if i >= len(all_dates) - 1:
                continue

            # Exits
            for sym, pos in list(open_pos.items()):
                df = prepared[sym]
                if dt not in df.index:
                    continue
                # hold-day count from entry
                bars_held = date_to_idx[dt] - date_to_idx[pos.entry_date]
                timed_out = bars_held >= self.strategy.config.max_hold_days
                if bool(self.strategy.exit_mask(df).loc[dt]) or timed_out:
                    exit_pending.add(sym)

            # Entries — only if not already in / exiting
            entry_candidates = []
            for sym, df in prepared.items():
                if sym in open_pos or sym in exit_pending:
                    continue
                if dt not in df.index:
                    continue
                if bool(self.strategy.entry_mask(df).loc[dt]):
                    row = df.loc[dt]
                    entry_candidates.append(
                        {
                            "symbol": sym,
                            "natr": float(row["natr_14"]),
                            "rsi": float(row["rsi_2"]),
                            "signal_idx": i,
                        }
                    )
            entry_candidates.sort(key=lambda x: x["natr"], reverse=True)
            for meta in entry_candidates:
                entry_pending[meta["symbol"]] = meta

        equity = pd.Series(
            {d: v for d, v in equity_points},
            name="equity",
        ).sort_index()
        return BacktestResult(
            trades=trades,
            equity_curve=equity,
            initial_capital=self.initial_capital,
        )


def run_single_symbol_backtest(
    ohlc: pd.DataFrame,
    symbol: str = "SYM",
    config: StrategyConfig | None = None,
    initial_capital: float = 100_000.0,
    commission_pct: float = 0.0005,
    slippage_pct: float = 0.0005,
) -> BacktestResult:
    """Convenience wrapper for one-symbol Connors-style backtest (100% equity)."""
    bt = PortfolioBacktester(
        strategy=MeanReversionStrategy(config),
        initial_capital=initial_capital,
        max_positions=1,
        commission_pct=commission_pct,
        slippage_pct=slippage_pct,
    )
    return bt.run({symbol: ohlc})
