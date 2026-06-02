"""Läser alla JSON-filer i results/ och skriver ut jämförelsetabeller.

Användning:
  uv run python show_results.py
"""

import json
import os
from pathlib import Path
from statistics import mean, stdev

RESULTS_DIR = Path("results")


def load_all(prefix: str) -> list[dict]:
    files = sorted(RESULTS_DIR.glob(f"{prefix}_*.json"))
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


def _fmt(val: float, std: float | None = None) -> str:
    s = f"{val:.1%}"
    if std is not None and std > 0:
        s += f" ±{std:.1%}"
    return s


def show_classifier():
    data = load_all("shot_classifier")
    if not data:
        print("Inga shot_classifier-resultat hittades.\n")
        return

    # Group by (model, lang)
    groups: dict[tuple, list] = {}
    for d in data:
        key = (d["model"], d["lang"])
        groups.setdefault(key, []).append(d)

    print("=" * 70)
    print("SHOT CLASSIFIER — parse-rate och accuracy per modell och språk")
    print("=" * 70)
    print(f"{'Modell':<38} {'Lang':<5} {'Runs':>5}  {'Parse-rate':>12}  {'Accuracy':>12}  {'Load(s)':>8}")
    print("-" * 70)

    for (model, lang), runs in sorted(groups.items()):
        pr_vals = [r["aggregate"]["parse_rate_mean"] for r in runs]
        ac_vals = [r["aggregate"]["accuracy_mean"]   for r in runs]
        load_vals = [r["load_time_s"] for r in runs]
        n_runs_total = sum(r["n_runs"] for r in runs)

        pr = mean(pr_vals)
        pr_s = stdev(pr_vals) if len(pr_vals) > 1 else runs[0]["aggregate"]["parse_rate_std"]
        ac = mean(ac_vals)
        ac_s = stdev(ac_vals) if len(ac_vals) > 1 else runs[0]["aggregate"]["accuracy_std"]
        load = mean(load_vals)

        short = model.split("/")[-1]
        print(f"{short:<38} {lang:<5} {n_runs_total:>5}  {_fmt(pr, pr_s):>12}  {_fmt(ac, ac_s):>12}  {load:>8.1f}")
    print()


def show_experiments():
    data = load_all("experiments")
    if not data:
        print("Inga experiments-resultat hittades.\n")
        return

    groups: dict[str, list] = {}
    for d in data:
        groups.setdefault(d["model"], []).append(d)

    for model, runs in sorted(groups.items()):
        short = model.split("/")[-1]
        print("=" * 70)
        print(f"LATENS — {short}  ({sum(r['n_runs'] for r in runs)} runs)")
        print("=" * 70)

        for exp_key in ("batch", "async"):
            print(f"\n  {exp_key.capitalize()}:")
            print(f"  {'n':>4}  {'per_s_mean':>12}  {'per_s_std':>10}  {'speedup':>9}")
            print(f"  {'-'*4}  {'-'*12}  {'-'*10}  {'-'*9}")
            # Collect per_s values per n across all runs
            ns = [r["n"] for r in runs[0]["aggregate"][exp_key]]
            for i, n in enumerate(ns):
                vals = []
                for run_file in runs:
                    for r_run in run_file["runs"]:
                        vals.append(r_run[exp_key][i]["per_s"])
                m = mean(vals)
                s = stdev(vals) if len(vals) > 1 else 0.0
                sp = runs[0]["aggregate"][exp_key][i]["speedup_mean"]
                print(f"  {n:>4}  {m:>12.3f}  {s:>10.3f}  {sp:>9.2f}x")
        print()


if __name__ == "__main__":
    show_classifier()
    show_experiments()
