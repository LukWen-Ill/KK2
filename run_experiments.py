"""Kör Exp 1 (batch) och Exp 2 (async) mot en HuggingFace-modell.

Användning:
  uv run python run_experiments.py
  uv run python run_experiments.py SupraLabs/Supra-50M-Instruct
"""
import asyncio
import concurrent.futures
import sys
import time

from transformers import pipeline

DEFAULT_MODEL = "HuggingFaceTB/SmolLM2-135M-Instruct"
MODEL = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL

PROMPT_CONTENT = (
    "Spelarens stats: GIR 38.9% (PGA 65%), "
    "Fairway 50% (PGA 60%), Putts/hal 2.28 (PGA 1.73). "
    "Vad ar min svagaste del?"
)
MAX_TOKENS = 60
BASELINE_PER_PROMPT = 4.190  # mean_s vid max_new_tokens=60 från SmolLM2-körning

print(f"Laddar modell: {MODEL}")
llm = pipeline("text-generation", model=MODEL)

# Avgör om modellen stöder chat-format
def _make_input(content: str):
    try:
        llm([{"role": "user", "content": content}], max_new_tokens=1)
        return lambda c: [{"role": "user", "content": c}]
    except ValueError:
        return lambda c: c

_fmt = _make_input(PROMPT_CONTENT)
print("Klar.\n")

# --- Experiment 1: Batch inference ---
print("=== Experiment 1: Batch inference ===")
batch_rows = []
for n in [5, 10, 15]:
    prompts = [_fmt(PROMPT_CONTENT)] * n
    print(f"  batch_size={n} ...", end=" ", flush=True)
    t0 = time.perf_counter()
    llm(prompts, max_new_tokens=MAX_TOKENS, batch_size=n)
    total_s = time.perf_counter() - t0
    per_s = total_s / n
    speedup = BASELINE_PER_PROMPT / per_s
    print(f"{total_s:.2f}s total | {per_s:.3f}s/prompt | speedup {speedup:.2f}x")
    batch_rows.append((n, total_s, per_s, speedup))

# --- Experiment 2: Async parallella anrop ---
print("\n=== Experiment 2: Async parallella anrop ===")

def _run_one(_):
    llm(_fmt(PROMPT_CONTENT), max_new_tokens=MAX_TOKENS)

async def run_parallel(n):
    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
        t0 = time.perf_counter()
        await asyncio.gather(*[loop.run_in_executor(pool, _run_one, i) for i in range(n)])
        return time.perf_counter() - t0

async_rows = []
for n in [5, 10, 15]:
    print(f"  n={n} ...", end=" ", flush=True)
    total_s = asyncio.run(run_parallel(n))
    per_s = total_s / n
    speedup = BASELINE_PER_PROMPT / per_s
    print(f"{total_s:.2f}s total | {per_s:.3f}s/prompt | speedup {speedup:.2f}x")
    async_rows.append((n, total_s, per_s, speedup))

# --- Sammanfattning ---
print("\n=== SAMMANFATTNING ===")
print(f"Baseline (sekventiell, max_new_tokens=60): {BASELINE_PER_PROMPT:.3f}s/prompt\n")
print(f"{'':4} {'n':>4} {'total_s':>8} {'per_s':>8} {'speedup':>8}")
print("Batch:")
for n, tot, per, sp in batch_rows:
    print(f"      {n:>4} {tot:>8.2f} {per:>8.3f} {sp:>8.2f}x")
print("Async:")
for n, tot, per, sp in async_rows:
    print(f"      {n:>4} {tot:>8.2f} {per:>8.3f} {sp:>8.2f}x")
