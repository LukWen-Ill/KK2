# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                                  # installera beroenden
uv run uvicorn app.main:app --reload     # starta API (Swagger: http://localhost:8000/docs)
uv run pytest app/tests/ -v             # kör alla tester
uv run pytest app/tests/test_chain.py::test_prompt_builder_contains_question -v  # ett enskilt test
```

## Arkitektur

Applikationen är ett FastAPI-API med tre lager:

**`app/main.py`** — registrerar routes och inkluderar `MODEL_NAME`-konstanten (`HuggingFaceTB/SmolLM2-135M-Instruct`).

**`app/data.py`** — globalt in-memory-state. Nyckelgrupper:
- Dataset: `validate_and_store()` (CSV-validering + charsetdetektering), `store_dataset()`, `get_dataset()`, `clear_dataset()`, `get_stats()`
- Användarstatistik: `store_user_stats()`, `get_user_stats()`, `_compute_user_stats()` (GIR%, fairway%, snittrundor)
- PGA-benchmarks: `load_pga_benchmarks()`, `get_pga_benchmarks()` (laddar från CSV eller fallback)

Testerna nollställer state via `clear_dataset()` i en `autouse`-fixture.

**`app/chain/`** — Runnable-kedjan:
- `runnable.py`: abstrakt `Runnable[I, O]` med `__or__`-operator och `RunnableSequence` för kedjning
- `steps.py`: `PromptBuilder` (bygger golfcoach-prompt med användarstatistik vs PGA-benchmarks), `LLMRunner` (lazy-laddar SmolLM2), `ResponseParser` (strippar "Svar:"-markör) — varje steg har egna Pydantic-modeller för in- och utdata
- `pipeline.py`: `oraklet = PromptBuilder() | LLMRunner() | ResponseParser()`

**`app/schemas.py`** — Pydantic-modeller för API-gränssnittet: `UploadResponse`, `AskRequest`, `AskResponse`, `HealthResponse`.

## Domän

Appen är en golf-coaching-assistent. Användaren laddar upp en CSV med sina golfronder, och LLM-kedjan jämför statistiken mot PGA Tour-benchmarks och ger råd på svenska.

Förväntade CSV-kolumner: `date`, `course`, `score`, `fairways_hit`, `fairways_total`, `greens_in_regulation`, `putts`.

## Experiment och modelljämförelse

Två script jämför godtyckliga HuggingFace-modeller. Modellnamnet är första argument; utelämnas används SmolLM2 som default. Modeller utan chat-template hanteras automatiskt.

```bash
# Slagtypsklassificering — parse-rate och accuracy mot 10 märkta yttranden
uv run python run_shot_classifier_eval.py [MODEL] [--lang en]

# Latens och genomströmning — batch (Exp 1) och async (Exp 2)
uv run python run_experiments.py [MODEL]
```

Resultat dokumenteras i `reflektion.md` under respektive experiment.

## Miljövariabler

`.env` (får **inte** checkas in):
```
HF_API_KEY=...   # valfritt — används om du kör via HuggingFace Inference API
```
Laddas i `app/config.py` via `python-dotenv`.
