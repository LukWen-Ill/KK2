import io
import json
import pytest
from fastapi.testclient import TestClient
from app.main import app
import app.data as data

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_data():
    data.clear_dataset()
    yield
    data.clear_dataset()


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_upload_valid_csv():
    csv = b"city,temp_c\nMalmoe,8.3\nStockholm,6.1\n"
    r = client.post("/data/upload", files={"file": ("data.csv", io.BytesIO(csv), "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["rows"] == 2
    assert "city" in body["columns"]


def test_upload_wrong_extension():
    r = client.post("/data/upload", files={"file": ("data.txt", io.BytesIO(b"a,b\n1,2"), "text/plain")})
    assert r.status_code == 400
    assert "Only .csv" in r.json()["detail"]


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


def test_stats_no_dataset():
    r = client.get("/data/stats")
    assert r.status_code == 404


def test_stats_after_upload():
    csv = b"city,temp_c\nMalmoe,8.3\nStockholm,6.1\n"
    client.post("/data/upload", files={"file": ("data.csv", io.BytesIO(csv), "text/csv")})
    r = client.get("/data/stats")
    assert r.status_code == 200
    body = r.json()
    assert "temp_c" in body
    assert "mean" in body["temp_c"]
    # Verify all values are JSON-native (no numpy types)
    json.dumps(body)  # raises TypeError if numpy types sneak through


def test_ask_no_dataset():
    r = client.post("/ai/ask", json={"question": "Vad är medelvärdet?"})
    assert r.status_code == 400
