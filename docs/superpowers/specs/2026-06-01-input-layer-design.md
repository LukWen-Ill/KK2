# KK2 Input Layer — Design Spec
*2026-06-01*

## Scope

Implement the data input pipeline for KK2 (Oraklet): `POST /data/upload` and `GET /data/stats`. Targets G + VG robustness requirements.

## Files changed

| File | Change |
|---|---|
| `app/data.py` | Add `validate_and_store()`, fix numpy serialization in `get_stats()` |
| `app/main.py` | Implement `upload()` and `stats()` endpoints |

## `POST /data/upload`

Accepts a CSV via `UploadFile`. Validation order (fail-fast):

1. Extension must be `.csv` → 400 "Only .csv files are accepted"
2. File size must be > 0 bytes → 400 "Uploaded file is empty"
3. File size must be ≤ 10 MB → 413 "File exceeds 10 MB limit"
4. Content must decode as UTF-8 or latin-1 → 400 "Could not decode file — try UTF-8 or latin-1"
5. Decoded content must parse as valid CSV → 400 "Could not parse file as CSV"
6. DataFrame must have at least 1 data row → 400 "CSV contains no data rows"

On success: stores dataset via `store_dataset()`, returns `UploadResponse(rows, columns, dtypes)`.

`dtypes` values are strings (e.g. `"float64"`, `"object"`).

## `GET /data/stats`

Returns `df.describe().to_dict()` as JSON.

- 404 "No dataset loaded" if `_dataset is None`
- numpy scalars (`np.float64`, `np.int64`, etc.) converted to native Python via `.item()` before returning — standard `json.JSONEncoder` does not handle numpy types

## `data.py` — `validate_and_store()`

```
def validate_and_store(contents: bytes, filename: str) -> pd.DataFrame
```

Raises `ValueError` with a human-readable message for each invalid case. `main.py` catches `ValueError` and re-raises as `HTTPException`.

Encoding strategy: try `utf-8`, fall back to `latin-1`. If both fail, raise.

## `get_stats()` fix

```python
def _to_native(v):
    return v.item() if hasattr(v, "item") else v

return {col: {k: _to_native(v) for k, v in stats.items()}
        for col, stats in df.describe().to_dict().items()}
```

## Out of scope

- `/ai/ask` endpoint (SmolLLM integration)
- Persistent storage (in-memory only, as per assignment)
- Authentication
