from __future__ import annotations

from typing import List, Optional

from utils.strategy.base_strategy import BaseStrategy
from .config import TrendRidingConfig
from .entry import compute_signal, Direction
from .risk import RiskManager
from .position import calculate_size

"""TrendRidingStrategy – minimal implementation compatible with new scaffold."""


class TrendRidingStrategy(BaseStrategy):
    """A placeholder strategy that counts quotes and uses helpers.

    The real trading logic will be fleshed out in subsequent iterations.
    """

    config_class = TrendRidingConfig

    def _setup(self) -> None:  # noqa: D401,override
        self._prices: List[float] = []
        self._dates: List[str] = []  # Track dates for each bar
        self._in_position: bool = False
        self._entry_price: Optional[float] = None
        self._entry_index: Optional[int] = None
        self._position_side: Optional[Direction] = None  # None until entry
        self.risk_mgr = RiskManager(self.config.sl_pct, self.config.tp_pct)
        self._trades: List[dict] = []
        self._current_trade: Optional[dict] = None
        super()._setup()

    # ------------------------------------------------------------------
    # Mocked hooks – in real environment quotes/bars carry rich info objects
    # ------------------------------------------------------------------
    def on_quote(self, price: float, date: str = None):  # date is optional for backward compatibility
        self._prices.append(price)
        if date is not None:
            self._dates.append(date)
        else:
            self._dates.append("")  # fallback if no date provided
        idx = len(self._prices) - 1
        try:
            sig = compute_signal(
                highs=self._prices,
                lows=self._prices,
                closes=self._prices,
                period=self.config.lookback_intervals,
                buffer_pct=self.config.entry_buffer_pct,
            )
        except ValueError:
            return  # not enough bars yet

        if not self._in_position:
            if sig in (Direction.LONG, Direction.SHORT):
                self._enter_trade(price, sig, idx)
        else:
            # Exit if SL/TP hit
            if self.risk_mgr.hit(
                self._prices,
                self._entry_price,
                side=self._position_side or Direction.LONG,
            ):
                self._exit_trade(price, idx)
                # Immediately check for new entry after exit
                if sig in (Direction.LONG, Direction.SHORT):
                    self._enter_trade(price, sig, idx)
                return

            # SAR logic: exit and reverse on opposite signal
            if self.config.sar_enabled:
                if (
                    (self._position_side == Direction.LONG and sig == Direction.SHORT)
                    or (self._position_side == Direction.SHORT and sig == Direction.LONG)
                ):
                    self._exit_trade(price, idx)
                    self._enter_trade(price, sig, idx)

    # ------------------------------------------------------------------
    def _enter_trade(self, price: float, direction: Direction, idx: int) -> None:
        size = calculate_size(
            capital=100_000,
            risk_per_trade_pct=0.01,
            price=price,
            sl_pct=self.config.sl_pct,
        )
        self.log.info("Entering %s at %.2f, size=%s", direction.name, price, size)
        self._in_position = True
        self._entry_price = price
        self._entry_index = idx
        self._position_side = direction
        entry_date = self._dates[idx] if idx < len(self._dates) else ""
        self._current_trade = {
            "entry_price": price,
            "entry_date": entry_date,
            "direction": direction.name,
            "size": size
        }

    def _exit_trade(self, price: float, idx: int) -> None:
        pnl = price - (self._entry_price or 0.0)
        if self._position_side == Direction.SHORT:
            pnl = -pnl
        self.log.info(
            "Exiting %s at %.2f, PnL=%.2f",
            self._position_side.name if self._position_side else "?",
            price,
            pnl,
        )
        exit_date = self._dates[idx] if idx < len(self._dates) else ""
        if self._current_trade:
            self._current_trade.update({
                "exit_price": price,
                "exit_date": exit_date,
                "pnl": pnl,
                "exit_reason": "SIGNAL"  # Default, can be overridden
            })
            self._trades.append(self._current_trade)
            self._current_trade = None
        self._in_position = False
        self._entry_price = None
        self._entry_index = None
        self._position_side = None

    # ------------------------------------------------------------------
    def on_stop(self):  # noqa: D401,override
        # Handle any open position at end of backtest
        if self._in_position and self._current_trade and self._prices:
            final_price = self._prices[-1]
            final_idx = len(self._prices) - 1
            pnl = final_price - (self._entry_price or 0.0)
            if self._position_side == Direction.SHORT:
                pnl = -pnl
            exit_date = self._dates[final_idx] if final_idx < len(self._dates) else ""
            self._current_trade.update({
                "exit_price": final_price,
                "exit_date": exit_date,
                "pnl": pnl,
                "exit_reason": "EXP_FORCED"
            })
            self._trades.append(self._current_trade)
            self._current_trade = None
        super().on_stop()
        self.log.info("Processed %s quotes in total.", len(self._prices))
        self.log.info("Generated %s trades in total.", len(self._trades))

    def get_trades(self) -> List[dict]:
        """Return all completed trades from this strategy run."""
        return self._trades.copy()


__all__ = ["TrendRidingStrategy"]
