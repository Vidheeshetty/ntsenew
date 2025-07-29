import glob
import pyarrow.parquet as pq
import pandas as pd
from datetime import datetime

# Find the parquet file for the instrument
files = glob.glob('catalog-data-nautilus/data/bar/NIFTY20230727.FUT.NSE-1-DAY-LAST-EXTERNAL/*.parquet')
if not files:
    print('No data found for NIFTY20230727.FUT.NSE')
    exit(0)

# Read the first parquet file
tbl = pq.read_table(files[0])
df = tbl.to_pandas()

# Try to find a date column
if 'ts_event' in df.columns:
    # ts_event is in nanoseconds since epoch
    first_ns = int(df.iloc[0]['ts_event'])
    first_date = datetime.utcfromtimestamp(first_ns // 1_000_000_000).strftime('%Y-%m-%d')
    print('First date in data:', first_date)
else:
    print('First row:', df.iloc[0]) 