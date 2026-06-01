import logging
import pandas as pd

from fastapi import FastAPI, UploadFile, HTTPException
from app.schemas import UploadResponse, AskRequest, AskResponse, HealthResponse
from app.chain.steps import PromptBuilderInput
from app.chain.pipeline import oraklet
import app.data as data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Oraklet")

MODEL_NAME = "HuggingFaceTB/SmolLM2-135M-Instruct"


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/data/upload", response_model=UploadResponse)
async def upload(file: UploadFile) -> UploadResponse:
    logger.info(f"Upload request: {file.filename}")
    contents = await file.read()
    try:
        df = data.validate_and_store(contents, file.filename or "")
    except ValueError as e:
        status_code = 413 if "10 MB" in str(e) else 400
        raise HTTPException(status_code=status_code, detail=str(e))
    return UploadResponse(
        rows=len(df),
        columns=list(df.columns),
        dtypes={col: str(dtype) for col, dtype in df.dtypes.items()},
    )


@app.get("/data/stats")
def stats() -> dict:
    logger.info("Stats request")
    # TODO: return get_stats(), raise 404 if no dataset
    raise HTTPException(status_code=501, detail="Not implemented")


@app.post("/ai/ask", response_model=AskResponse)
def ask(body: AskRequest) -> AskResponse:
    logger.info(f"Ask request: {body.question}")
    # TODO: build PromptBuilderInput, run oraklet.invoke(), return AskResponse
    raise HTTPException(status_code=501, detail="Not implemented")
