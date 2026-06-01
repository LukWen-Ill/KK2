"""Kör Exp 1 (batch) och Exp 2 (async) mot SmolLM2-135M-Instruct."""
import asyncio
import concurrent.futures
import time

from transformers import pipeline

PROMPT_CONTENT = (
    "Spelarens stats: GIR 38.9% (PGA 65%), "
    "Fairway 50% (PGA 60%), Putts/hal 2.28 (PGA 1.73). "
    "Vad ar min svagaste del?"
)
MAX_TOKENS = 60
BASELINE_PER_PROMPT = 4.190  # mean_s vid max_new_tokens=60 från tidigare körning

print("Laddar modell...")
llm = pipeline("text-generation", model="HuggingFaceTB/SmolLM2-135M-Instruct")
print("Klar.\n")

# --- Experiment 1: Batch inference ---
print("=== Experiment 1: Batch inference ===")
batch_rows = []
for n in [5, 10, 15]:
    prompts = [[{"role": "user", "content": PROMPT_CONTENT}]] * n
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
    llm([{"role": "user", "content": PROMPT_CONTENT}], max_new_tokens=MAX_TOKENS)

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
