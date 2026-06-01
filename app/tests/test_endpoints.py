import io
import json
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.chain.steps import LLMRunner, LLMRunnerOutput
import app.data as data

client = TestClient(app)

VALID_SCORECARD = (
    b"hole,par,strokes,fairway_hit,gir,putts\n"
    b"1,4,6,0,0,3\n2,3,4,0,0,2\n3,5,7,1,0,3\n4,4,5,0,0,2\n"
    b"5,4,5,1,1,2\n6,3,3,0,1,1\n7,5,6,1,1,2\n8,4,6,0,0,3\n9,4,5,0,0,2\n"
    b"10,4,5,1,1,2\n11,3,4,0,0,2\n12,5,7,0,0,3\n13,4,5,1,1,2\n14,4,6,0,0,3\n"
    b"15,3,3,0,1,1\n16,5,7,1,0,3\n17,4,6,0,0,2\n18,4,5,1,1,2\n"
)


@pytest.fixture(autouse=True)
def clear_data():
    data.clear_dataset()
    yield
    data.clear_dataset()


def _upload(csv_bytes, filename="scorecard.csv"):
    return client.post("/data/upload", files={"file": (filename, io.BytesIO(csv_bytes), "text/csv")})


# --- Health ---

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# --- Upload ---

def test_upload_valid_scorecard():
    r = _upload(VALID_SCORECARD)
    assert r.status_code == 200
    body = r.json()
    assert body["rows"] == 18
    assert "hole" in body["columns"]
    assert "gir" in body["columns"]


def test_upload_wrong_extension():
    r = _upload(VALID_SCORECARD, filename="scorecard.txt")
    assert r.status_code == 400
    assert "Only .csv" in r.json()["detail"]


def test_upload_empty_file():
    r = _upload(b"", filename="scorecard.csv")
    assert r.status_code == 400
    assert "empty" in r.json()["detail"].lower()


def test_upload_too_large():
    big = b"hole,par,strokes,gir,putts\n" + b"1,4,5,0,2\n" * (11 * 1024 * 1024 // 10)
    r = _upload(big)
    assert r.status_code == 413
    assert "10 MB" in r.json()["detail"]


def test_upload_missing_scorecard_columns():
    csv = b"city,temp_c\nMalmoe,8.3\nStockholm,6.1\n"
    r = _upload(csv)
    assert r.status_code == 400
    assert "Missing required scorecard columns" in r.json()["detail"]


def test_upload_no_data_rows():
    csv = b"hole,par,strokes,gir,putts\n"
    r = _upload(csv)
    assert r.status_code == 400
    assert "no data" in r.json()["detail"].lower()


def test_upload_latin1_encoding():
    csv_latin1 = "hole,par,strokes,gir,putts\n1,4,5,0,2\n".encode("latin-1")
    r = _upload(csv_latin1)
    assert r.status_code == 200
    assert r.json()["rows"] == 1


# --- Stats ---

def test_stats_no_dataset():
    r = client.get("/data/stats")
    assert r.status_code == 404


def test_stats_after_upload():
    _upload(VALID_SCORECARD)
    r = client.get("/data/stats")
    assert r.status_code == 200
    body = r.json()
    assert "strokes" in body
    assert "mean" in body["strokes"]
    json.dumps(body)  # raises if numpy types sneak through


# --- Ask ---

def test_ask_no_dataset():
    r = client.post("/ai/ask", json={"question": "Hur är min putting?"})
    assert r.status_code == 404


def test_ask_returns_answer():
    _upload(VALID_SCORECARD)
    mock_output = LLMRunnerOutput(raw_text="Svar: Fokusera på chip-shots för bättre GIR.")
    with patch.object(LLMRunner, "invoke", return_value=mock_output):
        r = client.post("/ai/ask", json={"question": "Hur kan jag förbättra mitt spel?"})
    assert r.status_code == 200
    body = r.json()
    assert body["question"] == "Hur kan jag förbättra mitt spel?"
    assert "answer" in body
    assert "model" in body
    assert len(body["answer"]) > 0


def test_ask_echoes_question_in_response():
    _upload(VALID_SCORECARD)
    mock_output = LLMRunnerOutput(raw_text="Svar: Träna mer putting.")
    with patch.object(LLMRunner, "invoke", return_value=mock_output):
        r = client.post("/ai/ask", json={"question": "Vad är min svagaste del?"})
    assert r.json()["question"] == "Vad är min svagaste del?"
