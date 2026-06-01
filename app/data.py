import io
import pandas as pd

_dataset: pd.DataFrame | None = None
MAX_SIZE = 10 * 1024 * 1024  # 10 MB


def validate_and_store(contents: bytes, filename: str) -> pd.DataFrame:
    if not filename.endswith(".csv"):
        raise ValueError("Only .csv files are accepted")
    if len(contents) == 0:
        raise ValueError("Uploaded file is empty")
    if len(contents) > MAX_SIZE:
        raise ValueError("File exceeds 10 MB limit")

    text: str | None = None
    for encoding in ("utf-8", "latin-1"):
        try:
            text = contents.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("Could not decode file — try UTF-8 or latin-1")

    try:
        df = pd.read_csv(io.StringIO(text))
    except Exception:
        raise ValueError("Could not parse file as CSV")

    if len(df) == 0:
        raise ValueError("CSV contains no data rows")

    store_dataset(df)
    return df


def store_dataset(df: pd.DataFrame) -> None:
    global _dataset
    _dataset = df


def get_dataset() -> pd.DataFrame:
    if _dataset is None:
        raise ValueError("No dataset loaded")
    return _dataset


def clear_dataset() -> None:
    global _dataset
    _dataset = None


def _to_native(v):
    return v.item() if hasattr(v, "item") else v


def get_stats() -> dict:
    df = get_dataset()
    return {
        col: {k: _to_native(v) for k, v in col_stats.items()}
        for col, col_stats in df.describe().to_dict().items()
    }
