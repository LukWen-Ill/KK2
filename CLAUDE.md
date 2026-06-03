# CLAUDE.md

## Kommandon

```bash
uv sync
uv run uvicorn app.main:app --reload          # Swagger: http://localhost:8000/docs
uv run pytest app/tests/ -v
uv run python scripts/run_shot_classifier_eval.py [MODEL] [--lang en]
uv run python scripts/run_experiments.py [MODEL]
uv run python scripts/run_index_eval.py       # eval-agent för reflektionsindex
```

## Arkitektur

FastAPI-API med tre lager:

- **`app/main.py`** — routes, `MODEL_NAME`-konstant
- **`app/data.py`** — in-memory state: dataset, användarstatistik, PGA-benchmarks
- **`app/chain/`** — Runnable-kedja (`PromptBuilder | LLMRunner | ResponseParser`); varje steg har egna Pydantic-modeller
- **`app/schemas.py`** — API-modeller (`UploadResponse`, `AskRequest`, `AskResponse`)

Tester nollställer state via `clear_dataset()` i en `autouse`-fixture.

## Domän

Golf-coaching-assistent. Användaren laddar upp en CSV med golfronder; LLM-kedjan jämför mot PGA Tour-benchmarks och ger råd.

Förväntade CSV-kolumner: `date`, `course`, `score`, `fairways_hit`, `fairways_total`, `greens_in_regulation`, `putts`.

## Reflektion

`docs/reflektion.md` är över 1100 rader — läs den aldrig i sin helhet. Flöde:

1. Läs `docs/reflektion_index.md` (~60 rader) — innehåller radnummer per sektion
2. `Read offset=N limit=80` för den sektion du behöver

**Skrivregel:** varje åtgärd, designval och experimentresultat ska följas av **varför** — inte bara vad som gjordes, utan mekanismen bakom.

## Miljövariabler

`.env` (checkas **inte** in):
```
HF_API_KEY=...   # valfritt — HuggingFace Inference API
```
