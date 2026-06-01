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

**`app/data.py`** — globalt in-memory-state för det uppladdade datasetet. Tre funktioner: `store_dataset`, `get_dataset` (kastar `ValueError` om inget finns), `get_stats`. Testerna nollställer state via `clear_dataset()` i en `autouse`-fixture.

**`app/chain/`** — Runnable-kedjan:
- `runnable.py`: abstrakt `Runnable[I, O]` med `__or__`-operator och `RunnableSequence` för kedjning
- `steps.py`: `PromptBuilder`, `LLMRunner` (lazy-laddar `transformers.pipeline`), `ResponseParser` — varje steg har egna Pydantic-modeller för in- och utdata
- `pipeline.py`: `oraklet = PromptBuilder() | LLMRunner() | ResponseParser()`

**`app/schemas.py`** — Pydantic-modeller för API-gränssnittet: `UploadResponse`, `AskRequest`, `AskResponse`, `HealthResponse`.

## Implementationsstatus

Flera delar är stubbar med `raise HTTPException(status_code=501)` och TODO-kommentarer:
- `POST /data/upload` — filvalidering, CSV-inläsning, `store_dataset()`
- `GET /data/stats` — anropa `get_stats()`, hantera `ValueError` → 404
- `POST /ai/ask` — bygg `PromptBuilderInput`, anropa `oraklet.invoke()`, returnera `AskResponse`
- `steps.py` — `PromptBuilder.invoke()` och `LLMRunner.invoke()` behöver fyllas i

## Miljövariabler

`.env` (får **inte** checkas in):
```
HF_API_KEY=...   # valfritt — används om du kör via HuggingFace Inference API
```
Laddas i `app/config.py` via `python-dotenv`.
