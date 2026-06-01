# KK2 Input Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `POST /data/upload` (VG-robust) and `GET /data/stats` (with numpy-fix) in KK2.

**Architecture:** All validation logic lives in `data.py` as `validate_and_store()` — `main.py` only catches `ValueError` and converts to `HTTPException`. This keeps routes thin and the core logic independently testable.

**Tech Stack:** FastAPI, Pandas, pytest, FastAPI TestClient

---

## File map

| File | Action |
|---|---|
| `app/data.py` | Add `validate_and_store()`, fix `get_stats()` |
| `app/main.py` | Implement `upload()` and `stats()` |
| `app/tests/test_endpoints.py` | Add VG edge-case tests and stats test |

---

### Task 1: Happy-path upload — `validate_and_store()` + endpoint

**Files:**
- Modify: `app/data.py`
- Modify: `app/main.py`
- Test: `app/tests/test_endpoints.py`

- [ ] **Step 1: Run the existing upload test to confirm it currently fails**

```
uv run pytest app/tests/test_endpoints.py::test_upload_valid_csv -v
```
Expected: FAIL — `501 Not Implemented`

- [ ] **Step 2: Add `validate_and_store()` to `app/data.py`**

Replace the full content of `app/data.py` with:

```python
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
```

- [ ] **Step 3: Implement `upload()` in `app/main.py`**

Replace the `upload` function:

```python
@app.post("/data/upload", response_model=UploadResponse)
async def upload(file: UploadFile) -> UploadResponse:
    logger.info(f"Upload request: {file.filename}")
    contents = await file.read()
    try:
        df = data.validate_and_store(contents, file.filename or "")
    except ValueError as e:
        status_code = 413 if "10 MB" in str(e) else 400
        raise HTTPException(status_code=status_code, detail=str(e))
    return UploadResponse(
        rows=len(df),
        columns=list(df.columns),
        dtypes={col: str(dtype) for col, dtype in df.dtypes.items()},
    )
```

- [ ] **Step 4: Run the test — should now pass**

```
uv run pytest app/tests/test_endpoints.py::test_upload_valid_csv -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/data.py app/main.py
git commit -m "feat: implement validate_and_store and upload endpoint (happy path)"
```

---

### Task 2: VG validation — all error cases

**Files:**
- Test: `app/tests/test_endpoints.py`
- No new implementation needed — `validate_and_store()` already handles all cases

- [ ] **Step 1: Run existing extension test to confirm it now passes (Task 1 implemented this)**

```
uv run pytest app/tests/test_endpoints.py::test_upload_wrong_extension -v
```
Expected: PASS — `400 Bad Request`

- [ ] **Step 2: Add VG edge-case tests to `app/tests/test_endpoints.py`**

Append after `test_upload_wrong_extension`:

```python
def test_upload_empty_file():
    r = client.post("/data/upload", files={"file": ("data.csv", io.BytesIO(b""), "text/csv")})
    assert r.status_code == 400
    assert "empty" in r.json()["detail"].lower()


def test_upload_too_large():
    big = b"a,b\n" + b"1,2\n" * (11 * 1024 * 1024 // 4)  # ~11 MB
    r = client.post("/data/upload", files={"file": ("data.csv", io.BytesIO(big), "text/csv")})
    assert r.status_code == 413
    assert "10 MB" in r.json()["detail"]


def test_upload_no_data_rows():
    csv = b"city,temp_c\n"  # header only
    r = client.post("/data/upload", files={"file": ("data.csv", io.BytesIO(csv), "text/csv")})
    assert r.status_code == 400
    assert "no data" in r.json()["detail"].lower()


def test_upload_latin1_csv():
    # Simulates pgatour_cleaned.csv which is latin-1 encoded (contains e.g. Björn Borg)
    csv_latin1 = "name,score\nBj\xf6rn,72\n".encode("latin-1")
    r = client.post("/data/upload", files={"file": ("data.csv", io.BytesIO(csv_latin1), "text/csv")})
    assert r.status_code == 200
    assert r.json()["rows"] == 1
```

- [ ] **Step 3: Run all new tests — should pass**

```
uv run pytest app/tests/test_endpoints.py -v
```
Expected: All PASS (test_upload_wrong_extension, test_upload_empty_file, test_upload_too_large, test_upload_no_data_rows, test_upload_latin1_csv)

- [ ] **Step 4: Commit**

```bash
git add app/tests/test_endpoints.py
git commit -m "test: add VG edge-case tests for upload validation"
```

---

### Task 3: `GET /data/stats` — numpy fix + endpoint

**Files:**
- Modify: `app/main.py`
- Test: `app/tests/test_endpoints.py`

- [ ] **Step 1: Run existing stats test to confirm it fails**

```
uv run pytest app/tests/test_endpoints.py::test_stats_no_dataset -v
```
Expected: FAIL — `501 Not Implemented`

- [ ] **Step 2: Add stats tests to `app/tests/test_endpoints.py`**

Append after existing stats test:

```python
def test_stats_after_upload():
    csv = b"city,temp_c\nMalmoe,8.3\nStockholm,6.1\n"
    client.post("/data/upload", files={"file": ("data.csv", io.BytesIO(csv), "text/csv")})
    r = client.get("/data/stats")
    assert r.status_code == 200
    body = r.json()
    assert "temp_c" in body
    assert "mean" in body["temp_c"]
    # Verify all values are JSON-native (no numpy types)
    import json
    json.dumps(body)  # raises TypeError if numpy types sneak through
```

- [ ] **Step 3: Run the new test — should fail**

```
uv run pytest app/tests/test_endpoints.py::test_stats_after_upload -v
```
Expected: FAIL — `501 Not Implemented`

- [ ] **Step 4: Implement `stats()` in `app/main.py`**

Replace the `stats` function:

```python
@app.get("/data/stats")
def stats() -> dict:
    logger.info("Stats request")
    try:
        return data.get_stats()
    except ValueError:
        raise HTTPException(status_code=404, detail="No dataset loaded")
```

- [ ] **Step 5: Run all stats tests — should pass**

```
uv run pytest app/tests/test_endpoints.py::test_stats_no_dataset app/tests/test_endpoints.py::test_stats_after_upload -v
```
Expected: Both PASS

- [ ] **Step 6: Run the full test suite**

```
uv run pytest app/tests/ -v
```
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add app/main.py app/tests/test_endpoints.py
git commit -m "feat: implement /data/stats with numpy serialization fix"
```
