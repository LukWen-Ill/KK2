# Plan: Experiment 9 — /ai/analyze med CoT-pipeline

## Nytt endpoint

```
GET /ai/analyze
Response:
{
  "good": "Fairway 58% (PGA: 60%) — nära PGA Tour-nivå.",
  "bad":  "GIR 15% (PGA: 65%) — störst förbättringspotential.",
  "tip":  "Träna approach-slag från 120–150 meter.",
  "model": "HuggingFaceTB/SmolLM2-135M-Instruct"
}
```

Kräver att ett dataset är uppladdat. Inget request-body.

---

## CoT-pipeline: 3 sekventiella LLM-anrop

```
AnalyzeState(user_stats, pga_benchmarks)
  → GoodStep(LLMRunner)   → state + good: str
  → BadStep(LLMRunner)    → state + bad: str
  → TipStep(LLMRunner)    → state + tip: str
```

Alla tre steg delar samma LLMRunner-instans (samma cachade modell, 3 anrop).
Varje steg har deterministisk fallback om LLM ekar prompten eller ger tomt svar.

### Steg 1 — GoodStep
Prompt: "Vad var bäst i spelarens runda? Nämn stat-värde och PGA Tour-snitt. Svar:"
Fallback: väljer stat med minst procentuellt gap mot PGA (deterministiskt).

### Steg 2 — BadStep
Prompt: "Vad var sämst? Nämn stat med störst gap mot PGA Tour-snittet. Svar:"
Fallback: väljer stat med störst procentuellt gap (deterministiskt).

### Steg 3 — TipStep
Prompt: "Spelaren har {bad}. Ge ett konkret träningstips. Svar:"
Fallback: fördefinierade råd per svaghet (GIR/Fairway/Putts/Scoring).

---

## Filer att skapa/ändra

| Fil | Åtgärd |
|---|---|
| `generate_chat_training_data.py` | Ny — ~130 träningsexempel för 3 CoT-steg |
| `run_chat_finetune.py` | Ny — fine-tunar SmolLM2-135M med LoRA |
| `app/schemas.py` | Lägg till `AnalyzeResponse(good, bad, tip, model)` |
| `app/chain/steps.py` | LLMRunner: PEFT-stöd + `AnalyzeState`, `GoodStep`, `BadStep`, `TipStep` |
| `app/chain/pipeline.py` | Bygg `analyse_kedjan`, auto-detect fine-tunad modell, `preload()` |
| `app/main.py` | `GET /ai/analyze`, dynamisk MODEL_NAME, `preload()` i lifespan |

---

## LLMRunner — förändringar

- `_pipeline` (class-var) → `_pipelines: dict` (nyckel = model-sträng, bakåtkompatibelt)
- Ny parameter `model_name_or_path: str = "HuggingFaceTB/SmolLM2-135M-Instruct"`
- `_load()`: detekterar lokal PEFT-adapter via `{path}/adapter_config.json`
  - Ja → PeftModel.from_pretrained(base_model, path)
  - Nej → befintligt beteende

---

## Fine-tuning (run_chat_finetune.py)

Modell: `HuggingFaceTB/SmolLM2-135M-Instruct`
LoRA: r=8, alpha=16, target_modules="all-linear", 3 epoker, batch_size=4, max_length=128
Output: `models/smollm2-chat-lora/`

Träningsdata — tre format (A/B/C):

**Format A — GoodStep (~45 ex)**
```
prompt:     "...stats...\nVad var bäst? Nämn stat-värde och PGA Tour-snitt. Svar:"
completion: "Fairway 58% (PGA: 60%) — nära PGA Tour-nivå."
```

**Format B — BadStep (~45 ex)**
```
prompt:     "...stats...\nVad var sämst? Nämn stat med störst gap. Svar:"
completion: "GIR 15% (PGA: 65%) — störst förbättringspotential."
```

**Format C — TipStep (~40 ex)**
```
prompt:     "Spelaren har GIR 15% (PGA: 65%) — störst förbättringspotential.\nGe ett konkret träningstips. Svar:"
completion: "Träna approach-slag från 120–150 meter och sikta mot grensenter."
```

Spelarprofiler: 5 nivåer (GIR 8→62%, FW 35→70%, Putts 1.85→2.9, Scoring 4.0→6.5)
Split: 80/20 → `data/chat_train.jsonl` (104 ex) + `data/chat_val.jsonl` (26 ex)

---

## pipeline.py

```python
CHAT_LORA_PATH = "models/smollm2-chat-lora"

def _make_runner() -> LLMRunner:
    lora = Path(CHAT_LORA_PATH)
    if lora.is_dir() and (lora / "adapter_config.json").exists():
        return LLMRunner(model_name_or_path=CHAT_LORA_PATH)
    return LLMRunner()

_runner = _make_runner()
oraklet = PromptBuilder() | _runner | ResponseParser()          # /ai/ask (oförändrad)
analyse_kedjan = GoodStep(_runner) | BadStep(_runner) | TipStep(_runner)  # /ai/analyze
slag_klassificerare = ShotClassifierPrompt() | LLMRunner() | ShotClassifierParser()

def preload() -> None:
    _runner._load()
```

---

## Körordning

```bash
uv run python generate_chat_training_data.py   # skapar data/chat_train.jsonl + chat_val.jsonl
uv run python run_chat_finetune.py              # skapar models/smollm2-chat-lora/
uv run uvicorn app.main:app --reload
curl -X POST http://localhost:8000/data/upload/demo
curl http://localhost:8000/ai/analyze
```

## Fallback

Om SmolLM2 inte räcker: byt modell i run_chat_finetune.py till `Qwen/Qwen3-0.6B`
och uppdatera CHAT_LORA_PATH. Inga arkitekturförändringar krävs.
