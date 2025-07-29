from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple

from src.strategies.trend_riding.strategy import TrendRidingStrategy
from src.strategies.trend_riding.config import TrendRidingConfig
from utils.runners.engine_manager import EngineManager
from utils.data.data_manager import DataManager

"""Continuous contract backtest runner for Trend-Riding strategy.

This runner combines multiple NIFTY futures contracts into a continuous
time series and runs the strategy across the entire period, generating
multiple trades instead of one trade per contract.
"""


class TrendRidingContinuousRunner:
    """Execute a continuous contract backtest across all NIFTY expiries."""

    def __init__(self):
        pass

    def run(self, symbol_pattern: str = "NIFTY", start_date: str = None, end_date: str = None) -> Dict[str, Any]:
        """Run continuous contract backtest for all NIFTY instruments.
        
        Args:
            symbol_pattern: Base symbol to find (e.g., "NIFTY")
            start_date: Start date for filtering (YYYY-MM-DD format, optional)
            end_date: End date for filtering (YYYY-MM-DD format, optional)
            
        Returns:
            Dictionary with backtest results including all trades
        """
        # Load strategy config
        default_yaml_path = Path(__file__).resolve().parents[2] / "strategy.yaml"
        if default_yaml_path.exists():
            cfg = TrendRidingConfig.from_yaml(
                default_yaml_path, instrument_id="CONTINUOUS_NIFTY"
            )
        else:
            cfg = TrendRidingConfig(instrument_id="CONTINUOUS_NIFTY")

        # Get all NIFTY instruments and their data
        data_mgr = DataManager()
        continuous_prices, continuous_dates, instrument_map = self._build_continuous_series(
            data_mgr, symbol_pattern
        )
        
        if not continuous_prices:
            raise ValueError(f"No data found for continuous contract {symbol_pattern}")
        
        # Filter by date range if specified
        if start_date or end_date:
            continuous_prices, continuous_dates, instrument_map = self._filter_by_date_range(
                continuous_prices, continuous_dates, instrument_map, start_date, end_date
            )
            
            if not continuous_prices:
                raise ValueError(f"No data found in date range {start_date} to {end_date}")

        # Create and run strategy on continuous data
        strat = TrendRidingStrategy(cfg)
        eng_mgr = EngineManager()
        engine = eng_mgr.create_engine()
        
        # Setup engine
        eng_mgr.setup_venue(engine)
        
        # Use dummy instrument for continuous contract
        dummy_instrument = {"id": "CONTINUOUS_NIFTY", "instrument_id": "CONTINUOUS_NIFTY"}
        eng_mgr.add_instrument(engine, dummy_instrument)
        eng_mgr.add_data(engine, continuous_prices)
        eng_mgr.add_strategy(engine, strat)
        
        # Feed prices and dates to the strategy
        for price, date in zip(continuous_prices, continuous_dates):
            strat.on_quote(price, date)

        # Run backtest
        eng_mgr.run_backtest(engine)
        result = eng_mgr.get_results(engine)
        
        # Get actual trades from strategy
        actual_trades = strat.get_trades() if hasattr(strat, 'get_trades') else []
        
        # Enhance trades with real dates and instrument info
        enhanced_trades = self._enhance_trades_with_dates(
            actual_trades, continuous_prices, continuous_dates, instrument_map
        )
        
        # Clean up
        eng_mgr.cleanup()
        
        # Calculate total PnL
        total_pnl = sum(trade.get("pnl", 0) for trade in enhanced_trades)
        
        # Return comprehensive results
        result.update({
            "instrument_id": "CONTINUOUS_NIFTY",
            "trades": enhanced_trades,
            "num_trades": len(enhanced_trades),
            "total_pnl": total_pnl,
            "num_quotes": len(continuous_prices),
            "time_period": f"{continuous_dates[0]} to {continuous_dates[-1]}" if continuous_dates else "Unknown",
            "instruments_used": list(instrument_map.keys()),
            "data_source": "Continuous Contract - Parquet catalog"
        })
        
        return result

    def _build_continuous_series(self, data_mgr: DataManager, symbol_pattern: str) -> Tuple[List[float], List[str], Dict[str, Tuple[int, int]]]:
        """Build continuous price and date series from all matching instruments.
        
        Returns:
            Tuple of (prices, dates, instrument_map)
            instrument_map maps instrument_id to (start_idx, end_idx) in the series
        """
        # Get all available instruments
        all_instruments = data_mgr.get_all_instrument_ids()
        
        # Filter for NIFTY instruments and sort by expiry date
        nifty_instruments = [
            inst for inst in all_instruments 
            if symbol_pattern in inst and "FUT.NSE" in inst
        ]
        
        # Sort by expiry date extracted from instrument ID
        def extract_expiry_date(inst_id: str) -> str:
            # Extract date from NIFTY20230629.FUT.NSE -> 20230629
            try:
                date_part = inst_id.replace(symbol_pattern, "").split(".")[0]
                # Convert YYYYMMDD to YYYY-MM-DD
                return f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
            except:
                return "9999-12-31"  # Put invalid dates at end
        
        nifty_instruments.sort(key=extract_expiry_date)
        
        print(f"Found {len(nifty_instruments)} NIFTY instruments for continuous contract")
        
        continuous_prices = []
        continuous_dates = []
        instrument_map = {}
        
        for instrument_id in nifty_instruments:
            try:
                # Try to get data for this instrument
                prices, dates = data_mgr.get_trade_ticks_with_dates(instrument_id, allow_stub=False)
                
                if prices and dates:
                    start_idx = len(continuous_prices)
                    continuous_prices.extend(prices)
                    continuous_dates.extend(dates)
                    end_idx = len(continuous_prices) - 1
                    
                    instrument_map[instrument_id] = (start_idx, end_idx)
                    print(f"Added {len(prices)} bars from {instrument_id} ({dates[0]} to {dates[-1]})")
                
            except Exception as e:
                print(f"Skipping {instrument_id}: {e}")
                continue
        
        print(f"Built continuous series with {len(continuous_prices)} total bars")
        return continuous_prices, continuous_dates, instrument_map

    def _enhance_trades_with_dates(
        self, 
        trades: List[dict], 
        prices: List[float], 
        dates: List[str], 
        instrument_map: Dict[str, Tuple[int, int]]
    ) -> List[dict]:
        """Enhance trade records with real dates and determine which instrument was used."""
        
        enhanced_trades = []
        
        for trade in trades:
            entry_price = trade.get("entry_price", 0)
            exit_price = trade.get("exit_price", 0)
            
            # Find the closest price indices for entry and exit
            entry_idx = self._find_closest_price_index(prices, entry_price)
            exit_idx = self._find_closest_price_index(prices, exit_price)
            
            # Determine which instrument(s) were used
            entry_instrument = self._find_instrument_at_index(entry_idx, instrument_map)
            exit_instrument = self._find_instrument_at_index(exit_idx, instrument_map)
            
            # Use dates from the price series
            entry_date = dates[entry_idx] if entry_idx < len(dates) else "Unknown"
            exit_date = dates[exit_idx] if exit_idx < len(dates) else "Unknown"
            
            enhanced_trade = {
                "Instrument": f"{entry_instrument}→{exit_instrument}" if entry_instrument != exit_instrument else entry_instrument,
                "Entry_Date": entry_date,
                "Trade_Type": trade.get("direction", "Long"),
                "Exit_Reason": trade.get("exit_reason", "SIGNAL"),
                "Entry_Price": round(entry_price, 2),
                "IV": round(entry_price * 0.25, 2),  # Synthetic
                "OI": int(entry_price * 10),  # Synthetic
                "Exit_Date": exit_date,
                "Exit_Price": round(exit_price, 2),
                "Threshold": round(entry_price * 1.002, 2),  # Placeholder
                "SL_Price": round(entry_price * 0.98, 2),  # 2% SL
                "Realised_PnL": round(trade.get("pnl", 0), 2),
                "PnL%": round((trade.get("pnl", 0) / entry_price) * 100, 2),
                "MDD_pct": 0.0,  # Placeholder
                "Sharpe": 0.0,  # Placeholder
                "Cum_PnL": None,
                "Entry_Index": entry_idx,
                "Exit_Index": exit_idx,
            }
            enhanced_trades.append(enhanced_trade)
        
        return enhanced_trades

    def _find_closest_price_index(self, prices: List[float], target_price: float) -> int:
        """Find the index of the price closest to the target price."""
        if not prices:
            return 0
        
        closest_idx = 0
        min_diff = abs(prices[0] - target_price)
        
        for i, price in enumerate(prices):
            diff = abs(price - target_price)
            if diff < min_diff:
                min_diff = diff
                closest_idx = i
        
        return closest_idx

    def _find_instrument_at_index(self, index: int, instrument_map: Dict[str, Tuple[int, int]]) -> str:
        """Find which instrument was active at the given index."""
        for instrument_id, (start_idx, end_idx) in instrument_map.items():
            if start_idx <= index <= end_idx:
                return instrument_id
        return "UNKNOWN"

    def _filter_by_date_range(
        self, 
        prices: List[float], 
        dates: List[str], 
        instrument_map: Dict[str, Tuple[int, int]], 
        start_date: str = None, 
        end_date: str = None
    ) -> Tuple[List[float], List[str], Dict[str, Tuple[int, int]]]:
        """Filter continuous series by date range."""
        
        print(f"Filtering data from {start_date or 'beginning'} to {end_date or 'end'}")
        
        # Create filtered lists
        filtered_prices = []
        filtered_dates = []
        new_instrument_map = {}
        
        for i, (price, date) in enumerate(zip(prices, dates)):
            include = True
            
            if start_date and date < start_date:
                include = False
            if end_date and date > end_date:
                include = False
                
            if include:
                filtered_prices.append(price)
                filtered_dates.append(date)
        
        print(f"Filtered from {len(prices)} to {len(filtered_prices)} bars")
        print(f"Date range: {filtered_dates[0] if filtered_dates else 'None'} to {filtered_dates[-1] if filtered_dates else 'None'}")
        
        # Update instrument map for filtered data
        for instrument_id, (orig_start, orig_end) in instrument_map.items():
            # Find where this instrument's data appears in the filtered series
            new_start = None
            new_end = None
            
            for i, date in enumerate(filtered_dates):
                if orig_start < len(dates) and dates[orig_start] <= date <= dates[min(orig_end, len(dates)-1)]:
                    if new_start is None:
                        new_start = i
                    new_end = i
            
            if new_start is not None and new_end is not None:
                new_instrument_map[instrument_id] = (new_start, new_end)
        
        return filtered_prices, filtered_dates, new_instrument_map


__all__ = ["TrendRidingContinuousRunner"] 