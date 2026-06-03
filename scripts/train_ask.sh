#!/usr/bin/env bash
# Komplett träningsflöde för /ai/ask LoRA-adaptern.
# Kör: bash scripts/train_ask.sh
set -e
cd "$(dirname "$0")/.."

echo "=== Steg 1: Generera träningsdata ==="
uv run python scripts/generate_ask_training_data.py

echo ""
echo "=== Steg 2: Fine-tuning (LoRA) ==="
uv run python scripts/run_chat_finetune.py 2>&1 | tee eval_err.txt

echo ""
echo "=== Steg 3: Eval mot 20 testfrågor ==="
uv run python scripts/run_ask_eval.py 2>&1 | tee eval_out.txt

echo ""
echo "=== Klart. Resultat i eval_out.txt, träningslogg i eval_err.txt ==="
