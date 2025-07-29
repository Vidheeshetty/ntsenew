#!/usr/bin/env python3
"""
Debug script to analyze why breakout signals aren't being generated.
Run this to see what's happening with your data.
"""

import pandas as pd
from pathlib import Path
import sys

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from src.strategies.trend_riding.breakout import previous_top_bottom, breakout_signal, Direction


def analyze_breakout_signals(file_path: str, lookback: int = 20, buffer_pct: float = 0.2):
    """Analyze a parquet file and show potential breakout points."""
    
    print(f"\nAnalyzing: {file_path}")
    print(f"Parameters: lookback={lookback}, buffer_pct={buffer_pct}%")
    print("-" * 80)
    
    # Load data
    df = pd.read_parquet(file_path)
    print(f"\nData shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
    
    # Determine if we have OHLC or single price
    if all(col in df.columns for col in ['open', 'high', 'low', 'close']):
        print("\n✓ OHLC data found")
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
    else:
        print("\n✗ No OHLC data - using single price")
        price_col = 'close' if 'close' in df.columns else 'price'
        prices = df[price_col].values
        highs = lows = closes = prices
    
    # Add date column if available
    dates = None
    if 'date' in df.columns:
        dates = df['date'].values
    elif 'timestamp' in df.columns:
        dates = pd.to_datetime(df['timestamp']).dt.strftime('%Y-%m-%d').values
    
    print(f"\nAnalyzing {len(closes)} bars...")
    
    # Track signals
    signals = []
    
    for i in range(lookback, len(closes)):
        # Get previous top/bottom
        prev_highs = highs[:i]
        prev_lows = lows[:i]
        
        prev_top, prev_bottom = previous_top_bottom(
            prev_highs[-lookback:], 
            prev_lows[-lookback:], 
            lookback
        )
        
        # Check for breakout
        signal = breakout_signal(closes[i], prev_top, prev_bottom, buffer_pct)
        
        if signal != Direction.NONE:
            signal_info = {
                'index': i,
                'date': dates[i] if dates is not None else f"Bar {i}",
                'signal': signal.name,
                'close': closes[i],
                'prev_top': prev_top,
                'prev_bottom': prev_bottom,
                'threshold_up': prev_top * (1 + buffer_pct / 100),
                'threshold_down': prev_bottom * (1 - buffer_pct / 100)
            }
            signals.append(signal_info)
    
    # Report findings
    print(f"\nFound {len(signals)} breakout signals:")
    
    if signals:
        for sig in signals[:10]:  # Show first 10
            print(f"\n{sig['date']}:")
            print(f"  Signal: {sig['signal']}")
            print(f"  Close: {sig['close']:.2f}")
            print(f"  Previous Top: {sig['prev_top']:.2f} (threshold: {sig['threshold_up']:.2f})")
            print(f"  Previous Bottom: {sig['prev_bottom']:.2f} (threshold: {sig['threshold_down']:.2f})")
        
        if len(signals) > 10:
            print(f"\n... and {len(signals) - 10} more signals")
    else:
        print("\nNo breakout signals found!")
        print("\nPossible reasons:")
        print("1. Buffer percentage too high (try reducing entry_buffer_pct)")
        print("2. Data doesn't have enough volatility")
        print("3. Lookback period too long for the data")
        
        # Show some statistics
        price_range = closes.max() - closes.min()
        price_volatility = (price_range / closes.mean()) * 100
        
        print(f"\nData statistics:")
        print(f"  Price range: {closes.min():.2f} - {closes.max():.2f}")
        print(f"  Volatility: {price_volatility:.2f}%")
        print(f"  Required move for breakout: {buffer_pct}%")
        
        # Check if any bar would have triggered with 0% buffer
        zero_buffer_signals = 0
        for i in range(lookback, len(closes)):
            prev_top, prev_bottom = previous_top_bottom(
                highs[:i][-lookback:], 
                lows[:i][-lookback:], 
                lookback
            )
            signal = breakout_signal(closes[i], prev_top, prev_bottom, 0.0)
            if signal != Direction.NONE:
                zero_buffer_signals += 1
        
        print(f"\n  Signals with 0% buffer: {zero_buffer_signals}")
    
    return signals


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python debug_breakout_signals.py <parquet_file> [lookback] [buffer_pct]")
        print("Example: python debug_breakout_signals.py data.parquet 20 0.2")
        sys.exit(1)
    
    file_path = sys.argv[1]
    lookback = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    buffer_pct = float(sys.argv[3]) if len(sys.argv) > 3 else 0.2
    
    analyze_breakout_signals(file_path, lookback, buffer_pct)


if __name__ == "__main__":
    main()