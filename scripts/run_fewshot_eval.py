"""Experiment 7 — Few-shot prompting.

Vad är few-shot prompting?
  Istället för att bara beskriva uppgiften ger vi modellen konkreta
  EXEMPEL direkt i prompten. Modellen "ser" mönstret och kan generalisera
  bättre utan att ha tränat på golfdata specifikt.

  Zero-shot (nuvarande): "Yttrande: X → välj ett av tre"
  Few-shot (nytt):       "Yttrande: A → putt
                          Yttrande: B → chip
                          Yttrande: C → fullslag
                          Yttrande: X → välj ett av tre"

Experiment:
  Kör samma modell med zero-shot och few-shot, N_RUNS gånger vardera,
  mot samma 10 svenska yttranden som Exp 3–5.
  Jämför parse-rate och accuracy för att se om few-shot hjälper.

Notera:
  Exemplen i few-shot-prompten är valda så att de INTE innehåller
  nyckelord som finns i testyttrandena (drive, jarn, putt, chip etc.).
  Det tvingar modellen att generalisera, inte bara nyckelordsmatch.

Usage:
  uv run python run_fewshot_eval.py
  uv run python run_fewshot_eval.py Qwen/Qwen2.5-0.5B-Instruct
  uv run python run_fewshot_eval.py HuggingFaceTB/SmolLM2-135M-Instruct
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from statistics import mean, stdev
from transformers import pipeline

from app.chain.steps import ShotClassifierParser, LLMRunnerOutput

DEFAULT_MODEL = "Qwen/Qwen3-0.6B"
MODEL = next((a for a in sys.argv[1:] if not a.startswith("--")), DEFAULT_MODEL)
N_RUNS = 3

# Samma 10 yttranden som Exp 3–5 (ASCII-folded svenska utan åäö)
UTTERANCES = [
    ("Tre meter rakt mot halet, rullde in.",         "putt"),
    ("Kort putt, missade till hoger.",               "putt"),
    ("Rullning in fran kanten, precis.",             "putt"),
    ("Lagchip mot flaggan, stannade en meter bort.", "chip"),
    ("Chippade ur bunkern, landade pa greenen.",     "chip"),
    ("Sandwedge fran rough, studsade forbi.",        "chip"),
    ("Bra drive langt ner mitten.",                  "fullslag"),
    ("Tog ett jarnslag mot par 3-halet.",            "fullslag"),
    ("7-jarn mot greenen, lite for lang.",           "fullslag"),
    ("Slog en wedge, bollen landade nara flaggan.",  "fullslag"),
]

# Zero-shot: samma format som Exp 3–5 (baseline)
ZERO_SHOT = (
    'Yttrande: "{utterance}"\n'
    "Slagtyp - valj ett: putt / chip / fullslag\n"
    "Svar:"
)

# Few-shot: tre exempel följt av frågan.
# Exemplen är medvetet valda utan de nyckelord som finns i testsetet
# (ingen "drive", "jarn", "putt", "chip" etc.) — modellen tvingas
# förstå kontexten, inte kopiera ett nyckelord.
FEW_SHOT = (
    "Klassificera slagtypen. Tre exempel:\n\n"
    'Yttrande: "Nappa in en halvmeter, rak linje." → putt\n'
    'Yttrande: "Pitchade upp fran ruffen, landade pa greenen." → chip\n'
    'Yttrande: "Langt utslag fran tee, bra treff." → fullslag\n\n'
    'Yttrande: "{utterance}"\n'
    "Slagtyp - valj ett: putt / chip / fullslag\n"
    "Svar:"
)

PROMPTS = {
    "zero-shot": ZERO_SHOT,
    "few-shot":  FEW_SHOT,
}

# ---

print(f"Modell : {MODEL}")
print(f"Runs   : {N_RUNS} per prompt-variant\n")

_t = time.perf_counter()
llm = pipeline("text-generation", model=MODEL)
print(f"Laddad : {time.perf_counter() - _t:.2f}s\n")

parser = ShotClassifierParser()


def generate(prompt: str) -> str:
    content = prompt + ("\n/no_think" if "Qwen3" in MODEL else "")
    try:
        messages = [{"role": "user", "content": content}]
        result = llm(messages, max_new_tokens=60)
        raw = result[0]["generated_text"][-1]["content"]
    except ValueError:
        result = llm(content, max_new_tokens=60)
        raw = result[0]["generated_text"][len(content):].strip()
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()


def run_eval(prompt_template: str, label: str) -> dict:
    """Kör N_RUNS omgångar och returnerar aggregerad statistik."""
    all_runs = []
    for run_idx in range(N_RUNS):
        run_results = []
        for utterance, expected in UTTERANCES:
            raw = generate(prompt_template.format(utterance=utterance))
            predicted = parser.invoke(LLMRunnerOutput(raw_text=raw)).shot_type
            run_results.append({
                "utterance": utterance,
                "expected": expected,
                "predicted": predicted,
                "correct": predicted == expected,
            })
        parsed = sum(1 for r in run_results if r["predicted"] != "okänd")
        correct = sum(1 for r in run_results if r["correct"])
        all_runs.append({
            "run": run_idx + 1,
            "parse_rate": parsed / len(run_results),
            "accuracy": correct / len(run_results),
            "utterances": run_results,
        })

    parse_rates = [r["parse_rate"] for r in all_runs]
    accuracies  = [r["accuracy"]   for r in all_runs]
    return {
        "label": label,
        "runs": all_runs,
        "aggregate": {
            "parse_rate_mean": mean(parse_rates),
            "parse_rate_std":  stdev(parse_rates) if N_RUNS > 1 else 0.0,
            "accuracy_mean":   mean(accuracies),
            "accuracy_std":    stdev(accuracies) if N_RUNS > 1 else 0.0,
        },
    }


# Kör zero-shot och few-shot
results = {}
for label, template in PROMPTS.items():
    print(f"--- {label.upper()} ---")
    results[label] = run_eval(template, label)

    agg = results[label]["aggregate"]
    # Visa sista run detaljerat
    last = results[label]["runs"][-1]["utterances"]
    print(f"{'Yttrande':<52} {'Forv.':<10} {'Utfall':<10} OK")
    print("-" * 80)
    for r in last:
        print(f"{r['utterance']:<52} {r['expected']:<10} {r['predicted']:<10} {'OK' if r['correct'] else '--'}")
    print(f"\nParse-rate : {agg['parse_rate_mean']:.1%} +/- {agg['parse_rate_std']:.1%}")
    print(f"Accuracy   : {agg['accuracy_mean']:.1%} +/- {agg['accuracy_std']:.1%}\n")


# Jämförelsetabell
print("=== SAMMANFATTNING ===\n")
print(f"{'Metod':<12} {'Parse-rate':>12} {'Accuracy':>10}   Forandring")
print("-" * 55)

zs = results["zero-shot"]["aggregate"]
fs = results["few-shot"]["aggregate"]
delta_acc  = fs["accuracy_mean"]   - zs["accuracy_mean"]
delta_pr   = fs["parse_rate_mean"] - zs["parse_rate_mean"]

print(f"{'zero-shot':<12} {zs['parse_rate_mean']:>11.1%} {zs['accuracy_mean']:>10.1%}")
print(f"{'few-shot':<12} {fs['parse_rate_mean']:>11.1%} {fs['accuracy_mean']:>10.1%}   "
      f"acc {delta_acc:+.1%}, parse {delta_pr:+.1%}")

print(f"\n--- Exp 5-baselines (Qwen3-0.6B, 5 runs) ---")
print(f"{'Qwen3 sv (Exp5)':<16} {'100%':>8} {'24%':>8}   (referens)")
print(f"{'Qwen3 en (Exp5)':<16} {'100%':>8} {'44%':>8}   (referens)")

# Spara
os.makedirs("results", exist_ok=True)
model_slug = MODEL.replace("/", "-")
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
out = {
    "model": MODEL,
    "n_runs": N_RUNS,
    "date": datetime.now().isoformat(),
    "zero_shot": results["zero-shot"],
    "few_shot":  results["few-shot"],
}
path = f"results/fewshot_{model_slug}_{ts}.json"
with open(path, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"\nResultat sparat: {path}")
