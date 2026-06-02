"""Evaluates a HuggingFace model on shot-type classification.

Usage:
  uv run python run_shot_classifier_eval.py
  uv run python run_shot_classifier_eval.py SupraLabs/Supra-50M-Instruct
  uv run python run_shot_classifier_eval.py SmolLM2 --lang en
  uv run python run_shot_classifier_eval.py SupraLabs/Supra-50M-Instruct --lang en

Measures:
  parse_rate  -- how often the model returns one of the three valid labels
  accuracy    -- how often the prediction matches the label
"""

import re
import sys
from transformers import pipeline
from app.chain.steps import ShotClassifierParser, LLMRunnerOutput

DEFAULT_MODEL = "HuggingFaceTB/SmolLM2-135M-Instruct"
args = sys.argv[1:]
LANG = "en" if "--lang en" in " ".join(args) else "sv"
MODEL = next((a for a in args if not a.startswith("--")), DEFAULT_MODEL)

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
    ("Three-foot straight putt, rolled it in.",      "putt"),
    ("Short putt, missed to the right.",             "putt"),
    ("Rolled in from the edge, just dropped.",       "putt"),
    ("Low chip toward the flag, stopped a foot away.", "chip"),
    ("Chipped out of the bunker, landed on the green.", "chip"),
    ("Sand wedge from the rough, bounced past.",     "chip"),
    ("Great drive, long and down the middle.",       "fullslag"),
    ("Hit an iron into the par 3.",                  "fullslag"),
    ("7-iron to the green, a bit long.",             "fullslag"),
    ("Wedge shot, ball landed near the flag.",       "fullslag"),
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
llm = pipeline("text-generation", model=MODEL)
print("Ready.\n")


def generate(prompt: str) -> str:
    try:
        messages = [{"role": "user", "content": prompt}]
        result = llm(messages, max_new_tokens=50)
        raw = result[0]["generated_text"][-1]["content"]
    except ValueError:
        result = llm(prompt, max_new_tokens=50)
        full_text: str = result[0]["generated_text"]
        raw = full_text[len(prompt):].strip()
    # Strip Qwen3-style thinking tokens before parsing
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()


parser = ShotClassifierParser()
results = []

for utterance, expected in UTTERANCES:
    prompt = PROMPT_TEMPLATE.format(utterance=utterance)
    raw = generate(prompt)
    predicted = parser.invoke(LLMRunnerOutput(raw_text=raw)).shot_type
    correct = predicted == expected
    results.append((utterance, expected, predicted, raw.strip(), correct))

# --- Report ---
print(f"{'Utterance':<52} {'Expected':<10} {'Model':<10} {'OK'}")
print("-" * 80)
for utterance, expected, predicted, _, correct in results:
    ok = "OK" if correct else "--"
    print(f"{utterance:<52} {expected:<10} {predicted:<10} {ok}")

total = len(results)
parsed = sum(1 for _, _, p, _, _ in results if p != "okand")
correct_count = sum(1 for *_, ok in results if ok)

print()
print(f"Parse-rate : {parsed}/{total} ({100*parsed/total:.0f}%)")
print(f"Accuracy   : {correct_count}/{total} ({100*correct_count/total:.0f}%)")

print("\n--- Raw model output ---")
for utterance, _, _, raw, _ in results:
    print(f"  [{utterance[:42]}] -> {repr(raw)}")
