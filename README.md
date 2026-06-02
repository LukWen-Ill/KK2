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

Obligatoriska CSV-kolumner: `hole`, `par`, `strokes`, `gir`, `putts`. Valfria: `fairway_hit`, `date`, `course` (aktiverar filtrering per runda/bana).

## Demo-flöde

`demo_scorecard.csv` innehåller 6 rundor på tre banor (LAGK, Bro Hof, Arlandastad) och är designat för att visa tre tydliga mönster:

| Runda | Bana | Slag | GIR | Avg putts |
|---|---|---|---|---|
| 2024-04-01 | LAGK | 92 | 22% | 2.17 |
| 2024-04-20 | Arlandastad | 99 | 11% | 2.44 |
| 2024-05-08 | Bro Hof | 95 | 17% | 2.22 |
| 2024-05-22 | LAGK | 88 | 33% | 2.00 |
| 2024-06-05 | Arlandastad | 97 | 17% | 2.11 |
| 2024-06-19 | Bro Hof | 90 | 28% | 2.00 |

- **Förbättring över tid** — snitt 95→91 från första till sista halvlek
- **Puttingproblem** — 2.44→2.00, alltid över PGA-snittet 1.73
- **Banspecifikt** — LAGK bäst (snitt 90), Arlandastad sämst (snitt 98)

I Swagger: tryck `POST /data/upload/demo` (ingen filuppladdning behövs) och börja sedan filtrera.

### `/data/stats` — filtrering och svar

```
GET /data/stats                         → alla 108 hål
GET /data/stats?course=LAGK             → bara LAGK-rundorna
GET /data/stats?course=Arlandastad      → visar puttingproblemet tydligast
GET /data/stats?par=3                   → alla par-3-hål
GET /data/stats?date=2024-05-22         → enskild runda
GET /data/stats?par=3&course=Bro+Hof    → par-3-hål på Bro Hof
```

Svarsformat:
```json
{
  "meta": { "holes_count": 18, "filters": { "par": null, "course": "LAGK", ... } },
  "scoring_avg": { "player": 5.11, "pga_avg": 3.92, "gap": 1.19 },
  "gir_pct":     { "player": 27.8, "pga_avg": 65.0, "gap": -37.2 },
  "fairway_pct": { "player": 71.4, "pga_avg": 60.0, "gap": 11.4  },
  "avg_putts":   { "player": 2.08, "pga_avg": 1.73, "gap": 0.35  }
}
```

`gap` är alltid `player − pga_avg` — negativt GIR och positivt putts/scoring visar var man tappar mot PGA.

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
