"""Fine-tune SmolLM2-135M-Instruct with LoRA on CoT golf-coach data."""
import json
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model, TaskType
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling,
)

BASE_MODEL = "HuggingFaceTB/SmolLM2-135M-Instruct"
OUTPUT_DIR = "models/smollm2-chat-lora"
MAX_LENGTH = 128


def load_jsonl(path: str) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def tokenize(examples, tokenizer):
    texts = [p + " " + c for p, c in zip(examples["prompt"], examples["completion"])]
    return tokenizer(texts, truncation=True, max_length=MAX_LENGTH, padding="max_length")


def main():
    train_data = load_jsonl("data/chat_train.jsonl")
    val_data = load_jsonl("data/chat_val.jsonl")
    print(f"Loaded {len(train_data)} train, {len(val_data)} val examples")

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    train_ds = Dataset.from_list(train_data)
    val_ds = Dataset.from_list(val_data)

    train_tok = train_ds.map(lambda ex: tokenize(ex, tokenizer), batched=True, remove_columns=["prompt", "completion"])
    val_tok = val_ds.map(lambda ex: tokenize(ex, tokenizer), batched=True, remove_columns=["prompt", "completion"])

    model = AutoModelForCausalLM.from_pretrained(BASE_MODEL)

    lora_cfg = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=8,
        lora_alpha=16,
        target_modules="all-linear",
        lora_dropout=0.05,
        bias="none",
    )
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()

    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        num_train_epochs=3,
        per_device_train_batch_size=4,
        per_device_eval_batch_size=4,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        logging_steps=10,
        fp16=torch.cuda.is_available(),
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_tok,
        eval_dataset=val_tok,
        data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False),
    )

    trainer.train()
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    print(f"Saved LoRA adapter to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
