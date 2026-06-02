import json
import logging
from pathlib import Path
from typing import Any
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
            f"- GIR: {u.get('gir_pct', 'N/A')}% (PGA Tour avg: {p.get('gir_pct', 'N/A'):.1f}%)",
            f"- Fairway: {fairway} (PGA Tour avg: {p.get('fairway_pct', 'N/A'):.1f}%)",
            f"- Avg putts/hole: {u.get('avg_putts', 'N/A')} (PGA Tour avg: {p.get('avg_putts', 'N/A')})",
            f"- Scoring avg/hole: {u.get('scoring_avg', 'N/A')} (PGA Tour avg: {p.get('scoring_avg', 70.5) / 18:.2f})",
        ]

        prompt = (
            "You are an experienced golf coach. Give short, concrete advice. "
            "Base your answer only on the stats below.\n\n"
            "Player stats vs PGA Tour averages:\n"
            + "\n".join(stats_lines)
            + f"\n\nQuestion: {input.question}\n\nAnswer:"
        )
        return PromptBuilderOutput(prompt=prompt)


class LLMRunner(Runnable[PromptBuilderOutput, LLMRunnerOutput]):
    _pipelines: dict[str, Any] = {}  # shared across all instances; keyed by model path

    _DEFAULT_MODEL = "HuggingFaceTB/SmolLM2-135M-Instruct"

    def __init__(
        self,
        model_name_or_path: str = _DEFAULT_MODEL,
        temperature: float = 1.0,
        max_new_tokens: int = 80,
    ) -> None:
        self._model_name_or_path = model_name_or_path
        self._temperature = temperature
        self._max_new_tokens = max_new_tokens

    def _load(self) -> None:
        key = self._model_name_or_path
        if key in LLMRunner._pipelines:
            return
        adapter_cfg = Path(key) / "adapter_config.json"
        if Path(key).is_dir() and adapter_cfg.exists():
            from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
            from peft import PeftModel
            cfg = json.loads(adapter_cfg.read_text())
            base = cfg["base_model_name_or_path"]
            logger.info("Loading PEFT model from %s (base: %s)...", key, base)
            base_model = AutoModelForCausalLM.from_pretrained(base)
            peft_model = PeftModel.from_pretrained(base_model, key)
            tokenizer = AutoTokenizer.from_pretrained(key)
            LLMRunner._pipelines[key] = pipeline(
                "text-generation", model=peft_model, tokenizer=tokenizer
            )
        else:
            from transformers import pipeline
            logger.info("Loading model %s...", key)
            LLMRunner._pipelines[key] = pipeline("text-generation", model=key)
        logger.info("Model loaded: %s", key)

    def invoke(self, input: PromptBuilderOutput) -> LLMRunnerOutput:
        try:
            self._load()
            pipe = LLMRunner._pipelines[self._model_name_or_path]
            gen_kwargs: dict = {"max_new_tokens": self._max_new_tokens, "max_length": None}
            if self._temperature != 1.0:
                gen_kwargs["temperature"] = self._temperature
                gen_kwargs["do_sample"] = True
            messages = [{"role": "user", "content": input.prompt}]
            result = pipe(messages, **gen_kwargs)
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


# --- /ai/ask CoT pipeline ---

class AskCoTState(BaseModel):
    question: str
    user_stats: dict
    pga_benchmarks: dict
    worst_stat: str = ""      # e.g. "GIR"
    worst_gap_str: str = ""   # e.g. "21.3% vs PGA avg 66.7%"
    weakness_desc: str = ""   # step 2 LLM output
    drill: str = ""           # step 3 LLM output
    impact: str = ""          # step 4 LLM output
    answer: str = ""          # step 5 LLM output


