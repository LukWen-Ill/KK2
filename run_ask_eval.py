"""Evaluates the 5-step CoT pipeline (Exp 9 iteration 2) for /ai/ask.

Usage:
  uv run python run_ask_eval.py

Runs 20 questions through ask_cot_kedjan and auto-categorizes each answer.
Prints per-answer detail and a summary table for documenting in reflektion.md.
"""

import time
from app.chain.pipeline import ask_cot_kedjan
from app.chain.steps import AskCoTState

# Representative user stats (same as used in iteration 1 docs)
USER_STATS = {
    "gir_pct": 21.3,
    "fairway_pct": 64.3,
    "avg_putts": 2.16,
    "scoring_avg": 5.19,
}

PGA = {
    "gir_pct": 66.7,
    "fairway_pct": 60.9,
    "avg_putts": 1.73,
    "scoring_avg": 70.5,
}

QUESTIONS = [
    "What is my biggest weakness?",
    "How can I improve my scoring?",
    "What should I practice first?",
    "Why am I missing so many greens?",
    "How do I lower my handicap?",
    "Am I a good putter compared to pros?",
    "What drill should I do for GIR?",
    "How far am I from PGA Tour level?",
    "Is my fairway accuracy good or bad?",
    "What one thing would help me most?",
    "How can I reduce my putts per hole?",
    "My GIR is low — what causes that?",
    "What's my strongest stat?",
    "How many more greens do pros hit?",
    "Should I focus on putting or approach shots?",
    "How does my scoring compare to scratch golfers?",
    "What practice routine would improve my game fastest?",
    "I'm struggling with approach shots. What drill helps?",
    "What does my GIR percentage tell about my iron play?",
    "Give me one concrete tip based on my stats.",
]


def _categorize(state: AskCoTState) -> str:
    """Auto-categorize based on answer content."""
    answer = state.answer.lower()

    # Check for stats references (specific numbers from user stats)
    has_stats = any(
        str(v) in state.answer
        for v in [21.3, 64.3, 2.16, 5.19, 66.7, 1.73]
    )
    # Check for worst stat reference
    mentions_gir = "gir" in answer
    # Check for drill content (usually contains action words)
    has_drill = any(w in answer for w in ["drill", "practice", "train", "range", "putt", "chip", "swing", "hit"])
    # Check for obvious hallucination/nonsense
    is_very_short = len(state.answer.strip()) < 20
    is_garbled = state.answer.count("?") > 3 or state.answer.count("!") > 4

    if is_very_short or is_garbled:
        return "Fel/kort svar"
    if has_stats and has_drill:
        return "Stats + drill (OK)"
    if has_stats and not has_drill:
        return "Stats, inget drill"
    if not has_stats and has_drill:
        return "Drill, inga stats"
    return "Generisk, inga stats"


def main():
    print("=" * 70)
    print("Exp 9 Iteration 2 — 5-stegs CoT eval (ask_cot_kedjan)")
    print(f"User stats: GIR {USER_STATS['gir_pct']}%, "
          f"FW {USER_STATS['fairway_pct']}%, "
          f"Putts {USER_STATS['avg_putts']}, "
          f"Scoring {USER_STATS['scoring_avg']}/hole")
    print("=" * 70)

    results = []
    total_start = time.time()

    for i, question in enumerate(QUESTIONS, 1):
        state = AskCoTState(
            question=question,
            user_stats=USER_STATS,
            pga_benchmarks=PGA,
        )
        t0 = time.time()
        try:
            result = ask_cot_kedjan.invoke(state)
            elapsed = time.time() - t0
            category = _categorize(result)
            error = None
            answer_preview = result.answer[:120].replace("\n", " ")
        except Exception as e:
            elapsed = time.time() - t0
            category = "Fel/crash"
            error = str(e)[:80]
            answer_preview = f"ERROR: {error}"
            result = state

        print(f"\n[{i:02d}] Q: {question}")
        print(f"     A: {answer_preview}")
        print(f"     Worst stat: {result.worst_stat} | {result.worst_gap_str}")
        print(f"     Category: {category}  ({elapsed:.1f}s)")

        results.append({
            "question": question,
            "answer": getattr(result, "answer", ""),
            "worst_stat": result.worst_stat,
            "category": category,
            "elapsed": elapsed,
        })

    total_elapsed = time.time() - total_start

    # Summary
    from collections import Counter
    counts = Counter(r["category"] for r in results)
    avg_time = sum(r["elapsed"] for r in results) / len(results)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total questions: {len(results)}")
    print(f"Total time: {total_elapsed:.0f}s  |  Avg per question: {avg_time:.1f}s")
    print()
    print("Category breakdown:")
    for cat, count in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {count:2d}/20  {cat}")

    print()
    print("Worst stat distribution:")
    stat_counts = Counter(r["worst_stat"] for r in results)
    for stat, count in stat_counts.most_common():
        print(f"  {count:2d}/20  {stat}")

    print()
    print("--- Paste into reflektion.md ---")
    print(f"| Kategori | Antal | Beskrivning |")
    print(f"|---|---|---|")
    for cat, count in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"| {cat} | {count}/20 |  |")
    print(f"\nSnittid: {avg_time:.1f}s/fråga  |  Total: {total_elapsed:.0f}s")


if __name__ == "__main__":
    main()
