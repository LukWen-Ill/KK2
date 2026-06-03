# KK2 – Oraklet

> En golf-coaching-assistent som lärde mig mer om vad små språkmodeller *inte* kan göra — än vad de kan.

## Ursprunget

Projektet startade enkelt: spelaren laddar upp en CSV med golfronder, en liten lokal LLM jämför statistiken mot PGA Tour-benchmarks och ger råd på svenska. SmolLM2-135M, 300 MB, kör lokalt, inget API-beroende.

Det fungerade inte.

Modellen ekade prompten. Den loopade. Den hallucinerade kolumnnamn. Den svarade på engelska när man frågade på svenska. Och viktigast av allt — den gav råd som inte var meningsfulla, oavsett hur prompten formulerades.

Det ledde till en mer intressant fråga: *vad ska en 135M-modell faktiskt användas till?*

## Svaret (spoiler)

Fri naturlig text → strukturerade golfdata. Det är rätt uppgift.

```
"Lågchip mot flaggan, stannade en meter bort."  →  { gir: 0, putts: 1 }
"Bra drive ner höger sida, landade i ruffen."   →  { fairway_hit: 0, lie: "rough" }
```

En spelare talar in ett fritt hålmemo — backend aggregerar det till `{ strokes, gir, putts, fairway_hit }`. Samma schema som CSV-uppladdningen, men genererat ur fri text. Det kräver inferens. Det går inte att lösa med regler. Och det är *precis* vad en liten modell kan bidra med när den tränas rätt.

## Nio experiment för att komma dit

| Exp | Vad testades | Slutsats |
|-----|-------------|---------|
| 1 — Batch inference | Throughput vid batch_size 5/10/15 | ~1.85× speedup, planar vid n=5; optimal batch=2–3 |
| 2 — Async parallellt | ThreadPoolExecutor + asyncio.gather | Sämre än sekventiellt vid n≥10 pga GIL-serialisering |
| 3 — Slagtypsklassificering (SV) | SmolLM2 mot 10 märkta svenska yttranden | 30% accuracy — nyckelordsmatching, inte klassificering |
| 4 — Engelska + Supra-50M | Språk som förklaring; okänd modell som kontroll | 100% parse-rate, 20% accuracy — kunskapsproblem, inte språkproblem |
| 5 — Fyra modeller, statistisk jämförelse | SmolLM2 / Supra-50M / Qwen2.5-0.5B / Qwen3-0.6B × 5 runs | Accuracy-tak ~44% (EN) / ~26% (SV) oavsett modellstorlek |
| 6 — Semantisk klassificering | Nyckelordsbaserad klassificerare utan modell | **90% accuracy, 0 ms latens** — slår samtliga LLM-baselines |
| 7 — Few-shot prompting | Qwen3-0.6B med ett exempel per klass | 33% accuracy (+20 pp vs zero-shot) — ett tak finns |
| 8 — Fine-tuning med LoRA | Qwen3-0.6B tränad på 160 svenska golfyttranden | **65% val-accuracy** — fördubbling mot few-shot |
| 9 — Constrained decoding + CoT | Outlines-biblioteket för garanterad JSON-output | Strukturerad output oavsett modell; CoT-kedja med 5 steg |

Poängen är inte att tabellen ser imponerande ut. Poängen är att accuracy-taket för all prompting (~33%) bara bröts när modellen fick domänspecifik träningsdata — inte när prompten förbättrades.

## Arkitekturens slutsats: tre nivåer

```
Yttrande från spelare
        ↓
┌─────────────────────────────────────────────────────┐
│  Nivå 1: Semantisk kod                              │
│  "ruffen" → fairway_hit: 0  |  "tre puttar" → 3    │
│  Täcker majoriteten. Noll latens. Inga API-anrop.   │
└───────────────────────┬─────────────────────────────┘
                        │ Genuint tvetydigt?
                        ↓
┌─────────────────────────────────────────────────────┐
│  Nivå 2: Fine-tunad LoRA (Qwen3-0.6B)              │
│  models/qwen3-golf-lora/ — tränad på svenska        │
│  golfyttranden. Kör lokalt, ingen nätanslutning.    │
└───────────────────────┬─────────────────────────────┘
                        │ Post-runda, precision krävs?
                        ↓
┌─────────────────────────────────────────────────────┐
│  Nivå 3: API-modell (Haiku / GPT-4o-mini)          │
│  ~70 anrop per runda är hanterbart för analys.      │
└─────────────────────────────────────────────────────┘
```

