import pandas as pd
from datetime import datetime

df = pd.read_parquet('catalog-data-nautilus/_meta/instruments.parquet')
results = []
for i, row in df.iterrows():
    exp = int(row['expiry']) // 1_000_000_000
    exp_date = datetime.utcfromtimestamp(exp).strftime('%Y-%m-%d')
    if '2023-06-30' <= exp_date <= '2023-07-29':
        results.append(f'{row["instrument_id"]} (expires {exp_date})')

if results:
    print('Instruments in range 2023-06-30 to 2023-07-29:')
    print('\n'.join(results))
else:
    print('No instruments found in range') 