def _compute_worst_stat(user_stats: dict, pga: dict) -> tuple[str, str]:
    """Return (stat_label, gap_string) for the stat furthest below PGA avg."""
    candidates = []
    u = user_stats
    if u.get("gir_pct") is not None:
        gap = (pga.get("gir_pct", 65.0) - u["gir_pct"]) / pga.get("gir_pct", 65.0)
        candidates.append(("GIR", gap, f"{u['gir_pct']}% vs PGA avg {pga.get('gir_pct', 65.0):.1f}%"))
    if u.get("fairway_pct") is not None:
        gap = (pga.get("fairway_pct", 60.0) - u["fairway_pct"]) / pga.get("fairway_pct", 60.0)
        candidates.append(("Fairway", gap, f"{u['fairway_pct']}% vs PGA avg {pga.get('fairway_pct', 60.0):.1f}%"))
    if u.get("avg_putts") is not None:
        gap = (u["avg_putts"] - pga.get("avg_putts", 1.73)) / pga.get("avg_putts", 1.73)
        candidates.append(("Putts", gap, f"{u['avg_putts']} vs PGA avg {pga.get('avg_putts', 1.73)}"))
    if u.get("scoring_avg") is not None:
        pga_per_hole = pga.get("scoring_avg", 70.5) / 18
        gap = (u["scoring_avg"] - pga_per_hole) / pga_per_hole
        candidates.append(("Scoring", gap, f"{u['scoring_avg']}/hole vs PGA avg {pga_per_hole:.2f}/hole"))
    if not candidates:
        return ("GIR", "unknown")
    worst = max(candidates, key=lambda x: x[1])
    return (worst[0], worst[2])


class GapAnalyzerStep(Runnable[AskCoTState, AskCoTState]):
    """Python-only step — no LLM. Deterministically finds the worst stat."""
    def invoke(self, state: AskCoTState) -> AskCoTState:
        worst_stat, worst_gap_str = _compute_worst_stat(state.user_stats, state.pga_benchmarks)
        return state.model_copy(update={"worst_stat": worst_stat, "worst_gap_str": worst_gap_str})


class WeaknessStep(Runnable[AskCoTState, AskCoTState]):
    """Step 2: one-phrase description of what the weakness causes."""
    def __init__(self, runner: "LLMRunner") -> None:
        self._runner = LLMRunner(model_name_or_path=runner._model_name_or_path, max_new_tokens=35)

    def invoke(self, state: AskCoTState) -> AskCoTState:
        prompt = (
            f"Golf stat: {state.worst_stat} is {state.worst_gap_str}.\n"
            f"Complete in one short phrase: 'Low {state.worst_stat} means the player...'\nAnswer:"
        )
        raw = self._runner.invoke(PromptBuilderOutput(prompt=prompt)).raw_text
        text = _parse_cot_response(raw) or raw.strip()[:120]
        return state.model_copy(update={"weakness_desc": text})


class DrillStep(Runnable[AskCoTState, AskCoTState]):
    """Step 3: one specific practice drill for the worst stat."""
    def __init__(self, runner: "LLMRunner") -> None:
        self._runner = LLMRunner(model_name_or_path=runner._model_name_or_path, max_new_tokens=50)

    def invoke(self, state: AskCoTState) -> AskCoTState:
        prompt = (
            f"A golfer has {state.worst_stat} at {state.worst_gap_str}.\n"
            f"Name one specific practice drill to improve {state.worst_stat}. Answer:"
        )
        raw = self._runner.invoke(PromptBuilderOutput(prompt=prompt)).raw_text
        text = _parse_cot_response(raw) or raw.strip()[:150]
        return state.model_copy(update={"drill": text})


class ImpactStep(Runnable[AskCoTState, AskCoTState]):
    """Step 4: connect weakness to user's specific question."""
    def __init__(self, runner: "LLMRunner") -> None:
        self._runner = LLMRunner(model_name_or_path=runner._model_name_or_path, max_new_tokens=35)

    def invoke(self, state: AskCoTState) -> AskCoTState:
        prompt = (
            f"Weakness: {state.worst_stat} {state.worst_gap_str}. {state.weakness_desc}\n"
            f"Question: {state.question}\n"
            f"One phrase connecting the weakness to this question: Answer:"
        )
        raw = self._runner.invoke(PromptBuilderOutput(prompt=prompt)).raw_text
        text = _parse_cot_response(raw) or raw.strip()[:120]
        return state.model_copy(update={"impact": text})


