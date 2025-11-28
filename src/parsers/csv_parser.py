import io
import pandas as pd

def sum_column_from_csv_bytes(csv_bytes, column_name=None):
    df = pd.read_csv(io.BytesIO(csv_bytes))
    if column_name:
        if column_name in df.columns:
            return float(df[column_name].sum())
        raise KeyError(f"Column {column_name} not found")
    # fallback: sum numeric columns
    numeric = df.select_dtypes(include='number')
    if numeric.shape[1] == 1:
        return float(numeric.iloc[:,0].sum())
    # if multiple numeric columns, return dict
    return {col: float(df[col].sum()) for col in numeric.columns}

