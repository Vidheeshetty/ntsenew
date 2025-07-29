from __future__ import annotations

from typing import List, Optional, Dict, Any

from utils.strategy.base_strategy import BaseStrategy
from .config import TrendRidingConfig
from .entry import compute_signal, Direction
from .risk import RiskManager
from .position import calculate_size

"""TrendRidingStrategy – updated to handle OHLC bar data properly."""


class TrendRidingStrategy(BaseStrategy):
    """A trend-following strategy using Dow theory breakouts with proper OHLC data."""

    config_class = TrendRidingConfig

    def _setup(self) -> None:
        """Initialize strategy state and data containers."""
        # Separate arrays for OHLC data
        self._opens: List[float] = []
        self._highs: List[float] = []
        self._lows: List[float] = []
        self._closes: List[float] = []
        self._dates: List[str] = []
        
        # Position tracking
        self._in_position: bool = False
        self._entry_price: Optional[float] = None
        self._entry_index: Optional[int] = None
        self._position_side: Optional[Direction] = None
        
        # Risk management
        self.risk_mgr = RiskManager(self.config.sl_pct, self.config.tp_pct)
        
        # Trade tracking
        self._trades: List[dict] = []
        self._current_trade: Optional[dict] = None
        
        super()._setup()

    def on_bar(self, bar: Dict[str, Any], date: str = None):
        """Process OHLC bar data.
        
        Args:
            bar: Dict with 'open', 'high', 'low', 'close' keys
            date: Optional date string
        """
        # Extract OHLC values
        open_price = bar.get('open', bar.get('close', 0))
        high_price = bar.get('high', bar.get('close', 0))
        low_price = bar.get('low', bar.get('close', 0))
        close_price = bar.get('close', 0)
        
        # Store OHLC data
        self._opens.append(open_price)
        self._highs.append(high_price)
        self._lows.append(low_price)
        self._closes.append(close_price)
        
        if date is not None:
            self._dates.append(date)
        else:
            self._dates.append("")
            
        self._process_bar()

    def on_quote(self, price: float, date: str = None):
        """Legacy method for single price quotes - converts to OHLC format."""
        # For backward compatibility, treat single price as OHLC where O=H=L=C
        bar = {
            'open': price,
            'high': price,
            'low': price,
            'close': price
        }
        self.on_bar(bar, date)

    def _process_bar(self):
        """Process the latest bar for entry/exit signals."""
        idx = len(self._closes) - 1
        
        # Check for breakout signal
        try:
            sig = compute_signal(
                highs=self._highs,
                lows=self._lows,
                closes=self._closes,
                period=self.config.lookback_intervals,
                buffer_pct=self.config.entry_buffer_pct,
            )
        except ValueError:
            return  # Not enough bars yet

        current_price = self._closes[-1]

        if not self._in_position:
            # Check for entry signal
            if sig in (Direction.LONG, Direction.SHORT):
                self._enter_trade(current_price, sig, idx)
        else:
            # Check exit conditions
            exit_reason = self._check_exit_conditions(idx)
            
            if exit_reason:
                self._exit_trade(current_price, idx, exit_reason)
                
                # Check for immediate re-entry (SAR)
                if self.config.sar_enabled and sig in (Direction.LONG, Direction.SHORT):
                    if sig != self._position_side:  # Only on opposite signal
                        self._enter_trade(current_price, sig, idx)

    def _check_exit_conditions(self, idx: int) -> Optional[str]:
        """Check if any exit condition is met.
        
        Returns:
            Exit reason string if exit triggered, None otherwise
        """
        if not self._in_position or self._entry_price is None:
            return None
            
        high = self._highs[idx]
        low = self._lows[idx]
        
        # Check stop-loss and take-profit using high/low of the bar
        if self._position_side == Direction.LONG:
            # For long positions
            if low <= self._entry_price * (1 - self.config.sl_pct):
                return "SL"
            if high >= self._entry_price * (1 + self.config.tp_pct):
                return "TP"
        else:  # SHORT
            # For short positions
            if high >= self._entry_price * (1 + self.config.sl_pct):
                return "SL"
            if low <= self._entry_price * (1 - self.config.tp_pct):
                return "TP"
        
        # Check for SAR signal
        if self.config.sar_enabled:
            try:
                sig = compute_signal(
                    highs=self._highs,
                    lows=self._lows,
                    closes=self._closes,
                    period=self.config.lookback_intervals,
                    buffer_pct=self.config.entry_buffer_pct,
                )
                if (self._position_side == Direction.LONG and sig == Direction.SHORT) or \
                   (self._position_side == Direction.SHORT and sig == Direction.LONG):
                    return "SAR"
            except ValueError:
                pass
                
        return None

    def _enter_trade(self, price: float, direction: Direction, idx: int) -> None:
        """Enter a new trade."""
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
            "size": size,
            "entry_high": self._highs[idx],
            "entry_low": self._lows[idx],
        }

    def _exit_trade(self, price: float, idx: int, reason: str = "SIGNAL") -> None:
        """Exit current trade."""
        if not self._in_position or self._entry_price is None:
            return
            
        # Calculate PnL
        pnl = price - self._entry_price
        if self._position_side == Direction.SHORT:
            pnl = -pnl
            
        self.log.info(
            "Exiting %s at %.2f, PnL=%.2f, Reason=%s",
            self._position_side.name if self._position_side else "?",
            price,
            pnl,
            reason
        )
        
        exit_date = self._dates[idx] if idx < len(self._dates) else ""
        
        if self._current_trade:
            self._current_trade.update({
                "exit_price": price,
                "exit_date": exit_date,
                "pnl": pnl,
                "exit_reason": reason,
                "exit_high": self._highs[idx],
                "exit_low": self._lows[idx],
            })
            self._trades.append(self._current_trade)
            self._current_trade = None
            
        # Reset position state
        self._in_position = False
        self._entry_price = None
        self._entry_index = None
        self._position_side = None

    def on_stop(self):
        """Handle strategy shutdown."""
        # Close any open position
        if self._in_position and self._current_trade and self._closes:
            final_price = self._closes[-1]
            final_idx = len(self._closes) - 1
            self._exit_trade(final_price, final_idx, "EXP_FORCED")
            
        super().on_stop()
        
        self.log.info("Processed %s bars in total.", len(self._closes))
        self.log.info("Generated %s trades in total.", len(self._trades))

    def get_trades(self) -> List[dict]:
        """Return all completed trades from this strategy run."""
        return self._trades.copy()


__all__ = ["TrendRidingStrategy"]