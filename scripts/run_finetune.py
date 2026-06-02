"""Experiment 8 — Fine-tuning Qwen3-0.6B med LoRA.

Tränar en LoRA-adapter på data/train.jsonl och utvärderar mot
data/val.jsonl. Sparar adaptern till models/qwen3-golf-lora/.

Förutsättningar:
  pip install peft trl   (eller: uv add peft trl)

Rekommenderad miljö: Google Colab med gratis T4 GPU (~15–30 min).
På CPU tar träningen 2–6 timmar.

Usage:
  python run_finetune.py
  python run_finetune.py --epochs 5
  python run_finetune.py --model Qwen/Qwen3-0.6B --rank 16
"""

import argparse
import json
import os
import time

import torch
from datasets import Dataset
from peft import LoraConfig, TaskType, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainerCallback, TrainerControl, TrainerState, TrainingArguments
from trl import SFTTrainer, SFTConfig
from tqdm.auto import tqdm

# --- Argument ---

parser = argparse.ArgumentParser()
parser.add_argument("--model",  default="Qwen/Qwen3-0.6B")
parser.add_argument("--epochs", type=int, default=3)
parser.add_argument("--rank",   type=int, default=8,  help="LoRA rank (r)")
parser.add_argument("--lr",     type=float, default=2e-4)
parser.add_argument("--output", default="models/qwen3-golf-lora")
args = parser.parse_args()

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Modell  : {args.model}")
print(f"Device  : {DEVICE}")
print(f"Epochs  : {args.epochs}  |  LoRA rank: {args.rank}  |  LR: {args.lr}\n")

if DEVICE == "cpu":
    print("VARNING: CPU-träning kan ta 2–6 timmar. Kör vidare...\n")


# --- Ladda data ---

def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def format_example(row: dict) -> str:
    """Formatera ett (yttrande, etikett)-par som en chat-tur."""
    prompt = (
        f'Yttrande: "{row["utterance"]}"\n'
        "Slagtyp - välj ett: putt / chip / fullslag /no_think\n"
        "Svar:"
    )
    return f"<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n{row['label']}<|im_end|>"


train_rows = load_jsonl("data/train.jsonl")
val_rows   = load_jsonl("data/val.jsonl")

train_ds = Dataset.from_list([{"text": format_example(r)} for r in train_rows])
val_ds   = Dataset.from_list([{"text": format_example(r)} for r in val_rows])

print(f"Träning : {len(train_ds)} exempel")
print(f"Val     : {len(val_ds)} exempel\n")


# --- Progress callback ---

class ProgressCallback(TrainerCallback):
    """Skriver ut loss och ETA per loggsteg."""

    def __init__(self) -> None:
        self._bar: tqdm | None = None
        self._step_start: float = 0.0
        self._step_times: list[float] = []

    def on_train_begin(self, args: TrainingArguments, state: TrainerState, control: TrainerControl, **_) -> None:
        total = state.max_steps
        self._bar = tqdm(total=total, unit="steg", dynamic_ncols=True, desc="Träning")

    def on_step_begin(self, *_, **__) -> None:
        self._step_start = time.perf_counter()

    def on_log(self, args: TrainingArguments, state: TrainerState, control: TrainerControl, logs: dict, **_) -> None:
        elapsed = time.perf_counter() - self._step_start
        self._step_times.append(elapsed)
        avg = sum(self._step_times[-20:]) / len(self._step_times[-20:])  # rullande snitt
        remaining = (state.max_steps - state.global_step) * avg
        m, s = divmod(int(remaining), 60)
        h, m = divmod(m, 60)
        eta = f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"

        loss = logs.get("loss", logs.get("train_loss", "?"))
        loss_str = f"{loss:.4f}" if isinstance(loss, float) else str(loss)

        if self._bar:
            self._bar.set_postfix(loss=loss_str, eta=eta, epoch=f"{state.epoch:.1f}")
            self._bar.update(state.global_step - self._bar.n)

    def on_train_end(self, *_, **__) -> None:
        if self._bar:
            self._bar.close()


# --- Ladda modell och tokenizer ---

t0 = time.perf_counter()
tokenizer = AutoTokenizer.from_pretrained(args.model)
model = AutoModelForCausalLM.from_pretrained(
    args.model,
    torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32,
    device_map="auto" if DEVICE == "cuda" else None,
)
print(f"Modell laddad: {time.perf_counter() - t0:.1f}s\n")


# --- LoRA-konfiguration ---

lora_config = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r=args.rank,
    lora_alpha=args.rank * 2,   # alpha = 2×r är tumregeln
    lora_dropout=0.05,
    target_modules="all-linear",
    bias="none",
)
model = get_peft_model(model, lora_config)
model.print_trainable_parameters()
print()


# --- Träning ---

training_args = SFTConfig(
    output_dir=args.output,
    num_train_epochs=args.epochs,
    per_device_train_batch_size=4,
    per_device_eval_batch_size=4,
    gradient_accumulation_steps=1,
    learning_rate=args.lr,
    lr_scheduler_type="cosine",
    warmup_ratio=0.1,
    logging_steps=10,
    eval_strategy="epoch",
    save_strategy="best",
    load_best_model_at_end=True,
    metric_for_best_model="eval_loss",
    fp16=False,
    bf16=False,
    use_cpu=(DEVICE == "cpu"),
    report_to="none",
    dataset_text_field="text",
    max_length=128,
)

trainer = SFTTrainer(
    model=model,
    args=training_args,
    train_dataset=train_ds,
    eval_dataset=val_ds,
    processing_class=tokenizer,
    callbacks=[ProgressCallback()],
)

t_start = time.perf_counter()
trainer.train()
elapsed = time.perf_counter() - t_start
print(f"\nTräning klar: {elapsed/60:.1f} minuter")


# --- Spara adapter ---

os.makedirs(args.output, exist_ok=True)
model.save_pretrained(args.output)
tokenizer.save_pretrained(args.output)
print(f"Adapter sparad: {args.output}/")


# --- Snabb eval mot valideringsdata ---

print("\n--- Val-eval (greedy decoding) ---")
model.eval()

def predict(utterance: str) -> str:
    prompt = (
        f'Yttrande: "{utterance}"\n'
        "Slagtyp - välj ett: putt / chip / fullslag /no_think\n"
        "Svar:"
    )
    msgs = [{"role": "user", "content": prompt}]
    text = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=10, do_sample=False)
    generated = tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    g = generated.strip().lower()
    for label in ("putt", "chip", "fullslag"):
        if label in g:
            return label
    return "okänd"

correct = 0
for row in tqdm(val_rows, desc="Eval", unit="ex"):
    pred = predict(row["utterance"])
    ok = pred == row["label"]
    correct += ok
    tqdm.write(f"  {'OK' if ok else '--'}  {row['label']:<10} {pred:<10}  {row['utterance'][:55]}")

accuracy = correct / len(val_rows)
print(f"\nVal accuracy: {correct}/{len(val_rows)} = {accuracy:.1%}")

# Spara eval-resultat
result = {
    "model": args.model,
    "adapter": args.output,
    "epochs": args.epochs,
    "lora_rank": args.rank,
    "train_examples": len(train_rows),
    "val_accuracy": accuracy,
    "training_minutes": elapsed / 60,
}
os.makedirs("results", exist_ok=True)
out_path = f"results/finetune_{args.output.replace('/', '-')}.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f"Resultat sparat: {out_path}")
