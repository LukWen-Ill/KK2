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
| Exp 5 — Fyra modeller, statistisk jämförelse | SmolLM2 / Supra-50M / Qwen2.5-0.5B / Qwen3-0.6B × 5 runs | Accuracy-tak ~44% (EN) / ~26% (SV) oavsett modellstorlek |
| Exp 6 — Semantisk klassificering | Nyckelordsbaserad klassificerare utan modell | 90% accuracy, 0 ms latens — slår samtliga LLM-baselines |
| Exp 7 — Few-shot prompting | Qwen3-0.6B med ett exempel per klass i prompten | 33% accuracy (+20 pp vs zero-shot) — promptdesign når ett tak |
| Exp 8 — Fine-tuning med LoRA | Qwen3-0.6B tränad på 160 svenska golfyttranden | **65% val-accuracy** — fördubbling mot few-shot; domänkunskap, inte promptdesign, är flaskhalsen |

Experimenten bekräftar att accuracy-taket för zero-/few-shot (~33%) bryts genom fine-tuning: en liten lokal modell med domänspecifik träning slår all prompting med stor marginal. Semantisk kod (Exp 6) täcker de enkla fallen bäst; fine-tunad LoRA (Exp 8) är starkast för genuint tvetydiga yttranden utan API-beroende.

Detaljerade resultat och analys finns i `reflektion.md` avsnitt 5.

## Arkitekturell slutsats

Tre nivåer, i stigande komplexitet:

**Nivå 1 — Semantisk kod** hanterar deterministiska fält via nyckelordslistor (`ruffen` → `fairway_hit: 0`, `tre puttar` → `putts: 3`). Täcker majoriteten av fallen utan modell.

**Nivå 2 — Fine-tunad LLM som fallback** används bara för genuint tvetydiga yttranden (`"studsade förbi"`, `"perfekt position"`). Qwen3-0.6B med LoRA-adapter tränad på svenska golfyttranden (`models/qwen3-golf-lora/`).

**Nivå 3 — API-modell post-runda** — en tyngre modell (Haiku, GPT-4o-mini) parsar hela rundan en gång när precision krävs. ~70 anrop per runda är hanterbart.

SmolLM2-135M är kvar för latens-kritiska moment under rundan; coaching-generering och fri-text-extraktion delegeras till större modeller.

## Appens arkitektur

FastAPI-app med tre lager:

- **`app/main.py`** — routes, `MODEL_NAME`-konstanten (`HuggingFaceTB/SmolLM2-135M-Instruct`)
- **`app/data.py`** — in-memory state: dataset, användarstatistik (GIR%, fairway%, snittrundor), PGA-benchmarks; TTL-rensning (1 h) och `DELETE /data` för GDPR
- **`app/schemas.py`** — API-modeller; `AskRequest.question` valideras mot prompt injection-mönster (max 500 tecken, regexblocklista → HTTP 422)
- **`app/chain/`** — Runnable-kedjan: `PromptBuilder | LLMRunner | ResponseParser`

Obligatoriska CSV-kolumner: `hole`, `par`, `strokes`, `gir`, `putts`. Valfria: `fairway_hit`, `date`, `course` (aktiverar filtrering per runda/bana). Max 1 000 rader per uppladdning (HTTP 413 om gränsen överskrids).

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

I Swagger: tryck `POST /data/upload/demo` (ingen filuppladdning behövs) och börja sedan filtrera. Data raderas explicit med `DELETE /data` (HTTP 204) eller automatiskt en timme efter uppladdning.

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
# Slagtypsklassificering — parse-rate och accuracy mot 10 märkta yttranden (Exp 3–5)
uv run python run_shot_classifier_eval.py [MODEL] [--lang en]

# Latens och genomströmning — batch (Exp 1) och async (Exp 2)
uv run python run_experiments.py [MODEL]

# Fine-tuning med LoRA (Exp 8) — generera data och träna adapter
uv run python generate_training_data.py   # skapar data/train.jsonl och data/val.jsonl
uv run python run_finetune.py             # tränar models/qwen3-golf-lora/ (~30 min CPU)
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
4. **Designval** — Runnable-mönstret, chat-format-insikten, experiment 1–8 och hybridarkitekturen

Rapporten avslutas med en prioriterad åtgärdsbacklogg.

## Noteringar

- Första anropet till `/ai/ask` laddar ner modellen (~300 MB). Efterföljande anrop använder cachad modell.
- Sätt `HF_API_KEY` i `.env` för HuggingFace Inference API istället för lokal körning.
