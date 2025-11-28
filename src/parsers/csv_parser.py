import io, pandas as pd

def parse_csv_from_bytes(b: bytes):
    df = pd.read_csv(io.BytesIO(b))
    if 'value' in df.columns:
        s = df['value'].sum()
        try:
            return float(s)
        except:
            return s
    return int(len(df))
