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

# Ladda upp dataset (CSV med kolumner: date, course, score, fairways_hit, fairways_total, greens_in_regulation, putts)
curl -X POST http://localhost:8000/data/upload \
  -F "file=@data.csv"

# Statistik
curl http://localhost:8000/data/stats

# Ställ en fråga
curl -X POST http://localhost:8000/ai/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hur kan jag förbättra mitt GIR-värde?"}'
```

## Tester

```bash
uv run pytest app/tests/ -v
```

## Reflektionsrapport

`reflektion.md` är en del av kursuppgiften KK2 och täcker fyra områden:

1. **Säkerhetsaspekter** — hantering av API-nycklar, filuppladdningsrisker, prompt injection, autentisering och LLM-output.
2. **Dataskydd (GDPR)** — konsekvenser av att lagra potentiellt personuppgiftsrika dataset i minnet.
3. **AI-risker och ansvar** — begränsningar hos SmolLM2, bias och hur kedjan testas för tillförlitlighet.
4. **Designval** — motivering till Runnable-mönstret och beskrivning av det största tekniska hindret.

Rapporten avslutas med en prioriterad åtgärdsbacklogg över kända brister.

## Noteringar

- Första anropet till `/ai/ask` laddar ner modellen (~300 MB). Efterföljande anrop använder cachad modell.
- Sätt `HF_API_KEY` i `.env` om du vill använda HuggingFace Inference API istället för lokal körning.
