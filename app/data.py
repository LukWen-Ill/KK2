import io
import logging
import time
import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED_SCORECARD_COLS = {"hole", "par", "strokes", "gir", "putts"}

# Fallback PGA Tour averages if CSV is unavailable
_PGA_FALLBACK = {
    "gir_pct": 65.0,
    "fairway_pct": 60.0,
    "avg_putts": 1.73,
    "scoring_avg": 70.5,
}

_dataset: pd.DataFrame | None = None
_user_stats: dict | None = None
_pga_benchmarks: dict | None = None
_upload_time: float | None = None

MAX_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_ROWS = 1000               # ~55 rounds of 18 holes
DATA_TTL_SECONDS = 3600       # GDPR: auto-purge after 1 hour


class FileTooLargeError(ValueError):
    pass


class TooManyRowsError(ValueError):
    pass


# --- PGA Tour benchmarks ---

def load_pga_benchmarks() -> None:
    global _pga_benchmarks
    from app.config import PGA_DATA_PATH
    try:
        df = pd.read_csv(PGA_DATA_PATH)
        _pga_benchmarks = {
            "gir_pct": float(df["GIR_%"].mean()),
            "fairway_pct": float(df["FWY_%"].mean()),
            "scoring_avg": float(df["SCORING"].mean()),
            "avg_putts": _PGA_FALLBACK["avg_putts"],  # not in CSV
        }
        logger.info("PGA Tour benchmarks loaded: %s", _pga_benchmarks)
    except Exception as e:
        logger.warning("Could not load PGA data (%s), using fallback averages", e)
        _pga_benchmarks = _PGA_FALLBACK.copy()


def get_pga_benchmarks() -> dict:
    if _pga_benchmarks is None:
        return _PGA_FALLBACK.copy()
    return _pga_benchmarks


# --- Scorecard validation & stats ---

def _compute_user_stats(df: pd.DataFrame) -> dict:
    total_holes = len(df)
    gir_pct = df["gir"].sum() / total_holes * 100

    par4_plus = df[df["par"] >= 4]
    if "fairway_hit" in df.columns and len(par4_plus) > 0:
        fairway_pct = par4_plus["fairway_hit"].sum() / len(par4_plus) * 100
    else:
        fairway_pct = None

    avg_putts = df["putts"].mean()
    scoring_avg = df["strokes"].mean()

    return {
        "gir_pct": round(float(gir_pct), 1),
        "fairway_pct": round(float(fairway_pct), 1) if fairway_pct is not None else None,
        "avg_putts": round(float(avg_putts), 2),
        "scoring_avg": round(float(scoring_avg), 2),
    }


def validate_and_store(contents: bytes, filename: str) -> pd.DataFrame:
    if not filename.endswith(".csv"):
        raise ValueError("Only .csv files are accepted")
    if len(contents) == 0:
        raise ValueError("Uploaded file is empty")
    if len(contents) > MAX_SIZE:
        raise FileTooLargeError("File exceeds 10 MB limit")

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

    if len(df) > MAX_ROWS:
        raise TooManyRowsError(f"CSV exceeds {MAX_ROWS}-row limit")

    missing = REQUIRED_SCORECARD_COLS - set(df.columns)
    if missing:
        raise ValueError(f"Missing required scorecard columns: {sorted(missing)}")

    if (df[["par", "strokes", "gir", "putts"]] < 0).any().any():
        raise ValueError("Scorecard contains negative values")

    store_dataset(df)
    store_user_stats(_compute_user_stats(df))
    return df


# --- Dataset storage ---

def _check_ttl() -> None:
    global _dataset, _user_stats, _upload_time
    if _upload_time is not None and time.time() - _upload_time > DATA_TTL_SECONDS:
        logger.info("Dataset TTL expired — purging data")
        _dataset = None
        _user_stats = None
        _upload_time = None


def store_dataset(df: pd.DataFrame) -> None:
    global _dataset, _upload_time
    _dataset = df
    _upload_time = time.time()


def get_dataset() -> pd.DataFrame:
    _check_ttl()
    if _dataset is None:
        raise ValueError("No dataset loaded")
    return _dataset


def clear_dataset() -> None:
    global _dataset, _user_stats, _upload_time
    _dataset = None
    _user_stats = None
    _upload_time = None


# --- User stats storage ---

def store_user_stats(stats: dict) -> None:
    global _user_stats
    _user_stats = stats


def get_user_stats() -> dict:
    _check_ttl()
    if _user_stats is None:
        raise ValueError("No dataset loaded")
    return _user_stats


# --- Filtering ---

def get_filtered_dataset(
    par: int | None = None,
    hole: int | None = None,
    course: str | None = None,
    date: str | None = None,
) -> pd.DataFrame:
    df = get_dataset()
    if par is not None:
        df = df[df["par"] == par]
    if hole is not None:
        df = df[df["hole"] == hole]
    if course is not None and "course" in df.columns:
        df = df[df["course"] == course]
    if date is not None and "date" in df.columns:
        df = df[df["date"] == date]
    if len(df) == 0:
        raise ValueError("No holes match the given filters")
    return df


# --- Stats for /data/stats endpoint ---

def _to_native(v):
    return v.item() if hasattr(v, "item") else v


def get_stats() -> dict:
    df = get_dataset()
    return {
        col: {k: _to_native(v) for k, v in col_stats.items()}
        for col, col_stats in df.describe().to_dict().items()
    }
