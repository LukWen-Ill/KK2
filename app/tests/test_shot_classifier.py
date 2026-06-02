import pytest
from unittest.mock import patch
from app.chain.steps import (
    HybridShotClassifier,
    LLMRunner,
    LLMRunnerOutput,
    SemanticShotClassifier,
    ShotClassifierInput,
    ShotClassifierParser,
    ShotClassifierPrompt,
)
from app.chain.pipeline import slag_klassificerare


# --- ShotClassifierPrompt ---

@pytest.mark.parametrize("utterance", [
    "Lågchip mot flaggan, stannade en meter bort.",
    "Tre meter rakt putt.",
    "Drive långt ner mitten.",
])
def test_prompt_contains_utterance_and_choices(utterance):
    out = ShotClassifierPrompt().invoke(ShotClassifierInput(utterance=utterance))
    assert utterance in out.prompt
    assert "putt / chip / fullslag" in out.prompt
    assert "Svar:" in out.prompt


# --- ShotClassifierParser ---

@pytest.mark.parametrize("raw, expected", [
    # Tydliga svar direkt efter "Svar:"
    ("Svar: chip", "chip"),
    ("Svar: putt", "putt"),
    ("Svar: fullslag", "fullslag"),
    # Modellen svarar med extra text men rätt nyckelord
    ("Svar: Det är ett chip-slag.", "chip"),
    ("Svar: Jag tror detta är ett fullslag baserat på beskrivningen.", "fullslag"),
    # Versal variant — parsern är case-insensitive
    ("Svar: PUTT", "putt"),
    ("Svar: Chip", "chip"),
    # Inget "Svar:"-prefix — söker i hela texten
    ("chip", "chip"),
    ("Det låter som ett fullslag.", "fullslag"),
    # Flera nyckelord — tar det första (putt > chip > fullslag i SHOT_TYPES-ordning)
    ("putt eller chip?", "putt"),
    # Okänd output — fallback
    ("Vet ej.", "okänd"),
    ("", "okänd"),
])
def test_shot_classifier_parser(raw, expected):
    out = ShotClassifierParser().invoke(LLMRunnerOutput(raw_text=raw))
    assert out.shot_type == expected


# --- Hel kedja med mockad LLM ---

@pytest.mark.parametrize("utterance, llm_response, expected", [
    ("Lågchip mot flaggan, stannade en meter bort.", "Svar: chip", "chip"),
    ("Tre meter rakt putt, rullde in.", "Svar: putt", "putt"),
    ("Bra drive ner höger sida.", "Svar: fullslag", "fullslag"),
    ("Kort järnslag mot par 3.", "Svar: fullslag", "fullslag"),
    ("Rullning in från kanten.", "Svar: putt", "putt"),
    ("Sandwedge ur bunkern.", "Svar: chip", "chip"),
    ("Modellen vet inte.", "Svar: nej tack", "okänd"),
])
def test_full_classifier_chain_mocked(utterance, llm_response, expected):
    mock_output = LLMRunnerOutput(raw_text=llm_response)
    with patch.object(LLMRunner, "invoke", return_value=mock_output):
        result = slag_klassificerare.invoke(ShotClassifierInput(utterance=utterance))
    assert result.shot_type == expected


# --- SemanticShotClassifier ---

@pytest.mark.parametrize("utterance, expected", [
    # Putt-nyckelord
    ("Tre meter rakt mot hålet, rullde in.",         "putt"),
    ("Kort putt, missade till höger.",               "putt"),
    ("Rullning in från kanten, precis.",             "putt"),
    ("Rullade in från kanten.",                      "putt"),
    # Chip-nyckelord
    ("Lågchip mot flaggan, stannade en meter bort.", "chip"),
    ("Chippade ur bunkern, landade på greenen.",     "chip"),
    ("Sandwedge från rough, studsade förbi.",        "chip"),
    ("Pitchade upp mot flaggan.",                    "chip"),
    # Utslag-nyckelord (drive)
    ("Bra drive långt ner mitten.",                  "utslag"),
    ("Utslag från tee, bollen i fairway.",           "utslag"),
    # Fullslag-nyckelord (järn, wood, hybrid)
    ("Tog ett järnslag mot par 3-hålet.",            "fullslag"),
    ("7-järn mot greenen, lite för lång.",           "fullslag"),
    ("3-wood mot greenen.",                          "fullslag"),
    # Genuint tvetydigt — inget nyckelord matchar
    ("Slog en wedge, bollen landade nära flaggan.",  "okänd"),
    ("Perfekt position inför nästa slag.",           "okänd"),
])
def test_semantic_shot_classifier(utterance, expected):
    result = SemanticShotClassifier().invoke(ShotClassifierInput(utterance=utterance))
    assert result.shot_type == expected


# --- HybridShotClassifier ---

def test_hybrid_uses_semantic_when_clear():
    # "putt" matchar semantik — LLM ska aldrig anropas
    with patch.object(LLMRunner, "invoke", side_effect=Exception("LLM should not be called")):
        result = HybridShotClassifier(LLMRunner()).invoke(
            ShotClassifierInput(utterance="Kort putt, rullde in.")
        )
    assert result.shot_type == "putt"


def test_hybrid_falls_back_to_llm_when_ambiguous():
    # "wedge" utan "sandwedge" matchar inget nyckelord — LLM används som fallback
    mock_output = LLMRunnerOutput(raw_text="Svar: chip")
    with patch.object(LLMRunner, "invoke", return_value=mock_output):
        result = HybridShotClassifier(LLMRunner()).invoke(
            ShotClassifierInput(utterance="Slog en wedge, bollen landade nära flaggan.")
        )
    assert result.shot_type == "chip"
