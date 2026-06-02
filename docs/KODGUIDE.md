# Kodguide – KK2 Oraklet

Referensdokumentation baserad på kursens egna kodexempel. Läs detta innan du börjar koda.

---

## 1. Runnable-mönstret

Källfil: `smol2-llm-chain-main/llm/llm.py`

Tre klasser bygger hela systemet:

```python
from pydantic import BaseModel, ConfigDict, SerializeAsAny
from typing import Any, Callable, Generic, TypeVar

I = TypeVar("I")
O = TypeVar("O")
M = TypeVar("M")

class Runnable(BaseModel, Generic[I, O]):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str | None = None

    def invoke(self, data: I) -> O:
        raise NotImplementedError("Subclasses is not implemented")

    def __or__(self, other: Any) -> 'RunnableSequence':
        if isinstance(other, Runnable):
            return RunnableSequence.model_construct(first=self, second=other)
        if callable(other):
            return RunnableSequence.model_construct(
                first=self,
                second=RunnableLambda.model_construct(func=other, name=other.__name__),
            )
        return NotImplemented

    def __ror__(self, other: Any) -> Any:
        if callable(other):
            return RunnableSequence.model_construct(
                first=RunnableLambda.model_construct(func=other),
                second=self,
            )
        return NotImplemented


class RunnableLambda(Runnable[I, O]):
    func: Callable[[I], O]

    def invoke(self, data: I) -> O:
        return self.func(data)


class RunnableSequence(Runnable[I, O], Generic[I, M, O]):
    first: SerializeAsAny[Runnable[I, M]]
    second: SerializeAsAny[Runnable[M, O]]

    def invoke(self, data: I) -> O:
        return self.second.invoke(self.first.invoke(data))
```

### Kedjning med `|`

```python
ticket_pipeline = SentimentAnalyser() | TicketParser() | route_ticket
result = ticket_pipeline.invoke(incoming_ticket)
```

`|` anropar `__or__` och returnerar en `RunnableSequence`. Det sista steget kan vara en vanlig funktion — den wrappas automatiskt i `RunnableLambda`.

### Exempelkedja från kursen

```python
class TicketInput(BaseModel):
    customer_id: int
    message: str

class ProcessedTicket(BaseModel):
    customer_id: int
    sentiment: str
    urgency: str
    summary: str

class SentimentAnalyser(Runnable[TicketInput, dict]):
    name: str = "sentiment_analyser"

    def invoke(self, ticket: TicketInput) -> dict:
        msg_lower = ticket.message.lower()
        return {
            "customer_id": ticket.customer_id,
            "sentiment": "negative" if "broken" in msg_lower else "neutral",
            "urgency": "high" if "urgent" in msg_lower else "low",
            "summary": ticket.message[:40] + "...",
        }

class TicketParser(Runnable[dict, ProcessedTicket]):
    name: str = "ticket_parser"

    def invoke(self, raw_dict: dict) -> ProcessedTicket:
        return ProcessedTicket(**raw_dict)

def route_ticket(ticket: ProcessedTicket) -> dict:
    destination = "engineering_team" if ticket.urgency == "high" else "general_support"
    return {"status": "routed", "assigned_to": destination}

ticket_pipeline = SentimentAnalyser() | TicketParser() | route_ticket
```

---

## 2. Dina kedjesteg för KK2

Samma mönster, nya steg. Kopiera och fyll i `...`:

```python
# app/chain/steps.py

from pydantic import BaseModel
from .runnable import Runnable


class PromptBuilderInput(BaseModel):
    question: str
    stats: dict


class PromptBuilderOutput(BaseModel):
    prompt: str


class PromptBuilder(Runnable[PromptBuilderInput, PromptBuilderOutput]):
    name: str = "prompt_builder"

    def invoke(self, data: PromptBuilderInput) -> PromptBuilderOutput:
        stats_str = ...  # formatera data.stats till läsbar text
        prompt = f"...\n\nStatistik:\n{stats_str}\n\nFråga: {data.question}"
        return PromptBuilderOutput(prompt=prompt)


class LLMRunnerOutput(BaseModel):
    raw_text: str


class LLMRunner(Runnable[PromptBuilderOutput, LLMRunnerOutput]):
    name: str = "llm_runner"

    def invoke(self, data: PromptBuilderOutput) -> LLMRunnerOutput:
        # anropa transformers.pipeline här
        raw = ...
        return LLMRunnerOutput(raw_text=raw)


class ResponseParserOutput(BaseModel):
    answer: str
    model: str


class ResponseParser(Runnable[LLMRunnerOutput, ResponseParserOutput]):
    name: str = "response_parser"

    def invoke(self, data: LLMRunnerOutput) -> ResponseParserOutput:
        # extrahera svaret ur modellens råoutput
        answer = ...
        return ResponseParserOutput(answer=answer, model="HuggingFaceTB/SmolLM2-135M-Instruct")
```

```python
# app/chain/pipeline.py

from .steps import PromptBuilder, LLMRunner, ResponseParser

oraklet = PromptBuilder() | LLMRunner() | ResponseParser()
```

---

## 3. FastAPI + Pydantic

Källfiler: `smol2-llm-chain-main/main.py` och `v21-dag-1/starter/todos.py`

