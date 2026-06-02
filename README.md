# KK2 – Oraklet

KK2-kursarbete som empiriskt undersöker var LLMs tillför värde i ett golf-statistiksystem. FastAPI-appen är kontexten; experimenten och reflektionen är innehållet.

## Bakgrund

Projektet startade som en coaching-assistent: spelaren laddar upp en CSV med golfronder, SmolLM2-135M jämför statistiken mot PGA Tour-benchmarks och ger råd på svenska. Tidigt stod det klart att modellen inte klarar meningsfull fri generering — den ekar prompten, loopar och hallucinerar kolumnnamn.

Det ledde till en mer intressant fråga: *vad ska en 135M-modell faktiskt användas till?*

## Det meningsfulla LLM-användningsområdet

Fri naturlig text → strukturerad slagstatistik är rätt uppgift för LLM — den kräver inferens som inte går att lösa med regler:

```
"Lågchip mot flaggan, stannade en meter bort."
→ { club: "wedge", gir: 0 }

"Bra drive ner höger sida, landade i ruffen."
→ { club: "driver", fairway_hit: 0, lie: "rough" }
```

Spelaren talar in ett fritt hålmemo; backend aggregerar slag till `{ strokes, gir, putts, fairway_hit }` — samma schemastruktur som CSV-uppladdningen, men genererad ur fri text.

## Experiment

| Experiment | Vad testades | Slutsats |
|---|---|---|
| Exp 1 — Batch inference | Throughput vid batch_size 5/10/15 | ~1.85x speedup, planar vid n=5; optimal batch_size=2–3 |
| Exp 2 — Async parallellt | ThreadPoolExecutor + asyncio.gather | Sämre än sekventiellt vid n≥10 pga GIL-serialisering |
| Exp 3 — Slagtypsklassificering (SV) | SmolLM2 mot 10 märkta svenska yttranden | 30% accuracy — nyckelordsmatching, inte klassificering |
| Exp 4 — Engelska + Supra-50M | Språk som förklaring; okänd modell som kontroll | 100% parse-rate, 20% accuracy — kunskapsproblem, inte språkproblem |

Experiment 3 och 4 testade om SmolLM2 klarar slagtypsklassificering (putt / chip / fullslag). Accuracy stannade på 20–30% oavsett språk och modell — båda modellerna saknar golf-domänkunskap.

Detaljerade resultat och analys finns i `reflektion.md` avsnitt 5.

## Arkitekturell slutsats

Tre nivåer, i stigande komplexitet:

**Nivå 1 — Semantisk kod** hanterar deterministiska fält via nyckelordslistor (`ruffen` → `fairway_hit: 0`, `tre puttar` → `putts: 3`). Täcker majoriteten av fallen utan modell.

**Nivå 2 — LLM som fallback** används bara för genuint tvetydiga yttranden (`"studsade förbi"`, `"perfekt position"`). Few-shot prompt med ett exempel per klass.

**Nivå 3 — API-modell post-runda** — en tyngre modell (Haiku, GPT-4o-mini) parsar hela rundan en gång när precision krävs. ~70 anrop per runda är hanterbart.

SmolLM2-135M är kvar för latens-kritiska moment under rundan; coaching-generering och fri-text-extraktion delegeras till större modeller.

## Appens arkitektur

FastAPI-app med tre lager:

- **`app/main.py`** — routes, `MODEL_NAME`-konstanten (`HuggingFaceTB/SmolLM2-135M-Instruct`)
- **`app/data.py`** — in-memory state: dataset, användarstatistik (GIR%, fairway%, snittrundor), PGA-benchmarks
- **`app/chain/`** — Runnable-kedjan: `PromptBuilder | LLMRunner | ResponseParser`

Förväntade CSV-kolumner: `date`, `course`, `score`, `fairways_hit`, `fairways_total`, `greens_in_regulation`, `putts`.

## Installation och kommandon

```bash
uv sync                                  # installera beroenden
uv run uvicorn app.main:app --reload     # starta API (Swagger: http://localhost:8000/docs)
uv run pytest app/tests/ -v             # kör alla tester
```

```bash
# Slagtypsklassificering — parse-rate och accuracy mot 10 märkta yttranden (Exp 3–4)
uv run python run_shot_classifier_eval.py [MODEL] [--lang en]

# Latens och genomströmning — batch (Exp 1) och async (Exp 2)
uv run python run_experiments.py [MODEL]
```

## Notebooks

| Notebook | Syfte |
|---|---|
| `notebooks/explore_smollm.ipynb` | Interaktiv testmiljö för pipeline-kedjan. Kör stegen ett i taget med syntetisk scorecard, testar olika frågor och temperatures. |
| `notebooks/prompt_eval.ipynb` | Jämför tre prompt-varianter (`minimal`, `schema`, `context`) på parse-rate, field-accuracy och hallucination-rate mot 10 märkta yttranden. |
| `notebooks/llm_latency_benchmark.ipynb` | Mäter latens mot max_new_tokens samt batch- och async-genomströmning (Exp 1–2). |

## Reflektionsrapport

`reflektion.md` täcker fyra områden:

1. **Säkerhetsaspekter** — API-nycklar, filuppladdningsrisker, prompt injection, autentisering, XSS
2. **Dataskydd (GDPR)** — in-memory-lagring, rättslig grund, åtkomstlogg, externa API:er
3. **AI-risker och ansvar** — SmolLM2:s begränsningar, bias, testtäckningsluckor
4. **Designval** — Runnable-mönstret, chat-format-insikten, experiment 1–4 och hybridarkitekturen

Rapporten avslutas med en prioriterad åtgärdsbacklogg.

## Noteringar

- Första anropet till `/ai/ask` laddar ner modellen (~300 MB). Efterföljande anrop använder cachad modell.
- Sätt `HF_API_KEY` i `.env` för HuggingFace Inference API istället för lokal körning.
