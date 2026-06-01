# KK2 – Oraklet

FastAPI-app som kombinerar Pandas-dataanalys med SmolLM2 via en typad Runnable-kedja.

## Installation

```bash
uv sync
```

## Starta

```bash
uv run uvicorn app.main:app --reload
```

Swagger UI: http://localhost:8000/docs

## Exempelanrop

```bash
# Hälsokontroll
curl http://localhost:8000/health

# Ladda upp dataset
curl -X POST http://localhost:8000/data/upload \
  -F "file=@data.csv"

# Statistik
curl http://localhost:8000/data/stats

# Ställ en fråga
curl -X POST http://localhost:8000/ai/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Vilken stad har högst medeltemperatur?"}'
```

## Tester

```bash
uv run pytest app/tests/ -v
```

## Noteringar

- Första anropet till `/ai/ask` laddar ner modellen (~300 MB). Efterföljande anrop använder cachad modell.
- Sätt `HF_API_KEY` i `.env` om du vill använda HuggingFace Inference API istället för lokal körning.
