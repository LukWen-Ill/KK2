import pytest
from unittest.mock import patch
from app.chain.steps import (
    PromptBuilder,
    PromptBuilderInput,
    PromptBuilderOutput,
    LLMRunner,
    LLMRunnerOutput,
    ResponseParser,
)

_USER_STATS = {
    "gir_pct": 33.3,
    "fairway_pct": 44.4,
    "avg_putts": 2.2,
    "scoring_avg": 5.5,
}

_PGA = {
    "gir_pct": 65.0,
    "fairway_pct": 60.0,
    "avg_putts": 1.73,
    "scoring_avg": 70.5,
}


def test_prompt_builder_contains_question():
    inp = PromptBuilderInput(
        question="Hur förbättrar jag min putting?",
        user_stats=_USER_STATS,
        pga_benchmarks=_PGA,
    )
    out = PromptBuilder().invoke(inp)
    assert "Hur förbättrar jag min putting?" in out.prompt


def test_prompt_builder_contains_stats():
    inp = PromptBuilderInput(
        question="Vad är min svagaste del?",
        user_stats=_USER_STATS,
        pga_benchmarks=_PGA,
    )
    out = PromptBuilder().invoke(inp)
    assert "33.3" in out.prompt
    assert "65.0" in out.prompt
    assert "GIR" in out.prompt


@pytest.mark.parametrize("raw, expected_contains, expected_excludes", [
    # Normalt fall: "Svar:" med svar efter
    (
        "Du är en golfcoach...\nSvar: Träna mer putting varje dag.",
        "Träna mer putting",
        "Du är en golfcoach",
    ),
    # Flera "Svar:"-markörer — rfind tar den sista
    (
        "Svar: ignorera detta\nSvar: Ta den sista markören.",
        "Ta den sista markören",
        "ignorera detta",
    ),
    # Whitespace runt svaret strippas
    (
        "Svar:   \n  Fokusera på bunkerträning.  \n",
        "Fokusera på bunkerträning",
        None,
    ),
    # Kort svar efter "Svar:" (≤10 tecken) → fallback till raw
    (
        "Svar: Ja.",
        "Svar: Ja.",
        None,
    ),
    # Ingen markör → returnera raw text
    (
        "Putting är viktigt och kräver daglig träning.",
        "Putting är viktigt",
        None,
    ),
    # "Svar:" allra sist utan text → fallback till raw
    (
        "Svaret finns här. Svar:",
        "Svaret finns här",
        None,
    ),
])
def test_response_parser(raw, expected_contains, expected_excludes):
    out = ResponseParser().invoke(LLMRunnerOutput(raw_text=raw))
    assert expected_contains in out.answer
    if expected_excludes:
        assert expected_excludes not in out.answer


def test_full_chain_with_mocked_llm():
    from app.chain.pipeline import oraklet

    mock_output = LLMRunnerOutput(raw_text="Svar: Träna chip-shots dagligen för bättre GIR.")
    with patch.object(LLMRunner, "invoke", return_value=mock_output):
        result = oraklet.invoke(PromptBuilderInput(
            question="Hur förbättrar jag min GIR?",
            user_stats=_USER_STATS,
            pga_benchmarks=_PGA,
        ))
    assert "Svar:" not in result.answer
    assert "Träna chip-shots" in result.answer
