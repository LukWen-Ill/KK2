"""
Diagnostic script: runs the chain stages separately to isolate model vs code issues.
Usage: uv run python diagnose_chain.py
"""
import json
from app.chain.steps import PromptBuilder, PromptBuilderInput, LLMRunner, ResponseParser

USER_STATS = {
    "gir_pct": 38.9,
    "fairway_pct": 50.0,
    "avg_putts": 2.28,
    "scoring_avg": 5.28,
}
PGA = {
    "gir_pct": 65.0,
    "fairway_pct": 60.0,
    "avg_putts": 1.73,
    "scoring_avg": 70.5,
}
QUESTION = "Vad är min svagaste del?"

# Stage 1: what does the prompt look like?
inp = PromptBuilderInput(question=QUESTION, user_stats=USER_STATS, pga_benchmarks=PGA)
prompt_out = PromptBuilder().invoke(inp)

print("=" * 60)
print("STAGE 1 — PROMPT SENT TO MODEL")
print("=" * 60)
print(prompt_out.prompt)

# Stage 2: raw model output
print("\n" + "=" * 60)
print("STAGE 2 — RAW MODEL OUTPUT (before ResponseParser)")
print("=" * 60)
llm_out = LLMRunner().invoke(prompt_out)
print(repr(llm_out.raw_text))
print("\n--- readable ---")
print(llm_out.raw_text)

# Stage 3: parsed answer
print("\n" + "=" * 60)
print("STAGE 3 — AFTER ResponseParser")
print("=" * 60)
parsed = ResponseParser().invoke(llm_out)
print(parsed.answer)
