import re

from pydantic import BaseModel, field_validator

# Common prompt-injection phrases to reject
_INJECTION_RE = re.compile(
    r"(?i)("
    r"ignore\s+(all\s+)?previous"
    r"|system\s+prompt"
    r"|you\s+are\s+now"
    r"|forget\s+everything"
    r"|disregard\s+(all\s+)?instructions"
    r"|new\s+instructions"
    r")"
)

MAX_QUESTION_LEN = 500


class UploadResponse(BaseModel):
    rows: int
    columns: list[str]
    dtypes: dict[str, str]


class AskRequest(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def sanitize_question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question cannot be empty")
        if len(v) > MAX_QUESTION_LEN:
            raise ValueError(f"question must be {MAX_QUESTION_LEN} characters or fewer")
        if _INJECTION_RE.search(v):
            raise ValueError("question contains disallowed content")
        return v


class AskResponse(BaseModel):
    question: str
    answer: str
    model: str


class HealthResponse(BaseModel):
    status: str


class AnalyzeResponse(BaseModel):
    good: str
    bad: str
    tip: str
    model: str
