#!/usr/bin/env python3
"""Continuous contract backtest runner for NIFTY futures.

This script runs a single backtest across ALL NIFTY futures contracts,
treating them as a continuous time series. This generates multiple trades
across the entire time period instead of one trade per contract.

Examples
--------
# Run continuous NIFTY backtest
python scripts/run_continuous_backtest.py --catalog_path catalog-data-nautilus

# Save results to file
python scripts/run_continuous_backtest.py --catalog_path catalog-data-nautilus --outfile continuous_backtest_results.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"
for p in (ROOT_DIR, SRC_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from src.strategies.trend_riding.runner.backtest_runner.continuous_runner import TrendRidingContinuousRunner
from utils.data.data_manager import DataManager


def parse_args():
    parser = argparse.ArgumentParser(description="Run continuous contract NIFTY backtest")
    parser.add_argument(
        "--catalog_path", 
        type=str, 
        default="catalog-data-nautilus",
        help="Path to Parquet catalog directory"
    )
    parser.add_argument(
        "--symbol", 
        type=str, 
        default="NIFTY",
        help="Base symbol to create continuous contract for"
    )
    parser.add_argument(
        "--outfile", 
        type=str, 
        help="Save results to JSON file"
    )
    parser.add_argument(
        "--bar_interval",
        type=str,
        default="1-DAY",
        help="Bar interval (e.g., 1-DAY, 1-MINUTE)"
    )
    parser.add_argument(
        "--start_date",
        type=str,
        help="Start date for filtering (YYYY-MM-DD format, e.g., 2023-07-01)"
    )
    parser.add_argument(
        "--end_date",
        type=str,
        help="End date for filtering (YYYY-MM-DD format, e.g., 2023-07-31)"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    
    # Set environment variables for data loading
    import os
    if args.catalog_path:
        os.environ["DATA_CATALOG_ROOTS"] = args.catalog_path
    if args.bar_interval:
        os.environ["BAR_INTERVAL"] = args.bar_interval.upper()
    
    print(f"Running continuous contract backtest for {args.symbol}")
    print(f"Using catalog: {args.catalog_path}")
    print(f"Bar interval: {args.bar_interval}")
    if args.start_date or args.end_date:
        print(f"Date filter: {args.start_date or 'beginning'} to {args.end_date or 'end'}")
    print("-" * 60)
    
    try:
        # Create and run the continuous backtest
        runner = TrendRidingContinuousRunner()
        result = runner.run(
            symbol_pattern=args.symbol,
            start_date=args.start_date,
            end_date=args.end_date
        )
        
        # Print summary
        print("\n" + "="*60)
        print("CONTINUOUS CONTRACT BACKTEST RESULTS")
        print("="*60)
        print(f"Symbol: {args.symbol}")
        print(f"Time Period: {result.get('time_period', 'Unknown')}")
        print(f"Total Quotes: {result.get('num_quotes', 0):,}")
        print(f"Total Trades: {result.get('num_trades', 0)}")
        print(f"Total PnL: ₹{result.get('total_pnl', 0):,.2f}")
        print(f"Instruments Used: {len(result.get('instruments_used', []))}")
        print(f"Return %: {result.get('return_pct', 0):.2f}%")
        print(f"Sharpe Ratio: {result.get('sharpe', 0):.2f}")
        print(f"Max Drawdown: {result.get('max_drawdown_pct', 0):.2f}%")
        
        # Print trade summary
        trades = result.get('trades', [])
        if trades:
            print(f"\nTRADE SUMMARY:")
            print("-" * 40)
            winning_trades = [t for t in trades if t.get('Realised_PnL', 0) > 0]
            losing_trades = [t for t in trades if t.get('Realised_PnL', 0) < 0]
            
            print(f"Winning Trades: {len(winning_trades)}")
            print(f"Losing Trades: {len(losing_trades)}")
            if winning_trades:
                avg_win = sum(t.get('Realised_PnL', 0) for t in winning_trades) / len(winning_trades)
                print(f"Average Win: ₹{avg_win:.2f}")
            if losing_trades:
                avg_loss = sum(t.get('Realised_PnL', 0) for t in losing_trades) / len(losing_trades)
                print(f"Average Loss: ₹{avg_loss:.2f}")
            
            # Show first few trades
            print(f"\nFIRST 5 TRADES:")
            print("-" * 40)
            for i, trade in enumerate(trades[:5]):
                print(f"{i+1}. {trade.get('Entry_Date')} → {trade.get('Exit_Date')}: "
                      f"₹{trade.get('Realised_PnL', 0):.2f} ({trade.get('Exit_Reason', 'Unknown')})")
        
        # Print full JSON results
        print(f"\nFULL RESULTS JSON:")
        print("-" * 40)
        print(json.dumps(result, indent=2))
        
        # Save to file if requested
        if args.outfile:
            Path(args.outfile).write_text(json.dumps(result, indent=2))
            print(f"\nResults saved to: {args.outfile}")
            
    except Exception as e:
        print(f"Error running continuous backtest: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main() 