"""Evaluates a HuggingFace model on shot-type classification.

Usage:
  uv run python run_shot_classifier_eval.py
  uv run python run_shot_classifier_eval.py SupraLabs/Supra-50M-Instruct
  uv run python run_shot_classifier_eval.py Qwen/Qwen3-0.6B --lang en
  uv run python run_shot_classifier_eval.py Qwen/Qwen3-0.6B --runs 5

Measures:
  parse_rate  -- how often the model returns one of the three valid labels
  accuracy    -- how often the prediction matches the label
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

DEFAULT_MODEL = "HuggingFaceTB/SmolLM2-135M-Instruct"
args = sys.argv[1:]
LANG = "en" if "--lang en" in " ".join(args) else "sv"
MODEL = next((a for a in args if not a.startswith("--")), DEFAULT_MODEL)
N_RUNS = 1
for i, arg in enumerate(args):
    if arg == "--runs" and i + 1 < len(args):
        N_RUNS = int(args[i + 1])

UTTERANCES_SV = [
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

UTTERANCES_EN = [
    ("Three-foot straight putt, rolled it in.",        "putt"),
    ("Short putt, missed to the right.",               "putt"),
    ("Rolled in from the edge, just dropped.",         "putt"),
    ("Low chip toward the flag, stopped a foot away.", "chip"),
    ("Chipped out of the bunker, landed on the green.", "chip"),
    ("Sand wedge from the rough, bounced past.",       "chip"),
    ("Great drive, long and down the middle.",         "fullslag"),
    ("Hit an iron into the par 3.",                    "fullslag"),
    ("7-iron to the green, a bit long.",               "fullslag"),
    ("Wedge shot, ball landed near the flag.",         "fullslag"),
]

PROMPT_SV = (
    'Yttrande: "{utterance}"\n'
    "Slagtyp - valj ett: putt / chip / fullslag\n"
    "Svar:"
)

PROMPT_EN = (
    'Utterance: "{utterance}"\n'
    "Shot type - choose one: putt / chip / fullslag\n"
    "Answer:"
)

UTTERANCES = UTTERANCES_EN if LANG == "en" else UTTERANCES_SV
PROMPT_TEMPLATE = PROMPT_EN if LANG == "en" else PROMPT_SV

print(f"Model : {MODEL}")
print(f"Lang  : {LANG}")
print(f"Runs  : {N_RUNS}")
_t_load = time.perf_counter()
llm = pipeline("text-generation", model=MODEL)
load_time_s = time.perf_counter() - _t_load
print(f"Load  : {load_time_s:.2f}s\n")


def generate(prompt: str) -> str:
    # Qwen3 soft-switch: append /no_think to disable reasoning mode
    content = prompt + ("\n/no_think" if "Qwen3" in MODEL else "")
    try:
        messages = [{"role": "user", "content": content}]
        result = llm(messages, max_new_tokens=100)
        raw = result[0]["generated_text"][-1]["content"]
    except ValueError:
        result = llm(content, max_new_tokens=100)
        full_text: str = result[0]["generated_text"]
        raw = full_text[len(content):].strip()
    # Strip any remaining thinking tokens as fallback
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()


parser = ShotClassifierParser()
all_runs = []

for run_idx in range(N_RUNS):
    if N_RUNS > 1:
        print(f"--- Run {run_idx + 1}/{N_RUNS} ---")

    run_results = []
    for utterance, expected in UTTERANCES:
        prompt = PROMPT_TEMPLATE.format(utterance=utterance)
        raw = generate(prompt)
        predicted = parser.invoke(LLMRunnerOutput(raw_text=raw)).shot_type
        correct = predicted == expected
        run_results.append((utterance, expected, predicted, raw.strip(), correct))

    total = len(run_results)
    parsed = sum(1 for _, _, p, _, _ in run_results if p != "okänd")
    correct_count = sum(1 for *_, ok in run_results if ok)
    parse_rate = parsed / total
    accuracy = correct_count / total

    print(f"{'Utterance':<52} {'Expected':<10} {'Model':<10} {'OK'}")
    print("-" * 80)
    for utterance, expected, predicted, _, correct in run_results:
        print(f"{utterance:<52} {expected:<10} {predicted:<10} {'OK' if correct else '--'}")
    print(f"\nParse-rate : {parsed}/{total} ({100*parse_rate:.0f}%)")
    print(f"Accuracy   : {correct_count}/{total} ({100*accuracy:.0f}%)\n")

    all_runs.append({
        "run": run_idx + 1,
        "parse_rate": parse_rate,
        "accuracy": accuracy,
        "utterances": [
            {"utterance": utt, "expected": exp, "predicted": pred, "raw": raw, "correct": ok}
            for utt, exp, pred, raw, ok in run_results
        ],
    })

# --- Aggregate ---
parse_rates = [r["parse_rate"] for r in all_runs]
accuracies  = [r["accuracy"]   for r in all_runs]
if N_RUNS > 1:
    print("=== AGGREGATE ===")
    print(f"Parse-rate : {mean(parse_rates):.1%} ± {stdev(parse_rates):.1%}")
    print(f"Accuracy   : {mean(accuracies):.1%} ± {stdev(accuracies):.1%}\n")

# --- Spara resultat ---
os.makedirs("results", exist_ok=True)
model_slug = MODEL.replace("/", "-")
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
out = {
    "model": MODEL,
    "lang": LANG,
    "n_runs": N_RUNS,
    "date": datetime.now().isoformat(),
    "load_time_s": round(load_time_s, 3),
    "aggregate": {
        "parse_rate_mean": round(mean(parse_rates), 4),
        "parse_rate_std":  round(stdev(parse_rates), 4) if N_RUNS > 1 else 0.0,
        "accuracy_mean":   round(mean(accuracies), 4),
        "accuracy_std":    round(stdev(accuracies), 4) if N_RUNS > 1 else 0.0,
    },
    "runs": all_runs,
}
path = f"results/shot_classifier_{model_slug}_{LANG}_{timestamp}.json"
with open(path, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"Resultat sparat: {path}")
