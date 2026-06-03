"""Eval-agent: mäter hur bra reflektion_index.md fungerar som navigationslager.

Agentflöde (två SmolLM2-anrop + ett kodsteg):
  1. Navigate  — SmolLM2 läser index (~60 rader) → väljer relevant sektion
  2. Retrieve  — kod extraherar sektionen från reflektion.md (via radnummer i index)
  3. Answer    — SmolLM2 läser sektionen → svarar på frågan
  4. Score     — kontrollerar att facit-nyckelord finns i svaret

Jämförelse: index-guided (steg 1-3) vs blind (SmolLM2 svarar utan dokument).

Kör: uv run python scripts/run_index_eval.py
"""

import re
import time
from pathlib import Path
from dataclasses import dataclass, field

REFLEKTION = Path("docs/reflektion.md")
INDEX_PATH = Path("docs/reflektion_index.md")
MODEL = "HuggingFaceTB/SmolLM2-135M-Instruct"

# Section window: how many lines to read after the section start
SECTION_WINDOW = 80

# --- Ground truth ---

@dataclass
class TestCase:
    question: str
    keywords: list[str]   # any keyword must appear in answer (case-insensitive)
    section_hint: str     # expected section name/keyword from index

CASES: list[TestCase] = [
    TestCase(
        question="What accuracy did the semantic classifier (Exp 6) achieve?",
        keywords=["90%", "90"],
        section_hint="Exp 6",
    ),
    TestCase(
        question="How many training examples were used in LoRA fine-tuning (Exp 8)?",
        keywords=["160"],
        section_hint="Exp 8",
    ),
    TestCase(
        question="What validation accuracy did fine-tuning (Exp 8) reach?",
        keywords=["65%", "65"],
        section_hint="Exp 8",
    ),
    TestCase(
        question="What is the recommended batch_size for SmolLM2?",
        keywords=["2", "3", "2-3", "2–3"],
        section_hint="Exp 1",
    ),
    TestCase(
        question="What does constrained decoding guarantee about player stats in answers?",
        keywords=["20/20", "100%", "all 20", "every"],
        section_hint="Exp 9 Iter 4",
    ),
    TestCase(
        question="What accuracy did few-shot prompting achieve in Exp 7?",
        keywords=["33%", "33"],
        section_hint="Exp 7",
    ),
    TestCase(
        question="What is the latency of the semantic classifier?",
        keywords=["0 ms", "0ms", "zero"],
        section_hint="Exp 6",
    ),
    TestCase(
        question="How many total training examples does generate_ask_training_data.py create?",
        keywords=["1000", "800", "1 000"],
        section_hint="Exp 9 Iter 5",
    ),
    TestCase(
        question="What is the P1 priority item about CSV uploads?",
        keywords=["radgräns", "row", "DoS", "limit"],
        section_hint="Åtgärdsbacklogg",
    ),
    TestCase(
        question="Which GDPR issue relates to missing consent?",
        keywords=["samtycke", "consent", "rättslig grund", "legal"],
        section_hint="2. Dataskydd",
    ),
]


# --- Index parsing ---

def parse_index(index_text: str) -> list[tuple[str, int]]:
    """Parse markdown table rows to (label, start_line) pairs.

    Looks for rows matching: | ... | <int> | ... |
    Returns list sorted by start_line.
    """
    rows = []
    for line in index_text.splitlines():
        m = re.search(r"\|\s*\*{0,2}(.+?)\*{0,2}\s*\|\s*(\d+)\s*\|", line)
        if m:
            label = m.group(1).strip()
            lineno = int(m.group(2))
            rows.append((label, lineno))
    return sorted(rows, key=lambda x: x[1])


def extract_section(reflektion_lines: list[str], start: int, end: int) -> str:
    """Extract lines [start-1 .. end-1] from reflektion (1-indexed)."""
    lo = max(0, start - 1)
    hi = min(len(reflektion_lines), end)
    return "".join(reflektion_lines[lo:hi])


def find_section_for_label(label: str, index_rows: list[tuple[str, int]]) -> tuple[int, int]:
    """Given a label picked by the model, return (start_line, end_line).

    Matches the closest label in the index, then uses the next label's
    start as the end boundary (or start+SECTION_WINDOW).
    """
    label_lower = label.lower().strip()
    best_idx = 0
    best_score = 0
    for i, (row_label, _) in enumerate(index_rows):
        # Simple overlap score: how many words from label appear in row_label
        words = [w for w in label_lower.split() if len(w) > 2]
        score = sum(1 for w in words if w in row_label.lower())
        if score > best_score:
            best_score = score
            best_idx = i

    start_line = index_rows[best_idx][1]
    if best_idx + 1 < len(index_rows):
        end_line = index_rows[best_idx + 1][1] - 1
        # Cap at SECTION_WINDOW to avoid huge sections
        end_line = min(end_line, start_line + SECTION_WINDOW)
    else:
        end_line = start_line + SECTION_WINDOW

    return start_line, end_line


# --- SmolLM2 calls ---

_pipe = None

def _load_model():
    global _pipe
    if _pipe is None:
        from transformers import pipeline
        print(f"  [model] Loading {MODEL}...", flush=True)
        t0 = time.time()
        _pipe = pipeline("text-generation", model=MODEL)
        print(f"  [model] Loaded in {time.time()-t0:.1f}s", flush=True)
    return _pipe


def _call(prompt: str, max_new_tokens: int = 40) -> str:
    pipe = _load_model()
    result = pipe(
        [{"role": "user", "content": prompt}],
        max_new_tokens=max_new_tokens,
        max_length=None,
        do_sample=False,
    )
    return result[0]["generated_text"][-1]["content"].strip()