class AskAnswerComposerStep(Runnable[AskCoTState, AskCoTState]):
    """Step 5: compose final answer using all prior context."""
    def __init__(self, runner: "LLMRunner") -> None:
        self._runner = LLMRunner(model_name_or_path=runner._model_name_or_path, max_new_tokens=80)

    def invoke(self, state: AskCoTState) -> AskCoTState:
        u = state.user_stats
        p = state.pga_benchmarks
        stats_line = (
            f"GIR {u.get('gir_pct','N/A')}% (PGA {p.get('gir_pct',65.0):.1f}%), "
            f"Fairway {u.get('fairway_pct','N/A')}% (PGA {p.get('fairway_pct',60.0):.1f}%), "
            f"Putts {u.get('avg_putts','N/A')} (PGA {p.get('avg_putts',1.73)}), "
            f"Scoring {u.get('scoring_avg','N/A')}/hole (PGA {p.get('scoring_avg',70.5)/18:.2f})"
        )
        prompt = (
            f"Player stats: {stats_line}.\n"
            f"Biggest weakness: {state.worst_stat} at {state.worst_gap_str}. {state.weakness_desc}\n"
            f"Recommended drill: {state.drill}\n"
            f"Question: {state.question}\n"
            f"Answer in 2 sentences using the stats above: Answer:"
        )
        raw = self._runner.invoke(PromptBuilderOutput(prompt=prompt)).raw_text
        text = _parse_cot_response(raw) or raw.strip()
        return state.model_copy(update={"answer": text})


# --- CoT analyze pipeline ---

class AnalyzeState(BaseModel):
    user_stats: dict
    pga_benchmarks: dict
    good: str = ""
    bad: str = ""
    tip: str = ""


def _build_stats_block(user_stats: dict, pga: dict) -> str:
    u = user_stats
    fairway = f"{u['fairway_pct']}%" if u.get("fairway_pct") is not None else "N/A"
    lines = [
        f"- GIR: {u.get('gir_pct', 'N/A')}% (PGA Tour-snitt: {pga.get('gir_pct', 65.0):.1f}%)",
        f"- Fairway: {fairway} (PGA Tour-snitt: {pga.get('fairway_pct', 60.0):.1f}%)",
        f"- Avg putts/hål: {u.get('avg_putts', 'N/A')} (PGA Tour-snitt: {pga.get('avg_putts', 1.73)})",
        f"- Scoring avg/hål: {u.get('scoring_avg', 'N/A')} (PGA Tour-snitt: {pga.get('scoring_avg', 70.5) / 18:.2f})",
    ]
    return "\n".join(lines)


def _parse_cot_response(raw: str) -> str:
    marker = "Svar:"
    idx = raw.rfind(marker)
    if idx != -1:
        after = raw[idx + len(marker):].strip()
        if len(after) > 5:
            return after
    return ""


def _stat_gaps(user_stats: dict, pga: dict) -> dict[str, float]:
    """Relative % gap per stat (higher = worse for player)."""
    u = user_stats
    p = pga
    gaps: dict[str, float] = {}
    if u.get("gir_pct") is not None:
        gaps["gir"] = abs(u["gir_pct"] - p.get("gir_pct", 65.0)) / max(p.get("gir_pct", 65.0), 1)
    if u.get("fairway_pct") is not None:
        gaps["fairway"] = abs(u["fairway_pct"] - p.get("fairway_pct", 60.0)) / max(p.get("fairway_pct", 60.0), 1)
    if u.get("avg_putts") is not None:
        gaps["putts"] = abs(u["avg_putts"] - p.get("avg_putts", 1.73)) / max(p.get("avg_putts", 1.73), 0.01)
    if u.get("scoring_avg") is not None:
        pga_per_hole = p.get("scoring_avg", 70.5) / 18
        gaps["scoring"] = abs(u["scoring_avg"] - pga_per_hole) / max(pga_per_hole, 0.01)
    return gaps


