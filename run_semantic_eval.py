"""Evaluates the semantic (keyword-based) shot classifier and compares to LLM baselines.

No model is loaded — runs instantly.

Usage:
  uv run python run_semantic_eval.py
"""

from app.chain.steps import SemanticShotClassifier, ShotClassifierInput

UTTERANCES_SV = [
    ("Tre meter rakt mot halet, rullde in.",         "putt"),
    ("Kort putt, missade till hoger.",               "putt"),
    ("Rullning in fran kanten, precis.",             "putt"),
    ("Lagchip mot flaggan, stannade en meter bort.", "chip"),
    ("Chippade ur bunkern, landade pa greenen.",     "chip"),
    ("Sandwedge fran rough, studsade forbi.",        "chip"),
    ("Bra drive langt ner mitten.",                  "utslag"),
    ("Tog ett jarnslag mot par 3-halet.",            "fullslag"),
    ("7-jarn mot greenen, lite for lang.",           "fullslag"),
    ("Slog en wedge, bollen landade nara flaggan.",  "fullslag"),
]

LLM_BASELINES = [
    ("Supra-50M",   "sv",  0.12, 0.10),
    ("SmolLM2-135M","sv",  0.30, 0.20),
    ("Qwen2.5-0.5B","sv",  0.66, 0.26),
    ("Qwen3-0.6B",  "sv",  1.00, 0.24),
    ("SmolLM2-135M","en",  0.96, 0.34),
    ("Qwen3-0.6B",  "en",  1.00, 0.44),
]

classifier = SemanticShotClassifier()

print("=== Semantisk klassificering (inga nyckelord -> okand) ===\n")
print(f"{'Yttrande':<52} {'Förväntat':<10} {'Utfall':<10} {'OK'}")
print("-" * 80)

results = []
for utterance, expected in UTTERANCES_SV:
    predicted = classifier.invoke(ShotClassifierInput(utterance=utterance)).shot_type
    correct = predicted == expected
    results.append((utterance, expected, predicted, correct))
    print(f"{utterance:<52} {expected:<10} {predicted:<10} {'OK' if correct else '--'}")

total = len(results)
parsed = sum(1 for *_, p, _ in results if p != "okänd")
correct_count = sum(1 for *_, ok in results if ok)
parse_rate = parsed / total
accuracy = correct_count / total

print(f"\nParse-rate : {parsed}/{total} ({100*parse_rate:.0f}%)")
print(f"Accuracy   : {correct_count}/{total} ({100*accuracy:.0f}%)")

# Identify which utterances fall through to LLM
llm_fallback = [(u, e) for u, e, p, _ in results if p == "okänd"]
if llm_fallback:
    print(f"\nFaller igenom till LLM ({len(llm_fallback)} yttranden):")
    for u, e in llm_fallback:
        print(f"  -> '{u}'  (forväntat: {e})")

print("\n=== Jämförelse mot LLM-baselines (Exp 3–5) ===\n")
print(f"{'Modell':<16} {'Språk':<6} {'Parse-rate':>11} {'Accuracy':>10}")
print("-" * 46)
for model, lang, pr, acc in LLM_BASELINES:
    print(f"{model:<16} {lang:<6} {100*pr:>10.0f}% {100*acc:>9.0f}%")
print(f"{'Semantisk kod':<16} {'sv':<6} {100*parse_rate:>10.0f}% {100*accuracy:>9.0f}%  <- ingen modell")
