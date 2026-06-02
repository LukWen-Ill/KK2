"""Experiment 7 — Few-shot prompting vs zero-shot for Qwen3-0.6B.

Testar om det racker att ge modellen tre konkreta exempel (ett per klass)
direkt i prompten for att forbattra accuracy pa svenska golfyttranden.

Usage:
  uv run python run_fewshot_eval.py
  uv run python run_fewshot_eval.py --runs 5
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

MODEL = "Qwen/Qwen3-0.6B"

N_RUNS = 3
for i, arg in enumerate(sys.argv[1:]):
    if arg == "--runs" and i + 1 < len(sys.argv) - 1:
        N_RUNS = int(sys.argv[i + 2])

# Samma 10 yttranden som Exp 3-5
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

# Zero-shot: bara uppgiftsbeskrivning, inga exempel
PROMPT_ZERO = (
    'Yttrande: "{utterance}"\n'
    "Slagtyp - valj ett: putt / chip / fullslag\n"
    "Svar:"
)

# Few-shot: tre konkreta exempel (ett per klass) foljt av fragan
# Exemplen ar valda for att:
#   - vara enkla och tydliga (inte fran testdatan)
#   - tacka alla tre klasser
#   - anvanda samma terminologi som testyttrandena
PROMPT_FEW = (
    'Yttrande: "Kort putt, rullde in." -> putt\n'
    'Yttrande: "Lagchip mot greenen, stannade nara." -> chip\n'
    'Yttrande: "Drive langt ner mitten." -> fullslag\n'
    'Yttrande: "{utterance}"\n'
    "Slagtyp - valj ett: putt / chip / fullslag\n"
    "Svar:"
)

print(f"Modell : {MODEL}")
print(f"Runs   : {N_RUNS}")
print("Laddar modell...")
t0 = time.perf_counter()
llm = pipeline("text-generation", model=MODEL)
load_s = time.perf_counter() - t0
print(f"Laddad : {load_s:.1f}s\n")

parser = ShotClassifierParser()


def generate(prompt: str) -> str:
    # /no_think stanger av Qwen3:s reasoning-lage sa att svaret kommer direkt
    content = prompt + "\n/no_think"
    result = llm([{"role": "user", "content": content}], max_new_tokens=100)
    raw = result[0]["generated_text"][-1]["content"]
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()


def run_eval(prompt_template: str, label: str) -> dict:
    """Kor ett komplett eval-pass och returnerar aggregerade resultat."""
    all_runs = []

    for run_idx in range(N_RUNS):
        run_results = []
        for utterance, expected in UTTERANCES:
            prompt = prompt_template.format(utterance=utterance)
            raw = generate(prompt)
            predicted = parser.invoke(LLMRunnerOutput(raw_text=raw)).shot_type
            run_results.append({
                "utterance": utterance,
                "expected": expected,
                "predicted": predicted,
                "correct": predicted == expected,
            })

        total = len(run_results)
        parsed = sum(1 for r in run_results if r["predicted"] != "okand")
        correct = sum(1 for r in run_results if r["correct"])
        all_runs.append({
            "run": run_idx + 1,
            "parse_rate": parsed / total,
            "accuracy": correct / total,
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


def print_detail(result: dict) -> None:
    """Skriver ut per-yttrande-resultat for sista run:en."""
    last = result["runs"][-1]
    print(f"  {'Yttrande':<52} {'Fatt':<10} {'Modell':<10} OK")
    print("  " + "-" * 76)
    for r in last["utterances"]:
        ok = "OK" if r["correct"] else "--"
        print(f"  {r['utterance']:<52} {r['expected']:<10} {r['predicted']:<10} {ok}")


# --- Kor zero-shot ---
print("=" * 60)
print("ZERO-SHOT (ingen exempel i prompten)")
print("=" * 60)
zero = run_eval(PROMPT_ZERO, "zero-shot")
print_detail(zero)
ag = zero["aggregate"]
print(f"\n  Parse-rate : {ag['parse_rate_mean']:.1%} +/- {ag['parse_rate_std']:.1%}")
print(f"  Accuracy   : {ag['accuracy_mean']:.1%} +/- {ag['accuracy_std']:.1%}\n")

# --- Kor few-shot ---
print("=" * 60)
print("FEW-SHOT (tre exempel i prompten)")
print("=" * 60)
print("  Exempel som gavs till modellen:")
print('    "Kort putt, rullde in."             -> putt')
print('    "Lagchip mot greenen, stannade nara." -> chip')
print('    "Drive langt ner mitten."            -> fullslag')
print()
few = run_eval(PROMPT_FEW, "few-shot")
print_detail(few)
ag_f = few["aggregate"]
print(f"\n  Parse-rate : {ag_f['parse_rate_mean']:.1%} +/- {ag_f['parse_rate_std']:.1%}")
print(f"  Accuracy   : {ag_f['accuracy_mean']:.1%} +/- {ag_f['accuracy_std']:.1%}\n")

# --- Jamforelsetabell ---
print("=" * 60)
print("SAMMANFATTNING")
print("=" * 60)
print(f"  {'Metod':<20} {'Parse-rate':>12} {'Accuracy':>10}")
print("  " + "-" * 44)

# Baslinjer fran Exp 5 (Qwen3 sv)
print(f"  {'Qwen3 zero-shot (Exp5)':<20} {'100%':>12} {'24%':>10}  (historisk baseline)")

z = zero["aggregate"]
f = few["aggregate"]
print(f"  {'Zero-shot (nu)':<20} {z['parse_rate_mean']:>11.0%} {z['accuracy_mean']:>9.0%}")
print(f"  {'Few-shot (nu)':<20} {f['parse_rate_mean']:>11.0%} {f['accuracy_mean']:>9.0%}")
print(f"  {'Semantisk kod (Exp6)':<20} {'90%':>12} {'90%':>10}  (ingen modell)")

diff = f["accuracy_mean"] - z["accuracy_mean"]
sign = "+" if diff >= 0 else ""
print(f"\n  Few-shot vs zero-shot: {sign}{diff:.0%} accuracy")

# --- Spara ---
os.makedirs("results", exist_ok=True)
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
out = {
    "experiment": "Exp7_fewshot",
    "model": MODEL,
    "n_runs": N_RUNS,
    "date": datetime.now().isoformat(),
    "load_time_s": round(load_s, 3),
    "zero_shot": zero,
    "few_shot": few,
}
path = f"results/exp7_fewshot_{ts}.json"
with open(path, "w", encoding="utf-8") as f_out:
    json.dump(out, f_out, ensure_ascii=False, indent=2)
print(f"\nResultat sparat: {path}")