_STAT_LABELS = {
    "gir": ("GIR", "gir_pct", "%", "gir_pct"),
    "fairway": ("Fairway", "fairway_pct", "%", "fairway_pct"),
    "putts": ("Avg putts", "avg_putts", "", "avg_putts"),
    "scoring": ("Scoring avg", "scoring_avg", "", None),
}

_TIP_FALLBACKS = {
    "gir": "Träna approach-slag från 120–150 meter och sikta mot grensenter.",
    "fairway": "Fokusera på driver-accuracy — öva tighta fairway-linjer på övningsbanan.",
    "putts": "Träna 2–3 meters puttar dagligen — distansbedömning är nyckeln.",
    "scoring": "Spela fler kortbanerundar och fokusera på konservativt par-spel.",
}


class GoodStep(Runnable[AnalyzeState, AnalyzeState]):
    def __init__(self, runner: "LLMRunner") -> None:
        self._runner = runner

    def invoke(self, state: AnalyzeState) -> AnalyzeState:
        stats_block = _build_stats_block(state.user_stats, state.pga_benchmarks)
        prompt = (
            f"{stats_block}\n\n"
            "Vad var bäst i spelarens runda? Nämn stat-värde och PGA Tour-snitt. Svar:"
        )
        raw = self._runner.invoke(PromptBuilderOutput(prompt=prompt)).raw_text
        text = _parse_cot_response(raw)
        if not text:
            gaps = _stat_gaps(state.user_stats, state.pga_benchmarks)
            best_key = min(gaps, key=lambda k: gaps[k]) if gaps else "fairway"
            label, user_key, unit, pga_key = _STAT_LABELS[best_key]
            u_val = state.user_stats.get(user_key, "N/A")
            p_val = state.pga_benchmarks.get(pga_key, "N/A") if pga_key else round(state.pga_benchmarks.get("scoring_avg", 70.5) / 18, 2)
            text = f"{label} {u_val}{unit} (PGA: {p_val}{unit}) — nära PGA Tour-nivå."
        return state.model_copy(update={"good": text})


class BadStep(Runnable[AnalyzeState, AnalyzeState]):
    def __init__(self, runner: "LLMRunner") -> None:
        self._runner = runner

    def invoke(self, state: AnalyzeState) -> AnalyzeState:
        stats_block = _build_stats_block(state.user_stats, state.pga_benchmarks)
        prompt = (
            f"{stats_block}\n\n"
            "Vad var sämst? Nämn stat med störst gap mot PGA Tour-snittet. Svar:"
        )
        raw = self._runner.invoke(PromptBuilderOutput(prompt=prompt)).raw_text
        text = _parse_cot_response(raw)
        if not text:
            gaps = _stat_gaps(state.user_stats, state.pga_benchmarks)
            worst_key = max(gaps, key=lambda k: gaps[k]) if gaps else "gir"
            label, user_key, unit, pga_key = _STAT_LABELS[worst_key]
            u_val = state.user_stats.get(user_key, "N/A")
            p_val = state.pga_benchmarks.get(pga_key, "N/A") if pga_key else round(state.pga_benchmarks.get("scoring_avg", 70.5) / 18, 2)
            text = f"{label} {u_val}{unit} (PGA: {p_val}{unit}) — störst förbättringspotential."
        return state.model_copy(update={"bad": text})


class TipStep(Runnable[AnalyzeState, AnalyzeState]):
    def __init__(self, runner: "LLMRunner") -> None:
        self._runner = runner

    def invoke(self, state: AnalyzeState) -> AnalyzeState:
        prompt = f"Spelaren har {state.bad}. Ge ett konkret träningstips. Svar:"
        raw = self._runner.invoke(PromptBuilderOutput(prompt=prompt)).raw_text
        text = _parse_cot_response(raw)
        if not text:
            bad_lower = state.bad.lower()
            if "gir" in bad_lower:
                text = _TIP_FALLBACKS["gir"]
            elif "fairway" in bad_lower:
                text = _TIP_FALLBACKS["fairway"]
            elif "putt" in bad_lower:
                text = _TIP_FALLBACKS["putts"]
            else:
                text = _TIP_FALLBACKS["scoring"]
        return state.model_copy(update={"tip": text})


# --- Shot classifier ---

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