### Fel: manuell dict-parsning

```python
# Undvik detta — ingen typning, ingen validering
async def ask(request: Request):
    body = await request.json()
    question = body["question"]  # kraschar utan nyckel, otypat
```

### Rätt: Pydantic-modell som parameter

```python
from pydantic import BaseModel
from fastapi import APIRouter

class AskRequest(BaseModel):
    question: str

class AskResponse(BaseModel):
    question: str
    answer: str
    model: str

router = APIRouter()

@router.post("/ai/ask", response_model=AskResponse)
def ask(body: AskRequest) -> AskResponse:
    # body.question är validerat och typat — FastAPI sköter parsningen
    result = oraklet.invoke(PromptBuilderInput(question=body.question, stats=...))
    return AskResponse(question=body.question, answer=result.answer, model=result.model)
```

### Integrera kedjan i FastAPI (från kursen)

```python
# smol2-llm-chain-main/main.py
from fastapi import FastAPI
from pydantic import BaseModel
from llm.llm import TicketInput, ticket_pipeline

app = FastAPI()

class LLMRequest(BaseModel):
    id: int
    message: str

@app.post("/llm")
def llm_route(body: LLMRequest):
    incoming_ticket = TicketInput(customer_id=body.id, message=body.message)
    return ticket_pipeline.invoke(incoming_ticket)
```

---

## 4. Testmönster

Källfil: `v21-dag-1/tests/conftest.py` och `exploits.py`

### conftest.py — reset och TestClient

```python
import pytest
from fastapi.testclient import TestClient

@pytest.fixture(autouse=True)
def reset_state():
    import app.data as state
    state.current_df = None
    yield

@pytest.fixture
def client() -> TestClient:
    from app.main import app
    return TestClient(app)
```

### Testa kedjesteg i isolation

```python
# test_chain.py
from app.chain.steps import PromptBuilder, PromptBuilderInput

def test_prompt_builder_innehåller_frågan():
    step = PromptBuilder()
    result = step.invoke(PromptBuilderInput(question="Vilken stad är varmast?", stats={}))
    assert "Vilken stad är varmast?" in result.prompt
```

### Testa endpoints med TestClient

```python
# test_endpoints.py
def test_upload_giltig_csv(client, tmp_path):
    csv = tmp_path / "data.csv"
    csv.write_text("city,temp\nMalmö,8.3\n")
    with open(csv, "rb") as f:
        resp = client.post("/data/upload", files={"file": ("data.csv", f, "text/csv")})
    assert resp.status_code == 200
    assert "rows" in resp.json()

def test_stats_utan_dataset_ger_404(client):
    resp = client.get("/data/stats")
    assert resp.status_code == 404

def test_upload_fel_extension_ger_400(client, tmp_path):
    f = tmp_path / "data.txt"
    f.write_text("inte en csv")
    with open(f, "rb") as fh:
        resp = client.post("/data/upload", files={"file": ("data.txt", fh, "text/plain")})
    assert resp.status_code == 400
```

### Mocka LLMRunner

```python
from unittest.mock import patch
from app.chain.steps import LLMRunner, LLMRunnerOutput

def test_ask_med_mockad_modell(client):
    # Ladda upp dataset först
    ...

    with patch.object(LLMRunner, "invoke", return_value=LLMRunnerOutput(raw_text="Malmö är varmast.")):
        resp = client.post("/ai/ask", json={"question": "Vilken stad är varmast?"})

    assert resp.status_code == 200
    assert "answer" in resp.json()
```

---

## 5. Projektstruktur

```
kk2-oraklet/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI-app, router-registration
│   ├── config.py        # os.getenv(), .env-inläsning
│   ├── schemas.py       # Pydantic-modeller för API-request/response
│   ├── data.py          # Pandas: läs CSV, lagra df, describe()
│   ├── chain/
│   │   ├── __init__.py
│   │   ├── runnable.py  # Runnable, RunnableLambda, RunnableSequence (kopiera från llm.py)
│   │   ├── steps.py     # PromptBuilder, LLMRunner, ResponseParser
│   │   └── pipeline.py  # oraklet = PromptBuilder() | LLMRunner() | ResponseParser()
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py      # fixtures
│       ├── test_endpoints.py
│       └── test_chain.py
├── pyproject.toml
├── README.md
├── reflektion.md
└── .gitignore
```

### pyproject.toml-beroenden

```toml
[project]
requires-python = ">=3.13"
dependencies = [
    "fastapi[standard]>=0.100",
    "pydantic>=2.0",
    "transformers>=4.40",
    "torch>=2.0",
    "pandas>=2.0",
    "python-dotenv>=1.0",
    "pytest>=8.0",
    "httpx>=0.27",
]
```

---

## Snabbstart

1. Kopiera `Runnable`, `RunnableLambda`, `RunnableSequence` från `smol2-llm-chain-main/llm/llm.py` till `app/chain/runnable.py`.
2. Implementera de tre stegen i `app/chain/steps.py` (skelett ovan).
3. Skapa `oraklet`-kedjan i `app/chain/pipeline.py`.
4. Bygg endpoints i `app/main.py` — använd Pydantic-modeller som parametrar, inte `Request`.
5. Skriv tester — minst ett per steg, plus endpoints och mockat LLM-anrop.
