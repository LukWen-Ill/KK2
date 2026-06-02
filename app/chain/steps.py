import logging
from pydantic import BaseModel
from app.chain.runnable import Runnable

logger = logging.getLogger(__name__)


# --- Schemas ---

class PromptBuilderInput(BaseModel):
    question: str
    user_stats: dict
    pga_benchmarks: dict


class PromptBuilderOutput(BaseModel):
    prompt: str


class LLMRunnerOutput(BaseModel):
    raw_text: str


class ResponseParserOutput(BaseModel):
    answer: str


# --- Steps ---

class PromptBuilder(Runnable[PromptBuilderInput, PromptBuilderOutput]):
    def invoke(self, input: PromptBuilderInput) -> PromptBuilderOutput:
        u = input.user_stats
        p = input.pga_benchmarks

        fairway = f"{u['fairway_pct']}%" if u.get("fairway_pct") is not None else "N/A"

        stats_lines = [
            f"- GIR: {u.get('gir_pct', 'N/A')}% (PGA Tour-snitt: {p.get('gir_pct', 'N/A'):.1f}%)",
            f"- Fairway: {fairway} (PGA Tour-snitt: {p.get('fairway_pct', 'N/A'):.1f}%)",
            f"- Avg putts/hål: {u.get('avg_putts', 'N/A')} (PGA Tour-snitt: {p.get('avg_putts', 'N/A')})",
            f"- Scoring avg/hål: {u.get('scoring_avg', 'N/A')} (PGA Tour-snitt: {p.get('scoring_avg', 70.5) / 18:.2f})",
        ]

        prompt = (
            "Du är en erfaren golfcoach. Svara på svenska med kortfattade, konkreta råd. "
            "Basera ditt svar enbart på statistiken nedan.\n\n"
            "Spelarens stats jämfört med PGA Tour-snitt:\n"
            + "\n".join(stats_lines)
            + f"\n\nFråga: {input.question}\n\nSvar:"
        )
        return PromptBuilderOutput(prompt=prompt)


class LLMRunner(Runnable[PromptBuilderOutput, LLMRunnerOutput]):
    _pipeline = None  # shared across all instances; survives notebook cell reruns

    def __init__(self, temperature: float = 1.0, max_new_tokens: int = 300) -> None:
        self._temperature = temperature
        self._max_new_tokens = max_new_tokens

    def _load(self) -> None:
        if LLMRunner._pipeline is None:
            from transformers import pipeline
            logger.info("Loading SmolLM2 model...")
            LLMRunner._pipeline = pipeline(
                "text-generation",
                model="HuggingFaceTB/SmolLM2-135M-Instruct",
            )
            logger.info("Model loaded.")

    def invoke(self, input: PromptBuilderOutput) -> LLMRunnerOutput:
        try:
            self._load()
            gen_kwargs: dict = {"max_new_tokens": self._max_new_tokens}
            if self._temperature != 1.0:
                gen_kwargs["temperature"] = self._temperature
                gen_kwargs["do_sample"] = True
            messages = [{"role": "user", "content": input.prompt}]
            result = LLMRunner._pipeline(messages, **gen_kwargs)
            # Chat output: generated_text is a list of message dicts; last is the assistant reply
            raw_text: str = result[0]["generated_text"][-1]["content"]
            logger.info("=== LLM RAW OUTPUT ===\n%s\n=== END ===", raw_text)
            return LLMRunnerOutput(raw_text=raw_text)
        except Exception as e:
            logger.error("LLM error: %s", e)
            raise


class ResponseParser(Runnable[LLMRunnerOutput, ResponseParserOutput]):
    def invoke(self, input: LLMRunnerOutput) -> ResponseParserOutput:
        text = input.raw_text.strip()
        # Strip the echoed prompt — take everything after the last "Svar:" marker
        marker = "Svar:"
        idx = text.rfind(marker)
        if idx != -1:
            after = text[idx + len(marker):].strip()
            if len(after) > 10:
                return ResponseParserOutput(answer=after)
        return ResponseParserOutput(answer=text)


# --- Shot classifier ---

SHOT_TYPES = ("putt", "chip", "fullslag", "utslag")


class ShotClassifierInput(BaseModel):
    utterance: str


class ShotClassifierOutput(BaseModel):
    shot_type: str  # "putt" | "chip" | "fullslag" | "okänd"


class ShotClassifierPrompt(Runnable[ShotClassifierInput, PromptBuilderOutput]):
    def invoke(self, input: ShotClassifierInput) -> PromptBuilderOutput:
        prompt = (
            f'Yttrande: "{input.utterance}"\n'
            "Slagtyp — välj ett: putt / chip / fullslag / utslag\n"
            "Svar:"
        )
        return PromptBuilderOutput(prompt=prompt)


class ShotClassifierParser(Runnable[LLMRunnerOutput, ShotClassifierOutput]):
    def invoke(self, input: LLMRunnerOutput) -> ShotClassifierOutput:
        text = input.raw_text.lower()
        marker = "svar:"
        idx = text.rfind(marker)
        search_in = text[idx + len(marker):].strip() if idx != -1 else text
        for shot_type in SHOT_TYPES:
            if shot_type in search_in:
                return ShotClassifierOutput(shot_type=shot_type)
        return ShotClassifierOutput(shot_type="okänd")


class SemanticShotClassifier(Runnable[ShotClassifierInput, ShotClassifierOutput]):
    """Deterministic keyword classifier — no model required. Covers ~90% of normal golf utterances."""

    _PUTT = ["putt", "rullade", "rullde", "rullning", "in i hål", "in i hal"]
    _CHIP = ["chip", "sandwedge", "sand wedge", "studsade", "ur bunker", "pitchade", "lobba"]
    _UTSLAG = ["drive", "utslag"]
    _FULLSLAG = ["järn", "jarn", "wood", "hybrid", "fullslag", "jarnslag", "järnslag"]

    def invoke(self, input: ShotClassifierInput) -> ShotClassifierOutput:
        text = input.utterance.lower()
        for kw in self._PUTT:
            if kw in text:
                return ShotClassifierOutput(shot_type="putt")
        for kw in self._CHIP:
            if kw in text:
                return ShotClassifierOutput(shot_type="chip")
        for kw in self._UTSLAG:
            if kw in text:
                return ShotClassifierOutput(shot_type="utslag")
        for kw in self._FULLSLAG:
            if kw in text:
                return ShotClassifierOutput(shot_type="fullslag")
        return ShotClassifierOutput(shot_type="okänd")


class HybridShotClassifier(Runnable[ShotClassifierInput, ShotClassifierOutput]):
    """Tries SemanticShotClassifier first; falls back to LLM only for genuinely ambiguous utterances."""

    def __init__(self, llm_runner: "LLMRunner") -> None:
        self._semantic = SemanticShotClassifier()
        self._prompt = ShotClassifierPrompt()
        self._llm = llm_runner
        self._parser = ShotClassifierParser()

    def invoke(self, input: ShotClassifierInput) -> ShotClassifierOutput:
        result = self._semantic.invoke(input)
        if result.shot_type != "okänd":
            return result
        raw = self._llm.invoke(self._prompt.invoke(input))
        return self._parser.invoke(raw)