SmolLM2-135M är kvar för latens-kritiska moment *under* rundan. Coaching och fri-text-extraktion delegeras uppåt.

## Appen

FastAPI med in-memory state, Pydantic-validering och en Runnable-kedja (`steg1 | steg2 | steg3`) som grund.

**Endpoints:**

| Metod | Path | Vad |
|-------|------|-----|
| GET | `/health` | Hälsokontroll |
| POST | `/data/upload` | Ladda CSV (max 10 MB, 1 000 rader) |
| POST | `/data/upload/demo` | Ladda demodata |
| DELETE | `/data` | Radera dataset (GDPR) |
| GET | `/data/stats` | Statistik med filter (par/hål/bana/datum) |
| GET | `/ai/analyze` | LLM analyserar bra/svaga sidor |
| POST | `/ai/ask` | Fri fråga — chain-of-thought med 5 steg |

**CSV-kolumner:** `hole`, `par`, `strokes`, `gir`, `putts` krävs. `fairway_hit`, `date`, `course` är valfria (aktiverar filtrering).

**Säkerhet:** `AskRequest.question` valideras mot prompt injection-mönster (max 500 tecken, regexblocklista). Dataset auto-raderas efter 1 timme.

## Prova det direkt

`demo_scorecard.csv` innehåller 6 rundor på tre banor — designat för att visa tre tydliga mönster:

| Datum | Bana | Slag | GIR | Avg putts |
|-------|------|------|-----|-----------|
| 2024-04-01 | LAGK | 92 | 22% | 2.17 |
| 2024-04-20 | Arlandastad | 99 | 11% | 2.44 |
| 2024-05-08 | Bro Hof | 95 | 17% | 2.22 |
| 2024-05-22 | LAGK | 88 | 33% | 2.00 |
| 2024-06-05 | Arlandastad | 97 | 17% | 2.11 |
| 2024-06-19 | Bro Hof | 90 | 28% | 2.00 |

Förbättring över tid, ett kroniskt puttingproblem (2.44 → 2.00, alltid över PGA-snittet 1.73), och tydlig banspecificitet (LAGK snitt 90, Arlandastad snitt 98).

I Swagger: `POST /data/upload/demo` → filtrera med `/data/stats` → fråga `/ai/ask`.

```
GET /data/stats                     → alla 108 hål
GET /data/stats?course=Arlandastad  → puttingproblemet tydligast
GET /data/stats?par=3               → alla par-3-hål
GET /data/stats?date=2024-05-22     → enskild runda
```

## Installation

```bash
uv sync
uv run uvicorn app.main:app --reload   # Swagger: http://localhost:8000/docs
uv run pytest app/tests/ -v
```

```bash
# Reproducera experimenten
uv run python scripts/run_shot_classifier_eval.py [MODEL] [--lang en]  # Exp 3–5
uv run python scripts/run_experiments.py [MODEL]                        # Exp 1–2
uv run python scripts/generate_training_data.py                         # data för Exp 8
uv run python scripts/run_finetune.py                                   # träna LoRA (~30 min CPU)
```

> Första anropet till `/ai/ask` laddar ner modellen (~300 MB). Sätt `HF_API_KEY` i `.env` för HuggingFace Inference API istället för lokal körning.

## Notebooks

| Notebook | Syfte |
|----------|-------|
| `explore_smollm.ipynb` | Interaktiv testmiljö för pipeline-kedjan |
| `prompt_eval.ipynb` | Jämför promptvarianter på parse-rate och hallucination-rate |
| `llm_latency_benchmark.ipynb` | Latens och batch-genomströmning (Exp 1–2) |

## Reflektionsrapport

`docs/reflektion.md` (1 162 rader) — läs via `docs/reflektion_index.md` för att navigera till rätt avsnitt. Täcker säkerhet, GDPR, AI-risker, designval och samtliga experiment med mekanismförklaringar.
