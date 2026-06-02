"""Kör Exp 1 (batch) och Exp 2 (async) mot en HuggingFace-modell.

Användning:
  uv run python run_experiments.py
  uv run python run_experiments.py SupraLabs/Supra-50M-Instruct
  uv run python run_experiments.py Qwen/Qwen3-0.6B --runs 5
"""
import asyncio
import concurrent.futures
import json
import os
import sys
import time
from datetime import datetime
from statistics import mean, stdev

from transformers import pipeline

DEFAULT_MODEL = "HuggingFaceTB/SmolLM2-135M-Instruct"
args = sys.argv[1:]
MODEL = next((a for a in args if not a.startswith("--")), DEFAULT_MODEL)
N_RUNS = 1
for i, arg in enumerate(args):
    if arg == "--runs" and i + 1 < len(args):
        N_RUNS = int(args[i + 1])

PROMPT_CONTENT = (
    "Spelarens stats: GIR 38.9% (PGA 65%), "
    "Fairway 50% (PGA 60%), Putts/hal 2.28 (PGA 1.73). "
    "Vad ar min svagaste del?"
)
MAX_TOKENS = 60
BASELINE_PER_PROMPT = 4.190  # mean_s vid max_new_tokens=60 från SmolLM2-körning

print(f"Laddar modell : {MODEL}")
print(f"Runs          : {N_RUNS}")
_t_load = time.perf_counter()
llm = pipeline("text-generation", model=MODEL)
load_time_s = time.perf_counter() - _t_load
print(f"Laddningstid  : {load_time_s:.2f}s")

# Avgör om modellen stöder chat-format
def _make_input(content: str):
    try:
        llm([{"role": "user", "content": content}], max_new_tokens=1)
        return lambda c: [{"role": "user", "content": c}]
    except ValueError:
        return lambda c: c

_fmt = _make_input(PROMPT_CONTENT)
print("Klar.\n")

def _run_one(_):
    llm(_fmt(PROMPT_CONTENT), max_new_tokens=MAX_TOKENS)

async def run_parallel(n):
    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
        t0 = time.perf_counter()
        await asyncio.gather(*[loop.run_in_executor(pool, _run_one, i) for i in range(n)])
        return time.perf_counter() - t0

all_runs = []

for run_idx in range(N_RUNS):
    if N_RUNS > 1:
        print(f"=== Run {run_idx + 1}/{N_RUNS} ===")

    # --- Experiment 1: Batch inference ---
    print("Experiment 1: Batch inference")
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
        batch_rows.append({"n": n, "total_s": round(total_s, 3), "per_s": round(per_s, 3), "speedup": round(speedup, 3)})

    # --- Experiment 2: Async parallella anrop ---
    print("Experiment 2: Async parallella anrop")
    async_rows = []
    for n in [5, 10, 15]:
        print(f"  n={n} ...", end=" ", flush=True)
        total_s = asyncio.run(run_parallel(n))
        per_s = total_s / n
        speedup = BASELINE_PER_PROMPT / per_s
        print(f"{total_s:.2f}s total | {per_s:.3f}s/prompt | speedup {speedup:.2f}x")
        async_rows.append({"n": n, "total_s": round(total_s, 3), "per_s": round(per_s, 3), "speedup": round(speedup, 3)})

    all_runs.append({"run": run_idx + 1, "batch": batch_rows, "async": async_rows})
    print()

# --- Aggregate ---
def _agg(rows_per_run, exp_key):
    ns = [r["n"] for r in rows_per_run[0]]
    result = []
    for i, n in enumerate(ns):
        per_s_vals = [run[i]["per_s"] for run in rows_per_run]
        speedup_vals = [run[i]["speedup"] for run in rows_per_run]
        result.append({
            "n": n,
            "per_s_mean":    round(mean(per_s_vals), 3),
            "per_s_std":     round(stdev(per_s_vals), 3) if N_RUNS > 1 else 0.0,
            "speedup_mean":  round(mean(speedup_vals), 3),
            "speedup_std":   round(stdev(speedup_vals), 3) if N_RUNS > 1 else 0.0,
        })
    return result

batch_agg = _agg([r["batch"] for r in all_runs], "batch")
async_agg = _agg([r["async"] for r in all_runs], "async")

print("=== SAMMANFATTNING ===")
print(f"Baseline (sekventiell, max_new_tokens=60): {BASELINE_PER_PROMPT:.3f}s/prompt\n")
print(f"{'Exp':<8} {'n':>4} {'per_s_mean':>12} {'per_s_std':>10} {'speedup_mean':>13}")
print("Batch:")
for r in batch_agg:
    print(f"         {r['n']:>4} {r['per_s_mean']:>12.3f} {r['per_s_std']:>10.3f} {r['speedup_mean']:>13.2f}x")
print("Async:")
for r in async_agg:
    print(f"         {r['n']:>4} {r['per_s_mean']:>12.3f} {r['per_s_std']:>10.3f} {r['speedup_mean']:>13.2f}x")

# --- Spara resultat ---
os.makedirs("results", exist_ok=True)
model_slug = MODEL.replace("/", "-")
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
out = {
    "model": MODEL,
    "n_runs": N_RUNS,
    "date": datetime.now().isoformat(),
    "load_time_s": round(load_time_s, 3),
    "max_new_tokens": MAX_TOKENS,
    "baseline_per_prompt_s": BASELINE_PER_PROMPT,
    "aggregate": {"batch": batch_agg, "async": async_agg},
    "runs": all_runs,
}
path = f"results/experiments_{model_slug}_{timestamp}.json"
with open(path, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"\nResultat sparat: {path}")
