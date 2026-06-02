from pathlib import Path
from app.chain.steps import (
    PromptBuilder, LLMRunner, ResponseParser,
    ShotClassifierPrompt, ShotClassifierParser,
    GoodStep, BadStep, TipStep,
    GapAnalyzerStep, WeaknessStep, DrillStep, ImpactStep, AskAnswerComposerStep,
)

CHAT_LORA_PATH = "models/smollm2-chat-lora"


def _make_runner() -> LLMRunner:
    lora = Path(CHAT_LORA_PATH)
    if lora.is_dir() and (lora / "adapter_config.json").exists():
        return LLMRunner(model_name_or_path=CHAT_LORA_PATH)
    return LLMRunner()


_runner = _make_runner()

oraklet = PromptBuilder() | _runner | ResponseParser()
analyse_kedjan = GoodStep(_runner) | BadStep(_runner) | TipStep(_runner)
ask_cot_kedjan = (
    GapAnalyzerStep()
    | WeaknessStep(_runner)
    | DrillStep()
    | ImpactStep(_runner)
    | AskAnswerComposerStep(_runner)
)
slag_klassificerare = ShotClassifierPrompt() | LLMRunner() | ShotClassifierParser()


def preload() -> None:
    _runner._load()