def navigate(question: str, index_text: str) -> str:
    """Step 1: SmolLM2 reads the index and returns the most relevant section label."""
    prompt = (
        "Below is an index of a reflection document. "
        "Reply with ONLY the section label (copy it exactly) that best answers the question.\n\n"
        f"INDEX:\n{index_text}\n\n"
        f"QUESTION: {question}\n\n"
        "Most relevant section label:"
    )
    return _call(prompt, max_new_tokens=20)


def answer_from_section(question: str, section_text: str) -> str:
    """Step 3: SmolLM2 reads the section and answers the question."""
    prompt = (
        "Answer the question using ONLY the text below. "
        "Be brief — one sentence or a number.\n\n"
        f"TEXT:\n{section_text}\n\n"
        f"QUESTION: {question}\n\n"
        "Answer:"
    )
    return _call(prompt, max_new_tokens=40)


def blind_answer(question: str) -> str:
    """Baseline: SmolLM2 answers without any document."""
    prompt = (
        f"Answer this question about a golf coaching experiment document. "
        f"Be brief.\n\nQUESTION: {question}\n\nAnswer:"
    )
    return _call(prompt, max_new_tokens=40)


# --- Scoring ---

def score(answer: str, keywords: list[str]) -> bool:
    a = answer.lower()
    return any(kw.lower() in a for kw in keywords)


# --- Main ---

@dataclass
class Result:
    question: str
    expected_section: str
    chosen_section: str
    section_matched: bool
    answer_indexed: str
    answer_blind: str
    correct_indexed: bool
    correct_blind: bool
    t_navigate: float
    t_answer: float
    t_blind: float
    lines_read: int


def main():
    index_text = INDEX_PATH.read_text(encoding="utf-8")
    reflektion_lines = REFLEKTION.read_text(encoding="utf-8").splitlines(keepends=True)
    index_rows = parse_index(index_text)

    print("=" * 70)
    print("Index eval agent — reflektion_index.md navigering med SmolLM2-135M")
    print(f"Index: {len(index_rows)} sektioner  |  Reflektion: {len(reflektion_lines)} rader")
    print("=" * 70)

    results: list[Result] = []

    for i, case in enumerate(CASES, 1):
        print(f"\n[{i:02d}] {case.question}")

        # Step 1: Navigate
        t0 = time.time()
        chosen_label = navigate(case.question, index_text)
        t_nav = time.time() - t0
        chosen_label_clean = chosen_label.strip().splitlines()[0][:60]

        # Step 2: Retrieve section
        start, end = find_section_for_label(chosen_label_clean, index_rows)
        section_text = extract_section(reflektion_lines, start, end)
        lines_read = end - start + 1

        section_matched = case.section_hint.lower() in chosen_label_clean.lower() or \
                          case.section_hint.lower() in section_text[:200].lower()

        print(f"     → Model chose: {chosen_label_clean!r}")
        print(f"     → Section lines {start}–{end} ({lines_read} rader) | match={section_matched}")

        # Step 3: Answer with section
        t0 = time.time()
        ans_indexed = answer_from_section(case.question, section_text)
        t_ans = time.time() - t0

        # Baseline: blind answer
        t0 = time.time()
        ans_blind = blind_answer(case.question)
        t_blind = time.time() - t0

        ok_indexed = score(ans_indexed, case.keywords)
        ok_blind = score(ans_blind, case.keywords)

        print(f"     Indexed answer : {ans_indexed[:100]!r}  [{'OK' if ok_indexed else 'FEL'}]")
        print(f"     Blind answer   : {ans_blind[:100]!r}  [{'OK' if ok_blind else 'FEL'}]")

        results.append(Result(
            question=case.question,
            expected_section=case.section_hint,
            chosen_section=chosen_label_clean,
            section_matched=section_matched,
            answer_indexed=ans_indexed,
            answer_blind=ans_blind,
            correct_indexed=ok_indexed,
            correct_blind=ok_blind,
            t_navigate=t_nav,
            t_answer=t_ans,
            t_blind=t_blind,
            lines_read=lines_read,
        ))

    # Summary
    n = len(results)
    nav_ok = sum(r.section_matched for r in results)
    idx_ok = sum(r.correct_indexed for r in results)
    blind_ok = sum(r.correct_blind for r in results)
    avg_lines = sum(r.lines_read for r in results) / n
    avg_t_total = sum(r.t_navigate + r.t_answer for r in results) / n

    print("\n" + "=" * 70)
    print("SAMMANFATTNING")
    print("=" * 70)
    print(f"Frågor totalt          : {n}")
    print(f"Rätt sektion (navigate): {nav_ok}/{n} ({100*nav_ok//n}%)")
    print(f"Rätt svar med index    : {idx_ok}/{n} ({100*idx_ok//n}%)")
    print(f"Rätt svar utan index   : {blind_ok}/{n} ({100*blind_ok//n}%)")
    print(f"Index-vinst            : +{idx_ok - blind_ok} svar")
    print(f"Snitt lästa rader/fråga: {avg_lines:.0f}  (av {len(reflektion_lines)} totalt)")
    print(f"Snitt tid (nav+svar)   : {avg_t_total:.1f}s/fråga")

    print("\n--- Tabell ---")
    print(f"{'Fråga':<50} {'Sekt':>4} {'Idx':>4} {'Blind':>5}")
    print("-" * 68)
    for r in results:
        sec = "✓" if r.section_matched else "✗"
        idx = "✓" if r.correct_indexed else "✗"
        bld = "✓" if r.correct_blind else "✗"
        print(f"{r.question[:49]:<50} {sec:>4} {idx:>4} {bld:>5}")


if __name__ == "__main__":
    main()
