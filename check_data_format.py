#!/usr/bin/env python3
"""
Script to check parquet data format and convert single price data to OHLC if needed.
This helps ensure your data has the proper format for breakout detection.
"""

import pandas as pd
from pathlib import Path
import sys


def check_parquet_format(file_path: Path):
    """Check the format of a parquet file and report its structure."""
    print(f"\nChecking: {file_path}")
    
    try:
        df = pd.read_parquet(file_path)
        print(f"  Rows: {len(df)}")
        print(f"  Columns: {list(df.columns)}")
        
        # Check for OHLC columns
        ohlc_cols = ['open', 'high', 'low', 'close']
        has_ohlc = all(col in df.columns for col in ohlc_cols)
        
        if has_ohlc:
            print("  ✓ Has OHLC data")
            # Show sample
            print("\n  Sample data:")
            print(df[['open', 'high', 'low', 'close']].head())
        else:
            print("  ✗ Missing OHLC data")
            if 'price' in df.columns or 'close' in df.columns:
                print("  → Has single price data only")
                
        return df, has_ohlc
        
    except Exception as e:
        print(f"  Error reading file: {e}")
        return None, False


def convert_to_ohlc(df: pd.DataFrame, price_col: str = None) -> pd.DataFrame:
    """Convert single price data to OHLC format with realistic variations."""
    if price_col is None:
        # Auto-detect price column
        if 'close' in df.columns:
            price_col = 'close'
        elif 'price' in df.columns:
            price_col = 'price'
        else:
            raise ValueError("No price column found")
    
    print(f"\nConverting {price_col} to OHLC format...")
    
    # Create a copy
    ohlc_df = df.copy()
    
    # Generate realistic OHLC from single price
    # This is a simple approximation - in reality you'd want actual OHLC data
    ohlc_df['close'] = df[price_col]
    
    # Calculate daily volatility estimate (simplified)
    returns = df[price_col].pct_change().fillna(0)
    daily_vol = returns.rolling(20).std().fillna(0.001) * 100  # Convert to percentage
    
    # Generate OHLC with realistic relationships
    for i in range(len(ohlc_df)):
        close = ohlc_df.loc[i, 'close']
        vol = max(daily_vol.iloc[i], 0.1)  # Minimum 0.1% volatility
        
        # Open: Close to previous close with small gap
        if i > 0:
            prev_close = ohlc_df.loc[i-1, 'close']
            gap = (close - prev_close) * 0.3  # 30% of the move happens in gap
            ohlc_df.loc[i, 'open'] = prev_close + gap
        else:
            ohlc_df.loc[i, 'open'] = close * 0.999
            
        # High and Low: Based on volatility
        range_size = close * vol / 100
        
        # Ensure high >= max(open, close) and low <= min(open, close)
        ohlc_df.loc[i, 'high'] = max(ohlc_df.loc[i, 'open'], close) + range_size * 0.5
        ohlc_df.loc[i, 'low'] = min(ohlc_df.loc[i, 'open'], close) - range_size * 0.5
    
    # Keep original columns except the price column if it's not 'close'
    if price_col != 'close' and price_col in ohlc_df.columns:
        ohlc_df = ohlc_df.drop(columns=[price_col])
    
    return ohlc_df


def save_ohlc_parquet(df: pd.DataFrame, output_path: Path):
    """Save DataFrame as parquet with OHLC data."""
    df.to_parquet(output_path, index=False)
    print(f"\nSaved OHLC data to: {output_path}")


def main():
    """Check and optionally convert parquet files to OHLC format."""
    if len(sys.argv) < 2:
        print("Usage: python check_data_format.py <parquet_file_or_directory> [--convert]")
        sys.exit(1)
    
    path = Path(sys.argv[1])
    convert = '--convert' in sys.argv
    
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = list(path.glob("**/*.parquet"))
    else:
        print(f"Path not found: {path}")
        sys.exit(1)
    
    print(f"Found {len(files)} parquet file(s)")
    
    needs_conversion = []
    
    for file_path in files:
        df, has_ohlc = check_parquet_format(file_path)
        
        if df is not None and not has_ohlc:
            needs_conversion.append((file_path, df))
    
    if needs_conversion:
        print(f"\n{len(needs_conversion)} file(s) need OHLC conversion")
        
        if convert:
            print("\nConverting files...")
            for file_path, df in needs_conversion:
                try:
                    ohlc_df = convert_to_ohlc(df)
                    
                    # Create backup
                    backup_path = file_path.with_suffix('.parquet.bak')
                    print(f"\nBacking up {file_path} to {backup_path}")
                    file_path.rename(backup_path)
                    
                    # Save converted file
                    save_ohlc_parquet(ohlc_df, file_path)
                    
                except Exception as e:
                    print(f"Error converting {file_path}: {e}")
        else:
            print("\nTo convert these files, run with --convert flag")
            print("Original files will be backed up with .bak extension")


if __name__ == "__main__":
    main()