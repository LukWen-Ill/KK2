# Index: reflektion.md

Navigationsguide för `docs/reflektion.md` (1162 rader). Läs detta index först — gå till reflektion.md:rad N för detaljer.

---

## Struktur

| Sektion | Rad | Innehåll |
|---|---|---|
| **1. Säkerhetsaspekter** | 3 | API-nycklar, filuppladdning, autentisering, XSS, prompt injection |
| **2. Dataskydd (GDPR)** | 57 | In-memory-lagring, samtycke, rättslig grund |
| **3. AI-risker och ansvar** | 73 | SmolLM2-begränsningar, bias, testtäckning |
| **4. Designval** | 115 | Runnable-mönstret, `|`-operator, tekniskt hinder |
| **5. Nästa steg / Experiment 1–9** | 132 | Se experimentindex nedan |
| **Fine-tuning — samlade lärdomar** | 1073 | CPU vs GPU, klassificering vs generering, data-kvalitet, varför fine-tuning |
| **6. AI at the Edge** | 1123 | Tre-nivå-arkitektur, ONNX, ExecuTorch, RAG-indexering |
| **7. Åtgärdsbacklogg** | 1178 | P1/P2/P3-prioriterade brister |

---

## Experimentindex (sektion 5)

| Exp | Rad | Metod | Nyckelresultat |
|---|---|---|---|
| **Exp 1** — Batch inference | 205 | `pipeline([p1..pN], batch_size=N)` | SmolLM2: ~1.85× speedup, planar vid n=5. Supra-50M: 7.5× |
| **Exp 2** — Async parallella anrop | 227 | `ThreadPoolExecutor` + `asyncio.gather` | n≥10 sämre än sekventiellt (GIL). Batch alltid att föredra |
| **Scope-kartläggning** | 249 | Token-längd, batch, token-effektivitet | Optimal max_new_tokens=60, batch_size=2–3, ~50–75% utnyttjande |
| **Prompt-eval** | 264 | 3 prompt-varianter × 10 yttranden | Field accuracy 0% för alla — kapacitetsproblem, inte prompt |
| **Arbetsdelning** | 286 | Semantisk kod vs LLM per fält | De flesta fält löses deterministiskt; LLM bara för parafras |
| **Exp 3** — Slagtypsklassificering | 328 | SmolLM2-135M, 10 märkta yttranden | Parse-rate 30%, Accuracy 30% — nyckelordsmatching, inte klassificering |
| **Exp 4** — Engelska + Supra-50M | 352 | Språkbyte + ny modell | EN parse-rate 100% men accuracy 20% — domänkunskapsproblem |
| **Exp 5** — 4 modeller × 5 runs | 380 | Qwen3-0.6B, Qwen2.5-0.5B, SmolLM2, Supra | Accuracy-tak ~44% EN / ~26% SV oavsett storlek 50–600M |
| **Exp 6** — Semantisk klassificering | 451 | `SemanticShotClassifier`, nyckelordslistor | **90% accuracy, 0 ms** — slår alla LLM-modeller |
| **Exp 7** — Few-shot Qwen3-0.6B | 487 | 3 few-shot-exempel i prompt | +20 pp → 33% accuracy. Parafras-fall olösta |
| **Exp 8** — Fine-tuning LoRA | 550 | Qwen3-0.6B + LoRA, 160 träningsex | **65% val-accuracy** — +32 pp vs few-shot. Chip-klassen svårast |
| **Exp 9 Iter 1** — Engelsk prompt | 706 | Enkel prompt på engelska, max_new_tokens=80 | Koherens löst, relevans inte — 3/20 stats korrekt |
| **Exp 9 Iter 2** — 5-stegs CoT | 747 | GapAnalyzerStep (Python) + 4 LLM-steg | 80% nämner stats/drill, men kombinerar dem ej tillförlitligt |
| **Exp 9 Iter 3** — Drill-databas (Förslag A) | 790 | DrillStep ersatt med Python-lookup `_DRILL_DB` | −34% svarstid, äkta drillnamn. Flaskhals: AskAnswerComposerStep |
| **Exp 9 Iter 4** — Constrained decoding (Förslag B) | 819 | Outlines JSON-schema, `CoachingOutput` | **20/20 innehåller stats** (+85 pp). 9/20 stats+drill. Genombrott |
| **Exp 9 Iter 5** — Chat fine-tuning (ej genomförd) | 1011 | Pipeline-anpassad träningsdata, 800 ex | Träning avbruten: ~74h CPU. Basmodell eval: 11/20 stats+drill |

---

## Hybridarkitektur — tre nivåer (rad 1079)

| Nivå | Komponent | Latens | Molnberoende |
|---|---|---|---|
| 1 | Semantisk kod (`SemanticShotClassifier`) | ~0 ms | nej |
| 2 | SmolLM2-135M eller fine-tunad Qwen3-LoRA | 2–4 s | nej |
| 3 | API-modell post-runda (Haiku, GPT-4o-mini) | ~1 s | ja |

---

## Kända öppna brister (rad 1128)

**P1 (implementerat / testat):** LLM-exception→500 ✅, tomt modellsvar ✅, negativa CSV-värden ✅, radgräns CSV ✅

**P2:** CSV utan `fairway_hit` ⚠️, binärdata med .csv-extension ⚠️, prompt injection-skydd `question` ✅

**P3:** Rate limiting ⚠️, API-nyckelskydd ⚠️, GDPR-rensning ✅ (TTL 1 h + `DELETE /data`)
